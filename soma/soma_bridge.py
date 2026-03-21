"""
SomaBridge — the single read/write API for SOMA (Shared Ontology for Market Analysis).

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

_DEFAULT_DB_PATH = Path.home() / "Desktop" / "DABEIBA" / "shared" / "soma" / "data" / "soma.db"
_MIGRATIONS_DIR = Path(__file__).parent / "migrations"


class SomaBridge:
    def __init__(self, db_path=None):
        self.db_path = str(db_path or _DEFAULT_DB_PATH)
        self.conn = None

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
        """
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
        except Exception:
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
            self.conn.commit()
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
            self.conn.commit()
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
            self.conn.commit()
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
            self.conn.commit()
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
            self.conn.commit()
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
            self.conn.commit()
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
            self.conn.commit()
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
            self.conn.commit()
        except Exception as e:
            print(f"[SOMA] write_event failed: {e}")

    # ── READ methods ─────────────────────────────────────────────────
    def _row_to_dict(self, row):
        if row is None:
            return None
        return dict(row)

    def _rows_to_dicts(self, rows):
        return [dict(r) for r in rows]

    # ── run_id consistency ────────────────────────────────────────────

    def get_latest_complete_run(self, table="regime_history"):
        """Return the most recent run_id whose expected writes are complete.

        For regime_history: at least 1 entry exists for that run_id.
        For valuations:     at least 1 entry exists for that run_id.

        Returns the run_id string, or None if no complete run exists.
        """
        try:
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

    def get_data_by_run_id(self, table, run_id):
        """Return all rows for a specific run_id in the given table."""
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
