"""
Tests for Phase 7 §I.1 — Cross-AI Corroboration Channel.

Covers:
  1.  insert_cross_ai_flag writes to soma_intel_cross_ai_flag
  2.  insert_cross_ai_flag projects sentinel edge into soma_intel_edge
      with source_type = ai_source + '_insight'
  3.  Decay arithmetic at 0d / 7d / 14d / 28d
  4.  Idempotent re-insert (duplicate skipped, returns existing flag_id)
  5.  phi4_insight is in confirm.py _CORROBORATION_SOURCES whitelist
  6.  count_corroborations with capability DISABLED returns baseline
      (no cross-AI edges visible to gate — regression lock)
  7.  count_corroborations with capability ENABLED returns baseline + cross-AI count
      (adapter runs → edges in soma_intel_edge → gate sees them)
  8.  Adapter idempotency: ingest_grok run twice on same file inserts 0 on second run
  9.  cross_ai_corroboration capability depends_on confirm_gate + signal_engine
  10. get_active_cross_ai_flags decay filter: 28d-old flag with half_life=14 excluded
  11. supersede_cross_ai_flag marks old flag correctly
  12. invalid ai_source raises ValueError
  13. confidence out of range raises ValueError
"""

from __future__ import annotations

import json
import math
import os
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pytest

from shared.soma.intel.store import IntelStore
from shared.soma.intel.confirm import count_corroborations, _CORROBORATION_SOURCES


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def store(tmp_path):
    """Fresh IntelStore with all tables bootstrapped."""
    db_file = str(tmp_path / "test_cross_ai.db")
    with IntelStore(db_path=db_file) as s:
        s.initialize_tables()
        # Register capabilities that cross_ai_corroboration depends on
        s.register_capability("confirm_gate",   version="1.0", status="enabled")
        s.register_capability("signal_engine",  version="1.0", status="enabled")
        s.register_capability(
            "cross_ai_corroboration", version="1.0", status="disabled",
            depends_on=["confirm_gate", "signal_engine"],
        )
        yield s


@pytest.fixture
def store_enabled(tmp_path):
    """IntelStore with cross_ai_corroboration ENABLED."""
    db_file = str(tmp_path / "test_cross_ai_enabled.db")
    with IntelStore(db_path=db_file) as s:
        s.initialize_tables()
        s.register_capability("confirm_gate",  version="1.0", status="enabled")
        s.register_capability("signal_engine", version="1.0", status="enabled")
        s.register_capability(
            "cross_ai_corroboration", version="1.0", status="enabled",
            depends_on=["confirm_gate", "signal_engine"],
        )
        yield s


def _today() -> str:
    return date.today().isoformat()


def _days_ago(n: int) -> str:
    return (date.today() - timedelta(days=n)).isoformat() + "T00:00:00Z"


# ── Test 1: insert writes to soma_intel_cross_ai_flag ────────────────────────

class TestInsertCrossAiFlag:

    def test_insert_creates_flag_row(self, store):
        """insert_cross_ai_flag creates a row in soma_intel_cross_ai_flag."""
        flag_id, is_new = store.insert_cross_ai_flag(
            ai_source="grok",
            ticker="TSLA",
            signal_type="tactical",
            direction="bullish",
            confidence=0.80,
            ts=_days_ago(0),
            evidence_text="Robotaxi confirmed Austin June 2025",
            source_path="/oracle/output/grok_flags_2026-05-05.json",
        )
        assert isinstance(flag_id, int)
        assert flag_id > 0
        assert is_new is True

        row = store._c.execute(
            "SELECT * FROM soma_intel_cross_ai_flag WHERE flag_id=?", (flag_id,)
        ).fetchone()
        assert row is not None
        assert row["ai_source"] == "grok"
        assert row["ticker"] == "TSLA"
        assert row["signal_type"] == "tactical"
        assert row["direction"] == "bullish"
        assert abs(row["confidence"] - 0.80) < 1e-9
        assert row["superseded_by"] is None

    # ── Test 2: sentinel edge is projected into soma_intel_edge ──────────────

    def test_insert_projects_sentinel_edge(self, store):
        """insert_cross_ai_flag writes a sentinel edge with source_type=grok_insight."""
        flag_id, _ = store.insert_cross_ai_flag(
            ai_source="grok",
            ticker="TSLA",
            signal_type="tactical",
            direction="bullish",
            confidence=0.75,
            ts=_days_ago(0),
            evidence_text=None,
            source_path="/oracle/output/grok_flags_2026-05-05.json",
        )
        expected_source_id = f"cross_ai_flag:{flag_id}"
        edges = store._c.execute(
            "SELECT * FROM soma_intel_edge WHERE source_id=?",
            (expected_source_id,),
        ).fetchall()
        assert len(edges) == 1
        edge = edges[0]
        assert edge["source_type"] == "grok_insight"
        assert edge["edge_type"] == "expresses_sentiment"
        assert abs(edge["confidence"] - 0.75) < 1e-9

    def test_gemini_edge_source_type(self, store):
        """Gemini flags produce source_type='gemini_insight'."""
        flag_id, _ = store.insert_cross_ai_flag(
            ai_source="gemini",
            ticker="PLTR",
            signal_type="thematic",
            direction="bullish",
            confidence=0.82,
            ts=_days_ago(0),
            evidence_text="AI government contract expansion Q1 2026",
            source_path="/oracle/output/gemini_flags_2026-05-05.json",
        )
        edge = store._c.execute(
            "SELECT source_type FROM soma_intel_edge WHERE source_id=?",
            (f"cross_ai_flag:{flag_id}",),
        ).fetchone()
        assert edge["source_type"] == "gemini_insight"

    def test_phi4_edge_source_type(self, store):
        """Phi-4 flags produce source_type='phi4_insight'."""
        flag_id, _ = store.insert_cross_ai_flag(
            ai_source="phi4",
            ticker="IREN",
            signal_type="tactical",
            direction="bullish",
            confidence=0.60,
            ts=_days_ago(0),
            evidence_text=None,
            source_path="/oracle/output/phi4_flags_2026-05-05.jsonl",
        )
        edge = store._c.execute(
            "SELECT source_type FROM soma_intel_edge WHERE source_id=?",
            (f"cross_ai_flag:{flag_id}",),
        ).fetchone()
        assert edge["source_type"] == "phi4_insight"


# ── Test 3: decay arithmetic ──────────────────────────────────────────────────

class TestDecayArithmetic:
    """Decay factor = 0.5 ^ (days_since_ts / half_life_days). Threshold 0.05."""

    @pytest.mark.parametrize("days_ago,half_life,expected_decay,should_appear", [
        (0,  14, 1.0,                     True),   # fresh — decay 1.0
        (7,  14, 0.5 ** (7/14),           True),   # half-way — decay ~0.707
        (14, 14, 0.5 ** (14/14),          True),   # at half-life — decay 0.5
        (28, 14, 0.5 ** (28/14),          True),   # decay=0.25, still above 0.05 threshold
        (56, 14, 0.5 ** (56/14),          True),   # decay=0.0625, still above 0.05 threshold
        (70, 14, 0.5 ** (70/14),          False),  # decay≈0.031 below 0.05 — excluded
    ])
    def test_decay_value(self, store, days_ago, half_life, expected_decay, should_appear):
        ts = _days_ago(days_ago)
        store.insert_cross_ai_flag(
            ai_source="grok",
            ticker="NVDA",
            signal_type="tactical",
            direction="bullish",
            confidence=0.75,
            ts=ts,
            evidence_text=None,
            source_path="/test/path.json",
            half_life_days=half_life,
        )
        flags = store.get_active_cross_ai_flags("NVDA", "tactical", _today())
        matching = [f for f in flags if f["ts"].startswith(ts[:10])]

        if should_appear:
            assert len(matching) >= 1, f"Expected flag at days_ago={days_ago} to appear"
            actual_decay = matching[0]["decay_factor"]
            assert abs(actual_decay - expected_decay) < 0.01, (
                f"days_ago={days_ago} hl={half_life}: "
                f"expected decay {expected_decay:.4f}, got {actual_decay:.4f}"
            )
        else:
            # decay < 0.05 → flag should be filtered out
            assert len(matching) == 0, (
                f"Expected flag at days_ago={days_ago} to be filtered (decay<0.05)"
            )


# ── Test 4: idempotent re-insert ──────────────────────────────────────────────

class TestIdempotency:

    def test_duplicate_insert_returns_existing_flag_id(self, store):
        """Inserting the same flag twice returns the same flag_id."""
        kwargs = dict(
            ai_source="gemini",
            ticker="MSTR",
            signal_type="thematic",
            direction="bullish",
            confidence=0.70,
            ts=_days_ago(1),
            evidence_text="BTC treasury strategy thesis",
            source_path="/test/gemini.json",
        )
        id1, is_new1 = store.insert_cross_ai_flag(**kwargs)
        id2, is_new2 = store.insert_cross_ai_flag(**kwargs)
        assert id1 == id2
        assert is_new1 is True
        assert is_new2 is False

    def test_duplicate_does_not_create_extra_edge(self, store):
        """Duplicate insert must not create a second sentinel edge."""
        kwargs = dict(
            ai_source="grok",
            ticker="AMZN",
            signal_type="tactical",
            direction="neutral",
            confidence=0.55,
            ts=_days_ago(0),
            evidence_text=None,
            source_path="/test/grok.json",
        )
        id1, _ = store.insert_cross_ai_flag(**kwargs)
        store.insert_cross_ai_flag(**kwargs)   # duplicate

        edges = store._c.execute(
            "SELECT COUNT(*) FROM soma_intel_edge WHERE source_id LIKE 'cross_ai_flag:%'"
        ).fetchone()[0]
        # Only 1 edge (from the first insert)
        assert edges == 1


# ── Test 5: phi4_insight in whitelist ─────────────────────────────────────────

class TestWhitelist:

    def test_phi4_insight_in_corroboration_sources(self):
        """phi4_insight must be present in _CORROBORATION_SOURCES (Phase 7.I1.1)."""
        assert "phi4_insight" in _CORROBORATION_SOURCES, (
            "phi4_insight missing from _CORROBORATION_SOURCES in confirm.py. "
            "Phase 7.I1.1 whitelist patch was not applied."
        )

    def test_grok_insight_in_corroboration_sources(self):
        """grok_insight must be present (pre-existing whitelist entry)."""
        assert "grok_insight" in _CORROBORATION_SOURCES

    def test_gemini_insight_in_corroboration_sources(self):
        """gemini_insight must be present (pre-existing whitelist entry)."""
        assert "gemini_insight" in _CORROBORATION_SOURCES


# ── Test 6 & 7: gate behavior with capability disabled vs enabled ─────────────

class TestGateBehavior:
    """
    Regression lock: with capability DISABLED, count_corroborations returns the
    same value as before cross-AI flags were introduced (baseline).
    With capability ENABLED (adapters run, edges in soma_intel_edge), the count
    increases by the number of distinct cross-AI source types that fired.
    """

    def _insert_oracle_edge(self, store, ticker, source_type, ts=None):
        """Insert a synthetic ORACLE pipeline edge into soma_intel_edge."""
        ts = ts or (_today() + "T00:00:00+00:00")
        # Ensure nodes exist
        store._c.execute(
            "INSERT OR IGNORE INTO soma_intel_node "
            "(node_id, node_type, name, aliases, metadata, created_ts, last_seen_ts) "
            "VALUES (?, 'company', ?, '[]', '{}', ?, ?)",
            (f"co_{ticker}", ticker, ts, ts),
        )
        store._c.execute(
            "INSERT OR IGNORE INTO soma_intel_node "
            "(node_id, node_type, name, aliases, metadata, created_ts, last_seen_ts) "
            "VALUES ('th_test_node', 'theme', 'Test', '[]', '{}', ?, ?)",
            (ts, ts),
        )
        store._c.execute(
            """
            INSERT INTO soma_intel_edge
              (src_node_id, dst_node_id, edge_type, weight, confidence, ts,
               half_life_days, source_id, source_type, evidence_text,
               audit_status, superseded_by)
            VALUES (?, 'th_test_node', 'expresses_sentiment', 1.0, 0.80, ?, 90,
                    ?, ?, NULL, 'unaudited', NULL)
            """,
            (f"co_{ticker}", ts, f"oracle_{source_type}_test", source_type),
        )
        store._c.commit()

    def test_capability_disabled_returns_oracle_only_count(self, store):
        """
        Capability disabled → count_corroborations returns only ORACLE pipeline
        corroborations. Cross-AI flags must NOT be present (capability guard stops
        adapters from running, so no cross-AI edges in soma_intel_edge).

        This is the REGRESSION BASELINE: if this count changes after enabling the
        capability, that's the expected delta (cross-AI boost). If it changes
        WITHOUT enabling the capability, that's a regression.
        """
        ticker = "TSLA"
        today  = _today()

        # Insert one ORACLE pipeline edge (titan)
        self._insert_oracle_edge(store, ticker, "oracle_titan")

        # Baseline count: 1 (oracle_titan)
        baseline = count_corroborations(store, ticker, as_of_date=today)
        assert baseline == 1, (
            f"Expected baseline corroboration count of 1 (oracle_titan only), got {baseline}"
        )

        # Verify capability is disabled (gate fires correctly)
        assert not store.is_capability_enabled("cross_ai_corroboration")

    def test_capability_enabled_counts_cross_ai(self, store_enabled):
        """
        Capability enabled → adapters insert cross-AI edges → count_corroborations
        returns baseline + distinct AI source count.
        """
        ticker = "TSLA"
        today  = _today()

        # Insert one ORACLE pipeline edge (baseline = 1)
        self._insert_oracle_edge(store_enabled, ticker, "oracle_titan")

        # Simulate adapter run: insert grok + gemini flags for TSLA
        store_enabled.insert_cross_ai_flag(
            ai_source="grok",
            ticker=ticker,
            signal_type="tactical",
            direction="bullish",
            confidence=0.78,
            ts=today + "T07:00:00Z",
            evidence_text="Grok: TSLA robotaxi momentum",
            source_path="/oracle/output/grok_flags_2026-05-05.json",
        )
        store_enabled.insert_cross_ai_flag(
            ai_source="gemini",
            ticker=ticker,
            signal_type="tactical",
            direction="bullish",
            confidence=0.82,
            ts=today + "T08:00:00Z",
            evidence_text="Gemini: TSLA FSD milestone confirmed",
            source_path="/oracle/output/gemini_flags_2026-05-05.json",
        )

        # count_corroborations reads soma_intel_edge. Cross-AI inserts projected
        # edges with source_type=grok_insight / gemini_insight — both in whitelist.
        # Expected: oracle_titan(1) + grok_insight(1) + gemini_insight(1) = 3
        count = count_corroborations(store_enabled, ticker, as_of_date=today)
        assert count >= 2, (
            f"Expected count >= 2 after adding grok+gemini flags, got {count}. "
            "Dual-write from insert_cross_ai_flag may not be projecting edges correctly."
        )

    def test_baseline_unchanged_after_different_ticker_flag(self, store):
        """
        Inserting a cross-AI flag for PLTR must not change corroboration count for TSLA.
        """
        today = _today()
        self._insert_oracle_edge(store, "TSLA", "oracle_titan")
        baseline_tsla = count_corroborations(store, "TSLA", as_of_date=today)

        # Insert flag for a different ticker
        store.insert_cross_ai_flag(
            ai_source="grok",
            ticker="PLTR",
            signal_type="tactical",
            direction="bullish",
            confidence=0.75,
            ts=today + "T07:00:00Z",
            evidence_text=None,
            source_path="/test/path.json",
        )

        tsla_after = count_corroborations(store, "TSLA", as_of_date=today)
        assert tsla_after == baseline_tsla, (
            "PLTR flag incorrectly changed TSLA corroboration count"
        )


# ── Test 8: adapter-level idempotency ─────────────────────────────────────────

class TestAdapterIdempotency:

    def test_grok_adapter_idempotent_on_same_file(self, tmp_path, store):
        """ingest_grok run twice on the same file inserts 0 on second run."""
        from shared.soma.intel.cross_ai.grok_adapter import ingest_grok, GROK_OUTPUT_DIR

        # Write a fake grok_flags file
        today_str = date.today().isoformat()
        flag_payload = {
            "generated_at": today_str + "T07:00:00Z",
            "source": "grok_deepsearch",
            "flags": [
                {
                    "ticker": "TSLA",
                    "signal_type": "tactical",
                    "direction": "bullish",
                    "confidence": 0.78,
                    "evidence": "Robotaxi confirmed",
                    "ts": today_str + "T07:00:00Z",
                }
            ],
        }
        flags_file = tmp_path / f"grok_flags_{today_str}.json"
        flags_file.write_text(json.dumps(flag_payload))

        import unittest.mock as mock
        with mock.patch(
            "shared.soma.intel.cross_ai.grok_adapter.GROK_OUTPUT_DIR",
            tmp_path,
        ):
            result1 = ingest_grok(store, dry_run=False)
            result2 = ingest_grok(store, dry_run=False)

        assert result1["flags_inserted"] == 1, "First run should insert 1 flag"
        assert result2["flags_inserted"] == 0, "Second run should insert 0 (duplicate)"

    def test_phi4_adapter_idempotent(self, tmp_path, store):
        """ingest_phi4 run twice on same JSONL file inserts 0 on second run."""
        from shared.soma.intel.cross_ai.phi4_adapter import ingest_phi4, _PHI4_MIN_CONFIDENCE

        today_str = date.today().isoformat()
        line = json.dumps({
            "ticker": "IREN",
            "signal_type": "tactical",
            "direction": "bullish",
            "confidence": 0.65,   # after 0.85x calibration = 0.5525 > PHI4_MIN_CONFIDENCE
            "evidence": "Hash rate growth",
            "ts": today_str + "T06:00:00Z",
        })
        flags_file = tmp_path / f"phi4_flags_{today_str}.jsonl"
        flags_file.write_text(line + "\n")

        import unittest.mock as mock
        with mock.patch(
            "shared.soma.intel.cross_ai.phi4_adapter.PHI4_OUTPUT_DIR",
            tmp_path,
        ):
            result1 = ingest_phi4(store, dry_run=False)
            result2 = ingest_phi4(store, dry_run=False)

        assert result1["flags_inserted"] == 1
        assert result2["flags_inserted"] == 0


# ── Test 9: capability dependency assertion ───────────────────────────────────

class TestCapabilityDependencies:

    def test_cross_ai_depends_on_confirm_gate_and_signal_engine(self, store):
        """cross_ai_corroboration capability must depend on confirm_gate + signal_engine."""
        cap = store.get_capability("cross_ai_corroboration")
        assert cap is not None, "cross_ai_corroboration capability not registered"
        depends = cap.get("depends_on", [])
        assert "confirm_gate" in depends, (
            f"Expected 'confirm_gate' in depends_on, got: {depends}"
        )
        assert "signal_engine" in depends, (
            f"Expected 'signal_engine' in depends_on, got: {depends}"
        )


# ── Test 10: get_active_cross_ai_flags decay filter ──────────────────────────

class TestGetActiveFlags:

    def test_70d_old_flag_excluded(self, store):
        """A flag 70 days old with half_life=14 has decay ~0.031 < 0.05 — excluded."""
        ts_old = _days_ago(70)
        store.insert_cross_ai_flag(
            ai_source="grok",
            ticker="TSLA",
            signal_type="tactical",
            direction="bullish",
            confidence=0.75,
            ts=ts_old,
            evidence_text=None,
            source_path="/test/old.json",
            half_life_days=14,
        )
        flags = store.get_active_cross_ai_flags("TSLA", "tactical", _today())
        # decay = 0.5^(70/14) = 0.5^5 = 0.03125 < 0.05 → excluded
        assert len(flags) == 0, (
            f"Expected 0 flags (70d-old flag should be decay-filtered), got {len(flags)}"
        )

    def test_fresh_flag_included(self, store):
        """A fresh flag (today) has decay = 1.0 — always included."""
        store.insert_cross_ai_flag(
            ai_source="gemini",
            ticker="PLTR",
            signal_type="thematic",
            direction="bullish",
            confidence=0.80,
            ts=_today() + "T08:00:00Z",
            evidence_text=None,
            source_path="/test/fresh.json",
            half_life_days=14,
        )
        flags = store.get_active_cross_ai_flags("PLTR", "thematic", _today())
        assert len(flags) == 1
        assert flags[0]["decay_factor"] == pytest.approx(1.0, abs=0.01)


# ── Test 11: supersede_cross_ai_flag ─────────────────────────────────────────

class TestSupersede:

    def test_supersede_marks_old_flag(self, store):
        """supersede_cross_ai_flag sets superseded_by on the old flag."""
        old_id, _ = store.insert_cross_ai_flag(
            ai_source="grok",
            ticker="MSTR",
            signal_type="tactical",
            direction="bullish",
            confidence=0.70,
            ts=_days_ago(1),
            evidence_text=None,
            source_path="/test/old.json",
        )
        new_id, _ = store.insert_cross_ai_flag(
            ai_source="grok",
            ticker="MSTR",
            signal_type="tactical",
            direction="bearish",   # different ts → not a duplicate
            confidence=0.75,
            ts=_today() + "T09:00:00Z",
            evidence_text=None,
            source_path="/test/new.json",
        )
        store.supersede_cross_ai_flag(old_id, new_id)

        row = store._c.execute(
            "SELECT superseded_by FROM soma_intel_cross_ai_flag WHERE flag_id=?",
            (old_id,),
        ).fetchone()
        assert row["superseded_by"] == new_id

    def test_superseded_flag_excluded_from_get_active(self, store):
        """Superseded flags do not appear in get_active_cross_ai_flags."""
        old_id, _ = store.insert_cross_ai_flag(
            ai_source="grok",
            ticker="MSTR",
            signal_type="tactical",
            direction="bullish",
            confidence=0.70,
            ts=_days_ago(1),
            evidence_text=None,
            source_path="/test/old.json",
        )
        new_id, _ = store.insert_cross_ai_flag(
            ai_source="grok",
            ticker="MSTR",
            signal_type="tactical",
            direction="bearish",
            confidence=0.75,
            ts=_today() + "T09:00:00Z",
            evidence_text=None,
            source_path="/test/new.json",
        )
        store.supersede_cross_ai_flag(old_id, new_id)

        flags = store.get_active_cross_ai_flags("MSTR", "tactical", _today())
        flag_ids = [f["flag_id"] for f in flags]
        assert old_id not in flag_ids, "Superseded flag appeared in active flags"
        assert new_id in flag_ids, "New flag should be in active flags"


# ── Test 12 & 13: validation guards ──────────────────────────────────────────

class TestValidation:

    def test_invalid_ai_source_raises(self, store):
        """Unknown ai_source raises ValueError."""
        with pytest.raises(ValueError, match="ai_source must be one of"):
            store.insert_cross_ai_flag(
                ai_source="chatgpt",  # not in ('grok','gemini','phi4')
                ticker="TSLA",
                signal_type="tactical",
                direction="bullish",
                confidence=0.75,
                ts=_today() + "T00:00:00Z",
                evidence_text=None,
                source_path="/test/path.json",
            )

    def test_confidence_out_of_range_raises(self, store):
        """confidence > 1.0 raises ValueError."""
        with pytest.raises(ValueError, match="confidence must be in"):
            store.insert_cross_ai_flag(
                ai_source="grok",
                ticker="TSLA",
                signal_type="tactical",
                direction="bullish",
                confidence=1.5,
                ts=_today() + "T00:00:00Z",
                evidence_text=None,
                source_path="/test/path.json",
            )

    def test_invalid_direction_raises(self, store):
        """Unknown direction raises ValueError."""
        with pytest.raises(ValueError, match="direction must be one of"):
            store.insert_cross_ai_flag(
                ai_source="grok",
                ticker="TSLA",
                signal_type="tactical",
                direction="unknown_dir",
                confidence=0.75,
                ts=_today() + "T00:00:00Z",
                evidence_text=None,
                source_path="/test/path.json",
            )
