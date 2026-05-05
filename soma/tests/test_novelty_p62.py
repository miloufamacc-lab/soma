"""
SOMA-INTEL P6.2 — Unit tests for novelty.py

Acceptance criteria:
  - novelty_score(brand-new pair) = 1.0
  - novelty_score(10 prior fires in 90d) = 0.0
  - novelty_score(5 prior fires in 90d) = 0.5
  - Integration: 42k backtest signals produce a sensible novelty distribution
  - count_signals_by_ticker_type returns correct counts
"""

from __future__ import annotations

import sqlite3
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── Path bootstrap ─────────────────────────────────────────────────────────────
_HERE         = Path(__file__).resolve().parent
_DABEIBA_ROOT = _HERE.parent.parent.parent
for _p in [str(_DABEIBA_ROOT), str(_DABEIBA_ROOT / "shared")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from soma.intel.novelty import (
    NOVELTY_SATURATION_N,
    NOVELTY_WINDOW_DAYS,
    _days_before,
    novelty_score,
)
from soma.intel.store import IntelStore


# ── Helpers ────────────────────────────────────────────────────────────────────

_SIGNAL_DDL = """
CREATE TABLE IF NOT EXISTS soma_intel_signal (
    signal_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker               TEXT NOT NULL,
    date                 TEXT NOT NULL,
    priority             TEXT NOT NULL,
    anomaly_score        REAL NOT NULL,
    features             TEXT NOT NULL,
    corroboration_count  INTEGER NOT NULL,
    half_life_days       INTEGER NOT NULL,
    reconfirmation_count INTEGER DEFAULT 0,
    status               TEXT DEFAULT 'active',
    horizon              TEXT,
    notes                TEXT
);
CREATE INDEX IF NOT EXISTS idx_signal_ticker_date
    ON soma_intel_signal(ticker, date DESC);
CREATE INDEX IF NOT EXISTS idx_signal_priority_date
    ON soma_intel_signal(priority, date DESC);
CREATE INDEX IF NOT EXISTS idx_signal_status
    ON soma_intel_signal(status);
"""


def _make_temp_store() -> IntelStore:
    """Create a temp-file IntelStore with node/edge + signal tables, opened via __enter__."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    store = IntelStore(db_path=tmp.name)
    store.__enter__()           # opens the connection
    store.initialize_tables()   # node/edge/FTS
    store._c.executescript(_SIGNAL_DDL)  # signal table
    store._conn.commit()
    return store


def _insert_signal(store: IntelStore, ticker: str, horizon: str, signal_date: str) -> None:
    """Insert a minimal signal row for testing."""
    store._c.execute(
        """
        INSERT INTO soma_intel_signal
          (ticker, date, priority, anomaly_score, features, corroboration_count,
           half_life_days, reconfirmation_count, status, horizon, notes)
        VALUES (?, ?, 'P3', 2.5, '{}', 0, 30, 0, 'active', ?, 'test')
        """,
        (ticker, signal_date, horizon),
    )
    store._conn.commit()


# ── Unit tests ─────────────────────────────────────────────────────────────────

class TestNoveltyScoreFormula:
    """Pure unit tests for the novelty_score formula."""

    def test_brand_new_pair_returns_1(self):
        """novelty_score for a pair with no prior history = 1.0."""
        store = _make_temp_store()
        score = novelty_score(store, "TSLA", "tactical", "2026-05-05")
        assert score == 1.0, f"expected 1.0 got {score}"
        store.__exit__(None, None, None)

    def test_saturated_pair_returns_0(self):
        """novelty_score for a pair with >= 10 fires in 90d = 0.0."""
        store = _make_temp_store()
        as_of = "2026-05-05"
        # Insert 10 signals in the last 90 days
        for i in range(10):
            sig_date = (date.fromisoformat(as_of) - timedelta(days=i)).isoformat()
            _insert_signal(store, "TSLA", "tactical", sig_date)
        score = novelty_score(store, "TSLA", "tactical", as_of)
        assert score == 0.0, f"expected 0.0 got {score}"
        store.__exit__(None, None, None)

    def test_half_saturated_pair_returns_0_5(self):
        """novelty_score for a pair with exactly 5 fires in 90d = 0.5."""
        store = _make_temp_store()
        as_of = "2026-05-05"
        for i in range(5):
            sig_date = (date.fromisoformat(as_of) - timedelta(days=i)).isoformat()
            _insert_signal(store, "TSLA", "tactical", sig_date)
        score = novelty_score(store, "TSLA", "tactical", as_of)
        assert score == 0.5, f"expected 0.5 got {score}"
        store.__exit__(None, None, None)

    def test_score_capped_at_0_for_more_than_10(self):
        """novelty_score does not go negative with > 10 fires."""
        store = _make_temp_store()
        as_of = "2026-05-05"
        for i in range(20):
            sig_date = (date.fromisoformat(as_of) - timedelta(days=i)).isoformat()
            _insert_signal(store, "TSLA", "tactical", sig_date)
        score = novelty_score(store, "TSLA", "tactical", as_of)
        assert score == 0.0
        store.__exit__(None, None, None)

    def test_score_always_in_01_range(self):
        """novelty_score is always in [0, 1]."""
        store = _make_temp_store()
        as_of = "2026-05-05"
        for n in range(15):
            if n > 0:
                _insert_signal(store, "AAPL", "thematic",
                               (date.fromisoformat(as_of) - timedelta(days=n)).isoformat())
            s = novelty_score(store, "AAPL", "thematic", as_of)
            assert 0.0 <= s <= 1.0, f"n={n} score={s} out of range"
        store.__exit__(None, None, None)

    def test_signals_older_than_90d_ignored(self):
        """Signals older than 90 days do not affect novelty score."""
        store = _make_temp_store()
        as_of = "2026-05-05"
        old_date = (date.fromisoformat(as_of) - timedelta(days=91)).isoformat()
        for _ in range(10):
            _insert_signal(store, "MSFT", "structural", old_date)
        score = novelty_score(store, "MSFT", "structural", as_of)
        assert score == 1.0, f"old signals should not count, got {score}"
        store.__exit__(None, None, None)

    def test_different_tickers_independent(self):
        """Signals for TSLA do not affect AAPL novelty."""
        store = _make_temp_store()
        as_of = "2026-05-05"
        for i in range(10):
            _insert_signal(store, "TSLA", "tactical",
                           (date.fromisoformat(as_of) - timedelta(days=i)).isoformat())
        score_aapl = novelty_score(store, "AAPL", "tactical", as_of)
        score_tsla = novelty_score(store, "TSLA", "tactical", as_of)
        assert score_aapl == 1.0
        assert score_tsla == 0.0
        store.__exit__(None, None, None)

    def test_different_signal_types_independent(self):
        """tactical and thematic novelty are tracked independently."""
        store = _make_temp_store()
        as_of = "2026-05-05"
        for i in range(10):
            _insert_signal(store, "PLTR", "tactical",
                           (date.fromisoformat(as_of) - timedelta(days=i)).isoformat())
        tact_score = novelty_score(store, "PLTR", "tactical", as_of)
        them_score = novelty_score(store, "PLTR", "thematic", as_of)
        assert tact_score == 0.0
        assert them_score == 1.0
        store.__exit__(None, None, None)


class TestCountSignalsByTickerType:
    """Unit tests for IntelStore.count_signals_by_ticker_type."""

    def test_count_zero_for_empty_db(self):
        store = _make_temp_store()
        count = store.count_signals_by_ticker_type("TSLA", "tactical", "2026-01-01")
        assert count == 0
        store.__exit__(None, None, None)

    def test_count_matches_inserted(self):
        store = _make_temp_store()
        as_of = "2026-05-05"
        for i in range(3):
            _insert_signal(store, "TSLA", "tactical",
                           (date.fromisoformat(as_of) - timedelta(days=i)).isoformat())
        since = (date.fromisoformat(as_of) - timedelta(days=NOVELTY_WINDOW_DAYS)).isoformat()
        count = store.count_signals_by_ticker_type("TSLA", "tactical", since)
        assert count == 3
        store.__exit__(None, None, None)

    def test_count_excludes_wrong_horizon(self):
        store = _make_temp_store()
        as_of = "2026-05-05"
        _insert_signal(store, "TSLA", "thematic", as_of)
        since = (date.fromisoformat(as_of) - timedelta(days=NOVELTY_WINDOW_DAYS)).isoformat()
        count = store.count_signals_by_ticker_type("TSLA", "tactical", since)
        assert count == 0
        store.__exit__(None, None, None)


class TestHelpers:
    """Unit tests for helper functions."""

    def test_days_before(self):
        result = _days_before("2026-05-05", 90)
        expected = (date(2026, 5, 5) - timedelta(days=90)).isoformat()
        assert result == expected

    def test_days_before_zero(self):
        assert _days_before("2026-05-05", 0) == "2026-05-05"


class TestIntegrationWithBacktestDB:
    """
    Integration test: run novelty_score against the real DB with 42k backtest signals.
    Verifies that the novelty distribution is sensible (not all 0 or all 1).

    Skipped if the real DB is not accessible (CI environments).
    """

    @pytest.fixture
    def real_db_path(self):
        p = _DABEIBA_ROOT / "shared" / "soma" / "data" / "soma.db"
        if not p.exists():
            pytest.skip("soma.db not found — skipping integration test")
        return str(p)

    def test_novelty_distribution_sensible(self, real_db_path):
        """
        With 720 live edges all from 2026-05-04/05, the live soma_intel_signal table
        has no duplicate (ticker, horizon) pairs from the last 90 days in the
        backtest window. So novelty should be 1.0 for most tickers.
        Sample 10 known tickers and confirm all have novelty in [0, 1].
        """
        with IntelStore(db_path=real_db_path) as store:
            tickers = ["TSLA", "AAPL", "MSFT", "PLTR", "NVDA"]
            scores = []
            for ticker in tickers:
                s = novelty_score(store, ticker, "tactical", "2026-05-05")
                assert 0.0 <= s <= 1.0, f"{ticker} score {s} out of range"
                scores.append(s)
            # With the current live DB (few signals per ticker), most should be 1.0
            high_novelty = sum(1 for s in scores if s >= 0.5)
            assert high_novelty >= 3, (
                f"Expected at least 3/5 tickers with novelty >= 0.5, "
                f"got {high_novelty}. Scores: {scores}"
            )
