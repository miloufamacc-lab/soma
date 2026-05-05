"""
SOMA-INTEL P6.3 — Unit tests for exploration.py

Acceptance criteria:
  - Daily P-X count: 1-2 average
  - Higher novelty_score correlates with selection probability
  - Uniform novelty → uniform sampling
  - Skewed novelty → high-novelty ticker preferentially selected
"""

from __future__ import annotations

import sys
import tempfile
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

import pytest

_HERE         = Path(__file__).resolve().parent
_DABEIBA_ROOT = _HERE.parent.parent.parent
for _p in [str(_DABEIBA_ROOT), str(_DABEIBA_ROOT / "shared")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from soma.intel.exploration import (
    EXPLORATION_DAILY_MAX,
    EXPLORATION_DAILY_MIN,
    EXPLORATION_PRIORITY,
    EXPLORATION_TAG,
    EXPLORATION_Z_MAX,
    EXPLORATION_Z_MIN,
    ExplorationChannel,
)
from soma.intel.store import IntelStore

# ── Re-use test helpers from novelty tests ─────────────────────────────────────

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
"""


def _make_store() -> IntelStore:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    store = IntelStore(db_path=tmp.name)
    store.__enter__()
    store.initialize_tables()
    store._c.executescript(_SIGNAL_DDL)
    store._conn.commit()
    return store


def _insert_signal(
    store: IntelStore,
    ticker: str,
    z_score: float,
    horizon: str = "tactical",
    sig_date: str = "2026-05-05",
    priority: str = "P3",
    notes: str = "",
) -> int:
    cur = store._c.execute(
        """
        INSERT INTO soma_intel_signal
          (ticker, date, priority, anomaly_score, features, corroboration_count,
           half_life_days, status, horizon, notes)
        VALUES (?, ?, ?, ?, '{}', 0, 30, 'active', ?, ?)
        """,
        (ticker, sig_date, priority, z_score, horizon, notes),
    )
    store._conn.commit()
    return cur.lastrowid


# ── Tests ──────────────────────────────────────────────────────────────────────

class TestExplorationCandidates:
    """Tests for get_candidates()."""

    def test_no_candidates_when_db_empty(self):
        store = _make_store()
        ch = ExplorationChannel(store, "2026-05-05", seed=42)
        assert ch.get_candidates() == []
        store.__exit__(None, None, None)

    def test_low_z_signals_included(self):
        store = _make_store()
        _insert_signal(store, "TSLA", z_score=2.0)  # in [1.5, 2.5) → included
        ch = ExplorationChannel(store, "2026-05-05", seed=42)
        cands = ch.get_candidates()
        assert len(cands) == 1
        assert cands[0]["ticker"] == "TSLA"
        store.__exit__(None, None, None)

    def test_high_z_signals_excluded(self):
        """Signals at or above EXPLORATION_Z_MAX are P3+ candidates, not exploration."""
        store = _make_store()
        _insert_signal(store, "AAPL", z_score=2.5)   # at boundary → excluded
        _insert_signal(store, "MSFT", z_score=3.0)   # above → excluded
        ch = ExplorationChannel(store, "2026-05-05", seed=42)
        assert ch.get_candidates() == []
        store.__exit__(None, None, None)

    def test_below_z_min_excluded(self):
        store = _make_store()
        _insert_signal(store, "PLTR", z_score=1.4)   # below 1.5 → excluded
        ch = ExplorationChannel(store, "2026-05-05", seed=42)
        assert ch.get_candidates() == []
        store.__exit__(None, None, None)

    def test_already_tagged_excluded(self):
        store = _make_store()
        _insert_signal(store, "NVDA", z_score=2.0, notes="exploration_channel")
        ch = ExplorationChannel(store, "2026-05-05", seed=42)
        assert ch.get_candidates() == []
        store.__exit__(None, None, None)

    def test_wrong_date_excluded(self):
        store = _make_store()
        _insert_signal(store, "AMD", z_score=2.0, sig_date="2026-05-04")
        ch = ExplorationChannel(store, "2026-05-05", seed=42)
        assert ch.get_candidates() == []
        store.__exit__(None, None, None)

    def test_novelty_key_added_to_candidates(self):
        store = _make_store()
        _insert_signal(store, "TSLA", z_score=2.0)
        ch = ExplorationChannel(store, "2026-05-05", seed=42)
        cands = ch.get_candidates()
        assert "novelty" in cands[0]
        assert 0.0 <= cands[0]["novelty"] <= 1.0
        store.__exit__(None, None, None)


class TestExplorationSampling:
    """Tests for sample() — P-X tagging and count constraints."""

    def test_sample_count_in_1_2_range(self):
        store = _make_store()
        for i in range(10):
            _insert_signal(store, f"T{i:02d}", z_score=1.8 + i * 0.02)
        ch = ExplorationChannel(store, "2026-05-05", seed=7)
        sampled = ch.sample()
        assert EXPLORATION_DAILY_MIN <= len(sampled) <= EXPLORATION_DAILY_MAX
        store.__exit__(None, None, None)

    def test_sample_tags_priority_px(self):
        store = _make_store()
        _insert_signal(store, "TSLA", z_score=2.0)
        _insert_signal(store, "AAPL", z_score=2.1)
        ch = ExplorationChannel(store, "2026-05-05", seed=42)
        sampled = ch.sample(n=1)
        assert len(sampled) == 1
        assert sampled[0]["priority"] == EXPLORATION_PRIORITY
        store.__exit__(None, None, None)

    def test_sample_tags_notes_with_exploration_channel(self):
        store = _make_store()
        _insert_signal(store, "TSLA", z_score=2.0)
        ch = ExplorationChannel(store, "2026-05-05", seed=42)
        sampled = ch.sample(n=1)
        assert EXPLORATION_TAG in sampled[0]["notes"]
        store.__exit__(None, None, None)

    def test_sample_writes_tag_to_db(self):
        store = _make_store()
        sid = _insert_signal(store, "TSLA", z_score=2.0)
        ch = ExplorationChannel(store, "2026-05-05", seed=42)
        ch.sample(n=1)
        row = store._c.execute(
            "SELECT priority, notes FROM soma_intel_signal WHERE signal_id=?", (sid,)
        ).fetchone()
        assert row["priority"] == EXPLORATION_PRIORITY
        assert EXPLORATION_TAG in row["notes"]
        store.__exit__(None, None, None)

    def test_empty_candidates_returns_empty(self):
        store = _make_store()
        ch = ExplorationChannel(store, "2026-05-05", seed=42)
        assert ch.sample() == []
        store.__exit__(None, None, None)

    def test_sample_n_capped_at_candidate_count(self):
        """If only 1 candidate, sample(n=2) returns 1."""
        store = _make_store()
        _insert_signal(store, "TSLA", z_score=2.0)
        ch = ExplorationChannel(store, "2026-05-05", seed=42)
        sampled = ch.sample(n=2)
        assert len(sampled) == 1
        store.__exit__(None, None, None)


class TestNoveltyWeighting:
    """Tests that novelty_score affects selection probability."""

    def test_uniform_novelty_produces_roughly_uniform_sampling(self):
        """
        When all candidates have equal novelty (1.0 — never seen),
        each should be selected with roughly equal frequency over many trials.
        """
        store = _make_store()
        tickers = [f"T{i:02d}" for i in range(6)]
        for t in tickers:
            _insert_signal(store, t, z_score=2.0)

        counts = Counter()
        N_TRIALS = 200
        for trial in range(N_TRIALS):
            ch = ExplorationChannel(store, "2026-05-05", seed=trial)
            for sig in ch.sample(n=1):
                counts[sig["ticker"]] += 1

            # Re-tag all back to non-exploration so they stay as candidates
            store._c.execute(
                "UPDATE soma_intel_signal SET priority='P3', notes='' WHERE date='2026-05-05'"
            )
            store._conn.commit()

        # Each ticker should appear at least 5% of the time (lower than 1/6=16.7%)
        for t in tickers:
            freq = counts[t] / N_TRIALS
            assert freq >= 0.05, f"ticker {t} selected only {freq:.1%} — not uniform enough"

        store.__exit__(None, None, None)

    def test_high_novelty_ticker_preferentially_selected(self):
        """
        When one ticker has novelty=1.0 and the rest have novelty≈0 (10 priors),
        the high-novelty ticker should be selected in a large majority of trials.
        """
        store = _make_store()
        AS_OF = "2026-05-05"

        # Fill up 10 signals for tickers A-E (novelty→0)
        for letter in ["A", "B", "C", "D", "E"]:
            ticker = f"SAT{letter}"
            for i in range(10):
                sig_date = (date.fromisoformat(AS_OF) - timedelta(days=i+1)).isoformat()
                _insert_signal(store, ticker, z_score=2.0, sig_date=sig_date)
            _insert_signal(store, ticker, z_score=2.0, sig_date=AS_OF)

        # High-novelty ticker: no prior history
        _insert_signal(store, "NOVEL", z_score=2.0, sig_date=AS_OF)

        counts: Counter = Counter()
        N_TRIALS = 100
        for trial in range(N_TRIALS):
            ch = ExplorationChannel(store, AS_OF, seed=trial * 7)
            for sig in ch.sample(n=1):
                counts[sig["ticker"]] += 1
            # Reset today's signals back to untagged so they remain candidates
            store._c.execute(
                "UPDATE soma_intel_signal SET priority='P3', notes='' WHERE date=?",
                (AS_OF,),
            )
            store._conn.commit()

        novel_freq = counts["NOVEL"] / N_TRIALS
        assert novel_freq >= 0.50, (
            f"High-novelty ticker selected only {novel_freq:.1%} of trials "
            f"(expected ≥ 50%). Counts: {dict(counts)}"
        )

        store.__exit__(None, None, None)
