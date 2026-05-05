"""
SOMA — Shared Ontology for Market Analysis
Core infrastructure for all DABEIBA pipelines (TITAN, DELTA, DOCTRINE, SENTINEL, etc.)

SomaBridge — the single read/write API for SOMA.

Usage:
    with SomaBridge() as db:
        db.write_regime(date="2026-03-20", run_id="abc-123", gli_value=0.72, regime="RISK_ON", ...)
        latest = db.get_latest_regime()

Design principles:
    - Context manager for clean connection handling
    - WAL mode for concurrent reads
    - Fire-and-forget writes: a SOMA failure never crashes the caller
"""

import sqlite3
import os
from datetime import datetime, timezone
from pathlib import Path

from .pipeline_registry import get_display_name, resolve

# SOM-005: Allow DB path override via SOMA_DB_PATH environment variable.
# This supports CI, multi-environment deployments, and isolated testing
# without modifying code. Falls back to the canonical Desktop path.
_DEFAULT_DB_PATH = (
    Path(os.environ["SOMA_DB_PATH"])
    if "SOMA_DB_PATH" in os.environ
    else Path.home() / "Desktop" / "DABEIBA" / "shared" / "soma" / "data" / "soma.db"
)
_MIGRATIONS_DIR = Path(__file__).parent / "migrations"


class SomaBridge:
    def __init__(self, db_path=None):
        self.db_path = str(db_path or _DEFAULT_DB_PATH)
        self.conn = None
        self._batch_mode = False

    # ── Context manager ──────────────────────────────────────────────
    def __enter__(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        # Phase 4.4 — allow the bridge connection to be used across threads.
        # The staging dispatcher (ThreadPoolExecutor) serializes SOMA calls
        # with its own _soma_lock, so concurrent-use safety is covered by the
        # caller. Without this flag, sqlite3's built-in thread check aborts
        # any cross-thread call even under the lock.
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            self.conn.close()
            self.conn = None
        return False  # do not suppress exceptions

    # ── Pipeline Name Translation (Phase 3 — Alias Layer) ─────────
    # Database stores internal_ids (TITAN, COBALT, etc.) — stable, never change.
    # These helpers translate to/from display names at the query boundary.

    @staticmethod
    def _enrich_pipeline_name(row_dict):
        """Add 'pipeline_display' key to a row dict that has 'target_pipeline'.
        Non-destructive: keeps original internal_id, adds display name alongside."""
        if "target_pipeline" in row_dict and row_dict["target_pipeline"]:
            row_dict["pipeline_display"] = get_display_name(row_dict["target_pipeline"])
        if "consumed_by" in row_dict and row_dict["consumed_by"]:
            row_dict["consumed_by_display"] = get_display_name(row_dict["consumed_by"])
        if "source_module" in row_dict and row_dict["source_module"]:
            row_dict["source_display"] = get_display_name(row_dict["source_module"])
        return row_dict

    @staticmethod
    def resolve_pipeline_param(name):
        """Resolve a pipeline name (display name, alias, or internal_id) → internal_id.
        Use this when accepting pipeline parameters from the user or UI.
        Returns the original string if resolution fails (safe fallback)."""
        resolved = resolve(name)
        return resolved if resolved else name

    @staticmethod
    def translate_pipeline_stats(stats_dict):
        """Translate internal_ids in a by_pipeline stats dict to display names.
        Input:  {'TITAN': 5, 'COBALT': 3}
        Output: {'TITAN': 5, 'COBALT': 3}  (or display names after Phase 4 rename)"""
        return {get_display_name(k): v for k, v in stats_dict.items()}

    # ── Utility ──────────────────────────────────────────────────────
    def _now(self):
        return datetime.now(timezone.utc).isoformat()

    def begin_batch(self):
        """Start a batch transaction — write methods skip individual commits."""
        self._batch_mode = True
        self.conn.execute("BEGIN")

    def commit_batch(self):
        """Commit the batch transaction. All writes since begin_batch() are atomic."""
        self.conn.commit()
        self._batch_mode = False

    def rollback_batch(self):
        """Rollback all writes since begin_batch() on failure."""
        try:
            self.conn.rollback()
        except Exception as e:
            print(f"[SOMA] rollback_batch failed: {e}")
        self._batch_mode = False

    def _maybe_commit(self):
        """Commit only if NOT in batch mode."""
        if not self._batch_mode:
            self.conn.commit()

    def initialize_db(self):
        """Run all pending migrations to create/update tables."""
        current_version = self.get_schema_version()
        migrations = sorted(_MIGRATIONS_DIR.glob("*.sql"))
        for mig in migrations:
            # Extract version number from filename (e.g., 001_initial_schema.sql -> 1)
            try:
                ver = int(mig.name.split("_")[0])
            except (ValueError, IndexError):
                continue
            if ver > current_version:
                self.conn.executescript(mig.read_text())

    def get_schema_version(self):
        """Return the current schema version number, or 0 if not initialized."""
        try:
            row = self.conn.execute(
                "SELECT MAX(version) AS v FROM schema_version"
            ).fetchone()
            return row["v"] if row and row["v"] is not None else 0
        except sqlite3.OperationalError:
            return 0

    def is_fresh(self, table="regime_history", max_age_hours=48):
        """Check whether the most recent row in *table* is younger than max_age_hours.

        Returns (is_fresh: bool, age_in_hours: float).
        If the table is empty, returns (False, float('inf')).

        Note: table name comes from internal allowlist of known tables.
        """
        # Allowlist of valid tables to prevent injection (table name cannot be parameterized)
        _VALID_TABLES = {
            "regime_history", "valuations", "trade_log", "outlook_snapshots",
            "portfolio_state", "client_profiles", "client_interactions", "events",
            "horizon_analyses", "philosophy_beliefs", "philosophy_evidence",
            "philosophy_history", "philosophy_alerts",
            "raw_intelligence",
            "geo_events", "geo_vectors", "geo_baselines",
            "onchain_metrics", "onchain_signals",
            "raptor_prospects", "raptor_pipeline_log", "raptor_touchpoints",
            "raptor_consent_ledger", "raptor_coi_network", "raptor_referrals",
        }
        if table not in _VALID_TABLES:
            return False, float("inf")

        try:
            row = self.conn.execute(
                f"SELECT write_timestamp FROM [{table}] ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if not row:
                return False, float("inf")
            ts = datetime.fromisoformat(row["write_timestamp"])
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - ts).total_seconds() / 3600
            return age < max_age_hours, round(age, 2)
        except Exception as e:
            print(f"[SOMA] is_fresh check failed for table {table}: {e}")
            return False, float("inf")

    # ── WRITE methods (fire-and-forget) ──────────────────────────────
    def write_regime(self, date, run_id, gli_value, regime, diffusion_index,
                     momentum, gli_components_json=None, module_version=None):
        try:
            # UPSERT on run_id — retries with same run_id overwrite instead of duplicating
            self.conn.execute(
                """INSERT OR REPLACE INTO regime_history
                   (date, run_id, gli_value, regime, diffusion_index, momentum,
                    gli_components_json, write_timestamp, module_version)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (date, run_id, gli_value, regime, diffusion_index, momentum,
                 gli_components_json, self._now(), module_version),
            )
            self._maybe_commit()
            # Active intelligence: validate against KB
            self._validate_write("regime", gli_value=gli_value, regime=regime,
                                 diffusion_index=diffusion_index, momentum=momentum,
                                 module_version=module_version)
        except Exception as e:
            print(f"[SOMA] write_regime failed: {e}")

    def write_valuation(self, date, run_id, ticker, fair_value, current_price,
                        implied_upside, execution_score=None, module_version=None):
        try:
            # UPSERT on (run_id, ticker) — retries with same run_id overwrite instead of duplicating
            self.conn.execute(
                """INSERT OR REPLACE INTO valuations
                   (date, run_id, ticker, fair_value, current_price, implied_upside,
                    execution_score, write_timestamp, module_version)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (date, run_id, ticker, fair_value, current_price, implied_upside,
                 execution_score, self._now(), module_version),
            )
            self._maybe_commit()
            # Active intelligence: validate against KB
            self._validate_write("valuation", ticker=ticker, fair_value=fair_value,
                                 current_price=current_price, implied_upside=implied_upside,
                                 execution_score=execution_score, module_version=module_version)
        except Exception as e:
            print(f"[SOMA] write_valuation failed: {e}")

    def write_trade(self, date, ticker, action, price, weight, reason=None,
                    regime_at_time=None, gli_value=None, diffusion_index=None,
                    momentum=None, vol_reading=None, onchain_tx_id=None,
                    confirm_block=None, module_version=None):
        try:
            # UPSERT on (date, ticker, action) — rerunning backtests overwrites instead of duplicating
            self.conn.execute(
                """INSERT OR REPLACE INTO trade_log
                   (date, ticker, action, price, weight, reason, regime_at_time,
                    gli_value, diffusion_index, momentum, vol_reading,
                    onchain_tx_id, confirm_block, write_timestamp, module_version)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (date, ticker, action, price, weight, reason, regime_at_time,
                 gli_value, diffusion_index, momentum, vol_reading,
                 onchain_tx_id, confirm_block, self._now(), module_version),
            )
            self._maybe_commit()
            # Active intelligence: validate against KB
            self._validate_write("trade", ticker=ticker, action=action,
                                 weight=weight, regime_at_time=regime_at_time,
                                 module_version=module_version)
        except Exception as e:
            print(f"[SOMA] write_trade failed: {e}")

    def write_outlook(self, date, version, full_text_hash,
                      key_conclusions_json=None, module_version=None):
        try:
            self.conn.execute(
                """INSERT INTO outlook_snapshots
                   (date, version, full_text_hash, key_conclusions_json,
                    write_timestamp, module_version)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (date, version, full_text_hash, key_conclusions_json,
                 self._now(), module_version),
            )
            self._maybe_commit()
        except Exception as e:
            print(f"[SOMA] write_outlook failed: {e}")

    def write_portfolio_state(self, date, positions_json, cash_pct, total_value,
                              dd_from_hwm=None, module_version=None):
        try:
            # UPSERT on date — rerunning backtests overwrites the snapshot for that date
            self.conn.execute(
                """INSERT OR REPLACE INTO portfolio_state
                   (date, positions_json, cash_pct, total_value, dd_from_hwm,
                    write_timestamp, module_version)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (date, positions_json, cash_pct, total_value, dd_from_hwm,
                 self._now(), module_version),
            )
            self._maybe_commit()
            # Active intelligence: validate against KB
            self._validate_write("portfolio", cash_pct=cash_pct, total_value=total_value,
                                 dd_from_hwm=dd_from_hwm, positions_json=positions_json,
                                 module_version=module_version)
        except Exception as e:
            print(f"[SOMA] write_portfolio_state failed: {e}")

    # ── CLIENT PROFILES (Phase 2.3 — Client Alpha Layer) ─────────────

    def write_client_profile(self, client_alias, display_name=None,
                             positioning='moderate', risk_tolerance='medium',
                             time_horizon='medium', wealth_level=None,
                             macro_bias='neutral', regime_sensitivity='moderate',
                             sector_convictions_json=None,
                             communication_style='formal',
                             preferred_frequency='quarterly',
                             preferred_channel='email',
                             money_script=None, primary_goal=None,
                             known_biases_json=None,
                             last_contact_date=None, last_contact_type=None,
                             next_review_date=None, notes=None,
                             module_version=None):
        """Create or update a client profile (upsert on client_alias)."""
        try:
            now = self._now()
            existing = self.conn.execute(
                "SELECT id FROM client_profiles WHERE client_alias = ?",
                (client_alias,),
            ).fetchone()
            if existing:
                self.conn.execute(
                    """UPDATE client_profiles SET
                       display_name=?, positioning=?, risk_tolerance=?,
                       time_horizon=?, wealth_level=?, macro_bias=?,
                       regime_sensitivity=?, sector_convictions_json=?,
                       communication_style=?, preferred_frequency=?,
                       preferred_channel=?, money_script=?, primary_goal=?,
                       known_biases_json=?, last_contact_date=?,
                       last_contact_type=?, next_review_date=?, notes=?,
                       updated_at=?, write_timestamp=?, module_version=?
                     WHERE client_alias = ?""",
                    (display_name, positioning, risk_tolerance,
                     time_horizon, wealth_level, macro_bias,
                     regime_sensitivity, sector_convictions_json,
                     communication_style, preferred_frequency,
                     preferred_channel, money_script, primary_goal,
                     known_biases_json, last_contact_date,
                     last_contact_type, next_review_date, notes,
                     now, now, module_version, client_alias),
                )
            else:
                self.conn.execute(
                    """INSERT INTO client_profiles
                       (client_alias, display_name, positioning, risk_tolerance,
                        time_horizon, wealth_level, macro_bias, regime_sensitivity,
                        sector_convictions_json, communication_style,
                        preferred_frequency, preferred_channel, money_script,
                        primary_goal, known_biases_json, last_contact_date,
                        last_contact_type, next_review_date, notes,
                        created_at, updated_at, write_timestamp, module_version)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (client_alias, display_name, positioning, risk_tolerance,
                     time_horizon, wealth_level, macro_bias, regime_sensitivity,
                     sector_convictions_json, communication_style,
                     preferred_frequency, preferred_channel, money_script,
                     primary_goal, known_biases_json, last_contact_date,
                     last_contact_type, next_review_date, notes,
                     now, now, now, module_version),
                )
            self._maybe_commit()
        except Exception as e:
            print(f"[SOMA] write_client_profile failed: {e}")

    def write_client_interaction(self, client_alias, date, interaction_type,
                                 topic=None, regime_at_time=None, notes=None,
                                 module_version=None):
        """Log a client interaction and update last_contact on the profile."""
        try:
            self.conn.execute(
                """INSERT INTO client_interactions
                   (client_alias, date, interaction_type, topic,
                    regime_at_time, notes, write_timestamp, module_version)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (client_alias, date, interaction_type, topic,
                 regime_at_time, notes, self._now(), module_version),
            )
            # Also update last_contact on profile
            self.conn.execute(
                """UPDATE client_profiles
                   SET last_contact_date=?, last_contact_type=?, updated_at=?, write_timestamp=?
                   WHERE client_alias=?""",
                (date, interaction_type, self._now(), self._now(), client_alias),
            )
            self._maybe_commit()
        except Exception as e:
            print(f"[SOMA] write_client_interaction failed: {e}")

    def write_event(self, date, event_type, source_module, details_json=None,
                    module_version=None):
        """Log a system event (universe change, config update, etc.)."""
        try:
            self.conn.execute(
                """INSERT INTO events
                   (date, event_type, source_module, details_json,
                    write_timestamp, module_version)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (date, event_type, source_module, details_json,
                 self._now(), module_version),
            )
            self._maybe_commit()
        except Exception as e:
            print(f"[SOMA] write_event failed: {e}")

    def write_backtest_summary(self, date, run_label, total_return=None,
                               sharpe_ratio=None, max_dd=None, years=None,
                               final_equity=None, metrics_json=None,
                               config_json=None, module_version=None):
        """Phase 4.5 — dedicated backtest summary row.

        UPSERT on (date, run_label) so reruns overwrite instead of duplicating.
        """
        try:
            self.conn.execute(
                """INSERT OR REPLACE INTO backtest_summary
                   (date, run_label, total_return, sharpe_ratio, max_dd, years,
                    final_equity, metrics_json, config_json,
                    write_timestamp, module_version)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (date, run_label, total_return, sharpe_ratio, max_dd, years,
                 final_equity, metrics_json, config_json,
                 self._now(), module_version),
            )
            self._maybe_commit()
        except Exception as e:
            print(f"[SOMA] write_backtest_summary failed: {e}")

    def write_stance_drift(self, speaker, topic, prior_stance, new_stance,
                           as_of_prior=None, as_of_new=None, source=None,
                           details_json=None):
        """Phase 3.2 — log a speaker's stance drift on a topic.

        Idempotent: if `drift_count` column is missing, adds it on first call.
        Increments speaker_accuracy.drift_count by 1 (row upserted if absent)
        and appends a `raw_intelligence` row tagged `STANCE_DRIFT` so the
        drift event is queryable alongside other intel.
        """
        try:
            # One-shot column add — idempotent because we check PRAGMA first.
            cols = {r[1] for r in self.conn.execute(
                "PRAGMA table_info(speaker_accuracy)"
            ).fetchall()}
            if "drift_count" not in cols:
                self.conn.execute(
                    "ALTER TABLE speaker_accuracy ADD COLUMN drift_count INTEGER DEFAULT 0"
                )

            # Upsert speaker row with incremented drift_count.
            exists = self.conn.execute(
                "SELECT 1 FROM speaker_accuracy WHERE speaker=?", (speaker,)
            ).fetchone()
            if exists:
                self.conn.execute(
                    """UPDATE speaker_accuracy
                       SET drift_count = COALESCE(drift_count, 0) + 1,
                           last_updated = ?
                       WHERE speaker = ?""",
                    (self._now(), speaker),
                )
            else:
                self.conn.execute(
                    """INSERT INTO speaker_accuracy (speaker, drift_count, last_updated)
                       VALUES (?, 1, ?)""",
                    (speaker, self._now()),
                )

            # Append a raw_intelligence row for searchability.
            import json as _json
            payload = {
                "speaker": speaker,
                "topic": topic,
                "prior_stance": prior_stance,
                "new_stance": new_stance,
                "as_of_prior": as_of_prior,
                "as_of_new": as_of_new,
            }
            self.conn.execute(
                """INSERT INTO raw_intelligence
                   (source_type, title, content, category, target_pipeline,
                    relevance_score, key_claims_json, write_timestamp, module_version)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    "STANCE_DRIFT",
                    f"Stance drift: {speaker} on {topic}",
                    details_json or _json.dumps(payload),
                    "stance_drift",
                    "SOMA",
                    7,
                    _json.dumps(payload),
                    self._now(),
                    "phase-3.2",
                ),
            )
            self._maybe_commit()
        except Exception as e:
            print(f"[SOMA] write_stance_drift failed: {e}")

    # ── READ methods ─────────────────────────────────────────────────
    def _row_to_dict(self, row) -> dict | None:
        """Convert a single sqlite3.Row to dict or None if empty."""
        if row is None:
            return None
        return dict(row)

    def _rows_to_dicts(self, rows) -> list[dict]:
        """Convert a list of sqlite3.Row objects to list of dicts."""
        return [dict(r) for r in rows]

    # ── run_id consistency ────────────────────────────────────────────

    def get_latest_complete_run(self, table="regime_history"):
        """Return the most recent run_id whose expected writes are complete.

        A run is 'complete' only if its run_id appears in BOTH regime_history
        AND valuations (ORACLE writes both atomically). This prevents partial
        runs (e.g. regime written but valuations failed) from being used by
        WhatChanged or other consumers.

        Returns the run_id string, or None if no complete run exists.
        """
        try:
            # Find run_ids that exist in BOTH tables
            row = self.conn.execute(
                """SELECT r.run_id
                   FROM regime_history r
                   INNER JOIN valuations v ON r.run_id = v.run_id
                   WHERE r.run_id IS NOT NULL
                   GROUP BY r.run_id
                   ORDER BY MAX(r.id) DESC LIMIT 1"""
            ).fetchone()
            if row:
                return row["run_id"]
            # Fallback: if no joined run exists, try the requested table alone
            # (handles MANTIS-only or CIPHER-only runs)
            row = self.conn.execute(
                f"SELECT run_id FROM [{table}] "
                "WHERE run_id IS NOT NULL "
                "GROUP BY run_id "
                "HAVING COUNT(*) >= 1 "
                "ORDER BY MAX(id) DESC LIMIT 1"
            ).fetchone()
            return row["run_id"] if row else None
        except Exception:
            return None

    def get_data_by_run_id(self, table: str, run_id: str) -> list[dict]:
        """Return all rows for a specific run_id in the given table.

        Note: table name comes from internal allowlist.
        """
        _VALID_TABLES = {
            "regime_history", "valuations", "trade_log", "outlook_snapshots",
            "portfolio_state", "client_profiles", "client_interactions", "events",
            "horizon_analyses", "philosophy_beliefs", "philosophy_evidence",
            "philosophy_history", "philosophy_alerts",
            "raw_intelligence",
            "geo_events", "geo_vectors", "geo_baselines",
            "onchain_metrics", "onchain_signals",
            "raptor_prospects", "raptor_pipeline_log", "raptor_touchpoints",
            "raptor_consent_ledger", "raptor_coi_network", "raptor_referrals",
        }
        if table not in _VALID_TABLES:
            return []

        rows = self.conn.execute(
            f"SELECT * FROM [{table}] WHERE run_id = ? ORDER BY id",
            (run_id,),
        ).fetchall()
        return self._rows_to_dicts(rows)

    def get_latest_regime(self):
        run_id = self.get_latest_complete_run("regime_history")
        if not run_id:
            return None
        row = self.conn.execute(
            "SELECT * FROM regime_history WHERE run_id = ? ORDER BY id DESC LIMIT 1",
            (run_id,),
        ).fetchone()
        return self._row_to_dict(row)

    def get_latest_valuations(self):
        run_id = self.get_latest_complete_run("valuations")
        if not run_id:
            return []
        rows = self.conn.execute(
            "SELECT * FROM valuations WHERE run_id = ? ORDER BY ticker",
            (run_id,),
        ).fetchall()
        return self._rows_to_dicts(rows)

    def get_latest_portfolio_state(self):
        row = self.conn.execute(
            "SELECT * FROM portfolio_state ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return self._row_to_dict(row)

    def get_latest_outlook(self):
        row = self.conn.execute(
            "SELECT * FROM outlook_snapshots ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return self._row_to_dict(row)

    def get_regime_history(self, limit=30):
        rows = self.conn.execute(
            "SELECT * FROM regime_history ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return self._rows_to_dicts(rows)

    def get_trade_log(self, limit=50):
        rows = self.conn.execute(
            "SELECT * FROM trade_log ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return self._rows_to_dicts(rows)

    def get_events(self, event_type=None, limit=50):
        """Return recent events, optionally filtered by event_type."""
        if event_type:
            rows = self.conn.execute(
                "SELECT * FROM events WHERE event_type = ? ORDER BY id DESC LIMIT ?",
                (event_type, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return self._rows_to_dicts(rows)

    # ── CLIENT PROFILE reads ──────────────────────────────────────────

    def get_client_profile(self, client_alias):
        """Return a single client profile by alias."""
        try:
            row = self.conn.execute(
                "SELECT * FROM client_profiles WHERE client_alias = ?",
                (client_alias,),
            ).fetchone()
            return self._row_to_dict(row)
        except Exception:
            return None

    def get_all_client_profiles(self):
        """Return all client profiles, sorted by alias."""
        try:
            rows = self.conn.execute(
                "SELECT * FROM client_profiles ORDER BY client_alias"
            ).fetchall()
            return self._rows_to_dicts(rows)
        except Exception:
            return []

    def get_clients_due_for_contact(self, before_date=None):
        """Return clients whose next_review_date is on or before the given date.

        If before_date is None, uses today.
        """
        try:
            if before_date is None:
                before_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            rows = self.conn.execute(
                """SELECT * FROM client_profiles
                   WHERE next_review_date IS NOT NULL
                     AND next_review_date <= ?
                   ORDER BY next_review_date""",
                (before_date,),
            ).fetchall()
            return self._rows_to_dicts(rows)
        except Exception:
            return []

    def get_clients_by_positioning(self, positioning):
        """Return all clients with a given positioning (conservative/moderate/aggressive/opportunistic)."""
        try:
            rows = self.conn.execute(
                "SELECT * FROM client_profiles WHERE positioning = ? ORDER BY client_alias",
                (positioning,),
            ).fetchall()
            return self._rows_to_dicts(rows)
        except Exception:
            return []

    def get_client_interactions(self, client_alias, limit=20):
        """Return recent interactions for a specific client."""
        try:
            rows = self.conn.execute(
                "SELECT * FROM client_interactions WHERE client_alias = ? ORDER BY date DESC LIMIT ?",
                (client_alias, limit),
            ).fetchall()
            return self._rows_to_dicts(rows)
        except Exception:
            return []

    # ── KB VALIDATION (Phase 2.4 — Active Intelligence Layer) ──────────

    def get_kb_validator(self):
        """Lazy-initialize and return a KBValidator instance."""
        if not hasattr(self, '_kb_validator'):
            from soma.kb_validator import KBValidator
            self._kb_validator = KBValidator(self)
        return self._kb_validator

    def _validate_write(self, write_type, **kwargs):
        """Fire-and-forget: validate a write against KB rules.

        Never crashes the caller — validation is advisory, not blocking.
        """
        try:
            v = self.get_kb_validator()
            if write_type == "regime":
                v.validate_regime_write(**kwargs)
            elif write_type == "valuation":
                v.validate_valuation_write(**kwargs)
            elif write_type == "portfolio":
                v.validate_portfolio_write(**kwargs)
            elif write_type == "trade":
                v.validate_trade_write(**kwargs)
        except Exception:
            pass  # validation must never crash a write

    # ── KB RULES (Phase 2.3b — Runtime KB Reader) ─────────────────────

    def get_kb_reader(self):
        """Lazy-initialize and return a KBReader instance."""
        if not hasattr(self, '_kb_reader'):
            from .kb_reader import KBReader
            self._kb_reader = KBReader(self)
        return self._kb_reader

    def get_rule(self, rule_id):
        """Convenience wrapper: get a KB rule by ID."""
        return self.get_kb_reader().get_rule(rule_id)

    def log_rule_usage(self, rule_id, module, run_id=None, context=None):
        """Convenience wrapper: log a KB rule read."""
        self.get_kb_reader().log_rule_usage(rule_id, module, run_id, context)

    # ── COBALT writes + reads (Phase C — Digital Assets) ──────────────

    def write_onchain_metric(self, date, asset, metric, value, source,
                             run_id=None, freshness_hours=None, module_version=None):
        """Write a single on-chain metric reading to SOMA."""
        try:
            self.conn.execute(
                """INSERT INTO onchain_metrics
                   (date, run_id, asset, metric, value, source,
                    freshness_hours, write_timestamp, module_version)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (date, run_id, asset, metric, value, source,
                 freshness_hours, self._now(), module_version),
            )
            self._maybe_commit()
        except Exception as e:
            print(f"[SOMA] write_onchain_metric failed: {e}")

    def write_onchain_signal(self, date, asset, signal_direction, composite_score,
                             confidence, components_json=None, run_id=None,
                             regime_at_time=None, module_version=None):
        """Write a composite on-chain signal to SOMA."""
        try:
            self.conn.execute(
                """INSERT INTO onchain_signals
                   (date, run_id, asset, signal_direction, composite_score,
                    confidence, components_json, regime_at_time,
                    write_timestamp, module_version)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (date, run_id, asset, signal_direction, composite_score,
                 confidence, components_json, regime_at_time,
                 self._now(), module_version),
            )
            self._maybe_commit()
        except Exception as e:
            print(f"[SOMA] write_onchain_signal failed: {e}")

    def get_latest_onchain_signal(self, asset="BTC"):
        """Return the most recent composite signal for an asset."""
        try:
            row = self.conn.execute(
                "SELECT * FROM onchain_signals WHERE asset = ? ORDER BY id DESC LIMIT 1",
                (asset,),
            ).fetchone()
            return self._row_to_dict(row)
        except Exception:
            return None

    def get_onchain_metrics(self, asset=None, metric=None, limit=30):
        """Return recent on-chain metrics, optionally filtered."""
        try:
            conditions = []
            params = []
            if asset:
                conditions.append("asset = ?")
                params.append(asset)
            if metric:
                conditions.append("metric = ?")
                params.append(metric)
            where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
            params.append(limit)
            rows = self.conn.execute(
                f"SELECT * FROM onchain_metrics{where} ORDER BY date DESC, id DESC LIMIT ?",
                params,
            ).fetchall()
            return self._rows_to_dicts(rows)
        except Exception:
            return []

    def get_onchain_signal_history(self, asset="BTC", limit=30):
        """Return recent composite signals for an asset."""
        try:
            rows = self.conn.execute(
                "SELECT * FROM onchain_signals WHERE asset = ? ORDER BY date DESC LIMIT ?",
                (asset, limit),
            ).fetchall()
            return self._rows_to_dicts(rows)
        except Exception:
            return []

    def get_cobalt_summary(self):
        """Return a compact dict for MANTIS/DELTA consumption.

        Provides: latest signal per asset, metric freshness, alert flags.
        """
        try:
            assets = {}
            for asset in ("BTC", "SOL", "ETH"):
                sig = self.get_latest_onchain_signal(asset)
                if sig:
                    assets[asset] = {
                        "direction": sig["signal_direction"],
                        "score": sig["composite_score"],
                        "confidence": sig["confidence"],
                        "date": sig["date"],
                    }
            return {
                "status": "ok" if assets else "no_data",
                "assets": assets,
            }
        except Exception:
            return {"status": "error", "assets": {}}

    # ── DOCTRINE reads (Phase A — Thesis & Convictions) ────────────────

    def get_active_beliefs(self):
        """Return all active DOCTRINE beliefs."""
        try:
            rows = self.conn.execute(
                "SELECT * FROM philosophy_beliefs WHERE is_active = 1 ORDER BY domain, belief_id"
            ).fetchall()
            return self._rows_to_dicts(rows)
        except Exception:
            return []

    def get_belief(self, belief_id):
        """Return a single belief by ID."""
        try:
            row = self.conn.execute(
                "SELECT * FROM philosophy_beliefs WHERE belief_id = ?",
                (belief_id,),
            ).fetchone()
            return self._row_to_dict(row)
        except Exception:
            return None

    def get_belief_evidence(self, belief_id, limit=20):
        """Return recent evidence entries for a belief."""
        try:
            rows = self.conn.execute(
                "SELECT * FROM philosophy_evidence WHERE belief_id = ? "
                "ORDER BY date_logged DESC LIMIT ?",
                (belief_id, limit),
            ).fetchall()
            return self._rows_to_dicts(rows)
        except Exception:
            return []

    def get_conviction_history(self, belief_id=None, limit=50):
        """Return conviction change history, optionally for a specific belief."""
        try:
            if belief_id:
                rows = self.conn.execute(
                    "SELECT * FROM philosophy_history WHERE belief_id = ? "
                    "ORDER BY change_date DESC LIMIT ?",
                    (belief_id, limit),
                ).fetchall()
            else:
                rows = self.conn.execute(
                    "SELECT * FROM philosophy_history ORDER BY change_date DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return self._rows_to_dicts(rows)
        except Exception:
            return []

    def get_open_doctrine_alerts(self):
        """Return all unresolved DOCTRINE alerts, highest severity first."""
        try:
            rows = self.conn.execute(
                "SELECT * FROM philosophy_alerts WHERE resolved = 0 "
                "ORDER BY CASE severity "
                "  WHEN 'CRITICAL' THEN 1 WHEN 'WARNING' THEN 2 ELSE 3 END, "
                "date_flagged DESC"
            ).fetchall()
            return self._rows_to_dicts(rows)
        except Exception:
            return []

    def get_doctrine_summary(self):
        """Return a compact dict for MANTIS/CIPHER consumption.

        Provides: domain-level average conviction (0-1 normalized),
        active alerts count, and overall thesis health.
        """
        try:
            beliefs = self.get_active_beliefs()
            if not beliefs:
                return {"status": "no_beliefs", "domains": {}}

            # Group by domain
            domains = {}
            for b in beliefs:
                d = b["domain"]
                if d not in domains:
                    domains[d] = []
                domains[d].append(b["conviction"])

            domain_scores = {}
            for d, convictions in domains.items():
                avg = sum(convictions) / len(convictions)
                domain_scores[d] = {
                    "avg_conviction": round(avg, 1),
                    "normalized": round(avg / 10.0, 2),  # 0-1 for MANTIS
                    "count": len(convictions),
                }

            alerts = self.get_open_doctrine_alerts()
            critical_count = sum(1 for a in alerts if a["severity"] == "CRITICAL")

            overall_avg = sum(b["conviction"] for b in beliefs) / len(beliefs)

            return {
                "status": "healthy" if critical_count == 0 else "attention_needed",
                "overall_conviction": round(overall_avg, 1),
                "overall_normalized": round(overall_avg / 10.0, 2),
                "domains": domain_scores,
                "open_alerts": len(alerts),
                "critical_alerts": critical_count,
            }
        except Exception:
            return {"status": "error", "domains": {}}

    # ── PRISM reads (Phase B — Ingestion Funnel) ───────────────────────

    def get_raw_intelligence(self, category=None, pipeline=None,
                             processed=None, limit=50):
        """Return raw intelligence entries, optionally filtered.

        The 'pipeline' param accepts internal IDs, display names, or aliases —
        all are resolved to the internal_id before querying.
        Results include 'pipeline_display' with the human-readable name.
        """
        try:
            conditions = []
            params = []
            if category:
                conditions.append("category = ?")
                params.append(category)
            if pipeline:
                conditions.append("target_pipeline = ?")
                params.append(self.resolve_pipeline_param(pipeline))
            if processed is not None:
                conditions.append("processed = ?")
                params.append(processed)

            where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
            params.append(limit)

            rows = self.conn.execute(
                f"SELECT * FROM raw_intelligence{where} ORDER BY ingested_at DESC LIMIT ?",
                params,
            ).fetchall()
            results = self._rows_to_dicts(rows)
            return [self._enrich_pipeline_name(r) for r in results]
        except Exception:
            return []

    def get_unprocessed_intelligence(self, pipeline=None, limit=50):
        """Return intelligence entries that haven't been consumed yet."""
        return self.get_raw_intelligence(
            pipeline=pipeline, processed=0, limit=limit
        )

    def mark_intelligence_consumed(self, intelligence_id, consumed_by):
        """Mark a raw_intelligence entry as consumed by a pipeline.
        consumed_by accepts internal IDs, display names, or aliases."""
        try:
            resolved = self.resolve_pipeline_param(consumed_by)
            now = datetime.now(timezone.utc).isoformat()
            self.conn.execute(
                """UPDATE raw_intelligence
                   SET processed = 3, consumed_by = ?, consumed_at = ?,
                       write_timestamp = ?
                   WHERE id = ?""",
                (resolved, now, now, intelligence_id),
            )
            self.conn.commit()
        except Exception as e:
            print(f"[SOMA] mark_intelligence_consumed failed: {e}")

    def get_intelligence_stats(self):
        """Return ingestion statistics for PRISM dashboard.
        The 'by_pipeline' dict uses display names (for UI) alongside internal IDs."""
        try:
            total = self.conn.execute(
                "SELECT COUNT(*) as n FROM raw_intelligence"
            ).fetchone()["n"]
            by_category = self.conn.execute(
                "SELECT category, COUNT(*) as n FROM raw_intelligence GROUP BY category"
            ).fetchall()
            by_pipeline = self.conn.execute(
                "SELECT target_pipeline, COUNT(*) as n FROM raw_intelligence GROUP BY target_pipeline"
            ).fetchall()
            unprocessed = self.conn.execute(
                "SELECT COUNT(*) as n FROM raw_intelligence WHERE processed < 3"
            ).fetchone()["n"]
            # Internal IDs for code, display names for humans
            raw_by_pipeline = {r["target_pipeline"]: r["n"] for r in by_pipeline}
            return {
                "total": total,
                "unprocessed": unprocessed,
                "by_category": {r["category"]: r["n"] for r in by_category},
                "by_pipeline": raw_by_pipeline,
                "by_pipeline_display": self.translate_pipeline_stats(raw_by_pipeline),
            }
        except Exception:
            return {"total": 0, "unprocessed": 0, "by_category": {},
                    "by_pipeline": {}, "by_pipeline_display": {}}

    # ── SPECTRE writes + reads (Phase D — Geopolitical Intelligence) ────

    def write_geo_event(self, date, source, title, url=None, content_snippet=None,
                        category=None, region=None, severity=3, keywords_json=None,
                        nlp_score=None, market_relevance="LOW",
                        run_id=None, module_version=None):
        """Write a single geopolitical event to SOMA."""
        try:
            self.conn.execute(
                """INSERT INTO geo_events
                   (date, run_id, source, title, url, content_snippet,
                    category, region, severity, keywords_json,
                    nlp_score, market_relevance, write_timestamp, module_version)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (date, run_id, source, title, url, content_snippet,
                 category, region, severity, keywords_json,
                 nlp_score, market_relevance, self._now(), module_version),
            )
            self._maybe_commit()
        except Exception as e:
            print(f"[SOMA] write_geo_event failed: {e}")

    def write_geo_vector(self, date, region, category, risk_score,
                         event_count=0, trend=None, components_json=None,
                         run_id=None, module_version=None):
        """Write an aggregated geopolitical risk vector to SOMA."""
        try:
            self.conn.execute(
                """INSERT INTO geo_vectors
                   (date, run_id, region, category, risk_score,
                    event_count, trend, components_json,
                    write_timestamp, module_version)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (date, run_id, region, category, risk_score,
                 event_count, trend, components_json,
                 self._now(), module_version),
            )
            self._maybe_commit()
        except Exception as e:
            print(f"[SOMA] write_geo_vector failed: {e}")

    def write_geo_baseline(self, date, region, category, baseline_score,
                           std_dev=None, sample_count=0, module_version=None):
        """Write/update a geopolitical risk baseline for delta detection."""
        try:
            self.conn.execute(
                """INSERT INTO geo_baselines
                   (date, region, category, baseline_score,
                    std_dev, sample_count, write_timestamp, module_version)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (date, region, category, baseline_score,
                 std_dev, sample_count, self._now(), module_version),
            )
            self._maybe_commit()
        except Exception as e:
            print(f"[SOMA] write_geo_baseline failed: {e}")

    def get_recent_geo_events(self, category=None, region=None,
                              min_severity=1, limit=50):
        """Return recent geopolitical events, optionally filtered."""
        try:
            conditions = ["severity >= ?"]
            params = [min_severity]
            if category:
                conditions.append("category = ?")
                params.append(category)
            if region:
                conditions.append("region = ?")
                params.append(region)
            where = " WHERE " + " AND ".join(conditions)
            params.append(limit)
            rows = self.conn.execute(
                f"SELECT * FROM geo_events{where} ORDER BY date DESC, id DESC LIMIT ?",
                params,
            ).fetchall()
            return self._rows_to_dicts(rows)
        except Exception:
            return []

    def get_latest_geo_vectors(self, date=None):
        """Return the most recent geo risk vectors (all regions/categories)."""
        try:
            if date:
                rows = self.conn.execute(
                    "SELECT * FROM geo_vectors WHERE date = ? ORDER BY region, category",
                    (date,),
                ).fetchall()
            else:
                # Get the latest date
                latest = self.conn.execute(
                    "SELECT MAX(date) as d FROM geo_vectors"
                ).fetchone()
                if not latest or not latest["d"]:
                    return []
                rows = self.conn.execute(
                    "SELECT * FROM geo_vectors WHERE date = ? ORDER BY region, category",
                    (latest["d"],),
                ).fetchall()
            return self._rows_to_dicts(rows)
        except Exception:
            return []

    def get_geo_baseline(self, region, category):
        """Return the most recent baseline for a region/category pair."""
        try:
            row = self.conn.execute(
                "SELECT * FROM geo_baselines WHERE region = ? AND category = ? "
                "ORDER BY date DESC LIMIT 1",
                (region, category),
            ).fetchone()
            return self._row_to_dict(row)
        except Exception:
            return None

    def get_spectre_summary(self):
        """Return a compact dict for DELTA/MANTIS consumption.

        Provides: overall risk level, hottest regions, material events count.
        """
        try:
            vectors = self.get_latest_geo_vectors()
            if not vectors:
                return {"status": "no_data", "overall_risk": 0, "regions": {}}

            # Aggregate by region
            regions = {}
            total_score = 0
            for v in vectors:
                r = v["region"]
                if r not in regions:
                    regions[r] = {"risk_score": 0, "categories": 0, "trend": "STABLE"}
                regions[r]["risk_score"] = max(regions[r]["risk_score"], v["risk_score"])
                regions[r]["categories"] += 1
                if v.get("trend") == "RISING":
                    regions[r]["trend"] = "RISING"
                total_score += v["risk_score"]

            overall = round(total_score / len(vectors), 4) if vectors else 0
            hot_regions = [r for r, d in regions.items() if d["risk_score"] > 0.6]

            # Count high-severity events from today
            today_events = self.get_recent_geo_events(min_severity=4, limit=100)

            return {
                "status": "ok",
                "overall_risk": overall,
                "hot_regions": hot_regions,
                "regions": regions,
                "high_severity_events": len(today_events),
            }
        except Exception:
            return {"status": "error", "overall_risk": 0, "regions": {}}

    def get_client_context_for_cipher(self, client_alias):
        """Return a dict formatted for CIPHER's framework engines.

        Maps SOMA fields to the dict shape that ADViCE, WIIFT, PRACTICE,
        and TalkingPointsGenerator expect.
        """
        profile = self.get_client_profile(client_alias)
        if not profile:
            return None
        return {
            'name': profile.get('display_name') or profile.get('client_alias'),
            'wealth_level': profile.get('wealth_level'),
            'risk_tolerance': profile.get('risk_tolerance'),
            'time_horizon': profile.get('time_horizon'),
            'money_script': profile.get('money_script'),
            'primary_goal': profile.get('primary_goal'),
            'positioning': profile.get('positioning'),
            'macro_bias': profile.get('macro_bias'),
            'communication_style': profile.get('communication_style'),
        }

    # ══════════════════════════════════════════════════════════════
    # RAPTOR — Revenue & Asset Prospecting Through Outreach &
    #          Relationship-building
    # ══════════════════════════════════════════════════════════════

    # Valid pipeline stages in order (used for gate validation)
    _RAPTOR_STAGES = [
        "identified", "researched", "contacted", "meeting_set",
        "proposal_sent", "onboarding", "active", "lost", "dormant"
    ]

    # ── Internal helpers ─────────────────────────────────────────

    def _validate_pipeline_transition(
        self, prospect_id: str, from_stage: str, to_stage: str,
        trigger_touchpoint_id: int = None,
    ):
        """Enforce compliance gate logic before any stage transition.

        Raises ValueError with a clear message if blocked.

        Rules (NI 31-103 / Law 25 / CASL):
        - → contacted  : prospect must have active consent
        - → onboarding : any linked COI referral must have agreement signed
        - → proposal_sent : prospect must have ≥1 compliance-approved touchpoint
                            AND caller must pass trigger_touchpoint_id that
                            (a) exists, (b) belongs to this prospect,
                            (c) is compliance_approved.  [Phase 5.3]
        """
        if to_stage == "contacted":
            status = self.get_consent_status(prospect_id)
            if not status.get("has_active_consent"):
                raise ValueError(
                    f"[RAPTOR GATE] Cannot move {prospect_id} to 'contacted': "
                    "no active consent on record (Law 25 / CASL requirement)."
                )

        if to_stage == "onboarding":
            # Check if any referral exists without a signed agreement
            refs = self.get_referrals_by_prospect(prospect_id)
            for ref in refs:
                coi = self.get_coi(ref["coi_id"])
                if coi and not coi["referral_agreement_signed"]:
                    raise ValueError(
                        f"[RAPTOR GATE] Cannot move {prospect_id} to 'onboarding': "
                        f"COI '{coi['name']}' has no signed referral agreement (NI 31-103)."
                    )

        if to_stage == "proposal_sent":
            approved = self.conn.execute(
                "SELECT COUNT(*) AS n FROM raptor_touchpoints "
                "WHERE prospect_id = ? AND compliance_approved = 1",
                (prospect_id,)
            ).fetchone()
            if not approved or approved["n"] == 0:
                raise ValueError(
                    f"[RAPTOR GATE] Cannot move {prospect_id} to 'proposal_sent': "
                    "zero compliance-approved touchpoints on record."
                )
            # Phase 5.3 — compliance audit trail: caller MUST cite the
            # touchpoint that justified the proposal.
            if not trigger_touchpoint_id:
                raise ValueError(
                    f"[RAPTOR GATE] Cannot move {prospect_id} to 'proposal_sent': "
                    "trigger_touchpoint_id is required (compliance audit trail)."
                )
            tp = self.conn.execute(
                "SELECT prospect_id, compliance_approved FROM raptor_touchpoints "
                "WHERE touchpoint_id = ?",
                (trigger_touchpoint_id,),
            ).fetchone()
            if not tp:
                raise ValueError(
                    f"[RAPTOR GATE] trigger_touchpoint_id {trigger_touchpoint_id} "
                    "does not exist."
                )
            if tp["prospect_id"] != prospect_id:
                raise ValueError(
                    f"[RAPTOR GATE] trigger_touchpoint_id {trigger_touchpoint_id} "
                    f"belongs to another prospect (not {prospect_id})."
                )
            if not tp["compliance_approved"]:
                raise ValueError(
                    f"[RAPTOR GATE] trigger_touchpoint_id {trigger_touchpoint_id} "
                    "is not compliance-approved."
                )

    # ── Staging Dispatcher Support ─────────────────────────────────

    def log_staging_event(self, filename, staging_type, status,
                          error_detail=None, source_hash=None):
        """Log a staging file processing event for idempotency and audit."""
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """INSERT INTO staging_log
               (filename, staging_type, source_hash, status, error_detail,
                processed_at, write_timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (filename, staging_type, source_hash, status, error_detail,
             now, now),
        )
        self.conn.commit()

    def staging_hash_exists(self, source_hash, staging_type):
        """Check if a source_hash + type combo was already processed (dedup)."""
        if not source_hash:
            return False
        row = self.conn.execute(
            """SELECT COUNT(*) FROM staging_log
               WHERE source_hash = ? AND staging_type = ? AND status = 'processed'""",
            (source_hash, staging_type),
        ).fetchone()
        return row[0] > 0 if row else False

    def write_model_flag(self, ticker, flag_type="FRESH_INTEL", source="",
                         source_hash=None, claims_summary=None,
                         impact_on_valuation=None, suggested_action=None):
        """Write a model flag for ORACLE ranking badges and stale detection."""
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """INSERT INTO model_flags
               (ticker, flag_type, source, source_hash, claims_summary,
                impact_on_valuation, suggested_action, created_at, write_timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (ticker, flag_type, source, source_hash, claims_summary,
             impact_on_valuation, suggested_action, now, now),
        )
        self.conn.commit()

    def get_pending_model_flags(self, ticker=None):
        """Get unconsumed model flags, optionally filtered by ticker."""
        where = "WHERE is_consumed = 0"
        params = []
        if ticker:
            where += " AND ticker = ?"
            params.append(ticker)
        rows = self.conn.execute(
            f"SELECT * FROM model_flags {where} ORDER BY created_at DESC",
            params,
        ).fetchall()
        cols = [d[0] for d in self.conn.execute(
            "SELECT * FROM model_flags LIMIT 0").description]
        return [dict(zip(cols, r)) for r in rows]

    def consume_model_flags(self, ticker, consumed_by="run_day"):
        """Mark model flags as consumed for a given ticker."""
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """UPDATE model_flags SET is_consumed = 1, consumed_at = ?,
               consumed_by = ? WHERE ticker = ? AND is_consumed = 0""",
            (now, consumed_by, ticker),
        )
        self.conn.commit()

    def add_belief_candidate(self, belief_id, domain, statement,
                             conviction=5, is_active=0):
        """Insert a CANDIDATE belief (inactive) for human review."""
        now = datetime.now(timezone.utc).isoformat()
        try:
            self.conn.execute(
                """INSERT INTO philosophy_beliefs
                   (belief_id, domain, statement, conviction, evidence_for,
                    evidence_against, last_tested, is_active, created_date,
                    write_timestamp, module_version)
                   VALUES (?, ?, ?, ?, 0, 0, ?, ?, ?, ?, ?)""",
                (belief_id, domain, statement, conviction, now, is_active,
                 now, now, "staging_dispatcher_v1"),
            )
            self.conn.commit()
            return True
        except Exception:
            # Likely duplicate belief_id — that's OK
            return False

    def write_evidence(self, belief_id, source_module, source_detail,
                       supports=True, weight=1.0, run_id=None):
        """Write evidence for an existing DOCTRINE belief."""
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """INSERT INTO philosophy_evidence
               (belief_id, source_module, source_detail, supports, weight,
                run_id, date_logged, write_timestamp, module_version)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (belief_id, source_module, source_detail,
             1 if supports else 0, weight, run_id, now, now,
             "staging_dispatcher_v1"),
        )
        # Update evidence counts on the belief
        col = "evidence_for" if supports else "evidence_against"
        self.conn.execute(
            f"UPDATE philosophy_beliefs SET {col} = {col} + 1 WHERE belief_id = ?",
            (belief_id,),
        )
        self.conn.commit()

    def write_horizon_signal(self, lens, direction, timeframe="",
                             signal_detail="", confidence=0.5,
                             speaker_tier=None, source=""):
        """Write a timing signal to horizon_analyses table.

        Maps transcript-derived signals to the existing horizon_analyses schema.
        Stores the signal detail in full_json as structured JSON.
        """
        import json as _json
        now = datetime.now(timezone.utc).isoformat()
        run_id = f"staging_{now[:10]}_{lens.lower()}"

        signal_payload = _json.dumps({
            "source": "staging_dispatcher",
            "lens": lens,
            "direction": direction,
            "timeframe": timeframe,
            "signal_detail": signal_detail,
            "speaker_tier": speaker_tier,
            "transcript_source": source,
        })

        self.conn.execute(
            """INSERT INTO horizon_analyses
               (run_id, analysis_date, question, composite_score,
                composite_direction, concordance_passed, concordance_count,
                regime, raw_confidence, final_confidence,
                n_lenses, full_json, write_timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (run_id, now[:10],
             f"Staging signal: {signal_detail[:100]}",
             confidence,                  # composite_score
             direction,                   # composite_direction
             0,                           # concordance_passed (not full analysis)
             1,                           # concordance_count (single lens)
             None,                        # regime (not available from staging)
             confidence,                  # raw_confidence
             confidence,                  # final_confidence
             1,                           # n_lenses
             signal_payload,              # full_json
             now),
        )
        self.conn.commit()

    # ── HORIZON Signal Contract (Migration 020) ──────────────────────

    def write_horizon_contract(
        self,
        signal_date: str,
        run_id: str,
        composite_direction: str,
        final_confidence: float,
        concordance_passed: int,
        regime: str | None,
        regime_gate_pass: int,
        concordance_gate_pass: int,
        horizon_multiplier: float,
        gate_failure_reason: str | None = None,
    ) -> int:
        """Persist a HorizonContract row (one per calendar date, UPSERT-safe).

        Uses INSERT OR REPLACE so a same-day re-run simply overwrites the old row.
        Returns the rowid of the inserted/replaced row.
        """
        now = datetime.now(timezone.utc).isoformat()
        cur = self.conn.execute(
            """INSERT OR REPLACE INTO horizon_signal
               (signal_date, run_id, composite_direction, final_confidence,
                concordance_passed, regime, regime_gate_pass, concordance_gate_pass,
                horizon_multiplier, gate_failure_reason, write_timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (signal_date, run_id, composite_direction, final_confidence,
             concordance_passed, regime, regime_gate_pass, concordance_gate_pass,
             horizon_multiplier, gate_failure_reason, now),
        )
        self.conn.commit()
        return cur.lastrowid

    def get_latest_horizon_signal(self) -> dict | None:
        """Return the most recently written horizon_signal row as a dict, or None.

        Ordered by write_timestamp DESC so a same-day re-run always returns the
        freshest contract even if signal_date is the same.
        """
        row = self.conn.execute(
            """SELECT * FROM horizon_signal
               ORDER BY write_timestamp DESC
               LIMIT 1"""
        ).fetchone()
        if row is None:
            return None
        return dict(row)

    def write_raw_intelligence(self, source_type, source_url, title, content,
                               category, target_pipeline, relevance_score=5,
                               key_claims_json="[]", tags_json="[]"):
        """Write a raw intelligence record (used by staging dispatcher)."""
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """INSERT INTO raw_intelligence
               (source_type, source_url, title, content, category,
                target_pipeline, relevance_score, key_claims_json,
                tags_json, processed, write_timestamp, module_version)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)""",
            (source_type, source_url, title, content, category,
             target_pipeline, relevance_score, key_claims_json,
             tags_json, now, "staging_dispatcher_v1"),
        )
        self.conn.commit()

    def get_staging_stats(self):
        """Health check: staging processing stats for monitoring."""
        try:
            today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
            processed = self.conn.execute(
                "SELECT COUNT(*) FROM staging_log WHERE status='processed' AND processed_at LIKE ?",
                (f"{today}%",),
            ).fetchone()[0]
            errors = self.conn.execute(
                "SELECT COUNT(*) FROM staging_log WHERE status='error' AND processed_at LIKE ?",
                (f"{today}%",),
            ).fetchone()[0]
            pending_flags = self.conn.execute(
                "SELECT COUNT(*) FROM model_flags WHERE is_consumed = 0"
            ).fetchone()[0]
            return {
                "processed_today": processed,
                "errors_today": errors,
                "pending_model_flags": pending_flags,
            }
        except Exception:
            return {"error": "staging tables not yet created"}

    # ── Prospects ────────────────────────────────────────────────

    def write_prospect(self, prospect_id: str, **kwargs) -> str:
        """Insert a new prospect. Returns prospect_id.

        Required: prospect_id (UUID string).
        All other columns are optional kwargs matching the schema.
        """
        now = self._now()
        kwargs.setdefault("pipeline_stage", "identified")
        kwargs.setdefault("lead_score", 0.0)
        self.conn.execute(
            """INSERT INTO raptor_prospects (
                prospect_id, created_date, updated_date,
                first_name, last_name, display_name,
                email, phone, linkedin_url,
                language_pref, province, city,
                estimated_assets_band, current_custodian,
                source_type, source_detail,
                pipeline_stage, lead_score, lead_score_updated,
                notes, write_timestamp, module_version
            ) VALUES (
                :prospect_id, :created_date, :updated_date,
                :first_name, :last_name, :display_name,
                :email, :phone, :linkedin_url,
                :language_pref, :province, :city,
                :estimated_assets_band, :current_custodian,
                :source_type, :source_detail,
                :pipeline_stage, :lead_score, :lead_score_updated,
                :notes, :write_timestamp, :module_version
            )""",
            {
                "prospect_id": prospect_id,
                "created_date": kwargs.get("created_date", now),
                "updated_date": now,
                "first_name": kwargs.get("first_name"),
                "last_name": kwargs.get("last_name"),
                "display_name": kwargs.get("display_name"),
                "email": kwargs.get("email"),
                "phone": kwargs.get("phone"),
                "linkedin_url": kwargs.get("linkedin_url"),
                "language_pref": kwargs.get("language_pref", "FR"),
                "province": kwargs.get("province"),
                "city": kwargs.get("city"),
                "estimated_assets_band": kwargs.get("estimated_assets_band"),
                "current_custodian": kwargs.get("current_custodian"),
                "source_type": kwargs.get("source_type"),
                "source_detail": kwargs.get("source_detail"),
                "pipeline_stage": kwargs.get("pipeline_stage"),
                "lead_score": kwargs.get("lead_score"),
                "lead_score_updated": kwargs.get("lead_score_updated"),
                "notes": kwargs.get("notes"),
                "write_timestamp": now,
                "module_version": kwargs.get("module_version", "RAPTOR-1.0"),
            }
        )
        self._maybe_commit()
        return prospect_id

    def update_prospect(self, prospect_id: str, **kwargs):
        """Update mutable fields on an existing prospect.

        Stage transitions are NOT done here — use write_pipeline_transition().
        """
        now = self._now()
        allowed = {
            "first_name", "last_name", "display_name", "email", "phone",
            "linkedin_url", "language_pref", "province", "city",
            "estimated_assets_band", "current_custodian", "source_type",
            "source_detail", "lead_score", "lead_score_updated", "notes",
        }
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return
        updates["updated_date"] = now
        updates["write_timestamp"] = now
        set_clause = ", ".join(f"{k} = :{k}" for k in updates)
        updates["prospect_id"] = prospect_id
        self.conn.execute(
            f"UPDATE raptor_prospects SET {set_clause} WHERE prospect_id = :prospect_id",
            updates
        )
        self._maybe_commit()

    def get_prospect(self, prospect_id: str) -> dict | None:
        """Return one prospect as a dict, or None."""
        row = self.conn.execute(
            "SELECT * FROM raptor_prospects WHERE prospect_id = ?",
            (prospect_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_all_prospects(self, stage: str = None) -> list[dict]:
        """Return all prospects, optionally filtered by pipeline_stage."""
        if stage:
            rows = self.conn.execute(
                "SELECT * FROM raptor_prospects WHERE pipeline_stage = ? ORDER BY created_date DESC",
                (stage,)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM raptor_prospects ORDER BY created_date DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    # ── Pipeline transitions ──────────────────────────────────────

    def write_pipeline_transition(
        self, prospect_id: str, to_stage: str,
        reason: str = None, transitioned_by: str = "manual",
        trigger_touchpoint_id: int = None,
    ) -> int:
        """Validate gate rules, update prospect stage, and log the transition.

        Phase 5.3 — accepts `trigger_touchpoint_id`. Required for any
        transition into `proposal_sent` (compliance audit trail). Stored on
        the raptor_pipeline_log row.

        Returns the new log_id.
        Raises ValueError if a compliance gate blocks the move.
        """
        prospect = self.get_prospect(prospect_id)
        if not prospect:
            raise ValueError(f"[RAPTOR] Unknown prospect_id: {prospect_id}")

        from_stage = prospect["pipeline_stage"]
        self._validate_pipeline_transition(
            prospect_id, from_stage, to_stage,
            trigger_touchpoint_id=trigger_touchpoint_id,
        )

        now = self._now()
        cur = self.conn.execute(
            """INSERT INTO raptor_pipeline_log
               (prospect_id, from_stage, to_stage, transition_date, reason,
                transitioned_by, trigger_touchpoint_id, write_timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (prospect_id, from_stage, to_stage, now, reason,
             transitioned_by, trigger_touchpoint_id, now)
        )
        log_id = cur.lastrowid
        self.conn.execute(
            "UPDATE raptor_prospects SET pipeline_stage = ?, updated_date = ?, write_timestamp = ? "
            "WHERE prospect_id = ?",
            (to_stage, now, now, prospect_id)
        )
        self._maybe_commit()
        return log_id

    def get_pipeline_history(self, prospect_id: str) -> list[dict]:
        """Return full stage transition history for a prospect, oldest first."""
        rows = self.conn.execute(
            "SELECT * FROM raptor_pipeline_log WHERE prospect_id = ? ORDER BY transition_date ASC",
            (prospect_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Touchpoints ───────────────────────────────────────────────

    def write_touchpoint(
        self, prospect_id: str, date: str, channel: str, direction: str,
        subject: str = None, content_hash: str = None, attachment_refs: str = None,
        compliance_approved: bool = False, approval_timestamp: str = None,
        approval_principal: str = None
    ) -> int:
        """Log a communication touchpoint. Returns touchpoint_id."""
        now = self._now()
        cur = self.conn.execute(
            """INSERT INTO raptor_touchpoints
               (prospect_id, date, channel, direction, subject, content_hash,
                attachment_refs, compliance_approved, approval_timestamp,
                approval_principal, write_timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                prospect_id, date, channel, direction, subject, content_hash,
                attachment_refs, 1 if compliance_approved else 0,
                approval_timestamp, approval_principal, now
            )
        )
        self._maybe_commit()
        return cur.lastrowid

    def get_touchpoints(self, prospect_id: str) -> list[dict]:
        """Return all touchpoints for a prospect, newest first."""
        rows = self.conn.execute(
            "SELECT * FROM raptor_touchpoints WHERE prospect_id = ? ORDER BY date DESC",
            (prospect_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Consent ledger ────────────────────────────────────────────

    def write_consent(
        self, prospect_id: str, consent_type: str, consent_date: str,
        consent_method: str = None, consent_text_hash: str = None,
        expiry_date: str = None
    ) -> int:
        """Record a new consent event (idempotent). Returns consent_id.

        Phase 5.2 — UPSERT on (prospect_id, consent_type, consent_date). If a
        record for the same prospect + consent type on the same day already
        exists, update its non-identity fields instead of inserting a
        duplicate. The unique index `ux_raptor_consent_prospect_type_date`
        (migration 017) backs the ON CONFLICT target.

        For casl_implied, expiry_date defaults to consent_date + 2 years if
        not provided.
        """
        from datetime import date as _date, timedelta
        now = self._now()

        if expiry_date is None and consent_type == "casl_implied":
            # CASL implied consent: 2-year rolling window
            base = _date.fromisoformat(consent_date[:10])
            expiry_date = (base + timedelta(days=730)).isoformat()

        cur = self.conn.execute(
            """INSERT INTO raptor_consent_ledger
               (prospect_id, consent_type, consent_date, expiry_date,
                consent_method, consent_text_hash, write_timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(prospect_id, consent_type, consent_date) DO UPDATE SET
                 expiry_date = COALESCE(excluded.expiry_date, raptor_consent_ledger.expiry_date),
                 consent_method = COALESCE(excluded.consent_method, raptor_consent_ledger.consent_method),
                 consent_text_hash = COALESCE(excluded.consent_text_hash, raptor_consent_ledger.consent_text_hash),
                 write_timestamp = excluded.write_timestamp""",
            (prospect_id, consent_type, consent_date, expiry_date,
             consent_method, consent_text_hash, now)
        )
        self._maybe_commit()

        # lastrowid is 0 on a pure UPDATE path — fetch the actual consent_id.
        if cur.lastrowid:
            return cur.lastrowid
        row = self.conn.execute(
            """SELECT consent_id FROM raptor_consent_ledger
               WHERE prospect_id = ? AND consent_type = ? AND consent_date = ?""",
            (prospect_id, consent_type, consent_date)
        ).fetchone()
        return row["consent_id"] if row else 0

    def revoke_consent(self, consent_id: int, revoked_date: str = None):
        """Mark a consent record as revoked."""
        now = self._now()
        self.conn.execute(
            "UPDATE raptor_consent_ledger SET revoked = 1, revoked_date = ? "
            "WHERE consent_id = ?",
            (revoked_date or now[:10], consent_id)
        )
        self._maybe_commit()

    def check_consent(self, prospect_id: str, consent_type: str) -> bool:
        """Return True if the prospect has a non-revoked, non-expired consent of the given type."""
        today = self._now()[:10]
        row = self.conn.execute(
            """SELECT COUNT(*) AS n FROM raptor_consent_ledger
               WHERE prospect_id = ?
                 AND consent_type = ?
                 AND revoked = 0
                 AND deletion_requested = 0
                 AND (expiry_date IS NULL OR expiry_date > ?)""",
            (prospect_id, consent_type, today)
        ).fetchone()
        return row["n"] > 0 if row else False

    def get_consent_status(self, prospect_id: str) -> dict:
        """Return a summary of consent health for a prospect.

        Returns:
            has_active_consent (bool): True if ANY non-expired consent exists
            consents (list): all consent records
            expiring_soon (list): records expiring within 30 days
        """
        today = self._now()[:10]
        from datetime import date as _date, timedelta
        threshold = (_date.fromisoformat(today) + timedelta(days=30)).isoformat()

        rows = self.conn.execute(
            "SELECT * FROM raptor_consent_ledger WHERE prospect_id = ? ORDER BY consent_date DESC",
            (prospect_id,)
        ).fetchall()
        all_consents = [dict(r) for r in rows]

        active = [
            c for c in all_consents
            if not c["revoked"]
            and not c["deletion_requested"]
            and (c["expiry_date"] is None or c["expiry_date"] > today)
        ]
        expiring = [
            c for c in active
            if c["expiry_date"] and c["expiry_date"] <= threshold
        ]
        return {
            "has_active_consent": len(active) > 0,
            "active_count": len(active),
            "consents": all_consents,
            "expiring_soon": expiring,
        }

    def get_expiring_consents(self, days_ahead: int = 30) -> list[dict]:
        """Return all prospects with CASL implied consent expiring within days_ahead days.

        Used by the daily run to flag re-consent needs.
        Returns list of dicts with prospect info + consent expiry details.
        """
        from datetime import date as _date, timedelta
        today = _date.today().isoformat()
        threshold = (_date.today() + timedelta(days=days_ahead)).isoformat()

        rows = self.conn.execute(
            """SELECT
                   cl.consent_id, cl.prospect_id, cl.consent_type,
                   cl.consent_date, cl.expiry_date,
                   p.display_name, p.email, p.language_pref, p.pipeline_stage
               FROM raptor_consent_ledger cl
               JOIN raptor_prospects p ON p.prospect_id = cl.prospect_id
               WHERE cl.revoked = 0
                 AND cl.deletion_requested = 0
                 AND cl.expiry_date IS NOT NULL
                 AND cl.expiry_date > ?
                 AND cl.expiry_date <= ?
               ORDER BY cl.expiry_date ASC""",
            (today, threshold)
        ).fetchall()
        return [dict(r) for r in rows]

    # ── COI network ───────────────────────────────────────────────

    def write_coi(self, coi_id: str, name: str, **kwargs) -> str:
        """Insert or replace a Centre of Influence record. Returns coi_id."""
        now = self._now()
        self.conn.execute(
            """INSERT OR REPLACE INTO raptor_coi_network (
                coi_id, name, firm, profession, email, phone, linkedin_url,
                relationship_start_date, referral_agreement_signed,
                referral_agreement_date, referral_agreement_path,
                reciprocity_given, reciprocity_received, notes, write_timestamp
            ) VALUES (
                :coi_id, :name, :firm, :profession, :email, :phone, :linkedin_url,
                :relationship_start_date, :referral_agreement_signed,
                :referral_agreement_date, :referral_agreement_path,
                :reciprocity_given, :reciprocity_received, :notes, :write_timestamp
            )""",
            {
                "coi_id": coi_id,
                "name": name,
                "firm": kwargs.get("firm"),
                "profession": kwargs.get("profession"),
                "email": kwargs.get("email"),
                "phone": kwargs.get("phone"),
                "linkedin_url": kwargs.get("linkedin_url"),
                "relationship_start_date": kwargs.get("relationship_start_date"),
                "referral_agreement_signed": 1 if kwargs.get("referral_agreement_signed") else 0,
                "referral_agreement_date": kwargs.get("referral_agreement_date"),
                "referral_agreement_path": kwargs.get("referral_agreement_path"),
                "reciprocity_given": kwargs.get("reciprocity_given", 0),
                "reciprocity_received": kwargs.get("reciprocity_received", 0),
                "notes": kwargs.get("notes"),
                "write_timestamp": now,
            }
        )
        self._maybe_commit()
        return coi_id

    def get_coi(self, coi_id: str) -> dict | None:
        """Return one COI record, or None."""
        row = self.conn.execute(
            "SELECT * FROM raptor_coi_network WHERE coi_id = ?", (coi_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_coi_network(self) -> list[dict]:
        """Return all COI records ordered by name."""
        rows = self.conn.execute(
            "SELECT * FROM raptor_coi_network ORDER BY name ASC"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_coi_referral_stats(self, coi_id: str) -> dict:
        """Return referral performance stats for one COI."""
        rows = self.conn.execute(
            "SELECT outcome, COUNT(*) AS n FROM raptor_referrals "
            "WHERE coi_id = ? GROUP BY outcome",
            (coi_id,)
        ).fetchall()
        stats = {"total": 0, "converted": 0, "lost": 0, "pending": 0}
        for r in rows:
            outcome = r["outcome"] or "pending"
            stats[outcome] = r["n"]
            stats["total"] += r["n"]
        if stats["total"] > 0:
            stats["conversion_rate"] = round(stats["converted"] / stats["total"], 4)
        else:
            stats["conversion_rate"] = 0.0
        return stats

    # ── Referrals ─────────────────────────────────────────────────

    def write_referral(
        self, coi_id: str, prospect_id: str, referral_date: str,
        disclosure_delivered: bool = False, disclosure_date: str = None,
        outcome: str = "pending"
    ) -> int:
        """Log a COI referral. Returns referral_id."""
        now = self._now()
        cur = self.conn.execute(
            """INSERT INTO raptor_referrals
               (coi_id, prospect_id, referral_date, disclosure_delivered,
                disclosure_date, outcome, write_timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                coi_id, prospect_id, referral_date,
                1 if disclosure_delivered else 0,
                disclosure_date, outcome, now
            )
        )
        self._maybe_commit()
        return cur.lastrowid

    def get_referrals_by_coi(self, coi_id: str) -> list[dict]:
        """Return all referrals from a given COI."""
        rows = self.conn.execute(
            "SELECT * FROM raptor_referrals WHERE coi_id = ? ORDER BY referral_date DESC",
            (coi_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_referrals_by_prospect(self, prospect_id: str) -> list[dict]:
        """Return all referrals that brought in this prospect."""
        rows = self.conn.execute(
            "SELECT * FROM raptor_referrals WHERE prospect_id = ? ORDER BY referral_date DESC",
            (prospect_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Dashboard summary ─────────────────────────────────────────

    def get_raptor_summary(self) -> dict:
        """Return a dashboard-ready summary of the RAPTOR pipeline.

        Includes:
        - pipeline_counts: prospects per stage
        - total_prospects: int
        - conversion_rate: identified → active
        - consent_health: % with active consent
        - expiring_consents_30d: count of consents expiring within 30 days
        - coi_count: total COIs in network
        - referral_outcomes: aggregate outcome counts
        """
        # Pipeline stage counts
        stage_rows = self.conn.execute(
            "SELECT pipeline_stage, COUNT(*) AS n FROM raptor_prospects GROUP BY pipeline_stage"
        ).fetchall()
        pipeline_counts = {r["pipeline_stage"]: r["n"] for r in stage_rows}
        total = sum(pipeline_counts.values())

        # Conversion rate (active / total)
        active_count = pipeline_counts.get("active", 0)
        conversion_rate = round(active_count / total, 4) if total > 0 else 0.0

        # Consent health
        today = self._now()[:10]
        total_prospects = self.conn.execute(
            "SELECT COUNT(DISTINCT prospect_id) AS n FROM raptor_prospects"
        ).fetchone()["n"]

        with_consent = self.conn.execute(
            """SELECT COUNT(DISTINCT prospect_id) AS n FROM raptor_consent_ledger
               WHERE revoked = 0 AND deletion_requested = 0
                 AND (expiry_date IS NULL OR expiry_date > ?)""",
            (today,)
        ).fetchone()["n"]

        consent_coverage = round(with_consent / total_prospects, 4) if total_prospects > 0 else 0.0

        # Expiring consents
        expiring = self.get_expiring_consents(days_ahead=30)

        # COI count
        coi_count = self.conn.execute(
            "SELECT COUNT(*) AS n FROM raptor_coi_network"
        ).fetchone()["n"]

        # Referral outcomes
        ref_rows = self.conn.execute(
            "SELECT outcome, COUNT(*) AS n FROM raptor_referrals GROUP BY outcome"
        ).fetchall()
        referral_outcomes = {r["outcome"]: r["n"] for r in ref_rows}

        return {
            "pipeline_counts": pipeline_counts,
            "total_prospects": total,
            "active_count": active_count,
            "conversion_rate": conversion_rate,
            "consent_coverage": consent_coverage,
            "expiring_consents_30d": len(expiring),
            "coi_count": coi_count,
            "referral_outcomes": referral_outcomes,
        }

    # ── Fund MER reference (CRM3 — Phase 4) ──────────────────────

    def write_fund_mer(
        self, fund_name: str, mer: float, *,
        ticker: str = None, ter: float = None, fund_family: str = None,
        fund_type: str = "mutual_fund", currency: str = "CAD", notes: str = None,
    ) -> int:
        """Insert or replace a fund MER record. Returns fund_id.

        When ticker is provided: upserts on ticker (ON CONFLICT DO UPDATE).
        When ticker is None: plain insert (no dedup — each call adds a row).
        """
        now = self._now()
        params = (ticker, fund_name, mer, ter, fund_family, fund_type, currency, notes, now)
        if ticker is not None:
            sql = """INSERT INTO raptor_fund_mers
                       (ticker, fund_name, mer, ter, fund_family, fund_type,
                        currency, notes, write_timestamp)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(ticker) DO UPDATE SET
                         fund_name=excluded.fund_name, mer=excluded.mer,
                         ter=excluded.ter, fund_family=excluded.fund_family,
                         fund_type=excluded.fund_type, currency=excluded.currency,
                         notes=excluded.notes, write_timestamp=excluded.write_timestamp"""
        else:
            sql = """INSERT INTO raptor_fund_mers
                       (ticker, fund_name, mer, ter, fund_family, fund_type,
                        currency, notes, write_timestamp)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"""
        cur = self.conn.execute(sql, params)
        self._maybe_commit()
        return cur.lastrowid

    def execute_data_deletion(self, prospect_id: str, executed_date: str = None) -> int:
        """Mark all consent records for a prospect as deletion executed (Law 25).

        Sets deletion_requested=1 and deletion_executed_date on all records.
        Returns count of rows updated.
        """
        today = executed_date or self._now()[:10]
        cur = self.conn.execute(
            "UPDATE raptor_consent_ledger "
            "SET deletion_requested = 1, deletion_executed_date = ? "
            "WHERE prospect_id = ?",
            (today, prospect_id),
        )
        self._maybe_commit()
        return cur.rowcount

    def get_fund_mer(self, ticker: str) -> dict | None:
        """Return fund MER record by ticker, or None."""
        row = self.conn.execute(
            "SELECT * FROM raptor_fund_mers WHERE ticker = ?", (ticker,)
        ).fetchone()
        return dict(row) if row else None

    def get_all_fund_mers(self) -> list[dict]:
        """Return all fund MER records ordered by fund_family, fund_name."""
        rows = self.conn.execute(
            "SELECT * FROM raptor_fund_mers ORDER BY fund_family ASC, fund_name ASC"
        ).fetchall()
        return [dict(r) for r in rows]

    # ── soma_events pub/sub (Phase 6.1) ───────────────────────────

    def publish_event(
        self,
        event_type: str,
        payload: dict,
        source_module: str,
        correlation_key: str = None,
    ) -> int:
        """Append an event to soma_events. Returns the new event_id.

        Fan-out is passive — subscribers read at their own pace via
        consume_events(). No broadcast, no callbacks, no threads.
        """
        import json as _json
        cur = self.conn.execute(
            """INSERT INTO soma_events
               (event_type, source_module, payload_json, published_at, correlation_key)
               VALUES (?, ?, ?, ?, ?)""",
            (event_type, source_module,
             _json.dumps(payload, default=str), self._now(), correlation_key)
        )
        self.conn.commit()
        return cur.lastrowid

    def register_subscriber(
        self,
        subscriber_name: str,
        type_filter: list = None,
        start_from: str = "now",
    ) -> int:
        """Register a subscriber and set the starting cursor.

        start_from:
          "now"   — cursor at current max event_id (default — only future events)
          "beginning" — cursor at 0 (replay all history)
        """
        existing = self.conn.execute(
            "SELECT last_seen_event_id FROM soma_event_subscribers WHERE subscriber_name = ?",
            (subscriber_name,)
        ).fetchone()
        if existing:
            return existing["last_seen_event_id"]
        if start_from == "now":
            max_row = self.conn.execute(
                "SELECT COALESCE(MAX(event_id), 0) AS m FROM soma_events"
            ).fetchone()
            initial = max_row["m"] if max_row else 0
        else:
            initial = 0
        filter_csv = ",".join(type_filter) if type_filter else None
        now = self._now()
        self.conn.execute(
            """INSERT INTO soma_event_subscribers
               (subscriber_name, last_seen_event_id, type_filter,
                first_registered_at, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            (subscriber_name, initial, filter_csv, now, now)
        )
        self.conn.commit()
        return initial

    def peek_events(
        self,
        subscriber_name: str,
        limit: int = 100,
    ) -> list:
        """Return unseen events for a subscriber WITHOUT advancing cursor."""
        import json as _json
        sub = self.conn.execute(
            "SELECT last_seen_event_id, type_filter FROM soma_event_subscribers WHERE subscriber_name = ?",
            (subscriber_name,)
        ).fetchone()
        if not sub:
            return []
        last = sub["last_seen_event_id"]
        filt = sub["type_filter"]
        if filt:
            types = [t.strip() for t in filt.split(",") if t.strip()]
            placeholders = ",".join("?" for _ in types)
            rows = self.conn.execute(
                f"""SELECT * FROM soma_events
                    WHERE event_id > ? AND event_type IN ({placeholders})
                    ORDER BY event_id ASC LIMIT ?""",
                (last, *types, limit)
            ).fetchall()
        else:
            rows = self.conn.execute(
                """SELECT * FROM soma_events
                   WHERE event_id > ?
                   ORDER BY event_id ASC LIMIT ?""",
                (last, limit)
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["payload"] = _json.loads(d["payload_json"])
            except Exception:
                d["payload"] = {}
            out.append(d)
        return out

    def consume_events(
        self,
        subscriber_name: str,
        limit: int = 100,
    ) -> list:
        """Return unseen events AND advance the subscriber's cursor to the
        last event_id returned. Idempotent for same cursor position.
        """
        events = self.peek_events(subscriber_name, limit=limit)
        if not events:
            return []
        new_cursor = events[-1]["event_id"]
        self.conn.execute(
            """UPDATE soma_event_subscribers
               SET last_seen_event_id = ?, updated_at = ?
               WHERE subscriber_name = ?""",
            (new_cursor, self._now(), subscriber_name)
        )
        self.conn.commit()
        return events

    def get_subscriber_status(self, subscriber_name: str) -> dict:
        """Introspection helper — cursor position + backlog count."""
        sub = self.conn.execute(
            "SELECT * FROM soma_event_subscribers WHERE subscriber_name = ?",
            (subscriber_name,)
        ).fetchone()
        if not sub:
            return {"registered": False}
        last = sub["last_seen_event_id"]
        backlog = self.conn.execute(
            "SELECT COUNT(*) AS n FROM soma_events WHERE event_id > ?", (last,)
        ).fetchone()["n"]
        return {
            "registered": True,
            "subscriber_name": subscriber_name,
            "last_seen_event_id": last,
            "type_filter": sub["type_filter"],
            "backlog_count": backlog,
            "updated_at": sub["updated_at"],
        }
