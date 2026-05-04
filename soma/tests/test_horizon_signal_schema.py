"""
Phase 2 — Round-trip test for migration 020 + SomaBridge horizon_signal methods.

Uses an isolated temp DB so production soma.db is never touched.
"""

import os
import sqlite3
import tempfile
from pathlib import Path

import pytest

# ── Path setup so we can import shared.soma without installing ──────────────
import sys
_DABEIBA_ROOT = Path(__file__).resolve().parent.parent.parent.parent  # tests/ → soma/ → shared/ → DABEIBA/
for _p in [str(_DABEIBA_ROOT), str(_DABEIBA_ROOT / "shared")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import os as _os
# We'll set SOMA_DB_PATH per-test via a fixture


@pytest.fixture
def tmp_db(tmp_path):
    """Provide an isolated SomaBridge connected to a temp DB with all migrations applied."""
    db_path = str(tmp_path / "soma_test.db")
    _os.environ["SOMA_DB_PATH"] = db_path

    from soma.soma_bridge import SomaBridge
    with SomaBridge(db_path=db_path) as db:
        db.initialize_db()
        yield db

    # Cleanup env var so it doesn't leak into other tests
    _os.environ.pop("SOMA_DB_PATH", None)


# ── Migration tests ─────────────────────────────────────────────────────────

class TestMigration020:

    def test_schema_version_is_20(self, tmp_db):
        """initialize_db() must apply migration 020 and report version=20."""
        ver = tmp_db.get_schema_version()
        assert ver >= 20, f"Expected schema_version >= 20, got {ver}"

    def test_horizon_signal_table_exists(self, tmp_db):
        """horizon_signal table must exist after initialize_db()."""
        row = tmp_db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='horizon_signal'"
        ).fetchone()
        assert row is not None, "horizon_signal table not found after migration 020"

    def test_horizon_signal_has_required_columns(self, tmp_db):
        """horizon_signal must have all columns defined in the spec."""
        cols = {
            r["name"]
            for r in tmp_db.conn.execute("PRAGMA table_info(horizon_signal)").fetchall()
        }
        required = {
            "id", "signal_date", "run_id", "composite_direction", "final_confidence",
            "concordance_passed", "regime", "regime_gate_pass", "concordance_gate_pass",
            "horizon_multiplier", "gate_failure_reason", "write_timestamp",
        }
        missing = required - cols
        assert not missing, f"horizon_signal missing columns: {missing}"

    def test_unique_index_on_signal_date(self, tmp_db):
        """Inserting two rows with the same signal_date must replace the first (UPSERT)."""
        from soma.soma_bridge import SomaBridge
        db = tmp_db
        db.write_horizon_contract(
            signal_date="2026-01-01",
            run_id="run-A",
            composite_direction="BUY",
            final_confidence=0.70,
            concordance_passed=1,
            regime="RISK_ON",
            regime_gate_pass=1,
            concordance_gate_pass=1,
            horizon_multiplier=1.25,
        )
        # Second write for same date should REPLACE (not raise)
        db.write_horizon_contract(
            signal_date="2026-01-01",
            run_id="run-B",
            composite_direction="SELL",
            final_confidence=0.60,
            concordance_passed=1,
            regime="RISK_ON",
            regime_gate_pass=1,
            concordance_gate_pass=1,
            horizon_multiplier=0.85,
        )
        count = tmp_db.conn.execute(
            "SELECT COUNT(*) FROM horizon_signal WHERE signal_date='2026-01-01'"
        ).fetchone()[0]
        assert count == 1, f"Expected 1 row after UPSERT, got {count}"

        row = tmp_db.get_latest_horizon_signal()
        assert row["run_id"] == "run-B", "Latest row should be the second write"
        assert abs(row["horizon_multiplier"] - 0.85) < 1e-9


# ── SomaBridge method tests ─────────────────────────────────────────────────

class TestSomaBridgeHorizonContract:

    def test_write_horizon_contract_returns_rowid(self, tmp_db):
        """write_horizon_contract() must return a positive integer rowid."""
        rowid = tmp_db.write_horizon_contract(
            signal_date="2026-02-01",
            run_id="run-001",
            composite_direction="BUY",
            final_confidence=0.80,
            concordance_passed=1,
            regime="RISK_ON",
            regime_gate_pass=1,
            concordance_gate_pass=1,
            horizon_multiplier=1.30,
        )
        assert isinstance(rowid, int) and rowid > 0

    def test_write_and_read_round_trip(self, tmp_db):
        """write_horizon_contract() then get_latest_horizon_signal() returns same values."""
        tmp_db.write_horizon_contract(
            signal_date="2026-02-15",
            run_id="run-rt-01",
            composite_direction="NEUTRAL",
            final_confidence=0.55,
            concordance_passed=0,
            regime="TURBULENCE",
            regime_gate_pass=1,
            concordance_gate_pass=0,
            horizon_multiplier=1.0,
            gate_failure_reason="concordance_gate: concordance_passed=0",
        )
        row = tmp_db.get_latest_horizon_signal()
        assert row is not None
        assert row["signal_date"] == "2026-02-15"
        assert row["run_id"] == "run-rt-01"
        assert row["composite_direction"] == "NEUTRAL"
        assert abs(row["final_confidence"] - 0.55) < 1e-9
        assert row["concordance_passed"] == 0
        assert row["regime"] == "TURBULENCE"
        assert row["regime_gate_pass"] == 1
        assert row["concordance_gate_pass"] == 0
        assert abs(row["horizon_multiplier"] - 1.0) < 1e-9
        assert row["gate_failure_reason"] == "concordance_gate: concordance_passed=0"

    def test_get_latest_returns_none_when_empty(self, tmp_db):
        """get_latest_horizon_signal() must return None on an empty table."""
        result = tmp_db.get_latest_horizon_signal()
        assert result is None

    def test_get_latest_returns_most_recent_by_timestamp(self, tmp_db):
        """get_latest_horizon_signal() returns the row with the highest write_timestamp."""
        import time
        tmp_db.write_horizon_contract(
            signal_date="2026-03-01",
            run_id="run-first",
            composite_direction="BUY",
            final_confidence=0.75,
            concordance_passed=1,
            regime="RISK_ON",
            regime_gate_pass=1,
            concordance_gate_pass=1,
            horizon_multiplier=1.20,
        )
        time.sleep(0.01)  # ensure distinct timestamps
        tmp_db.write_horizon_contract(
            signal_date="2026-03-02",  # different date → new row
            run_id="run-second",
            composite_direction="SELL",
            final_confidence=0.65,
            concordance_passed=1,
            regime="RISK_ON",
            regime_gate_pass=1,
            concordance_gate_pass=1,
            horizon_multiplier=0.80,
        )
        row = tmp_db.get_latest_horizon_signal()
        assert row["run_id"] == "run-second", "Should return the most recently written row"
        assert abs(row["horizon_multiplier"] - 0.80) < 1e-9

    def test_null_regime_allowed(self, tmp_db):
        """regime column may be NULL (HORIZON sometimes can't determine regime)."""
        tmp_db.write_horizon_contract(
            signal_date="2026-04-01",
            run_id="run-no-regime",
            composite_direction="NEUTRAL",
            final_confidence=0.50,
            concordance_passed=0,
            regime=None,
            regime_gate_pass=1,
            concordance_gate_pass=0,
            horizon_multiplier=1.0,
        )
        row = tmp_db.get_latest_horizon_signal()
        assert row["regime"] is None

    def test_gate_failure_reason_null_on_pass(self, tmp_db):
        """gate_failure_reason should be None when both gates pass."""
        tmp_db.write_horizon_contract(
            signal_date="2026-05-01",
            run_id="run-pass",
            composite_direction="BUY",
            final_confidence=0.80,
            concordance_passed=1,
            regime="RISK_ON",
            regime_gate_pass=1,
            concordance_gate_pass=1,
            horizon_multiplier=1.35,
            gate_failure_reason=None,
        )
        row = tmp_db.get_latest_horizon_signal()
        assert row["gate_failure_reason"] is None
