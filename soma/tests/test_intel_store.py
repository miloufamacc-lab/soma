"""
SOMA-INTEL Step 0.0 — Unit tests for IntelStore repository abstraction.

Tests cover all 8 locked interface methods (§H.1):
  upsert_node, upsert_edge, get_node, neighbors,
  query_fts, time_travel, audit_pending, audit_record

All tests use an isolated temp DB (SOMA_DB_PATH env var override).
No production DB is touched.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

# ── Path setup ────────────────────────────────────────────────────────────────
_DABEIBA_ROOT = Path(__file__).resolve().parent.parent.parent.parent
for _p in [str(_DABEIBA_ROOT), str(_DABEIBA_ROOT / "shared")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from soma.intel.store import IntelStore, Node, Edge, VALID_EDGE_TYPES


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def store(tmp_path):
    """Fresh IntelStore backed by a temp DB. Tables initialized before yield."""
    db_path = str(tmp_path / "soma_intel_test.db")
    with IntelStore(db_path=db_path) as s:
        s.initialize_tables()
        yield s


def _node(store: IntelStore, node_id="co_TSLA", node_type="company", name="Tesla Inc."):
    """Helper: insert a node and return the node_id."""
    store.upsert_node(node_id, node_type, name)
    return node_id


def _edge(
    store: IntelStore,
    src="co_TSLA",
    dst="pl_ai",
    edge_type="belongs_to_platform",
    confidence=0.85,
) -> int:
    """Helper: insert a minimal edge and return edge_id."""
    return store.upsert_edge(
        src, dst, edge_type,
        confidence=confidence,
        source_id="test/fixture",
        evidence="Test evidence.",
    )


# ════════════════════════════════════════════════════════════════════════════
# Context manager guard
# ════════════════════════════════════════════════════════════════════════════

def test_requires_context_manager(tmp_path):
    """IntelStore raises RuntimeError if used without `with` block."""
    s = IntelStore(db_path=str(tmp_path / "bare.db"))
    with pytest.raises(RuntimeError, match="context manager"):
        s.get_node("co_TSLA")


# ════════════════════════════════════════════════════════════════════════════
# upsert_node
# ════════════════════════════════════════════════════════════════════════════

class TestUpsertNode:
    def test_insert_basic(self, store):
        store.upsert_node("co_PLTR", "company", "Palantir Technologies")
        node = store.get_node("co_PLTR")
        assert node is not None
        assert node.node_id == "co_PLTR"
        assert node.name == "Palantir Technologies"
        assert node.node_type == "company"

    def test_upsert_preserves_created_ts(self, store):
        store.upsert_node("co_NVDA", "company", "Nvidia")
        first = store.get_node("co_NVDA")
        store.upsert_node("co_NVDA", "company", "NVIDIA Corporation")
        second = store.get_node("co_NVDA")
        assert second is not None and first is not None
        assert second.created_ts == first.created_ts, "created_ts must not change on update"
        assert second.name == "NVIDIA Corporation", "name must update"
        assert second.last_seen_ts >= first.last_seen_ts, "last_seen_ts must advance"

    def test_upsert_idempotent_same_data(self, store):
        for _ in range(3):
            store.upsert_node("co_META", "company", "Meta Platforms")
        node = store.get_node("co_META")
        assert node is not None

    def test_aliases_and_metadata_stored(self, store):
        store.upsert_node(
            "co_MSTR", "company", "Strategy Inc.",
            aliases=["MICROSTRATEGY", "MSTR"],
            metadata={"sector": "software", "platform_tags": ["pl_blockchain"]},
        )
        node = store.get_node("co_MSTR")
        assert node is not None
        assert "MSTR" in node.aliases
        assert node.metadata["sector"] == "software"

    def test_node_types(self, store):
        """Verify all 9 node types from §A.1 can be inserted."""
        types = [
            ("co_TSLA", "company"), ("sec_energy", "sector"), ("th_robotaxi", "theme"),
            ("pl_ai", "platform"), ("pn_elon_musk", "person"), ("rg_2024q1", "regime"),
            ("ev_2024_election", "event"), ("etf_ARKK", "etf"), ("cn_wrights_law", "concept"),
        ]
        for node_id, node_type in types:
            store.upsert_node(node_id, node_type, f"Test {node_type}")
        for node_id, node_type in types:
            n = store.get_node(node_id)
            assert n is not None and n.node_type == node_type


# ════════════════════════════════════════════════════════════════════════════
# upsert_edge
# ════════════════════════════════════════════════════════════════════════════

class TestUpsertEdge:
    def test_returns_edge_id(self, store):
        _node(store, "co_TSLA")
        _node(store, "pl_ai", "platform", "AI Platform")
        edge_id = _edge(store)
        assert isinstance(edge_id, int)
        assert edge_id > 0

    def test_invalid_edge_type_raises(self, store):
        _node(store, "co_TSLA")
        _node(store, "pl_ai", "platform", "AI Platform")
        with pytest.raises(ValueError, match="Unknown edge_type"):
            store.upsert_edge(
                "co_TSLA", "pl_ai", "INVALID_TYPE",
                confidence=0.8, source_id="test", evidence=None,
            )

    def test_confidence_out_of_range_raises(self, store):
        _node(store, "co_TSLA")
        _node(store, "pl_ai", "platform", "AI")
        with pytest.raises(ValueError, match="confidence"):
            store.upsert_edge(
                "co_TSLA", "pl_ai", "belongs_to_platform",
                confidence=1.5, source_id="test", evidence=None,
            )

    def test_all_valid_edge_types(self, store):
        """Every locked edge type in §A.2 must insert without error."""
        _node(store, "src_node", "company", "Source")
        _node(store, "dst_node", "company", "Dest")
        for et in VALID_EDGE_TYPES:
            eid = store.upsert_edge(
                "src_node", "dst_node", et,
                confidence=0.7, source_id="test", evidence="fixture",
            )
            assert eid > 0

    def test_default_half_life_applied(self, store):
        """half_life_days should default to §A.2 value for the edge type."""
        _node(store, "co_TSLA")
        _node(store, "pl_ai", "platform", "AI")
        eid = _edge(store, edge_type="expresses_sentiment")
        edges = store.neighbors("co_TSLA", edge_types=["expresses_sentiment"])
        assert edges[0].half_life_days == 14, "expresses_sentiment default = 14d"

    def test_metadata_kwargs(self, store):
        _node(store, "co_TSLA")
        _node(store, "pl_ai", "platform", "AI")
        eid = store.upsert_edge(
            "co_TSLA", "pl_ai", "belongs_to_platform",
            confidence=0.9, source_id="test", evidence="Evidence.",
            weight=0.75, source_type="wiki", half_life_days=200,
        )
        edges = store.neighbors("co_TSLA")
        e = next(x for x in edges if x.edge_id == eid)
        assert e.weight == 0.75
        assert e.source_type == "wiki"
        assert e.half_life_days == 200


# ════════════════════════════════════════════════════════════════════════════
# get_node
# ════════════════════════════════════════════════════════════════════════════

class TestGetNode:
    def test_returns_none_for_missing(self, store):
        assert store.get_node("co_DOESNOTEXIST") is None

    def test_returns_node_dataclass(self, store):
        _node(store)
        n = store.get_node("co_TSLA")
        assert isinstance(n, Node)
        assert n.node_id == "co_TSLA"


# ════════════════════════════════════════════════════════════════════════════
# neighbors
# ════════════════════════════════════════════════════════════════════════════

class TestNeighbors:
    def test_returns_outbound_and_inbound(self, store):
        _node(store, "co_TSLA")
        _node(store, "pl_ai", "platform", "AI")
        _node(store, "co_NVDA", "company", "Nvidia")
        _edge(store, src="co_TSLA", dst="pl_ai")          # outbound
        _edge(store, src="co_NVDA", dst="co_TSLA", edge_type="competes_with")  # inbound
        edges = store.neighbors("co_TSLA")
        edge_types = {e.edge_type for e in edges}
        assert "belongs_to_platform" in edge_types
        assert "competes_with" in edge_types

    def test_filter_by_edge_type(self, store):
        _node(store, "co_TSLA")
        _node(store, "pl_ai", "platform", "AI")
        _node(store, "pl_robotics", "platform", "Robotics")
        _edge(store, dst="pl_ai", edge_type="belongs_to_platform")
        _edge(store, dst="pl_robotics", edge_type="disrupts")
        edges = store.neighbors("co_TSLA", edge_types=["belongs_to_platform"])
        assert all(e.edge_type == "belongs_to_platform" for e in edges)
        assert len(edges) == 1

    def test_as_of_ts_filters(self, store):
        _node(store, "co_TSLA")
        _node(store, "pl_ai", "platform", "AI")
        cutoff = datetime.now(timezone.utc)
        _edge(store)  # inserted AFTER cutoff
        before_str = cutoff.isoformat()
        edges = store.neighbors("co_TSLA", as_of_ts=before_str)
        # Edge inserted after cutoff should not appear
        assert len(edges) == 0

    def test_max_hops_gt_1_raises(self, store):
        with pytest.raises(NotImplementedError):
            store.neighbors("co_TSLA", max_hops=2)

    def test_superseded_excluded(self, store):
        _node(store, "co_TSLA")
        _node(store, "pl_ai", "platform", "AI")
        old_id = _edge(store)
        # Insert a superseding edge
        _edge(store, edge_type="belongs_to_platform")
        # Mark old edge as superseded (update superseded_by via raw mechanism)
        store._c.execute(
            "UPDATE soma_intel_edge SET superseded_by=? WHERE edge_id=?",
            (old_id + 1, old_id),
        )
        store._c.commit()
        edges = store.neighbors("co_TSLA")
        edge_ids = {e.edge_id for e in edges}
        assert old_id not in edge_ids


# ════════════════════════════════════════════════════════════════════════════
# query_fts
# ════════════════════════════════════════════════════════════════════════════

class TestQueryFts:
    def test_finds_node_by_name(self, store):
        store.upsert_node("co_TSLA", "company", "Tesla Motors Inc")
        store.upsert_node("co_PLTR", "company", "Palantir Technologies")
        results = store.query_fts("Tesla")
        ids = [n.node_id for n in results]
        assert "co_TSLA" in ids
        assert "co_PLTR" not in ids

    def test_filters_by_node_type(self, store):
        store.upsert_node("co_TSLA", "company", "Tesla")
        store.upsert_node("pl_ai", "platform", "AI Platform Tesla-style")
        results = store.query_fts("Tesla", node_types=["platform"])
        ids = [n.node_id for n in results]
        assert "pl_ai" in ids
        assert "co_TSLA" not in ids

    def test_no_results_returns_empty(self, store):
        store.upsert_node("co_TSLA", "company", "Tesla")
        results = store.query_fts("Palantir")
        assert results == []

    def test_special_chars_do_not_crash(self, store):
        store.upsert_node("co_TSLA", "company", "Tesla")
        # These should not raise a FTS5 parse error
        store.query_fts('"bad "query"')
        store.query_fts("hello AND OR NOT")


# ════════════════════════════════════════════════════════════════════════════
# time_travel
# ════════════════════════════════════════════════════════════════════════════

class TestTimeTravel:
    def test_returns_only_edges_before_cutoff(self, store):
        _node(store, "co_TSLA")
        _node(store, "pl_ai", "platform", "AI")
        _edge(store)  # edge 1 — now
        cutoff = datetime.now(timezone.utc).isoformat()
        _edge(store)  # edge 2 — after cutoff
        edges_before = store.time_travel("co_TSLA", as_of_ts=cutoff)
        edge_ids = [e.edge_id for e in edges_before]
        # At least edge 1 visible; edge 2 may or may not appear based on exact ms
        # The contract: no edge asserted after cutoff appears
        for e in edges_before:
            assert e.ts <= cutoff

    def test_includes_superseded_edges(self, store):
        """time_travel shows superseded edges — it's the raw historical record."""
        _node(store, "co_TSLA")
        _node(store, "pl_ai", "platform", "AI")
        old_id = _edge(store)
        new_id = store.upsert_edge(
            "co_TSLA", "pl_ai", "belongs_to_platform",
            confidence=0.95, source_id="test", evidence="Updated.",
            superseded_by=old_id,
        )
        cutoff = datetime.now(timezone.utc).isoformat()
        edges = store.time_travel("co_TSLA", as_of_ts=cutoff)
        edge_ids = {e.edge_id for e in edges}
        assert old_id in edge_ids
        assert new_id in edge_ids

    def test_empty_before_any_edges(self, store):
        _node(store, "co_TSLA")
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        edges = store.time_travel("co_TSLA", as_of_ts=past)
        assert edges == []


# ════════════════════════════════════════════════════════════════════════════
# audit_pending
# ════════════════════════════════════════════════════════════════════════════

class TestAuditPending:
    def test_returns_only_unaudited(self, store):
        _node(store, "co_TSLA")
        _node(store, "pl_ai", "platform", "AI")
        eid1 = _edge(store, confidence=0.40)  # low-conf, should appear
        eid2 = _edge(store, confidence=0.90)
        # Approve eid2
        store.audit_record(eid2, "approved", "Looks good.", "user")
        pending = store.audit_pending()
        pending_ids = {e.edge_id for e in pending}
        assert eid1 in pending_ids
        assert eid2 not in pending_ids

    def test_limit_respected(self, store):
        _node(store, "co_TSLA")
        _node(store, "pl_ai", "platform", "AI")
        for _ in range(10):
            _edge(store)
        pending = store.audit_pending(limit=3)
        assert len(pending) <= 3

    def test_stratify_by_confidence(self, store):
        _node(store, "co_TSLA")
        _node(store, "pl_ai", "platform", "AI")
        _edge(store, confidence=0.90)
        _edge(store, confidence=0.40)
        _edge(store, confidence=0.65)
        pending = store.audit_pending(stratify_by="confidence")
        confs = [e.confidence for e in pending]
        assert confs == sorted(confs), "Should be ordered confidence ASC"


# ════════════════════════════════════════════════════════════════════════════
# audit_record
# ════════════════════════════════════════════════════════════════════════════

class TestAuditRecord:
    def test_approved(self, store):
        _node(store, "co_TSLA")
        _node(store, "pl_ai", "platform", "AI")
        eid = _edge(store)
        store.audit_record(eid, "approved", "Primary source confirmed.", "user")
        edges = store.time_travel("co_TSLA", as_of_ts=datetime.now(timezone.utc).isoformat())
        e = next(x for x in edges if x.edge_id == eid)
        assert e.audit_status == "approved"

    def test_rejected(self, store):
        _node(store, "co_TSLA")
        _node(store, "pl_ai", "platform", "AI")
        eid = _edge(store)
        store.audit_record(eid, "rejected", "Claim not supported.", "user")
        pending = store.audit_pending()
        assert eid not in {e.edge_id for e in pending}

    def test_corrected(self, store):
        _node(store, "co_TSLA")
        _node(store, "pl_ai", "platform", "AI")
        eid = _edge(store)
        store.audit_record(eid, "corrected", "Confidence adjusted.", "claude_adversarial")
        edges = store.time_travel("co_TSLA", as_of_ts=datetime.now(timezone.utc).isoformat())
        e = next(x for x in edges if x.edge_id == eid)
        assert e.audit_status == "corrected"

    def test_invalid_decision_raises(self, store):
        _node(store, "co_TSLA")
        _node(store, "pl_ai", "platform", "AI")
        eid = _edge(store)
        with pytest.raises(ValueError, match="decision"):
            store.audit_record(eid, "maybe", "Bad decision.", "user")

    def test_auditor_recorded_in_notes(self, store):
        _node(store, "co_TSLA")
        _node(store, "pl_ai", "platform", "AI")
        eid = _edge(store)
        store.audit_record(eid, "approved", "Confirmed.", "meta_learner")
        # audit_notes should contain auditor name
        row = store._c.execute(
            "SELECT audit_notes FROM soma_intel_edge WHERE edge_id=?", (eid,)
        ).fetchone()
        assert "meta_learner" in row["audit_notes"]


# ════════════════════════════════════════════════════════════════════════════
# Idempotency / isolation sanity checks
# ════════════════════════════════════════════════════════════════════════════

class TestIdempotency:
    def test_upsert_node_3x_stays_1_row(self, store):
        for _ in range(3):
            store.upsert_node("co_TSLA", "company", "Tesla")
        count = store._c.execute(
            "SELECT COUNT(*) FROM soma_intel_node WHERE node_id='co_TSLA'"
        ).fetchone()[0]
        assert count == 1

    def test_edges_are_versioned_not_deduplicated(self, store):
        """Each upsert_edge call creates a new row (versioned model)."""
        _node(store, "co_TSLA")
        _node(store, "pl_ai", "platform", "AI")
        _edge(store)
        _edge(store)
        count = store._c.execute(
            "SELECT COUNT(*) FROM soma_intel_edge WHERE src_node_id='co_TSLA'"
        ).fetchone()[0]
        assert count == 2
