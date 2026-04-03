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
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            self.conn.close()
            self.conn = None
        return False  # do not suppress exceptions

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
            "raw_intelligence"
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
            self.conn.execute(
                """INSERT INTO regime_history
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
            self.conn.execute(
                """INSERT INTO valuations
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
            self.conn.execute(
                """INSERT INTO trade_log
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
            self.conn.execute(
                """INSERT INTO portfolio_state
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
            "raw_intelligence"
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

    # ── COBALT writes + reads (Phase C — On-Chain Intelligence) ────────

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

    # ── DOCTRINE reads (Phase A — Thesis Engine) ───────────────────────

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
        """Return raw intelligence entries, optionally filtered."""
        try:
            conditions = []
            params = []
            if category:
                conditions.append("category = ?")
                params.append(category)
            if pipeline:
                conditions.append("target_pipeline = ?")
                params.append(pipeline)
            if processed is not None:
                conditions.append("processed = ?")
                params.append(processed)

            where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
            params.append(limit)

            rows = self.conn.execute(
                f"SELECT * FROM raw_intelligence{where} ORDER BY ingested_at DESC LIMIT ?",
                params,
            ).fetchall()
            return self._rows_to_dicts(rows)
        except Exception:
            return []

    def get_unprocessed_intelligence(self, pipeline=None, limit=50):
        """Return intelligence entries that haven't been consumed yet."""
        return self.get_raw_intelligence(
            pipeline=pipeline, processed=0, limit=limit
        )

    def mark_intelligence_consumed(self, intelligence_id, consumed_by):
        """Mark a raw_intelligence entry as consumed by a pipeline."""
        try:
            now = datetime.now(timezone.utc).isoformat()
            self.conn.execute(
                """UPDATE raw_intelligence
                   SET processed = 3, consumed_by = ?, consumed_at = ?,
                       write_timestamp = ?
                   WHERE id = ?""",
                (consumed_by, now, now, intelligence_id),
            )
            self.conn.commit()
        except Exception as e:
            print(f"[SOMA] mark_intelligence_consumed failed: {e}")

    def get_intelligence_stats(self):
        """Return ingestion statistics for PRISM dashboard."""
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
            return {
                "total": total,
                "unprocessed": unprocessed,
                "by_category": {r["category"]: r["n"] for r in by_category},
                "by_pipeline": {r["target_pipeline"]: r["n"] for r in by_pipeline},
            }
        except Exception:
            return {"total": 0, "unprocessed": 0, "by_category": {}, "by_pipeline": {}}

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
