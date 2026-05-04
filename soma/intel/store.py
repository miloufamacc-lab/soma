#!/usr/bin/env python3
"""
SOMA-INTEL — IntelStore Repository Abstraction Layer

Single source of truth for all soma_intel_* graph reads/writes.
v1 backend: SQLite (WAL mode, foreign keys ON).
Swap path: Kuzu when graph > 50,000 edges — replace _conn internals, keep interface.

Design rules (LOCKED per OPUS_DELIVERABLES §H.1):
  - All other soma/intel/ modules import IntelStore; never issue raw SQL directly.
  - Interface signatures are frozen — backend can change, method names/args cannot.
  - Context-manager required: `with IntelStore() as store: ...`

Usage:
    from shared.soma.intel.store import IntelStore

    with IntelStore() as store:
        store.upsert_node("co_TSLA", "company", "Tesla Inc.")
        edge_id = store.upsert_edge(
            "co_TSLA", "pl_ai", "belongs_to_platform",
            confidence=0.90,
            source_id="wiki/articles/companies/tsla.md",
            evidence="Tesla FSD stack is a vertically integrated AI system.",
        )
        node = store.get_node("co_TSLA")
        edges = store.neighbors("co_TSLA", edge_types=["belongs_to_platform"])
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger(__name__)

# ── DB path resolution (mirrors SomaBridge pattern) ──────────────────────────
# Override via SOMA_DB_PATH env var for tests and CI.
_DEFAULT_DB_PATH = (
    Path(os.environ["SOMA_DB_PATH"])
    if "SOMA_DB_PATH" in os.environ
    else Path.home() / "Desktop" / "DABEIBA" / "shared" / "soma" / "data" / "soma.db"
)

# ── Valid edge types (LOCKED §A.2 — do not add without Opus escalation) ──────
_HALF_LIFE_DEFAULTS: dict[str, int] = {
    "is_a": 730,
    "competes_with": 365,
    "supplies": 365,
    "holds": 90,
    "mentioned_in": 9999,       # no decay — sentinel value
    "causes": 180,
    "has_thesis": 90,
    "has_target_price": 30,
    "expresses_sentiment": 14,
    "belongs_to_platform": 365,
    "convergence_of": 180,
    "regime_was": 9999,         # immutable once set
    "correlated_with": 90,
    "disrupts": 365,
    "succeeded_by": 9999,       # immutable
}

VALID_EDGE_TYPES: frozenset[str] = frozenset(_HALF_LIFE_DEFAULTS.keys())


# ── Typed return types ────────────────────────────────────────────────────────

@dataclass
class Node:
    """Graph node. Immutable ID; renames go through the aliases field."""
    node_id: str
    node_type: str
    name: str
    aliases: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_ts: str = ""
    last_seen_ts: str = ""


@dataclass
class Edge:
    """Directed graph edge with confidence, decay, provenance, and audit state."""
    edge_id: int
    src_node_id: str
    dst_node_id: str
    edge_type: str
    weight: float
    confidence: float
    ts: str
    half_life_days: int
    source_id: str
    source_type: str
    evidence_text: Optional[str]
    audit_status: str
    superseded_by: Optional[int]


# ── DDL (minimal — used by initialize_tables() in tests/dev only) ─────────────
# Production uses migrations/021_soma_intel_schema.sql.
# These two tables are the IntelStore's minimum viable substrate.

_DDL_NODE = """
CREATE TABLE IF NOT EXISTS soma_intel_node (
  node_id      TEXT PRIMARY KEY,
  node_type    TEXT NOT NULL,
  name         TEXT NOT NULL,
  aliases      TEXT,            -- JSON array
  metadata     TEXT,            -- JSON object
  created_ts   TEXT NOT NULL,
  last_seen_ts TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_intel_node_type
  ON soma_intel_node(node_type);
"""

_DDL_EDGE = """
CREATE TABLE IF NOT EXISTS soma_intel_edge (
  edge_id        INTEGER PRIMARY KEY AUTOINCREMENT,
  src_node_id    TEXT NOT NULL,
  dst_node_id    TEXT NOT NULL,
  edge_type      TEXT NOT NULL,
  weight         REAL NOT NULL DEFAULT 1.0,
  confidence     REAL NOT NULL CHECK(confidence BETWEEN 0 AND 1),
  ts             TEXT NOT NULL,
  half_life_days INTEGER NOT NULL,
  source_id      TEXT NOT NULL,
  source_type    TEXT NOT NULL,
  evidence_text  TEXT,
  audit_status   TEXT DEFAULT 'unaudited',
  audit_ts       TEXT,
  audit_notes    TEXT,
  superseded_by  INTEGER,
  FOREIGN KEY (src_node_id)   REFERENCES soma_intel_node(node_id),
  FOREIGN KEY (dst_node_id)   REFERENCES soma_intel_node(node_id),
  FOREIGN KEY (superseded_by) REFERENCES soma_intel_edge(edge_id)
);
CREATE INDEX IF NOT EXISTS idx_intel_edge_src
  ON soma_intel_edge(src_node_id, edge_type, ts DESC);
CREATE INDEX IF NOT EXISTS idx_intel_edge_dst
  ON soma_intel_edge(dst_node_id, edge_type, ts DESC);
CREATE INDEX IF NOT EXISTS idx_intel_edge_ts
  ON soma_intel_edge(ts);
CREATE INDEX IF NOT EXISTS idx_intel_edge_audit
  ON soma_intel_edge(audit_status)
  WHERE audit_status = 'unaudited';
"""

# FTS5 virtual table + sync triggers for full-text node search
_DDL_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS soma_intel_node_fts
  USING fts5(
    node_id UNINDEXED,
    name,
    node_type,
    content=soma_intel_node,
    content_rowid=rowid
  );
"""

_DDL_FTS_INSERT_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS soma_intel_node_fts_ai
AFTER INSERT ON soma_intel_node BEGIN
  INSERT INTO soma_intel_node_fts(rowid, node_id, name, node_type)
  VALUES (new.rowid, new.node_id, new.name, new.node_type);
END;
"""

_DDL_FTS_UPDATE_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS soma_intel_node_fts_au
AFTER UPDATE ON soma_intel_node BEGIN
  INSERT INTO soma_intel_node_fts(soma_intel_node_fts, rowid, node_id, name, node_type)
    VALUES ('delete', old.rowid, old.node_id, old.name, old.node_type);
  INSERT INTO soma_intel_node_fts(rowid, node_id, name, node_type)
    VALUES (new.rowid, new.node_id, new.name, new.node_type);
END;
"""


# ════════════════════════════════════════════════════════════════════════════
# IntelStore
# ════════════════════════════════════════════════════════════════════════════

class IntelStore:
    """
    Repository abstraction for the SOMA-INTEL knowledge graph.

    All soma_intel_* table reads/writes flow exclusively through this class.
    No other module in soma/intel/ may issue raw SQL.

    Backend: SQLite v1 (WAL, foreign keys).
    Swap path to Kuzu: replace the sqlite3 internals below, keep the 8 public
    method signatures untouched.

    Lifecycle:
        with IntelStore() as store:
            store.upsert_node(...)
            edge_id = store.upsert_edge(...)

    Test / dev isolation:
        Instantiate with an explicit db_path and call store.initialize_tables()
        to bootstrap the schema without running the full migration file.
    """

    def __init__(self, db_path: Optional[str | Path] = None) -> None:
        self._db_path = str(db_path or _DEFAULT_DB_PATH)
        self._conn: Optional[sqlite3.Connection] = None

    # ── Context manager ───────────────────────────────────────────────────────

    def __enter__(self) -> "IntelStore":
        db_dir = os.path.dirname(self._db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        if self._conn:
            self._conn.close()
            self._conn = None
        return False  # never suppress exceptions

    @property
    def _c(self) -> sqlite3.Connection:
        """Active connection. Raises if called outside `with` block."""
        if self._conn is None:
            raise RuntimeError(
                "IntelStore must be used as a context manager: "
                "`with IntelStore() as store: ...`"
            )
        return self._conn

    # ── Schema bootstrap (tests / dev only) ───────────────────────────────────

    def initialize_tables(self) -> None:
        """
        Create soma_intel_node, soma_intel_edge, FTS table, and sync triggers.

        Idempotent (uses IF NOT EXISTS). Safe to call multiple times.

        DO NOT call in production — migrations/021_soma_intel_schema.sql is the
        authoritative DDL for production deployments.
        """
        for ddl in (
            _DDL_NODE,
            _DDL_EDGE,
            _DDL_FTS,
            _DDL_FTS_INSERT_TRIGGER,
            _DDL_FTS_UPDATE_TRIGGER,
        ):
            self._c.executescript(ddl)
        self._c.commit()
        log.debug("soma_intel tables initialized (dev/test mode).")

    # ── Internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _row_to_node(row: sqlite3.Row) -> Node:
        return Node(
            node_id=row["node_id"],
            node_type=row["node_type"],
            name=row["name"],
            aliases=json.loads(row["aliases"] or "[]"),
            metadata=json.loads(row["metadata"] or "{}"),
            created_ts=row["created_ts"],
            last_seen_ts=row["last_seen_ts"],
        )

    @staticmethod
    def _row_to_edge(row: sqlite3.Row) -> Edge:
        return Edge(
            edge_id=row["edge_id"],
            src_node_id=row["src_node_id"],
            dst_node_id=row["dst_node_id"],
            edge_type=row["edge_type"],
            weight=row["weight"],
            confidence=row["confidence"],
            ts=row["ts"],
            half_life_days=row["half_life_days"],
            source_id=row["source_id"],
            source_type=row["source_type"],
            evidence_text=row["evidence_text"],
            audit_status=row["audit_status"],
            superseded_by=row["superseded_by"],
        )

    # ════════════════════════════════════════════════════════════════════════
    # LOCKED INTERFACE — §H.1 (signatures must not change)
    # ════════════════════════════════════════════════════════════════════════

    def upsert_node(
        self,
        node_id: str,
        node_type: str,
        name: str,
        **meta: Any,
    ) -> None:
        """
        Insert or update a node. created_ts is preserved on subsequent upserts.

        Keyword args:
            aliases  (list[str]): alternate IDs / names for this node.
            metadata (dict):      arbitrary JSON metadata.
        """
        aliases_json = json.dumps(meta.get("aliases", []))
        metadata_json = json.dumps(meta.get("metadata", {}))
        now = self._now_iso()

        self._c.execute(
            """
            INSERT INTO soma_intel_node
              (node_id, node_type, name, aliases, metadata, created_ts, last_seen_ts)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(node_id) DO UPDATE SET
              name         = excluded.name,
              aliases      = excluded.aliases,
              metadata     = excluded.metadata,
              last_seen_ts = excluded.last_seen_ts
            """,
            (node_id, node_type, name, aliases_json, metadata_json, now, now),
        )
        self._c.commit()
        log.debug("upsert_node: %s (%s)", node_id, node_type)

    def upsert_edge(
        self,
        src: str,
        dst: str,
        edge_type: str,
        confidence: float,
        source_id: str,
        evidence: Optional[str],
        **meta: Any,
    ) -> int:
        """
        Insert a new edge and return its edge_id.

        Each call creates a new row (edges are versioned, not deduplicated).
        To supersede an old edge, pass superseded_by=<old_edge_id> in meta.

        Keyword args:
            weight        (float):  base weight, default 1.0.
            source_type   (str):    'wiki'|'transcript'|'oracle_titan'|'10k'|'news'|'manual'|'derived'.
            half_life_days(int):    overrides §A.2 default for this edge_type.
            audit_status  (str):    default 'unaudited'.
            superseded_by (int):    edge_id this edge replaces.

        Raises:
            ValueError: if edge_type not in VALID_EDGE_TYPES or confidence out of [0,1].
        """
        if edge_type not in VALID_EDGE_TYPES:
            raise ValueError(
                f"Unknown edge_type '{edge_type}'. "
                f"Locked types (§A.2): {sorted(VALID_EDGE_TYPES)}"
            )
        if not (0.0 <= confidence <= 1.0):
            raise ValueError(
                f"confidence must be in [0.0, 1.0], got {confidence!r}"
            )

        half_life = meta.get("half_life_days", _HALF_LIFE_DEFAULTS[edge_type])
        weight = meta.get("weight", 1.0)
        source_type = meta.get("source_type", "manual")
        audit_status = meta.get("audit_status", "unaudited")
        superseded_by = meta.get("superseded_by", None)
        now = self._now_iso()

        cur = self._c.execute(
            """
            INSERT INTO soma_intel_edge
              (src_node_id, dst_node_id, edge_type, weight, confidence, ts,
               half_life_days, source_id, source_type, evidence_text,
               audit_status, superseded_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                src, dst, edge_type, weight, confidence, now,
                half_life, source_id, source_type, evidence,
                audit_status, superseded_by,
            ),
        )
        self._c.commit()
        edge_id: int = cur.lastrowid  # type: ignore[assignment]
        log.debug("upsert_edge: %s -[%s]-> %s (id=%d)", src, edge_type, dst, edge_id)
        return edge_id

    def get_node(self, node_id: str) -> Optional[Node]:
        """Return Node by ID, or None if not found."""
        row = self._c.execute(
            "SELECT * FROM soma_intel_node WHERE node_id = ?",
            (node_id,),
        ).fetchone()
        return self._row_to_node(row) if row else None

    def neighbors(
        self,
        node_id: str,
        edge_types: Optional[list[str]] = None,
        max_hops: int = 1,
        as_of_ts: Optional[str] = None,
    ) -> list[Edge]:
        """
        Return edges incident to node_id (both outbound and inbound).

        Args:
            node_id:    target node.
            edge_types: if provided, filter to only these edge types.
            max_hops:   depth of traversal. v1 supports max_hops=1 only;
                        multi-hop graph traversal is deferred to Phase 1.
            as_of_ts:   ISO 8601 timestamp; if provided, return only edges
                        asserted at or before this point (time-filtered view).
                        Superseded edges are excluded by default.

        Returns:
            List of Edge, ordered by ts DESC.

        Raises:
            NotImplementedError: if max_hops > 1 (deferred to Phase 1).
        """
        if max_hops != 1:
            raise NotImplementedError(
                "max_hops > 1 is deferred to Phase 1 graph traversal. "
                "Use time_travel() for historical state of a single node."
            )

        clauses: list[str] = [
            "(src_node_id = ? OR dst_node_id = ?)",
            "superseded_by IS NULL",
        ]
        params: list[Any] = [node_id, node_id]

        if edge_types:
            placeholders = ",".join("?" * len(edge_types))
            clauses.append(f"edge_type IN ({placeholders})")
            params.extend(edge_types)

        if as_of_ts:
            clauses.append("ts <= ?")
            params.append(as_of_ts)

        sql = (
            "SELECT * FROM soma_intel_edge WHERE "
            + " AND ".join(clauses)
            + " ORDER BY ts DESC"
        )
        rows = self._c.execute(sql, params).fetchall()
        return [self._row_to_edge(r) for r in rows]

    def query_fts(
        self,
        text: str,
        node_types: Optional[list[str]] = None,
    ) -> list[Node]:
        """
        Full-text search across node names and aliases.

        Args:
            text:       FTS5 query string (plain text; special chars are escaped).
            node_types: if provided, restrict results to these node type prefixes.

        Returns:
            List of matching Node objects (order: FTS5 BM25 relevance).
        """
        # Wrap in FTS5 phrase quotes to prevent boolean operator injection.
        # AND/OR/NOT/NEAR are FTS5 operators; wrapping forces literal phrase match.
        # Embedded double-quotes are escaped by doubling them per FTS5 spec.
        safe_text = '"' + text.replace('"', '""') + '"'
        sql = (
            "SELECT n.* FROM soma_intel_node n "
            "JOIN soma_intel_node_fts fts ON n.rowid = fts.rowid "
            "WHERE soma_intel_node_fts MATCH ?"
        )
        params: list[Any] = [safe_text]

        if node_types:
            placeholders = ",".join("?" * len(node_types))
            sql += f" AND n.node_type IN ({placeholders})"
            params.extend(node_types)

        rows = self._c.execute(sql, params).fetchall()
        return [self._row_to_node(r) for r in rows]

    def time_travel(self, node_id: str, as_of_ts: str) -> list[Edge]:
        """
        Return the full edge history for node_id as of the given timestamp.

        Unlike neighbors(), includes superseded edges — this is the raw
        historical record of every claim ever made about this node up to as_of_ts.

        Args:
            node_id:   target node.
            as_of_ts:  ISO 8601 cutoff (inclusive). Edges asserted after this
                       timestamp are excluded.

        Returns:
            List of Edge, ordered by ts DESC (most recent first within the window).
        """
        rows = self._c.execute(
            """
            SELECT * FROM soma_intel_edge
            WHERE (src_node_id = ? OR dst_node_id = ?)
              AND ts <= ?
            ORDER BY ts DESC
            """,
            (node_id, node_id, as_of_ts),
        ).fetchall()
        return [self._row_to_edge(r) for r in rows]

    def audit_pending(
        self,
        limit: int = 50,
        stratify_by: Optional[str] = None,
    ) -> list[Edge]:
        """
        Return edges awaiting audit, ordered for review.

        Per §K.1, 100% of [0.30, 0.55] confidence edges enter the audit queue.
        This method surfaces the highest-priority unaudited edges.

        Args:
            limit:        max rows to return (default 50, matches §A.5 batch size).
            stratify_by:  ordering hint — 'edge_type' | 'source_type' | 'confidence'.
                          Defaults to 'confidence' ascending (lowest confidence first).

        Returns:
            List of Edge with audit_status='unaudited'.
        """
        order_col = {
            "edge_type":   "edge_type, confidence ASC",
            "source_type": "source_type, confidence ASC",
            "confidence":  "confidence ASC",
        }.get(stratify_by or "", "confidence ASC")

        rows = self._c.execute(
            f"""
            SELECT * FROM soma_intel_edge
            WHERE audit_status = 'unaudited'
            ORDER BY {order_col}
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [self._row_to_edge(r) for r in rows]

    def audit_record(
        self,
        edge_id: int,
        decision: str,
        rationale: str,
        auditor: str,
    ) -> None:
        """
        Record an audit decision against an edge.

        Updates edge.audit_status + audit_ts + audit_notes on the edge row.
        In Step 0.1+, this also writes an immutable row to soma_intel_audit_log
        (the log table is created in migration 021).

        Args:
            edge_id:   the edge being audited.
            decision:  'approved' | 'rejected' | 'corrected'.
            rationale: free-text explanation (stored in audit_notes).
            auditor:   'user' | 'claude_adversarial' | 'meta_learner'.

        Raises:
            ValueError: if decision is not one of the valid options.
        """
        _valid = {"approved", "rejected", "corrected"}
        if decision not in _valid:
            raise ValueError(
                f"decision must be one of {_valid}, got {decision!r}"
            )

        now = self._now_iso()
        self._c.execute(
            """
            UPDATE soma_intel_edge
            SET audit_status = ?,
                audit_ts     = ?,
                audit_notes  = ?
            WHERE edge_id = ?
            """,
            (decision, now, f"[{auditor}] {rationale}", edge_id),
        )
        self._c.commit()
        log.debug("audit_record: edge %d → %s by %s", edge_id, decision, auditor)
