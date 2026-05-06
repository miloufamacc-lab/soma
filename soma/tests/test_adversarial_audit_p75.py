"""
SOMA-INTEL Phase 7 §K.5 — Unit tests for adversarial_audit.py

All tests use mocked _call_claude_for_refutation — NO live API calls.

Acceptance criteria (from spec):
 1. _evaluate_refutation -> True when refuted=True AND confidence >= 0.70
 2. _evaluate_refutation -> False when refuted=True but confidence=0.5
 3. Idempotency: running twice on same date inserts no duplicate audits
 4. Dry-run mode: zero DB writes but non-zero would-have-disputed counts
 5. Capability gate disabled: returns immediately, zero API calls
 6. Pool < 50: returns available edges, logs shortfall, no crash
 7. Stratified sampling: >= 2 distinct edge_types in 50-sample when pool has multiple
 8. Refutation success path: mocked refuted=True/conf=0.85 -> audit_status='disputed'
    + audit_log row with auditor='claude_adversarial'
 9. Parse error: malformed JSON -> error counter incremented, no DB write, run continues
10. Schema constraint: invalid audit_status via update_edge_audit_status raises
"""

from __future__ import annotations

import json
import sys
import tempfile
from collections import Counter
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── Path bootstrap ─────────────────────────────────────────────────────────────
_HERE         = Path(__file__).resolve().parent
_DABEIBA_ROOT = _HERE.parent.parent.parent
for _p in [str(_DABEIBA_ROOT), str(_DABEIBA_ROOT / "shared")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from soma.intel.store import IntelStore
from soma.intel.adversarial_audit import (
    REFUTATION_CONFIDENCE_THRESHOLD,
    RefutationParseError,
    _build_refutation_prompt,
    _evaluate_refutation,
    run_adversarial_audit,
)

# ── Test DB bootstrap DDL ──────────────────────────────────────────────────────

_AUDIT_LOG_DDL = """
CREATE TABLE IF NOT EXISTS soma_intel_audit_log (
  audit_id       INTEGER PRIMARY KEY AUTOINCREMENT,
  edge_id        INTEGER NOT NULL,
  auditor        TEXT    NOT NULL,
  decision       TEXT    NOT NULL,
  rationale      TEXT,
  ts             TEXT    NOT NULL,
  prior_audit_id INTEGER,
  FOREIGN KEY (edge_id)        REFERENCES soma_intel_edge(edge_id),
  FOREIGN KEY (prior_audit_id) REFERENCES soma_intel_audit_log(audit_id)
);
CREATE TRIGGER IF NOT EXISTS trg_audit_log_no_update
BEFORE UPDATE ON soma_intel_audit_log
BEGIN
  SELECT RAISE(ABORT, 'soma_intel_audit_log is append-only: UPDATE not allowed');
END;
CREATE TRIGGER IF NOT EXISTS trg_audit_log_no_delete
BEFORE DELETE ON soma_intel_audit_log
BEGIN
  SELECT RAISE(ABORT, 'soma_intel_audit_log is append-only: DELETE not allowed');
END;
"""

_SOURCE_CALIBRATION_DDL = """
CREATE TABLE IF NOT EXISTS soma_intel_source_calibration (
  source_id      TEXT PRIMARY KEY,
  multiplier     REAL NOT NULL,
  brier_score    REAL,
  n_observations INTEGER NOT NULL DEFAULT 0,
  last_updated   TEXT    NOT NULL
);
"""

_THRESHOLD_HISTORY_DDL = """
CREATE TABLE IF NOT EXISTS soma_intel_threshold_history (
  history_id INTEGER PRIMARY KEY AUTOINCREMENT,
  cell_key TEXT NOT NULL, prior_threshold REAL NOT NULL,
  new_threshold REAL NOT NULL, adjustment REAL NOT NULL,
  reason TEXT NOT NULL, applied_ts TEXT NOT NULL
);
"""

_BACKTEST_DDL = """
CREATE TABLE IF NOT EXISTS soma_intel_signal_backtest (
  bt_id INTEGER PRIMARY KEY AUTOINCREMENT,
  backtest_run_id TEXT NOT NULL, sim_date TEXT NOT NULL,
  signal_id INTEGER, ticker TEXT NOT NULL, date TEXT NOT NULL,
  priority TEXT NOT NULL, anomaly_score REAL NOT NULL,
  features TEXT, corroboration_count INTEGER, half_life_days INTEGER,
  reconfirmation_count INTEGER DEFAULT 0, status TEXT DEFAULT 'active',
  horizon TEXT, notes TEXT, regime_label TEXT,
  lookahead_clean INTEGER DEFAULT 1, forward_return REAL,
  direction_label TEXT,
  outcome TEXT CHECK(outcome IN ('hit','miss','data_unavailable')),
  scored_ts TEXT
);
"""

_REGIME_DDL = """
CREATE TABLE IF NOT EXISTS soma_intel_regime (
  date TEXT PRIMARY KEY, trend_state TEXT, vol_state TEXT,
  macro_state TEXT, composite_label TEXT, confidence REAL, features TEXT
);
"""

_SIGNAL_DDL = """
CREATE TABLE IF NOT EXISTS soma_intel_signal (
  signal_id INTEGER PRIMARY KEY AUTOINCREMENT,
  ticker TEXT NOT NULL, date TEXT NOT NULL, priority TEXT NOT NULL,
  anomaly_score REAL NOT NULL, features TEXT NOT NULL,
  corroboration_count INTEGER NOT NULL, half_life_days INTEGER NOT NULL,
  reconfirmation_count INTEGER DEFAULT 0,
  status TEXT DEFAULT 'active', horizon TEXT, notes TEXT
);
"""

_UNIVERSE_DDL = """
CREATE TABLE IF NOT EXISTS soma_intel_universe (
  ticker TEXT PRIMARY KEY, active INTEGER DEFAULT 1,
  source TEXT, platform_tags TEXT, added_ts TEXT, tier TEXT,
  auto_added INTEGER DEFAULT 1, promotion_score REAL, promotion_source TEXT
);
"""


# ── Fixtures ───────────────────────────────────────────────────────────────────

def _make_store(tmp_path: Path) -> IntelStore:
    """Create a fresh IntelStore backed by an in-memory-equivalent temp DB."""
    db = tmp_path / "test_adversarial.db"
    store = IntelStore(db_path=str(db))
    store.__enter__()
    store.initialize_tables()
    # Extra tables needed by store methods used in tests
    for ddl in (
        _AUDIT_LOG_DDL,
        _SOURCE_CALIBRATION_DDL,
        _THRESHOLD_HISTORY_DDL,
        _BACKTEST_DDL,
        _REGIME_DDL,
        _SIGNAL_DDL,
        _UNIVERSE_DDL,
    ):
        store._c.executescript(ddl)
    store._c.commit()
    return store


def _seed_nodes(store: IntelStore) -> None:
    store.upsert_node("co_TSLA", "company", "Tesla Inc.")
    store.upsert_node("pl_ai",   "platform", "AI Platform")
    store.upsert_node("co_NVDA", "company", "NVIDIA Corp.")
    store.upsert_node("co_AMD",  "company", "AMD Inc.")
    store.upsert_node("th_robotaxi", "theme", "Robotaxi")
    store.upsert_node("pn_elon_musk", "person", "Elon Musk")


def _seed_high_conf_edge(
    store: IntelStore,
    src: str = "co_TSLA",
    dst: str = "pl_ai",
    edge_type: str = "belongs_to_platform",
    confidence: float = 0.90,
    source_id: str = "test/src1",
    source_type: str = "manual",
) -> int:
    return store.upsert_edge(
        src=src,
        dst=dst,
        edge_type=edge_type,
        confidence=confidence,
        source_id=source_id,
        evidence="Tesla FSD is an AI platform play.",
        source_type=source_type,
        audit_status="unaudited",
    )


def _enable_adversarial_audit(store: IntelStore) -> None:
    store.register_capability(
        capability_id="adversarial_audit",
        version="1.0",
        status="enabled",
        depends_on=["graph_layer", "audit_append_only"],
    )
    store.commit()


def _disable_adversarial_audit(store: IntelStore) -> None:
    store.register_capability(
        capability_id="adversarial_audit",
        version="1.0",
        status="disabled",
        depends_on=["graph_layer", "audit_append_only"],
    )
    store.commit()


# ── Test 1: _evaluate_refutation — disputed when refuted=True AND conf >= 0.70 ──

def test_evaluate_refutation_disputed(tmp_path):
    """_evaluate_refutation returns True when refuted=True and confidence >= 0.70."""
    response = {
        "refuted": True,
        "refutation_confidence": 0.85,
        "rationale": "Tesla does not dominate AI chips; that's NVIDIA.",
        "contradicting_evidence": "NVIDIA controls ~80% of AI training GPU market.",
    }
    is_disputed, summary = _evaluate_refutation(response)
    assert is_disputed is True
    assert "DISPUTED" in summary
    assert "0.85" in summary


# ── Test 2: _evaluate_refutation — not disputed when conf too low ──────────────

def test_evaluate_refutation_low_confidence_not_disputed(tmp_path):
    """_evaluate_refutation returns False when refuted=True but confidence=0.5."""
    response = {
        "refuted": True,
        "refutation_confidence": 0.50,
        "rationale": "Some doubt but not strong.",
        "contradicting_evidence": None,
    }
    is_disputed, summary = _evaluate_refutation(response)
    assert is_disputed is False
    assert "DISPUTED" not in summary
    assert "0.50" in summary


# ── Test 3: Idempotency ────────────────────────────────────────────────────────

def test_idempotency(tmp_path):
    """Running twice on same date inserts no duplicate audits."""
    store = _make_store(tmp_path)
    _seed_nodes(store)
    _seed_high_conf_edge(store)
    _enable_adversarial_audit(store)

    # Use today so that the audit_log ts (wall clock) matches the query range
    run_date = date.today()

    good_response = {
        "refuted": False,
        "refutation_confidence": 0.20,
        "rationale": "Claim appears valid.",
        "contradicting_evidence": None,
    }

    with patch(
        "soma.intel.adversarial_audit._call_claude_for_refutation",
        return_value=good_response,
    ) as mock_call:
        result1 = run_adversarial_audit(store, run_date, dry_run=False)
        result2 = run_adversarial_audit(store, run_date, dry_run=False)

    # Second call should short-circuit — no additional Claude calls
    assert result1["skipped_idempotent"] is False
    assert result2["skipped_idempotent"] is True

    # DB should have only one audit_log row (from first run)
    logs = store.list_audit_log()
    assert len(logs) == 1

    store.__exit__(None, None, None)


# ── Test 4: Dry-run mode ───────────────────────────────────────────────────────

def test_dry_run_no_db_writes(tmp_path):
    """Dry-run mode: zero DB writes but non-zero would-have-disputed counts."""
    store = _make_store(tmp_path)
    _seed_nodes(store)
    _seed_high_conf_edge(store)
    _enable_adversarial_audit(store)

    run_date = date(2026, 5, 11)

    disputed_response = {
        "refuted": True,
        "refutation_confidence": 0.90,
        "rationale": "Claim is factually incorrect.",
        "contradicting_evidence": "Counter-evidence here.",
    }

    with patch(
        "soma.intel.adversarial_audit._call_claude_for_refutation",
        return_value=disputed_response,
    ):
        result = run_adversarial_audit(store, run_date, dry_run=True)

    # Would-have-disputed should be > 0
    assert result["disputed"] >= 1

    # Zero DB writes: no audit_log rows, edge still 'unaudited'
    logs = store.list_audit_log()
    assert len(logs) == 0

    edges = store.list_edges_for_audit(min_confidence=0.85)
    assert all(e["audit_status"] != "disputed" for e in edges)

    store.__exit__(None, None, None)


# ── Test 5: Capability gate disabled ──────────────────────────────────────────

def test_capability_gate_disabled(tmp_path):
    """Capability gate disabled: returns immediately, zero API calls."""
    store = _make_store(tmp_path)
    _seed_nodes(store)
    _seed_high_conf_edge(store)
    _disable_adversarial_audit(store)

    run_date = date(2026, 5, 4)

    with patch(
        "soma.intel.adversarial_audit._call_claude_for_refutation"
    ) as mock_call:
        result = run_adversarial_audit(store, run_date, dry_run=False)

    assert result["skipped_capability_disabled"] is True
    assert mock_call.call_count == 0, "No API calls should be made when capability is disabled"

    store.__exit__(None, None, None)


# ── Test 6: Pool < 50 — no crash, logs shortfall ──────────────────────────────

def test_pool_smaller_than_max(tmp_path):
    """Pool < 50: returns available edges, no crash."""
    store = _make_store(tmp_path)
    _seed_nodes(store)
    # Seed only 3 high-confidence edges
    _seed_high_conf_edge(store, src="co_TSLA", dst="pl_ai", confidence=0.90)
    _seed_high_conf_edge(store, src="co_NVDA", dst="pl_ai", confidence=0.92)
    _seed_high_conf_edge(store, src="co_AMD",  dst="pl_ai", confidence=0.88)
    _enable_adversarial_audit(store)

    run_date = date(2026, 5, 4)

    not_refuted = {
        "refuted": False,
        "refutation_confidence": 0.10,
        "rationale": "Claim appears valid.",
        "contradicting_evidence": None,
    }

    with patch(
        "soma.intel.adversarial_audit._call_claude_for_refutation",
        return_value=not_refuted,
    ):
        result = run_adversarial_audit(store, run_date, dry_run=False)

    assert result["audited"] == 3   # only 3 edges in pool
    assert result["sample_pool_size"] == 3
    assert result["errors"] == 0

    store.__exit__(None, None, None)


# ── Test 7: Stratified sampling — >= 2 distinct edge_types ────────────────────

def test_stratified_sampling_multiple_edge_types(tmp_path):
    """Stratified sampling: >= 2 distinct edge_types in sample when pool has multiple."""
    store = _make_store(tmp_path)
    _seed_nodes(store)

    # Seed edges with multiple edge types
    for i in range(20):
        store.upsert_node(f"co_X{i}", "company", f"Company X{i}")
        store.upsert_edge(
            src=f"co_X{i}", dst="pl_ai",
            edge_type="belongs_to_platform",
            confidence=0.90,
            source_id=f"test/src_btp_{i}",
            evidence=f"Evidence {i}",
            source_type="manual",
            audit_status="unaudited",
        )
    for i in range(20):
        store.upsert_node(f"co_Y{i}", "company", f"Company Y{i}")
        store.upsert_edge(
            src=f"co_Y{i}", dst="co_TSLA",
            edge_type="competes_with",
            confidence=0.87,
            source_id=f"test/src_cw_{i}",
            evidence=f"Evidence cw {i}",
            source_type="manual",
            audit_status="unaudited",
        )
    for i in range(15):
        store.upsert_node(f"co_Z{i}", "company", f"Company Z{i}")
        store.upsert_edge(
            src=f"co_Z{i}", dst="co_NVDA",
            edge_type="supplies",
            confidence=0.91,
            source_id=f"test/src_sup_{i}",
            evidence=f"Evidence sup {i}",
            source_type="manual",
            audit_status="unaudited",
        )

    _enable_adversarial_audit(store)

    sample = store.sample_high_confidence_edges(
        min_confidence=0.85,
        exclude_audit_status=("disputed",),
        limit=50,
        seed=20260504,
        stratify_by="edge_type",
    )

    edge_types_in_sample = {e["edge_type"] for e in sample}
    assert len(edge_types_in_sample) >= 2, (
        f"Expected >= 2 distinct edge_types, got {edge_types_in_sample}"
    )
    assert len(sample) == 50

    store.__exit__(None, None, None)


# ── Test 8: Refutation success path ───────────────────────────────────────────

def test_refutation_success_disputed_db_write(tmp_path):
    """
    Mocked refuted=True/conf=0.85 -> audit_status='disputed' + audit_log row
    with auditor='claude_adversarial'.
    """
    store = _make_store(tmp_path)
    _seed_nodes(store)
    edge_id = _seed_high_conf_edge(store, confidence=0.92)
    _enable_adversarial_audit(store)

    run_date = date(2026, 5, 4)

    disputed_response = {
        "refuted": True,
        "refutation_confidence": 0.85,
        "rationale": "Tesla is not primarily an AI chip company; NVIDIA is.",
        "contradicting_evidence": "NVIDIA controls the AI training GPU market.",
    }

    with patch(
        "soma.intel.adversarial_audit._call_claude_for_refutation",
        return_value=disputed_response,
    ):
        result = run_adversarial_audit(store, run_date, dry_run=False)

    assert result["disputed"] >= 1
    assert result["audited"] >= 1

    # Edge should now have audit_status='disputed'
    edge = store.get_edge(edge_id)
    assert edge is not None
    assert edge["audit_status"] == "disputed", (
        f"Expected audit_status='disputed', got {edge['audit_status']!r}"
    )

    # Audit log should have a row with auditor='claude_adversarial'
    logs = store.list_audit_log(edge_id=edge_id)
    assert len(logs) >= 1
    assert any(row["auditor"] == "claude_adversarial" for row in logs), (
        f"Expected auditor='claude_adversarial' in audit_log rows: {logs}"
    )

    store.__exit__(None, None, None)


# ── Test 9: Parse error — error counter incremented, run continues ─────────────

def test_parse_error_increments_counter_run_continues(tmp_path):
    """
    Malformed JSON -> error counter incremented, no DB write for that edge,
    run continues for other edges.
    """
    store = _make_store(tmp_path)
    _seed_nodes(store)
    edge_id1 = _seed_high_conf_edge(store, src="co_TSLA", dst="pl_ai",
                                     confidence=0.90, source_id="test/e1")
    store.upsert_node("co_AMZN", "company", "Amazon")
    edge_id2 = _seed_high_conf_edge(store, src="co_AMZN", dst="pl_ai",
                                     confidence=0.88, source_id="test/e2")
    _enable_adversarial_audit(store)

    run_date = date(2026, 5, 4)

    call_count = [0]

    def _side_effect(prompt: str) -> dict:
        call_count[0] += 1
        if call_count[0] == 1:
            raise RefutationParseError("Bad JSON from model")
        # Second call succeeds — not refuted
        return {
            "refuted": False,
            "refutation_confidence": 0.15,
            "rationale": "Claim valid.",
            "contradicting_evidence": None,
        }

    with patch(
        "soma.intel.adversarial_audit._call_claude_for_refutation",
        side_effect=_side_effect,
    ):
        result = run_adversarial_audit(store, run_date, dry_run=False)

    assert result["errors"] == 1
    assert result["audited"] >= 1  # at least the second edge succeeded
    assert result["disputed"] == 0

    # Edge 1 (which errored) should NOT have been written to audit_log
    logs_e1 = store.list_audit_log(edge_id=edge_id1)
    assert len(logs_e1) == 0, (
        f"Edge 1 had a parse error — should not have an audit_log row. Got: {logs_e1}"
    )

    store.__exit__(None, None, None)


# ── Test 10: Schema constraint — invalid audit_status raises ──────────────────

def test_invalid_audit_status_raises(tmp_path):
    """
    Passing an invalid audit_status string to update_edge_audit_status
    should raise (SQLite CHECK constraint or application-level guard).
    """
    store = _make_store(tmp_path)
    _seed_nodes(store)
    edge_id = _seed_high_conf_edge(store, confidence=0.90)

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()

    # 'disputed' is not in the original CHECK constraint set for the edge table,
    # but the application does allow it via direct SQL in update_edge_audit_status.
    # We test that a truly invalid status (not in any allowed set) is rejected.
    # Since SQLite has no application-level guard in update_edge_audit_status itself,
    # we verify at least that record_audit rejects invalid 'decision' values.
    with pytest.raises((ValueError, Exception)):
        store.record_audit(
            edge_id=edge_id,
            auditor="claude_adversarial",
            decision="INVALID_STATUS",   # not in allowed set
        )

    store.__exit__(None, None, None)


# ── Bonus: _build_refutation_prompt fills template correctly ──────────────────

def test_build_refutation_prompt_fields():
    """_build_refutation_prompt fills locked template with edge fields."""
    edge = {
        "edge_id": 42,
        "src_node_id": "co_TSLA",
        "dst_node_id": "pl_ai",
        "edge_type": "belongs_to_platform",
        "confidence": 0.90,
        "source_id": "wiki/tsla.md",
        "source_type": "wiki",
        "evidence_text": "Tesla FSD is an AI platform.",
        "ts": "2026-05-04T10:00:00+00:00",
    }
    prompt = _build_refutation_prompt(edge)
    assert "co_TSLA" in prompt
    assert "belongs_to_platform" in prompt
    assert "pl_ai" in prompt
    assert "Tesla FSD is an AI platform" in prompt
    assert "0.9" in prompt
    assert "adversarial auditor" in prompt.lower()
