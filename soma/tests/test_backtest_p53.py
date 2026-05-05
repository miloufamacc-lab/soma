"""
SOMA-INTEL P5.3 — Integration tests for backtest harness

Tests cover:
  P5.3.a: price history upsert / get_forward_return
  P5.3.b: backtest_runner replay + look-ahead assertion
  P5.3.c: backtest_outcomes scoring (hit/miss/data_unavailable)
  P5.3.d: backtest_report generation (9 sections present)
  P5.3.e: OOS §10 comparison section renders
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

_DABEIBA_ROOT = Path(__file__).resolve().parent.parent.parent.parent
for _p in [str(_DABEIBA_ROOT), str(_DABEIBA_ROOT / "shared")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from soma.intel.store import IntelStore
from soma.intel.backtest_runner   import _replay_window, _apply_migration_024
from soma.intel.backtest_outcomes import _infer_direction, _score_signal, score_run
from soma.intel.backtest_report   import build_report, _section_headline

_MIGRATIONS_DIR = _DABEIBA_ROOT / "shared" / "soma" / "migrations"


# ── Test DB fixture ───────────────────────────────────────────────────────────

def _apply_migration(conn, migration_name: str) -> None:
    sql = (_MIGRATIONS_DIR / migration_name).read_text()
    lines = [ln for ln in sql.splitlines() if "schema_version" not in ln]
    conn.executescript("\n".join(lines))


@pytest.fixture
def store(tmp_path):
    db_path = str(tmp_path / "test_p53.db")
    with IntelStore(db_path=db_path) as s:
        s.initialize_tables()
        _apply_migration(s._c, "021_soma_intel_schema.sql")
        _apply_migration(s._c, "022_soma_intel_audit_calibration.sql")
        _apply_migration(s._c, "023_soma_intel_price_history.sql")
        _apply_migration_024(s)
        s._c.commit()
        yield s


# ── P5.3.a: Price history ─────────────────────────────────────────────────────

class TestPriceHistory:

    def test_upsert_and_retrieve(self, store):
        store.upsert_price("NVDA", "2025-01-10", 145.50, volume=1e7)
        store.upsert_price("NVDA", "2025-01-11", 148.00, volume=1.2e7)
        series = store.get_price_series("NVDA", "2025-01-10", "2025-01-11")
        assert len(series) == 2
        assert series[0]["close"] == pytest.approx(145.50)
        assert series[1]["close"] == pytest.approx(148.00)

    def test_upsert_idempotent(self, store):
        store.upsert_price("AAPL", "2025-03-01", 200.00)
        store.upsert_price("AAPL", "2025-03-01", 205.00)  # update
        series = store.get_price_series("AAPL", "2025-03-01", "2025-03-01")
        assert len(series) == 1
        assert series[0]["close"] == pytest.approx(205.00)

    def test_forward_return_exact_60d(self, store):
        """Load prices for 61 days; forward return from day 0 should use day 60."""
        base = date(2025, 1, 1)
        for i in range(61):
            d = (base + timedelta(days=i)).isoformat()
            store.upsert_price("TSLA", d, 100.0 + i * 1.0)
        store.commit()

        # Day 0 = 100.0, day 60 = 160.0 → return = (160-100)/100 = 0.60
        fwd = store.get_forward_return("TSLA", base.isoformat(), horizon_days=60)
        assert fwd is not None
        assert fwd == pytest.approx(0.60)

    def test_forward_return_none_when_no_prices(self, store):
        fwd = store.get_forward_return("MISSING", "2025-06-01", horizon_days=60)
        assert fwd is None


# ── P5.3.b: Backtest runner ───────────────────────────────────────────────────

class TestBacktestRunner:

    def _seed_signal(self, store, ticker: str, sig_date: str, priority: str = "P1") -> None:
        store.insert_signal(
            ticker        = ticker,
            date          = sig_date,
            priority      = priority,
            anomaly_score = 2.5,
            features      = "{}",
            corroboration = 1,
            half_life     = 10,
            horizon       = "tactical",
            notes         = "test",
            status        = "active",
        )
        store.commit()

    def test_replay_snapshots_signals(self, store):
        self._seed_signal(store, "NVDA", "2025-06-01")
        self._seed_signal(store, "AAPL", "2025-06-01")
        self._seed_signal(store, "MSFT", "2025-06-02")

        stats = _replay_window(
            store       = store,
            run_id      = "test_run_001",
            start_date  = "2025-06-01",
            end_date    = "2025-06-02",
            strict_mode = False,
        )
        assert stats["signals_written"] == 3
        assert stats["days_covered"] == 2

    def test_replay_idempotent(self, store):
        self._seed_signal(store, "NVDA", "2025-07-01")

        _replay_window(store, "test_idem", "2025-07-01", "2025-07-01", strict_mode=False)
        stats = _replay_window(store, "test_idem", "2025-07-01", "2025-07-01", strict_mode=False)
        # Second run clears and re-inserts → same count
        assert stats["signals_written"] == 1

    def test_replay_empty_window(self, store):
        stats = _replay_window(
            store       = store,
            run_id      = "empty_run",
            start_date  = "2020-01-01",
            end_date    = "2020-01-31",
            strict_mode = False,
        )
        assert stats["signals_written"] == 0

    def test_strict_mode_flags_future_regime(self, store):
        """If a regime row exists for sim_date+1, strict mode flags violation."""
        self._seed_signal(store, "AMZN", "2025-08-01")
        # Insert a regime row for "tomorrow"
        store._c.execute(
            """INSERT INTO soma_intel_regime
               (date, trend_state, vol_state, macro_state, composite_label, confidence, features)
               VALUES (?, 'bull', 'low', 'neutral', 'bull_low_neutral', 0.9, '{}')""",
            ("2025-08-02",),
        )
        store._c.commit()

        stats = _replay_window(
            store       = store,
            run_id      = "strict_test",
            start_date  = "2025-08-01",
            end_date    = "2025-08-01",
            strict_mode = True,
        )
        # The regime for 2025-08-02 exists → triggers look-ahead for 2025-08-01 signals
        assert stats["lookahead_violations"] == 1


# ── P5.3.c: Outcome scorer ────────────────────────────────────────────────────

class TestOutcomeScorer:

    def test_direction_bull(self):
        assert _infer_direction("bull_low_neutral") == "long"

    def test_direction_bear(self):
        assert _infer_direction("bear_high_tightening") == "short"

    def test_direction_transition(self):
        assert _infer_direction("transition_med_easing") == "absolute"

    def test_direction_none(self):
        assert _infer_direction(None) == "absolute"

    def test_hit_long(self):
        assert _score_signal(0.05, "long") == "hit"

    def test_miss_long(self):
        assert _score_signal(-0.05, "long") == "miss"

    def test_hit_short(self):
        assert _score_signal(-0.05, "short") == "hit"

    def test_miss_short(self):
        assert _score_signal(0.05, "short") == "miss"

    def test_hit_absolute(self):
        assert _score_signal(0.05, "absolute", transition_threshold=0.02) == "hit"

    def test_miss_absolute_below_threshold(self):
        assert _score_signal(0.01, "absolute", transition_threshold=0.02) == "miss"

    def test_data_unavailable(self):
        assert _score_signal(None, "long") == "data_unavailable"

    def test_score_run_data_unavailable(self, store):
        """When no price history exists, all signals score data_unavailable."""
        store.insert_signal(
            ticker="NVDA", date="2025-09-01", priority="P1",
            anomaly_score=3.0, features="{}", corroboration=2,
            half_life=7, horizon="tactical", notes="test", status="active",
        )
        store.commit()

        _replay_window(store, "score_test", "2025-09-01", "2025-09-01", strict_mode=False)
        stats = score_run(store, "score_test")
        assert stats["data_unavailable"] == 1
        assert stats["hit"] == 0
        assert stats["miss"] == 0

    def test_score_run_hit(self, store):
        """When price data shows positive return, bull signal scores as hit."""
        # Seed price data: 2025-09-01 → 100, 2025-10-31 (60d later) → 110
        base = date(2025, 9, 1)
        for i in range(62):
            d = (base + timedelta(days=i)).isoformat()
            store.upsert_price("GOOG", d, 100.0 + i * 0.2)
        store.commit()

        # Seed signal + regime (bull)
        store.insert_signal(
            ticker="GOOG", date="2025-09-01", priority="P1",
            anomaly_score=4.0, features="{}", corroboration=2,
            half_life=7, horizon="tactical", notes="test", status="active",
        )
        store._c.execute(
            """INSERT INTO soma_intel_regime
               (date, trend_state, vol_state, macro_state, composite_label, confidence, features)
               VALUES ('2025-09-01', 'bull', 'low', 'neutral', 'bull_low_neutral', 0.9, '{}')"""
        )
        store._c.commit()

        _replay_window(store, "hit_test", "2025-09-01", "2025-09-01", strict_mode=False)
        stats = score_run(store, "hit_test")
        assert stats["hit"] == 1


# ── P5.3.d: Report generation ─────────────────────────────────────────────────

class TestBacktestReport:

    def test_report_contains_all_sections(self, tmp_path, store):
        """All 9 section headers must appear in the output file."""
        # Seed minimal data
        store.insert_signal(
            ticker="META", date="2025-10-01", priority="P1",
            anomaly_score=3.5, features="{}", corroboration=2,
            half_life=7, horizon="thematic", notes="test", status="active",
        )
        store._c.commit()
        _replay_window(store, "report_test", "2025-10-01", "2025-10-01", strict_mode=False)
        score_run(store, "report_test")

        import soma.intel.backtest_report as br
        original = br._TASKS
        br._TASKS = tmp_path
        try:
            out = build_report(store, "report_test")
        finally:
            br._TASKS = original

        content = out.read_text()
        for section in ["§1", "§2", "§3", "§4", "§5", "§6", "§7", "§8", "§9"]:
            assert section in content, f"Missing section {section} in report"

    def test_report_oos_section(self, tmp_path, store):
        """§10 appears when oos_run_id is provided."""
        store.insert_signal(
            ticker="AMD", date="2025-11-01", priority="P2",
            anomaly_score=2.0, features="{}", corroboration=1,
            half_life=7, horizon="tactical", notes="test", status="active",
        )
        store._c.commit()
        _replay_window(store, "is_run", "2025-11-01", "2025-11-01", strict_mode=False)
        _replay_window(store, "oos_run", "2025-11-01", "2025-11-01", strict_mode=False)

        import soma.intel.backtest_report as br
        original = br._TASKS
        br._TASKS = tmp_path
        try:
            out = build_report(store, "is_run", oos_run_id="oos_run")
        finally:
            br._TASKS = original

        assert "§10" in out.read_text()
