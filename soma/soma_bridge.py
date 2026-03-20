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
        """Run the initial migration to create all tables."""
        migration = _MIGRATIONS_DIR / "001_initial_schema.sql"
        sql = migration.read_text()
        self.conn.executescript(sql)

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

    # ── READ methods ─────────────────────────────────────────────────
    def _row_to_dict(self, row):
        if row is None:
            return None
        return dict(row)

    def _rows_to_dicts(self, rows):
        return [dict(r) for r in rows]

    def get_latest_regime(self):
        row = self.conn.execute(
            "SELECT * FROM regime_history ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return self._row_to_dict(row)

    def get_latest_valuations(self):
        latest = self.conn.execute(
            "SELECT run_id FROM valuations ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if not latest:
            return []
        rows = self.conn.execute(
            "SELECT * FROM valuations WHERE run_id = ? ORDER BY ticker",
            (latest["run_id"],),
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
