"""
SOMA-INTEL Phase 7 §K.5S — Unit tests for the scheduled-task refactor.

Tests cover --mode sample and --mode ingest paths in adversarial_audit.py.
All DB writes use in-memory temp DBs. No live API calls. No live DB writes.

Acceptance criteria (K5S.4):
 1. test_mode_sample_writes_json               — file shape + locked schema
 2. test_mode_sample_idempotent                — second run exits code 2 (returns skipped_file_exists)
 3. test_mode_sample_capability_disabled       — exits cleanly, writes nothing
 4. test_mode_sample_filter_excludes_provenance — no mentioned_in / regime_was / succeeded_by in JSON
 5. test_mode_ingest_run_id_mismatch_rejects   — mismatched run_id raises ValueError
 6. test_mode_ingest_unknown_edge_id_rejects   — unknown edge_id in decisions raises ValueError
 7. test_mode_ingest_size_mismatch_rejects     — N edges, N-1 decisions raises ValueError
 8. test_mode_ingest_dispute_threshold         — conf=0.65 NOT disputed; conf=0.71 IS; refuted=False NOT
 9. test_mode_ingest_idempotent               — second ingest on same file skips without --reingest
10. test_mode_ingest_writes_audit_log_with_correct_auditor — auditor='claude_scheduled' not 'claude_adversarial'
11. test_mode_ingest_capability_disabled       — exits clean, writes nothing to DB
"""

from __future__ import annotations

import json
import sys
import tempfile
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

# ── Path bootstrap ─────────────────────────────────────────────────────────────
_HERE         = Path(__file__).resolve().parent
_DABEIBA_ROOT = _HERE.parent.parent.parent
for _p in [str(_DABEIBA_ROOT), str(_DABEIBA_ROOT / "shared")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from soma.intel.store import IntelStore
from soma.intel.adversarial_audit import (
    AUDIT_STAGING_DIR,
    MAX_AUDITS_PER_RUN,
    PROVENANCE_EDGE_TYPES,
    REFUTATION_CONFIDENCE_THRESHOLD,
    _AUDITOR_SCHEDULED,
    _run_ingest_mode,
    _run_sample_mode,
)


# ── Additional DDL needed by tests ─────────────────────────────────────────────

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

_EXTRA_DDL = """
CREATE TABLE IF NOT EXISTS soma_intel_source_calibration (
  source_id TEXT PRIMARY KEY, multiplier REAL NOT NULL,
  brier_score REAL, n_observations INTEGER NOT NULL DEFAULT 0, last_updated TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS soma_intel_threshold_history (
  history_id INTEGER PRIMARY KEY AUTOINCREMENT,
  cell_key TEXT NOT NULL, prior_threshold REAL NOT NULL, new_threshold REAL NOT NULL,
  adjustment REAL NOT NULL, reason TEXT NOT NULL, applied_ts TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS soma_intel_signal_backtest (
  bt_id INTEGER PRIMARY KEY AUTOINCREMENT, backtest_run_id TEXT NOT NULL,
  sim_date TEXT NOT NULL, signal_id INTEGER, ticker TEXT NOT NULL, date TEXT NOT NULL,
  priority TEXT NOT NULL, anomaly_score REAL NOT NULL, features TEXT,
  corroboration_count INTEGER, half_life_days INTEGER,
  reconfirmation_count INTEGER DEFAULT 0, status TEXT DEFAULT 'active',
  horizon TEXT, notes TEXT, regime_label TEXT, lookahead_clean INTEGER DEFAULT 1,
  forward_return REAL, direction_label TEXT,
  outcome TEXT CHECK(outcome IN ('hit','miss','data_unavailable')), scored_ts TEXT
);
CREATE TABLE IF NOT EXISTS soma_intel_regime (
  date TEXT PRIMARY KEY, trend_state TEXT, vol_state TEXT,
  macro_state TEXT, composite_label TEXT, confidence REAL, features TEXT
);
CREATE TABLE IF NOT EXISTS soma_intel_signal (
  signal_id INTEGER PRIMARY KEY AUTOINCREMENT, ticker TEXT NOT NULL, date TEXT NOT NULL,
  priority TEXT NOT NULL, anomaly_score REAL NOT NULL, features TEXT NOT NULL,
  corroboration_count INTEGER NOT NULL, half_life_days INTEGER NOT NULL,
  reconfirmation_count INTEGER DEFAULT 0, status TEXT DEFAULT 'active', horizon TEXT, notes TEXT
);
CREATE TABLE IF NOT EXISTS soma_intel_universe (
  ticker TEXT PRIMARY KEY, active INTEGER DEFAULT 1, source TEXT, platform_tags TEXT,
  added_ts TEXT, tier TEXT, auto_added INTEGER DEFAULT 1, promotion_score REAL, promotion_source TEXT
);
"""


# ── Test helpers ───────────────────────────────────────────────────────────────

def _make_store(tmp_path: Path) -> IntelStore:
    """Return an open IntelStore backed by a fresh temp DB with all tables."""
    db = tmp_path / "test_scheduled.db"
    store = IntelStore(db_path=str(db))
    store.__enter__()
    store.initialize_tables()
    for ddl in (_AUDIT_LOG_DDL, _EXTRA_DDL):
        store._c.executescript(ddl)
    store._c.commit()
    return store


def _seed_nodes(store: IntelStore) -> None:
    store.upsert_node("co_TSLA", "company",  "Tesla Inc.")
    store.upsert_node("co_NVDA", "company",  "NVIDIA Corp.")
    store.upsert_node("pl_ai",   "platform", "AI Platform")
    store.upsert_node("cn_tech", "concept",  "Technology")
    store.upsert_node("cn_auto", "concept",  "Automotive")


def _seed_edge(
    store: IntelStore,
    src: str = "co_TSLA",
    dst: str = "pl_ai",
    edge_type: str = "belongs_to_platform",
    confidence: float = 0.90,
) -> int:
    return store.upsert_edge(
        src=src, dst=dst, edge_type=edge_type,
        confidence=confidence,
        source_id=f"test/{src}_{dst}",
        evidence=f"Evidence for {src} -> {dst}",
        source_type="oracle_titan",
        audit_status="unaudited",
    )


def _enable_cap(store: IntelStore) -> None:
    store.register_capability(
        capability_id="adversarial_audit",
        version="1.0",
        status="enabled",
        depends_on=["graph_layer", "audit_append_only"],
    )
    store.commit()


def _disable_cap(store: IntelStore) -> None:
    # Two-step: register (INSERT OR IGNORE — no-op if exists) then set status.
    # Handles both the "never registered" case and the "already enabled" case.
    try:
        store.set_capability_status("adversarial_audit", "disabled", notes="test teardown")
    except ValueError:
        # Capability not yet registered — register it as disabled.
        store.register_capability(
            capability_id="adversarial_audit",
            version="1.0",
            status="disabled",
            depends_on=["graph_layer", "audit_append_only"],
        )
    store.commit()


def _make_decisions_json(
    edges_file: Path,
    decisions_dir: Path,
    refuted: bool = False,
    refutation_confidence: float = 0.0,
) -> Path:
    """Build a synthetic decisions file matching the edges file. All edges share the same verdict."""
    with open(edges_file) as fh:
        edges_doc = json.load(fh)

    date_str   = edges_doc["run_date"]
    decisions  = [
        {
            "edge_id":               e["edge_id"],
            "refuted":               refuted,
            "refutation_confidence": refutation_confidence,
            "rationale":             "Synthetic test verdict.",
            "contradicting_evidence": None,
        }
        for e in edges_doc["edges"]
    ]
    payload = {
        "run_id":     edges_doc["run_id"],
        "run_date":   date_str,
        "decided_ts": datetime.now(timezone.utc).isoformat(),
        "auditor":    "claude_scheduled",
        "decisions":  decisions,
    }
    out = decisions_dir / f"audit_decisions_{date_str}.json"
    with open(out, "w") as fh:
        json.dump(payload, fh, indent=2)
    return out


# ══════════════════════════════════════════════════════════════════════════════
# Test 1 — Sample mode writes correct JSON schema
# ══════════════════════════════════════════════════════════════════════════════

def test_mode_sample_writes_json(tmp_path):
    """_run_sample_mode writes audit_edges_<date>.json with locked schema."""
    store = _make_store(tmp_path)
    _seed_nodes(store)
    _seed_edge(store, edge_type="is_a", src="co_TSLA", dst="cn_tech", confidence=0.91)
    _enable_cap(store)

    staging = tmp_path / "staging"
    run_date = date(2026, 5, 10)
    out_path = staging / f"audit_edges_{run_date.isoformat()}.json"

    result = _run_sample_mode(
        store, run_date,
        output=out_path,
        force=False,
    )

    assert result["skipped_capability_disabled"] is False
    assert result["skipped_file_exists"] is False
    assert result["edges_written"] >= 1
    assert out_path.exists()

    with open(out_path) as fh:
        doc = json.load(fh)

    # Top-level required fields
    assert "run_id"           in doc
    assert "run_date"         in doc
    assert "generated_ts"     in doc
    assert "sample_pool_size" in doc
    assert "edges"            in doc
    assert doc["run_date"]    == run_date.isoformat()

    # Per-edge required fields
    for edge in doc["edges"]:
        assert "edge_id"           in edge
        assert "src_node_id"       in edge
        assert "edge_type"         in edge
        assert "dst_node_id"       in edge
        assert "confidence"        in edge
        assert "ts"                in edge
        assert "source_id"         in edge
        assert "source_type"       in edge
        assert "evidence_text"     in edge
        assert "refutation_prompt" in edge
        # refutation_prompt must contain the system-level instruction
        assert "adversarial auditor" in edge["refutation_prompt"].lower()

    store.__exit__(None, None, None)


# ══════════════════════════════════════════════════════════════════════════════
# Test 2 — Sample mode is idempotent (exit code 2 on second run)
# ══════════════════════════════════════════════════════════════════════════════

def test_mode_sample_idempotent(tmp_path):
    """Second sample run without --overwrite returns skipped_file_exists=True."""
    store = _make_store(tmp_path)
    _seed_nodes(store)
    _seed_edge(store, edge_type="is_a", src="co_TSLA", dst="cn_tech", confidence=0.91)
    _enable_cap(store)

    staging  = tmp_path / "staging"
    run_date = date(2026, 5, 10)
    out_path = staging / f"audit_edges_{run_date.isoformat()}.json"

    # First run — should succeed
    r1 = _run_sample_mode(store, run_date, output=out_path, force=False)
    assert r1["edges_written"] >= 1
    assert out_path.exists()

    # Second run — must report file exists (no overwrite)
    r2 = _run_sample_mode(store, run_date, output=out_path, overwrite=False, force=False)
    assert r2["skipped_file_exists"] is True
    assert r2["edges_written"] == 0

    store.__exit__(None, None, None)


# ══════════════════════════════════════════════════════════════════════════════
# Test 3 — Sample mode respects capability gate
# ══════════════════════════════════════════════════════════════════════════════

def test_mode_sample_capability_disabled(tmp_path):
    """Capability disabled: _run_sample_mode returns immediately, writes no file."""
    store = _make_store(tmp_path)
    _seed_nodes(store)
    _seed_edge(store, edge_type="is_a", src="co_TSLA", dst="cn_tech", confidence=0.91)
    _disable_cap(store)

    staging  = tmp_path / "staging"
    run_date = date(2026, 5, 10)
    out_path = staging / f"audit_edges_{run_date.isoformat()}.json"

    result = _run_sample_mode(
        store, run_date,
        output=out_path,
        force=False,   # must not bypass gate
    )

    assert result["skipped_capability_disabled"] is True
    assert not out_path.exists(), "No file should be written when capability is disabled"

    store.__exit__(None, None, None)


# ══════════════════════════════════════════════════════════════════════════════
# Test 4 — Sample mode excludes provenance edge types
# ══════════════════════════════════════════════════════════════════════════════

def test_mode_sample_filter_excludes_provenance(tmp_path):
    """No mentioned_in / regime_was / succeeded_by edges appear in the output JSON."""
    store = _make_store(tmp_path)
    _seed_nodes(store)

    # Insert provenance edges with high confidence — should NOT appear in output
    store.upsert_node("wiki_tsla", "article", "TSLA Valuation Article")
    store.upsert_edge(
        src="co_TSLA", dst="wiki_tsla",
        edge_type="mentioned_in",
        confidence=0.97,
        source_id="wiki/tsla.md",
        evidence="co_TSLA mentioned in wiki",
        source_type="wiki",
        audit_status="unaudited",
    )
    # Insert a regime_was edge if schema allows (just skip if not in VALID_EDGE_TYPES)
    try:
        store.upsert_node("rg_bull", "regime", "Bull Regime")
        store.upsert_edge(
            src="rg_bull", dst="rg_bull",
            edge_type="regime_was",
            confidence=0.98,
            source_id="oracle/regime",
            evidence="regime_was label",
            source_type="derived",
            audit_status="unaudited",
        )
    except ValueError:
        pass  # regime_was may not have valid src/dst nodes in test schema

    # Insert a non-provenance edge — SHOULD appear
    _seed_edge(store, edge_type="is_a", src="co_TSLA", dst="cn_tech", confidence=0.90)
    _enable_cap(store)

    staging  = tmp_path / "staging"
    run_date = date(2026, 5, 10)
    out_path = staging / f"audit_edges_{run_date.isoformat()}.json"

    _run_sample_mode(store, run_date, output=out_path, force=False)

    with open(out_path) as fh:
        doc = json.load(fh)

    edge_types_in_output = {e["edge_type"] for e in doc["edges"]}
    for provenance_type in PROVENANCE_EDGE_TYPES:
        assert provenance_type not in edge_types_in_output, (
            f"Provenance edge type {provenance_type!r} must be excluded from sample output. "
            f"Found edge_types: {edge_types_in_output}"
        )
    assert "is_a" in edge_types_in_output

    store.__exit__(None, None, None)


# ══════════════════════════════════════════════════════════════════════════════
# Test 5 — Ingest: run_id mismatch rejects
# ══════════════════════════════════════════════════════════════════════════════

def test_mode_ingest_run_id_mismatch_rejects(tmp_path):
    """Decisions file with wrong run_id raises ValueError — will not ingest."""
    store = _make_store(tmp_path)
    _seed_nodes(store)
    _seed_edge(store, edge_type="is_a", src="co_TSLA", dst="cn_tech", confidence=0.91)
    _enable_cap(store)

    staging  = tmp_path / "staging"
    run_date = date(2026, 5, 10)
    out_path = staging / f"audit_edges_{run_date.isoformat()}.json"

    _run_sample_mode(store, run_date, output=out_path, force=False)

    with open(out_path) as fh:
        edges_doc = json.load(fh)

    # Build decisions with a DIFFERENT run_id
    bad_decisions = {
        "run_id":     "completely-wrong-run-id-that-does-not-match",
        "run_date":   run_date.isoformat(),
        "decided_ts": datetime.now(timezone.utc).isoformat(),
        "auditor":    "claude_scheduled",
        "decisions":  [
            {
                "edge_id":               e["edge_id"],
                "refuted":               False,
                "refutation_confidence": 0.0,
                "rationale":             "Test.",
                "contradicting_evidence": None,
            }
            for e in edges_doc["edges"]
        ],
    }
    dec_path = staging / f"audit_decisions_{run_date.isoformat()}.json"
    with open(dec_path, "w") as fh:
        json.dump(bad_decisions, fh)

    with pytest.raises(ValueError, match="run_id mismatch"):
        _run_ingest_mode(
            store, dec_path,
            dry_run=True, force=False,
        )

    store.__exit__(None, None, None)


# ══════════════════════════════════════════════════════════════════════════════
# Test 6 — Ingest: unknown edge_id rejects
# ══════════════════════════════════════════════════════════════════════════════

def test_mode_ingest_unknown_edge_id_rejects(tmp_path):
    """A decision that references an edge_id not in the edges file raises ValueError."""
    store = _make_store(tmp_path)
    _seed_nodes(store)
    _seed_edge(store, edge_type="is_a", src="co_TSLA", dst="cn_tech", confidence=0.91)
    _enable_cap(store)

    staging  = tmp_path / "staging"
    run_date = date(2026, 5, 10)
    out_path = staging / f"audit_edges_{run_date.isoformat()}.json"

    _run_sample_mode(store, run_date, output=out_path, force=False)

    with open(out_path) as fh:
        edges_doc = json.load(fh)

    # Build decisions with a bogus edge_id injected
    decisions = [
        {
            "edge_id":               e["edge_id"],
            "refuted":               False,
            "refutation_confidence": 0.0,
            "rationale":             "Test.",
            "contradicting_evidence": None,
        }
        for e in edges_doc["edges"]
    ]
    # Replace last decision's edge_id with something that doesn't exist
    decisions[-1]["edge_id"] = 999999999

    bad_doc = {
        "run_id":     edges_doc["run_id"],
        "run_date":   run_date.isoformat(),
        "decided_ts": datetime.now(timezone.utc).isoformat(),
        "auditor":    "claude_scheduled",
        "decisions":  decisions,
    }
    dec_path = staging / f"audit_decisions_{run_date.isoformat()}.json"
    with open(dec_path, "w") as fh:
        json.dump(bad_doc, fh)

    with pytest.raises(ValueError, match="Unknown edge_id"):
        _run_ingest_mode(store, dec_path, dry_run=True, force=False)

    store.__exit__(None, None, None)


# ══════════════════════════════════════════════════════════════════════════════
# Test 7 — Ingest: size mismatch rejects
# ══════════════════════════════════════════════════════════════════════════════

def test_mode_ingest_size_mismatch_rejects(tmp_path):
    """If edges array has N items and decisions has N-1, ingest raises ValueError."""
    store = _make_store(tmp_path)
    _seed_nodes(store)
    # Seed two edges
    _seed_edge(store, edge_type="is_a",             src="co_TSLA", dst="cn_tech", confidence=0.91)
    _seed_edge(store, edge_type="belongs_to_platform", src="co_NVDA", dst="pl_ai", confidence=0.90)
    _enable_cap(store)

    staging  = tmp_path / "staging"
    run_date = date(2026, 5, 10)
    out_path = staging / f"audit_edges_{run_date.isoformat()}.json"

    _run_sample_mode(store, run_date, output=out_path, force=False)

    with open(out_path) as fh:
        edges_doc = json.load(fh)

    assert len(edges_doc["edges"]) >= 2, (
        "Need at least 2 edges to test size mismatch — check seed data."
    )

    # Build decisions with one fewer entry than edges
    decisions = [
        {
            "edge_id":               e["edge_id"],
            "refuted":               False,
            "refutation_confidence": 0.0,
            "rationale":             "Test.",
            "contradicting_evidence": None,
        }
        for e in edges_doc["edges"][:-1]   # drop the last one
    ]
    bad_doc = {
        "run_id":     edges_doc["run_id"],
        "run_date":   run_date.isoformat(),
        "decided_ts": datetime.now(timezone.utc).isoformat(),
        "auditor":    "claude_scheduled",
        "decisions":  decisions,
    }
    dec_path = staging / f"audit_decisions_{run_date.isoformat()}.json"
    with open(dec_path, "w") as fh:
        json.dump(bad_doc, fh)

    with pytest.raises(ValueError, match="Size mismatch"):
        _run_ingest_mode(store, dec_path, dry_run=True, force=False)

    store.__exit__(None, None, None)


# ══════════════════════════════════════════════════════════════════════════════
# Test 8 — Ingest: dispute threshold applied correctly
# ══════════════════════════════════════════════════════════════════════════════

def test_mode_ingest_dispute_threshold(tmp_path):
    """
    Threshold rule (locked):
      refuted=True  + conf=0.65  -> NOT disputed (below 0.70 gate)
      refuted=True  + conf=0.71  -> disputed
      refuted=False + conf=0.99  -> NOT disputed (refuted must be True)
    """
    store = _make_store(tmp_path)
    _seed_nodes(store)
    e1 = _seed_edge(store, edge_type="is_a",             src="co_TSLA", dst="cn_tech", confidence=0.91)
    e2 = _seed_edge(store, edge_type="belongs_to_platform", src="co_NVDA", dst="pl_ai", confidence=0.90)
    e3 = _seed_edge(store, edge_type="is_a",             src="co_TSLA", dst="cn_auto", confidence=0.88)
    _enable_cap(store)

    staging  = tmp_path / "staging"
    run_date = date(2026, 5, 10)
    out_path = staging / f"audit_edges_{run_date.isoformat()}.json"

    _run_sample_mode(store, run_date, output=out_path, force=False)

    with open(out_path) as fh:
        edges_doc = json.load(fh)

    # Map edge_id to verdict we want to assign
    sampled_ids = {e["edge_id"] for e in edges_doc["edges"]}

    def _verdict(edge_id):
        if edge_id == e1:
            return {"refuted": True,  "refutation_confidence": 0.65}  # NOT disputed
        elif edge_id == e2:
            return {"refuted": True,  "refutation_confidence": 0.71}  # disputed
        elif edge_id == e3:
            return {"refuted": False, "refutation_confidence": 0.99}  # NOT disputed
        else:
            return {"refuted": False, "refutation_confidence": 0.0}

    decisions = [
        {
            "edge_id":               e["edge_id"],
            **_verdict(e["edge_id"]),
            "rationale":             "Test threshold case.",
            "contradicting_evidence": None,
        }
        for e in edges_doc["edges"]
    ]
    doc = {
        "run_id":     edges_doc["run_id"],
        "run_date":   run_date.isoformat(),
        "decided_ts": datetime.now(timezone.utc).isoformat(),
        "auditor":    "claude_scheduled",
        "decisions":  decisions,
    }
    dec_path = staging / f"audit_decisions_{run_date.isoformat()}.json"
    with open(dec_path, "w") as fh:
        json.dump(doc, fh)

    # Run with dry_run=False so DB writes happen
    result = _run_ingest_mode(store, dec_path, dry_run=False, force=False)
    assert result["skipped_capability_disabled"] is False
    assert result["errors"] == 0

    # e2 should be disputed; e1 and e3 should not
    if e2 in sampled_ids:
        edge2 = store.get_edge(e2)
        assert edge2["audit_status"] == "disputed", (
            f"edge {e2} with refuted=True, conf=0.71 should be 'disputed', "
            f"got {edge2['audit_status']!r}"
        )

    if e1 in sampled_ids:
        edge1 = store.get_edge(e1)
        assert edge1["audit_status"] != "disputed", (
            f"edge {e1} with conf=0.65 must NOT be disputed (below 0.70 gate)"
        )

    if e3 in sampled_ids:
        edge3 = store.get_edge(e3)
        assert edge3["audit_status"] != "disputed", (
            f"edge {e3} with refuted=False must NOT be disputed"
        )

    store.__exit__(None, None, None)


# ══════════════════════════════════════════════════════════════════════════════
# Test 9 — Ingest is idempotent (second run rejected without --reingest)
# ══════════════════════════════════════════════════════════════════════════════

def test_mode_ingest_idempotent(tmp_path):
    """Second _run_ingest_mode on the same decisions file skips without --reingest."""
    store = _make_store(tmp_path)
    _seed_nodes(store)
    _seed_edge(store, edge_type="is_a", src="co_TSLA", dst="cn_tech", confidence=0.91)
    _enable_cap(store)

    staging  = tmp_path / "staging"
    run_date = date.today()   # use today so audit_log date filter hits
    out_path = staging / f"audit_edges_{run_date.isoformat()}.json"

    _run_sample_mode(store, run_date, output=out_path, force=False)

    dec_path = _make_decisions_json(out_path, staging, refuted=False)

    # First ingest
    r1 = _run_ingest_mode(store, dec_path, dry_run=False, force=False)
    assert r1["skipped_already_ingested"] is False

    # Second ingest — should be skipped
    r2 = _run_ingest_mode(store, dec_path, dry_run=False, reingest=False, force=False)
    assert r2["skipped_already_ingested"] is True

    # Audit log should have only the rows from the first run (no duplicates)
    logs = store.get_audits_by_date_and_auditor(run_date, "claude_scheduled")
    first_run_count = r1["valid"]
    assert len(logs) == first_run_count, (
        f"Expected {first_run_count} audit_log rows after first run; "
        f"found {len(logs)} (second run should not have added any)."
    )

    store.__exit__(None, None, None)


# ══════════════════════════════════════════════════════════════════════════════
# Test 10 — Ingest writes audit_log with auditor='claude_scheduled'
# ══════════════════════════════════════════════════════════════════════════════

def test_mode_ingest_writes_audit_log_with_correct_auditor(tmp_path):
    """
    After ingest, audit_log rows use auditor='claude_scheduled', not 'claude_adversarial'.
    The two auditor strings must never be interchanged — they track different execution paths.
    """
    store = _make_store(tmp_path)
    _seed_nodes(store)
    e1 = _seed_edge(store, edge_type="is_a", src="co_TSLA", dst="cn_tech", confidence=0.91)
    _enable_cap(store)

    staging  = tmp_path / "staging"
    run_date = date.today()
    out_path = staging / f"audit_edges_{run_date.isoformat()}.json"

    _run_sample_mode(store, run_date, output=out_path, force=False)

    dec_path = _make_decisions_json(out_path, staging, refuted=False)

    _run_ingest_mode(store, dec_path, dry_run=False, force=False)

    logs = store.list_audit_log()
    assert len(logs) >= 1

    auditors_used = {row["auditor"] for row in logs}
    assert "claude_scheduled" in auditors_used, (
        f"Expected auditor='claude_scheduled' in audit_log. Got: {auditors_used}"
    )
    assert "claude_adversarial" not in auditors_used, (
        "Ingest mode must NEVER write 'claude_adversarial' to audit_log — "
        "that auditor is reserved for the legacy API path."
    )

    store.__exit__(None, None, None)


# ══════════════════════════════════════════════════════════════════════════════
# Test 11 — Ingest: capability disabled exits clean, writes nothing
# ══════════════════════════════════════════════════════════════════════════════

def test_mode_ingest_capability_disabled(tmp_path):
    """With capability disabled, _run_ingest_mode returns immediately — no DB writes."""
    store = _make_store(tmp_path)
    _seed_nodes(store)
    _seed_edge(store, edge_type="is_a", src="co_TSLA", dst="cn_tech", confidence=0.91)

    # Enable temporarily just to sample, then disable before ingest
    _enable_cap(store)
    staging  = tmp_path / "staging"
    run_date = date.today()
    out_path = staging / f"audit_edges_{run_date.isoformat()}.json"

    _run_sample_mode(store, run_date, output=out_path, force=True)
    dec_path = _make_decisions_json(out_path, staging, refuted=True, refutation_confidence=0.9)

    # Now disable the capability
    _disable_cap(store)

    result = _run_ingest_mode(
        store, dec_path,
        dry_run=False,
        force=False,   # must not bypass gate
    )

    assert result["skipped_capability_disabled"] is True

    # No audit_log rows, no disputed edges
    logs = store.list_audit_log()
    assert len(logs) == 0

    all_edges = store.list_edges_for_audit(min_confidence=0.0)
    assert all(e["audit_status"] != "disputed" for e in all_edges)

    store.__exit__(None, None, None)
