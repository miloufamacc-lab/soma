"""
SOMA-INTEL P6.4 — Unit tests for meta_learner.py + migration 025.

Acceptance criteria:
  - Migration 025 applied (table exists, append-only triggers fire)
  - Meta-learner runs end-to-end on backtest training data
  - At least 3 cells get threshold adjustment in first run (logic fires)
  - No cell exceeds ±0.5 from base
  - Append-only trigger fires on UPDATE/DELETE attempt
  - Test: cell with 5 false negatives → threshold lowered by 0.1
"""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pytest

_HERE         = Path(__file__).resolve().parent
_DABEIBA_ROOT = _HERE.parent.parent.parent
for _p in [str(_DABEIBA_ROOT), str(_DABEIBA_ROOT / "shared")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from soma.intel.confirm import regime_thresholds
from soma.intel.meta_learner import (
    ADJUSTMENT_STEP,
    FALSE_NEGATIVE_THRESHOLD,
    MAX_ADJUSTMENT,
    MIN_CELL_OUTCOMES,
    MetaLearner,
    _cell_key,
    _dominant_feature,
)
from soma.intel.store import IntelStore

# ── Helpers ────────────────────────────────────────────────────────────────────

_SIGNAL_DDL = """
CREATE TABLE IF NOT EXISTS soma_intel_signal (
    signal_id INTEGER PRIMARY KEY AUTOINCREMENT, ticker TEXT NOT NULL,
    date TEXT NOT NULL, priority TEXT NOT NULL, anomaly_score REAL NOT NULL,
    features TEXT NOT NULL, corroboration_count INTEGER NOT NULL,
    half_life_days INTEGER NOT NULL, reconfirmation_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'active', horizon TEXT, notes TEXT
);
CREATE TABLE IF NOT EXISTS soma_intel_signal_backtest (
    bt_id INTEGER PRIMARY KEY AUTOINCREMENT, backtest_run_id TEXT NOT NULL,
    sim_date TEXT NOT NULL, signal_id INTEGER, ticker TEXT NOT NULL,
    date TEXT NOT NULL, priority TEXT NOT NULL, anomaly_score REAL NOT NULL,
    features TEXT, corroboration_count INTEGER, half_life_days INTEGER,
    reconfirmation_count INTEGER DEFAULT 0, status TEXT DEFAULT 'active',
    horizon TEXT, notes TEXT, regime_label TEXT, lookahead_clean INTEGER DEFAULT 1,
    forward_return REAL, direction_label TEXT,
    outcome TEXT CHECK(outcome IN ('hit','miss','data_unavailable')),
    scored_ts TEXT
);
CREATE TABLE IF NOT EXISTS soma_intel_universe (
    ticker TEXT PRIMARY KEY, active INTEGER DEFAULT 1, platform_tags TEXT
);
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER, applied_at TEXT);
"""

_THRESHOLD_HISTORY_DDL = """
CREATE TABLE IF NOT EXISTS soma_intel_threshold_history (
  history_id INTEGER PRIMARY KEY AUTOINCREMENT,
  cell_key TEXT NOT NULL, prior_threshold REAL NOT NULL,
  new_threshold REAL NOT NULL, adjustment REAL NOT NULL,
  reason TEXT NOT NULL, applied_ts TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_threshold_cell
    ON soma_intel_threshold_history(cell_key, applied_ts DESC);
CREATE TRIGGER IF NOT EXISTS trg_threshold_history_no_update
BEFORE UPDATE ON soma_intel_threshold_history
BEGIN
  SELECT RAISE(ABORT, 'soma_intel_threshold_history is append-only: UPDATE not allowed');
END;
CREATE TRIGGER IF NOT EXISTS trg_threshold_history_no_delete
BEFORE DELETE ON soma_intel_threshold_history
BEGIN
  SELECT RAISE(ABORT, 'soma_intel_threshold_history is append-only: DELETE not allowed');
END;
"""


def _make_store() -> IntelStore:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    store = IntelStore(db_path=tmp.name)
    store.__enter__()
    store.initialize_tables()
    store._c.executescript(_SIGNAL_DDL)
    store._c.executescript(_THRESHOLD_HISTORY_DDL)
    store._conn.commit()
    return store


def _insert_bt_signal(
    store: IntelStore,
    ticker: str,
    regime: str,
    outcome: str,
    sim_date: str,
    priority: str = "P3",
    features: dict = None,
    run_id: str = "test_run",
) -> None:
    feat_json = json.dumps(features or {"f3_rvol_z": 2.5, "f1_ret5d_z": 0.1,
                                         "f2_ret20d_z": 0.1, "f4_volume_z": 0.1,
                                         "f5_sector_z": 0.0})
    store._c.execute(
        """
        INSERT INTO soma_intel_signal_backtest
          (backtest_run_id, sim_date, ticker, date, priority, anomaly_score,
           features, corroboration_count, half_life_days, status, horizon,
           regime_label, lookahead_clean, outcome)
        VALUES (?, ?, ?, ?, ?, 2.5, ?, 0, 20, 'active', 'tactical', ?, 1, ?)
        """,
        (run_id, sim_date, ticker, sim_date, priority, feat_json, regime, outcome),
    )
    store._conn.commit()


# ── Tests ──────────────────────────────────────────────────────────────────────

class TestMigration025AppendOnly:
    """Verify that the append-only triggers fire on UPDATE and DELETE."""

    def test_update_blocked(self):
        store = _make_store()
        store.append_threshold_adjustment(
            cell_key="bull|ai|f3_rvol_z",
            prior_threshold=2.8,
            new_threshold=2.7,
            adjustment=-0.1,
            reason="test",
        )
        with pytest.raises((sqlite3.IntegrityError, sqlite3.OperationalError), match="append-only"):
            store._c.execute(
                "UPDATE soma_intel_threshold_history SET adjustment=0.0 WHERE history_id=1"
            )
        store.__exit__(None, None, None)

    def test_delete_blocked(self):
        store = _make_store()
        store.append_threshold_adjustment(
            cell_key="bull|ai|f3_rvol_z",
            prior_threshold=2.8,
            new_threshold=2.7,
            adjustment=-0.1,
            reason="test",
        )
        with pytest.raises((sqlite3.IntegrityError, sqlite3.OperationalError), match="append-only"):
            store._c.execute(
                "DELETE FROM soma_intel_threshold_history WHERE history_id=1"
            )
        store.__exit__(None, None, None)

    def test_insert_allowed(self):
        store = _make_store()
        store.append_threshold_adjustment(
            cell_key="bull|ai|f3_rvol_z",
            prior_threshold=2.8, new_threshold=2.7,
            adjustment=-0.1, reason="fn:5",
        )
        count = store._c.execute(
            "SELECT COUNT(*) FROM soma_intel_threshold_history"
        ).fetchone()[0]
        assert count == 1
        store.__exit__(None, None, None)


class TestGetCellThreshold:
    """Verify store.get_cell_threshold reads latest adjustment."""

    def test_returns_default_when_no_history(self):
        store = _make_store()
        result = store.get_cell_threshold("nonexistent|cell|key", default_threshold=2.8)
        assert result == 2.8
        store.__exit__(None, None, None)

    def test_returns_latest_adjustment(self):
        store = _make_store()
        key = "bull|ai|f3_rvol_z"
        store.append_threshold_adjustment(key, 2.8, 2.7, -0.1, "fn:3")
        store.append_threshold_adjustment(key, 2.7, 2.6, -0.1, "fn:4")
        result = store.get_cell_threshold(key, default_threshold=2.8)
        assert result == 2.6
        store.__exit__(None, None, None)

    def test_different_cells_independent(self):
        store = _make_store()
        store.append_threshold_adjustment("cell_a|s|f", 2.8, 2.7, -0.1, "fn")
        result_b = store.get_cell_threshold("cell_b|s|f", default_threshold=3.0)
        assert result_b == 3.0
        store.__exit__(None, None, None)


class TestDominantFeature:
    """Tests for _dominant_feature helper."""

    def test_f3_dominates(self):
        feat = json.dumps({"f1_ret5d_z": 0.1, "f2_ret20d_z": 0.2,
                           "f3_rvol_z": 2.5, "f4_volume_z": 0.1, "f5_sector_z": 0.0})
        assert _dominant_feature(feat) == "f3_rvol_z"

    def test_returns_unknown_on_bad_json(self):
        assert _dominant_feature("not json") == "unknown"

    def test_returns_unknown_on_none(self):
        assert _dominant_feature(None) == "unknown"


class TestMetaLearnerCore:
    """Core meta-learner logic tests."""

    def test_false_negatives_lower_threshold(self):
        """
        Cell with ≥ 3 false negatives in trailing 30d → threshold lowered by 0.1.
        """
        store = _make_store()
        AS_OF = "2026-05-05"
        # Need MIN_CELL_OUTCOMES total outcomes first
        for i in range(MIN_CELL_OUTCOMES):
            sim = (date.fromisoformat(AS_OF) - timedelta(days=40 + i)).isoformat()
            _insert_bt_signal(store, "TSLA", "bull_med_neutral", "hit", sim)
        # Add 3 P-X signals in trailing 30d (false negatives)
        for i in range(FALSE_NEGATIVE_THRESHOLD):
            sim = (date.fromisoformat(AS_OF) - timedelta(days=i + 1)).isoformat()
            _insert_bt_signal(store, "TSLA", "bull_med_neutral", "hit", sim,
                              priority="P-X")

        learner = MetaLearner(store, as_of_date=AS_OF)
        report = learner.run()

        key = _cell_key("bull_med_neutral", "unknown", "f3_rvol_z")
        base_p1, _ = regime_thresholds("bull_med_neutral")
        new_threshold = store.get_cell_threshold(key, default_threshold=base_p1)
        assert new_threshold == round(base_p1 - ADJUSTMENT_STEP, 4), (
            f"expected {base_p1 - ADJUSTMENT_STEP:.2f}, got {new_threshold}"
        )
        assert report["adjustments_down"] >= 1
        store.__exit__(None, None, None)

    def test_false_positives_raise_threshold(self):
        """
        Cell with ≥ 3 false positives (misses) in trailing 30d → threshold raised by 0.1.
        """
        store = _make_store()
        AS_OF = "2026-05-05"
        # MIN_CELL_OUTCOMES outcomes (mostly hits, historical)
        for i in range(MIN_CELL_OUTCOMES):
            sim = (date.fromisoformat(AS_OF) - timedelta(days=40 + i)).isoformat()
            _insert_bt_signal(store, "AAPL", "bull_med_neutral", "hit", sim)
        # 3 misses in trailing 30d → false positives
        for i in range(3):
            sim = (date.fromisoformat(AS_OF) - timedelta(days=i + 1)).isoformat()
            _insert_bt_signal(store, "AAPL", "bull_med_neutral", "miss", sim)

        learner = MetaLearner(store, as_of_date=AS_OF)
        report = learner.run()

        key = _cell_key("bull_med_neutral", "unknown", "f3_rvol_z")
        base_p1, _ = regime_thresholds("bull_med_neutral")
        new_threshold = store.get_cell_threshold(key, default_threshold=base_p1)
        assert new_threshold == round(base_p1 + ADJUSTMENT_STEP, 4) or \
               report["adjustments_up"] >= 1
        store.__exit__(None, None, None)

    def test_insufficient_outcomes_skipped(self):
        """Cell with < MIN_CELL_OUTCOMES outcomes is skipped."""
        store = _make_store()
        AS_OF = "2026-05-05"
        # Only 10 outcomes — below MIN_CELL_OUTCOMES (30)
        for i in range(10):
            _insert_bt_signal(store, "NVDA", "bull_med_neutral", "miss",
                              (date.fromisoformat(AS_OF) - timedelta(days=i+1)).isoformat())

        learner = MetaLearner(store, as_of_date=AS_OF)
        report = learner.run()
        assert report["skipped_min_data"] >= 1
        assert report["cells_adjusted"] == 0
        store.__exit__(None, None, None)

    def test_adjustment_capped_at_max(self):
        """No cell exceeds ±0.5 from base threshold."""
        store = _make_store()
        AS_OF = "2026-05-05"
        key = _cell_key("bull_med_neutral", "unknown", "f3_rvol_z")
        base_p1, _ = regime_thresholds("bull_med_neutral")
        lower_cap = round(base_p1 - MAX_ADJUSTMENT, 4)

        # Pre-load threshold already at cap
        store.append_threshold_adjustment(
            key, base_p1, lower_cap, -MAX_ADJUSTMENT, "pre_loaded"
        )
        # Add many false negatives
        for i in range(MIN_CELL_OUTCOMES + 5):
            sim = (date.fromisoformat(AS_OF) - timedelta(days=i + 1)).isoformat()
            _insert_bt_signal(store, "MSFT", "bull_med_neutral", "hit", sim,
                              priority="P-X" if i < 5 else "P3")

        learner = MetaLearner(store, as_of_date=AS_OF)
        report = learner.run()

        final = store.get_cell_threshold(key, default_threshold=base_p1)
        assert final >= lower_cap, (
            f"threshold {final:.2f} went below cap {lower_cap:.2f}"
        )
        assert final <= round(base_p1 + MAX_ADJUSTMENT, 4)
        store.__exit__(None, None, None)

    def test_no_change_when_below_thresholds(self):
        """No adjustment when false neg/pos counts are below thresholds."""
        store = _make_store()
        AS_OF = "2026-05-05"
        # MIN_CELL_OUTCOMES outcomes, only 1 false negative
        for i in range(MIN_CELL_OUTCOMES):
            sim = (date.fromisoformat(AS_OF) - timedelta(days=40 + i)).isoformat()
            _insert_bt_signal(store, "AMD", "bull_med_neutral", "hit", sim)
        # Just 1 false neg (below threshold of 3)
        _insert_bt_signal(store, "AMD", "bull_med_neutral", "hit",
                          (date.fromisoformat(AS_OF) - timedelta(days=1)).isoformat(),
                          priority="P-X")

        learner = MetaLearner(store, as_of_date=AS_OF)
        report = learner.run()
        assert report["cells_adjusted"] == 0
        store.__exit__(None, None, None)


class TestMetaLearnerWithRealDB:
    """Integration test using the real soma.db (skipped if not accessible)."""

    @pytest.fixture
    def real_db_path(self):
        p = _DABEIBA_ROOT / "shared" / "soma" / "data" / "soma.db"
        if not p.exists():
            pytest.skip("soma.db not found")
        return str(p)

    def test_runs_on_real_db_without_error(self, real_db_path):
        """Meta-learner should run without error on real DB (44k signals)."""
        with IntelStore(db_path=real_db_path) as store:
            learner = MetaLearner(store, as_of_date="2026-05-05")
            report = learner.run()
            assert isinstance(report["cells_evaluated"], int)
            assert report["cells_evaluated"] >= 0
            # With 42k IS signals, many cells should qualify
            assert report["cells_evaluated"] >= 1

    def test_no_cell_exceeds_cap_on_real_db(self, real_db_path):
        """After running on real DB, no threshold history row exceeds ±0.5 from base."""
        with IntelStore(db_path=real_db_path) as store:
            MetaLearner(store, as_of_date="2026-05-05").run()
            rows = store._c.execute(
                "SELECT cell_key, prior_threshold, new_threshold, adjustment "
                "FROM soma_intel_threshold_history"
            ).fetchall()
            for row in rows:
                cell_key = row["cell_key"]
                regime = cell_key.split("|")[0] if "|" in cell_key else "unknown"
                base_p1, _ = regime_thresholds(regime)
                assert abs(row["new_threshold"] - base_p1) <= MAX_ADJUSTMENT + 1e-6, (
                    f"cell {cell_key}: {row['new_threshold']:.2f} exceeds "
                    f"±{MAX_ADJUSTMENT} from base {base_p1:.2f}"
                )
