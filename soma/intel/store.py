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

    def commit(self) -> None:
        """Explicit commit. Prefer calling this instead of store._c.commit() directly."""
        self._c.commit()

    # ════════════════════════════════════════════════════════════════════════
    # EXTENDED INTERFACE — additional methods for soma/intel/ modules
    # All raw SQL in soma/intel/ MUST go through one of the methods below
    # (or the LOCKED INTERFACE above).  Do not add store._c.execute() calls
    # in any other module — extend this section instead.
    # ════════════════════════════════════════════════════════════════════════

    # ── Universe ─────────────────────────────────────────────────────────────

    def list_active_universe_tickers(self) -> list[str]:
        """Return sorted list of active ticker symbols from soma_intel_universe."""
        rows = self._c.execute(
            "SELECT ticker FROM soma_intel_universe WHERE active=1 ORDER BY ticker"
        ).fetchall()
        return [r["ticker"] for r in rows]

    def list_universe(self, active_only: bool = True) -> list[dict]:
        """Return universe rows as plain dicts (keys: ticker, auto_added, tier)."""
        if active_only:
            rows = self._c.execute(
                "SELECT ticker, auto_added, tier FROM soma_intel_universe WHERE active=1"
            ).fetchall()
        else:
            rows = self._c.execute(
                "SELECT ticker, auto_added, tier FROM soma_intel_universe"
            ).fetchall()
        return [dict(r) for r in rows]

    def list_universe_with_scores(self) -> list[dict]:
        """Return active universe rows including promotion_score and promotion_source."""
        rows = self._c.execute(
            """
            SELECT ticker, promotion_score, promotion_source
            FROM soma_intel_universe
            WHERE active=1 AND promotion_score IS NOT NULL
            ORDER BY promotion_score DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]

    def upsert_universe_ticker(
        self,
        ticker: str,
        source: str,
        platform_tags: list,
        added_ts: str,
        score: float,
        promo_source: str,
        tier: str = "watchlist",
        auto_added: bool = True,
    ) -> int:
        """
        Insert or activate a ticker in soma_intel_universe.
        Returns SQLite changes() count (1 if inserted/updated, 0 if no-op).
        """
        import json as _json
        pt = _json.dumps(platform_tags)
        ai = int(auto_added)
        self._c.execute(
            """
            INSERT INTO soma_intel_universe
              (ticker, source, platform_tags, added_ts, active, tier,
               auto_added, promotion_score, promotion_source)
            VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET
              active           = 1,
              tier             = CASE WHEN excluded.tier != '' THEN excluded.tier ELSE tier END,
              auto_added       = ?,
              promotion_score  = excluded.promotion_score,
              promotion_source = excluded.promotion_source
            """,
            (ticker, source, pt, added_ts, tier, ai, score, promo_source, ai),
        )
        return self._c.execute("SELECT changes()").fetchone()[0]

    def demote_universe_ticker(self, ticker: str) -> int:
        """
        Set active=0 for an auto-added ticker (manual tickers are never demoted).
        Returns SQLite changes() count.
        """
        self._c.execute(
            "UPDATE soma_intel_universe SET active=0 WHERE ticker=? AND auto_added=1",
            (ticker,),
        )
        return self._c.execute("SELECT changes()").fetchone()[0]

    def refresh_universe_score(self, ticker: str, score: float, promo_source: str) -> int:
        """
        Update promotion_score + promotion_source for any universe row (active or not).
        Returns SQLite changes() count.
        """
        self._c.execute(
            """
            UPDATE soma_intel_universe
            SET promotion_score=?, promotion_source=?
            WHERE ticker=?
            """,
            (score, promo_source, ticker),
        )
        return self._c.execute("SELECT changes()").fetchone()[0]

    # ── Belief ────────────────────────────────────────────────────────────────

    def get_active_belief(self, node_id: str, predicate: str) -> Optional[dict]:
        """
        Return the active (non-superseded) belief for (node_id, predicate).
        Keys: belief_id, value, confidence, ts, source_id. Returns None if not found.
        """
        row = self._c.execute(
            """
            SELECT belief_id, value, confidence, ts, source_id
            FROM soma_intel_belief
            WHERE subject_node_id=? AND predicate=? AND superseded_by IS NULL
            """,
            (node_id, predicate),
        ).fetchone()
        return dict(row) if row else None

    def get_active_beliefs(self, predicate: str) -> list[dict]:
        """
        Return all active beliefs for a given predicate.
        Keys: subject_node_id, belief_id, value, confidence, ts, source_id.
        """
        rows = self._c.execute(
            """
            SELECT subject_node_id, belief_id, value, confidence, ts, source_id
            FROM soma_intel_belief
            WHERE predicate=? AND superseded_by IS NULL
            """,
            (predicate,),
        ).fetchall()
        return [dict(r) for r in rows]

    def upsert_belief(
        self,
        node_id: str,
        predicate: str,
        value: str,
        confidence: float,
        source_id: str,
    ) -> int:
        """
        Insert a new belief, superseding any prior active belief for (node_id, predicate).

        The supersede chain is: old belief → new belief (old.superseded_by = new.belief_id).
        Returns the new belief_id.
        """
        prior = self._c.execute(
            """
            SELECT belief_id FROM soma_intel_belief
            WHERE subject_node_id=? AND predicate=? AND superseded_by IS NULL
            """,
            (node_id, predicate),
        ).fetchone()
        prior_id: Optional[int] = prior["belief_id"] if prior else None

        now = self._now_iso()
        cur = self._c.execute(
            """
            INSERT INTO soma_intel_belief
              (subject_node_id, predicate, value, confidence, ts, source_id, superseded_by)
            VALUES (?, ?, ?, ?, ?, ?, NULL)
            """,
            (node_id, predicate, value, confidence, now, source_id),
        )
        new_id: int = cur.lastrowid  # type: ignore[assignment]

        if prior_id is not None:
            self._c.execute(
                "UPDATE soma_intel_belief SET superseded_by=? WHERE belief_id=?",
                (new_id, prior_id),
            )
        return new_id

    def count_active_beliefs(self, predicate: str) -> int:
        """Count active (non-superseded) beliefs for a predicate."""
        return self._c.execute(
            """
            SELECT COUNT(*) FROM soma_intel_belief
            WHERE predicate=? AND superseded_by IS NULL
            """,
            (predicate,),
        ).fetchone()[0]

    # ── Signal ────────────────────────────────────────────────────────────────

    def get_signal(
        self,
        ticker: str,
        date: str,
        notes_prefix: str,
    ) -> Optional[dict]:
        """
        Return the signal row for (ticker, date) whose notes column starts with notes_prefix.
        Keys: signal_id, reconfirmation_count. Returns None if not found.
        """
        row = self._c.execute(
            """
            SELECT signal_id, reconfirmation_count
            FROM soma_intel_signal
            WHERE ticker=? AND date=? AND notes LIKE ?
            """,
            (ticker, date, f"{notes_prefix}%"),
        ).fetchone()
        return dict(row) if row else None

    def insert_signal(
        self,
        ticker: str,
        date: str,
        priority: str,
        anomaly_score: float,
        features: str,
        corroboration: int,
        half_life: int,
        horizon: str,
        notes: str,
        status: str = "active",
    ) -> None:
        """
        Insert a new signal row.

        Valid horizon values (§J spec): 'tactical' | 'thematic' | 'structural'.
        Use 'thematic' as placeholder until horizon track modules are wired.
        """
        _valid_horizons = {"tactical", "thematic", "structural"}
        if horizon not in _valid_horizons:
            raise ValueError(
                f"horizon must be one of {_valid_horizons}, got {horizon!r}. "
                "Use 'thematic' as placeholder until horizon tracks are built."
            )
        self._c.execute(
            """
            INSERT INTO soma_intel_signal
              (ticker, date, priority, anomaly_score, features,
               corroboration_count, half_life_days,
               reconfirmation_count, status, horizon, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
            """,
            (ticker, date, priority, anomaly_score, features,
             corroboration, half_life, status, horizon, notes),
        )

    def update_signal(
        self,
        signal_id: int,
        priority: str,
        anomaly_score: float,
        features: str,
        corroboration: int,
        half_life: int,
        horizon: str,
        notes: str,
    ) -> None:
        """Reconfirm (update) an existing signal row. Increments reconfirmation_count."""
        _valid_horizons = {"tactical", "thematic", "structural"}
        if horizon not in _valid_horizons:
            raise ValueError(
                f"horizon must be one of {_valid_horizons}, got {horizon!r}."
            )
        self._c.execute(
            """
            UPDATE soma_intel_signal
            SET priority             = ?,
                anomaly_score        = ?,
                features             = ?,
                corroboration_count  = ?,
                half_life_days       = ?,
                reconfirmation_count = reconfirmation_count + 1,
                status               = 'reconfirmed',
                horizon              = ?,
                notes                = ?
            WHERE signal_id = ?
            """,
            (priority, anomaly_score, features, corroboration,
             half_life, horizon, notes, signal_id),
        )

    # ── Platform ──────────────────────────────────────────────────────────────

    def list_platform_positions(self) -> dict[str, str]:
        """Return mapping of platform_id → position label (or 'unknown')."""
        rows = self._c.execute(
            "SELECT platform_id, position FROM soma_intel_platform"
        ).fetchall()
        return {r["platform_id"]: (r["position"] or "unknown") for r in rows}

    def get_ticker_platforms(self) -> dict[str, list[str]]:
        """
        Return ticker → sorted list of platform_ids from active belongs_to_platform edges.
        Only includes co_* → pl_* non-superseded edges.
        """
        rows = self._c.execute(
            """
            SELECT DISTINCT src_node_id, dst_node_id
            FROM soma_intel_edge
            WHERE edge_type = 'belongs_to_platform'
              AND src_node_id LIKE 'co_%'
              AND dst_node_id LIKE 'pl_%'
              AND superseded_by IS NULL
            """
        ).fetchall()
        membership: dict[str, set[str]] = {}
        for r in rows:
            ticker = r["src_node_id"][3:]   # strip "co_"
            membership.setdefault(ticker, set()).add(r["dst_node_id"])
        return {t: sorted(pls) for t, pls in membership.items()}

    # ── Node batch ────────────────────────────────────────────────────────────

    def list_nodes_by_type(self, node_type: str) -> list[Node]:
        """Return all nodes of a given node_type as Node objects."""
        rows = self._c.execute(
            "SELECT * FROM soma_intel_node WHERE node_type=?",
            (node_type,),
        ).fetchall()
        return [self._row_to_node(r) for r in rows]

    # ── Edge batch ────────────────────────────────────────────────────────────

    def edge_source_counts_for_companies(self) -> dict[str, dict[str, int]]:
        """
        Aggregate edge counts by (company_node_id, source_type) for all co_* nodes.

        Returns: node_id → {source_type → total count}.
        Counts both outgoing and incoming edges (bidirectional signal density).
        Used by universe_manager to score signal richness per ticker.
        """
        rows = self._c.execute(
            """
            SELECT src_node_id AS node_id, source_type, COUNT(*) AS cnt
            FROM soma_intel_edge
            WHERE src_node_id LIKE 'co_%'
            GROUP BY src_node_id, source_type
            UNION ALL
            SELECT dst_node_id AS node_id, source_type, COUNT(*) AS cnt
            FROM soma_intel_edge
            WHERE dst_node_id LIKE 'co_%'
            GROUP BY dst_node_id, source_type
            """
        ).fetchall()
        result: dict[str, dict[str, int]] = {}
        for r in rows:
            nid = r["node_id"]
            st  = r["source_type"]
            result.setdefault(nid, {})
            result[nid][st] = result[nid].get(st, 0) + r["cnt"]
        return result

    def get_edges_of_type(
        self,
        edge_type: str,
        src_prefix: Optional[str] = None,
        dst_prefix: Optional[str] = None,
        active_only: bool = True,
    ) -> list[Edge]:
        """
        Return edges of a given type with optional LIKE prefix filters on src/dst.

        Args:
            edge_type:   must be in VALID_EDGE_TYPES.
            src_prefix:  e.g. 'co_%' to restrict to company sources.
            dst_prefix:  e.g. 'th_%' to restrict to thesis destinations.
            active_only: if True (default), exclude superseded edges.

        Returns:
            List of Edge objects.
        """
        clauses: list[str] = ["edge_type = ?"]
        params: list[Any] = [edge_type]

        if active_only:
            clauses.append("superseded_by IS NULL")
        if src_prefix:
            clauses.append("src_node_id LIKE ?")
            params.append(src_prefix)
        if dst_prefix:
            clauses.append("dst_node_id LIKE ?")
            params.append(dst_prefix)

        sql = "SELECT * FROM soma_intel_edge WHERE " + " AND ".join(clauses)
        rows = self._c.execute(sql, params).fetchall()
        return [self._row_to_edge(r) for r in rows]

    def structural_thesis_node_ids(self, max_mentions: int) -> set[str]:
        """
        Return thesis node IDs mentioned by more than max_mentions distinct company nodes.

        Used to identify structural/framework theses (e.g. 'Value Investing') vs
        investable signal theses (e.g. 'Tesla FSD Monetisation').

        Args:
            max_mentions: threshold (exclusive). Theses with count > this are structural.
        """
        rows = self._c.execute(
            """
            SELECT dst_node_id, COUNT(DISTINCT src_node_id) AS c
            FROM soma_intel_edge
            WHERE edge_type = 'mentioned_in'
              AND src_node_id LIKE 'co_%'
              AND dst_node_id LIKE 'th_%'
            GROUP BY dst_node_id
            HAVING c > ?
            """,
            (max_mentions,),
        ).fetchall()
        return {r["dst_node_id"] for r in rows}

    def existing_edge_pairs_of_type(
        self,
        edge_type: str,
        src_prefix: str = "co_%",
    ) -> set[tuple[str, str]]:
        """
        Return set of (src_node_id, dst_node_id) for active edges of a given type.

        Used for deduplication checks before writing derived edges (e.g. has_thesis).

        Args:
            edge_type:   the edge type to query.
            src_prefix:  LIKE pattern to restrict source nodes (default 'co_%').
        """
        rows = self._c.execute(
            """
            SELECT src_node_id, dst_node_id FROM soma_intel_edge
            WHERE edge_type=? AND src_node_id LIKE ? AND superseded_by IS NULL
            """,
            (edge_type, src_prefix),
        ).fetchall()
        return {(r["src_node_id"], r["dst_node_id"]) for r in rows}

    # ── Statistics ────────────────────────────────────────────────────────────

    def graph_stats(self) -> dict:
        """
        Return DB-wide graph statistics.

        Keys:
            node_total (int)
            edge_total (int)
            unaudited  (int)
            node_by_type  (list[dict] — node_type, c)
            edge_by_source (list[dict] — source_type, c)
        """
        node_total = self._c.execute(
            "SELECT COUNT(*) FROM soma_intel_node"
        ).fetchone()[0]
        edge_total = self._c.execute(
            "SELECT COUNT(*) FROM soma_intel_edge"
        ).fetchone()[0]
        unaudited = self._c.execute(
            "SELECT COUNT(*) FROM soma_intel_edge WHERE audit_status='unaudited'"
        ).fetchone()[0]
        node_by_type = [
            dict(r) for r in self._c.execute(
                """
                SELECT node_type, COUNT(*) AS c
                FROM soma_intel_node GROUP BY node_type ORDER BY c DESC
                """
            ).fetchall()
        ]
        edge_by_source = [
            dict(r) for r in self._c.execute(
                """
                SELECT source_type, COUNT(*) AS c
                FROM soma_intel_edge GROUP BY source_type ORDER BY c DESC
                """
            ).fetchall()
        ]
        return {
            "node_total":     node_total,
            "edge_total":     edge_total,
            "unaudited":      unaudited,
            "node_by_type":   node_by_type,
            "edge_by_source": edge_by_source,
        }

    def edge_type_counts(self) -> list[tuple[str, int]]:
        """Return list of (edge_type, count) sorted by count DESC."""
        rows = self._c.execute(
            """
            SELECT edge_type, COUNT(*) AS c
            FROM soma_intel_edge GROUP BY edge_type ORDER BY c DESC
            """
        ).fetchall()
        return [(r["edge_type"], r["c"]) for r in rows]

    def count_table(self, table_name: str) -> int:
        """
        Count all rows in a soma_intel_* table.

        Args:
            table_name: must be one of the whitelisted soma_intel_* table names.

        Raises:
            ValueError: if table_name is not in the whitelist (prevents SQL injection).
        """
        _ALLOWED = {
            "soma_intel_node",
            "soma_intel_edge",
            "soma_intel_signal",
            "soma_intel_belief",
            "soma_intel_universe",
            "soma_intel_platform",
            "soma_intel_scurve_history",
            "soma_intel_baseline",
            "soma_intel_audit_log",
        }
        if table_name not in _ALLOWED:
            raise ValueError(
                f"table_name must be one of {sorted(_ALLOWED)}, got {table_name!r}"
            )
        return self._c.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]

    def count_unaudited_edges(self) -> int:
        """Count edges with audit_status='unaudited'."""
        return self._c.execute(
            "SELECT COUNT(*) FROM soma_intel_edge WHERE audit_status='unaudited'"
        ).fetchone()[0]

    # ── Signal sweep helpers ──────────────────────────────────────────────────

    def list_signals_active(
        self,
        tickers: Optional[list[str]] = None,
    ) -> list[dict]:
        """
        Return all non-expired signals (status NOT IN ('expired')), ordered by date ASC.

        Args:
            tickers: if provided, restrict to these ticker symbols.

        Returns:
            List of dicts with keys: signal_id, ticker, date, priority,
            half_life_days, status, notes, reconfirmation_count.
        """
        clauses = ["status NOT IN ('expired')"]
        params: list[Any] = []
        if tickers:
            placeholders = ",".join("?" * len(tickers))
            clauses.append(f"ticker IN ({placeholders})")
            params.extend(tickers)
        sql = (
            "SELECT signal_id, ticker, date, priority, half_life_days, "
            "status, notes, reconfirmation_count "
            "FROM soma_intel_signal WHERE "
            + " AND ".join(clauses)
            + " ORDER BY date ASC"
        )
        rows = self._c.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def list_active_signals_not_today(
        self,
        today: str,
        notes_prefix: str,
        tickers: Optional[list[str]] = None,
    ) -> list[dict]:
        """
        Return active/reconfirmed signals whose date != today and whose notes
        start with notes_prefix. Used by signal_sweep Pass 3.

        Returns dicts with keys: signal_id, ticker, date, half_life_days,
        reconfirmation_count.
        """
        clauses = [
            "status IN ('active', 'reconfirmed')",
            "date != ?",
            "notes LIKE ?",
        ]
        params: list[Any] = [today, f"{notes_prefix}%"]
        if tickers:
            placeholders = ",".join("?" * len(tickers))
            clauses.append(f"ticker IN ({placeholders})")
            params.extend(tickers)
        sql = (
            "SELECT signal_id, ticker, date, half_life_days, reconfirmation_count "
            "FROM soma_intel_signal WHERE "
            + " AND ".join(clauses)
            + " ORDER BY date ASC"
        )
        rows = self._c.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def expire_signal(self, signal_id: int) -> None:
        """Set status='expired' on a signal row. Used by signal_sweep passes 1 + 3."""
        self._c.execute(
            "UPDATE soma_intel_signal SET status='expired' WHERE signal_id=?",
            (signal_id,),
        )

    def boost_signal_half_life(
        self,
        signal_id:  int,
        factor:     float,
        max_factor: float,
    ) -> int:
        """
        Multiply the signal's half_life_days by `factor`, capped at max_factor
        total boosts (derived from `max_factor` / `factor` exponent count).

        Per §C.3: factor=1.3, max_factor=1.3**3 — cap is 3 reconfirmations.

        MUST be called immediately after update_signal() increments
        reconfirmation_count, so reconfirmation_count reflects the boost number.

        Algorithm:
          - max_boosts = round(log(max_factor) / log(factor))   [= 3]
          - If reconfirmation_count > max_boosts → already capped, return unchanged.
          - Else → new_hl = round(current_hl * factor), write back.

        Avoids floating-point base-reconstruction (dividing rounded value by
        factor would accumulate error over multiple boosts).

        Returns the new half_life_days value (unchanged if capped).
        """
        import math as _math

        row = self._c.execute(
            "SELECT half_life_days, reconfirmation_count FROM soma_intel_signal "
            "WHERE signal_id=?",
            (signal_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"signal_id {signal_id} not found")

        current_hl: int   = row["half_life_days"]
        reconfirm_count: int = row["reconfirmation_count"]

        # Derive how many boosts are allowed from the max_factor parameter.
        # For factor=1.3, max_factor=1.3^3: max_boosts = 3.
        max_boosts = max(1, round(_math.log(max_factor) / _math.log(factor)))

        if reconfirm_count > max_boosts:
            # Already at or past the cap — no further increase.
            return current_hl

        new_hl = round(current_hl * factor)
        self._c.execute(
            "UPDATE soma_intel_signal SET half_life_days=? WHERE signal_id=?",
            (new_hl, signal_id),
        )
        return new_hl

    def count_signals_by_status(self, status: str) -> int:
        """Count signals with a given status ('active'|'reconfirmed'|'expired')."""
        return self._c.execute(
            "SELECT COUNT(*) FROM soma_intel_signal WHERE status=?",
            (status,),
        ).fetchone()[0]

    def count_recent_signals(
        self,
        ticker:       str,
        notes_prefix: str,
        since_date:   str,
    ) -> int:
        """
        Count active signals for a given ticker whose notes start with
        `notes_prefix`, created on or after `since_date` (ISO YYYY-MM-DD).
        Used by confirm.py to compute novelty_score.
        """
        return self._c.execute(
            """
            SELECT COUNT(*)
            FROM soma_intel_signal
            WHERE ticker = ?
              AND date  >= ?
              AND (notes LIKE ? OR notes IS NULL)
              AND status  = 'active'
            """,
            (ticker, since_date, notes_prefix + "%"),
        ).fetchone()[0]

    def count_signals_by_ticker_type(
        self,
        ticker:      str,
        signal_type: str,
        since_date:  str,
    ) -> int:
        """
        Count live signals for (ticker, signal_type) in the last N days.
        Used by novelty.py to compute novelty_score.

        signal_type — v1 definition: the `horizon` column value
        ('tactical' | 'thematic' | 'structural').  When signal_propagator is
        updated to write f1..f5 features to live signals, this method should
        be upgraded to extract the dominant feature from the features JSON.

        Args:
            ticker:      Ticker symbol (e.g. 'TSLA')
            signal_type: Horizon string — 'tactical' | 'thematic' | 'structural'
            since_date:  ISO YYYY-MM-DD lower bound (inclusive)

        Returns:
            Count of matching signals.
        """
        return self._c.execute(
            """
            SELECT COUNT(*)
            FROM soma_intel_signal
            WHERE ticker = ?
              AND date   >= ?
              AND horizon = ?
            """,
            (ticker, since_date, signal_type),
        ).fetchone()[0]

    def list_recent_edges_for_ticker(
        self,
        ticker:     str,
        since_ts:   str,
        as_of_date: str,
    ) -> list[dict]:
        """
        Return edges (src→ticker or ticker→dst) with ts between since_ts and
        as_of_date.  Used by confirm.py for corroboration and exclusion checks.
        Returns dicts with keys: edge_id, source_type, edge_type, confidence, ts.
        """
        rows = self._c.execute(
            """
            SELECT e.edge_id, e.source_type, e.edge_type,
                   e.confidence, e.ts
            FROM soma_intel_edge e
            WHERE (e.src_node_id = ? OR e.dst_node_id = ?)
              AND e.ts >= ?
              AND e.ts <= ?
            ORDER BY e.ts DESC
            """,
            (f"co_{ticker}", f"co_{ticker}", since_ts, as_of_date),
        ).fetchall()
        return [dict(r) for r in rows]

    def count_ticker_edges(self, ticker: str) -> int:
        """
        Count all edges where the ticker's company node is source or target.
        Used by confirm.py for the 'effective edge count ≥ 5' gate.

        bt_strict_mode: raises AssertionError — use count_ticker_edges_as_of() instead.
        """
        if getattr(self, "_bt_strict", False):
            raise AssertionError(
                "bt_strict_mode violation: count_ticker_edges() reads ALL edges "
                "regardless of date. Use count_ticker_edges_as_of(ticker, as_of_ts) "
                f"with cutoff={self._bt_cutoff_ts!r} in backtest mode."
            )
        return self._c.execute(
            """
            SELECT COUNT(*)
            FROM soma_intel_edge
            WHERE src_node_id = ?
               OR dst_node_id = ?
            """,
            (f"co_{ticker}", f"co_{ticker}"),
        ).fetchone()[0]

    def count_ticker_edges_as_of(self, ticker: str, as_of_ts: str) -> int:
        """
        Count edges for ticker with ts <= as_of_ts. Backtest-safe version of
        count_ticker_edges(). Use this in historical replay to avoid look-ahead.
        """
        return self._c.execute(
            """
            SELECT COUNT(*)
            FROM soma_intel_edge
            WHERE (src_node_id = ? OR dst_node_id = ?)
              AND ts <= ?
            """,
            (f"co_{ticker}", f"co_{ticker}", as_of_ts),
        ).fetchone()[0]

    # ── Backtest mode (bt_strict) ─────────────────────────────────────────────

    def set_bt_mode(self, cutoff_date: str) -> None:
        """
        Enable backtest strict mode.

        While enabled, calling count_ticker_edges() (which reads ALL edges
        with no date cutoff) raises AssertionError — forcing replay code to
        use count_ticker_edges_as_of() instead.

        cutoff_date: YYYY-MM-DD of the simulation date being processed.
        """
        self._bt_strict = True
        self._bt_cutoff_ts = cutoff_date + "T23:59:59"

    def clear_bt_mode(self) -> None:
        """Disable backtest strict mode."""
        self._bt_strict = False
        self._bt_cutoff_ts = None

    # ── Backtest signal table helpers ─────────────────────────────────────────

    def count_active_backtest_signals_for_date(
        self, run_id: str, date_str: str, priority: str
    ) -> int:
        """
        Count signals in soma_intel_signal_backtest for a given run/date/priority.
        Replaces count_active_signals_for_date() in historical replay (reads
        from the backtest table, not the live signals table).
        """
        return self._c.execute(
            """
            SELECT COUNT(*)
            FROM soma_intel_signal_backtest
            WHERE backtest_run_id = ? AND sim_date = ? AND priority = ?
            """,
            (run_id, date_str, priority),
        ).fetchone()[0]

    def count_recent_backtest_signals(
        self, run_id: str, ticker: str, notes_prefix: str, since_date: str
    ) -> int:
        """
        Novelty counter reading from soma_intel_signal_backtest.
        Replaces count_recent_signals() in historical replay so novelty uses
        only already-written backtest signals (no look-ahead into live table).
        """
        return self._c.execute(
            """
            SELECT COUNT(*)
            FROM soma_intel_signal_backtest
            WHERE backtest_run_id = ?
              AND ticker    = ?
              AND sim_date >= ?
              AND (notes LIKE ? OR notes IS NULL)
            """,
            (run_id, ticker, since_date, notes_prefix + "%"),
        ).fetchone()[0]

    def insert_backtest_signal(
        self,
        run_id:    str,
        sim_date:  str,
        ticker:    str,
        priority:  str,
        anomaly_score: float,
        features_json: str,
        corroboration_count: int,
        half_life_days: int,
        horizon:   str,
        notes:     str,
        regime_label: Optional[str],
    ) -> None:
        """
        Write one generated signal into soma_intel_signal_backtest.
        signal_id is NULL (not copied from live table — these are new signals).
        lookahead_clean is set to 1 (verified by caller).
        """
        self._c.execute(
            """
            INSERT INTO soma_intel_signal_backtest (
                backtest_run_id, sim_date,
                signal_id, ticker, date, priority, anomaly_score, features,
                corroboration_count, half_life_days, reconfirmation_count,
                status, horizon, notes, regime_label, lookahead_clean
            ) VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, 0, 'active', ?, ?, ?, 1)
            """,
            (
                run_id, sim_date,
                ticker, sim_date, priority,
                round(anomaly_score, 4), features_json,
                corroboration_count, half_life_days,
                horizon, notes, regime_label,
            ),
        )

    def count_active_signals_for_date(self, date_str: str, priority: str) -> int:
        """
        Count active signals for a given date and priority.
        Used by anomaly.py to enforce daily caps (P1 ≤ 5, P2 ≤ 10).
        """
        return self._c.execute(
            """
            SELECT COUNT(*)
            FROM soma_intel_signal
            WHERE date = ? AND priority = ? AND status = 'active'
            """,
            (date_str, priority),
        ).fetchone()[0]

    def insert_anomaly_signal(
        self,
        ticker:               str,
        date:                 str,
        priority:             str,
        anomaly_score:        float,
        features_json:        str,
        corroboration_count:  int,
        half_life_days:       int,
        notes:                str,
        horizon:              str = "tactical",
    ) -> int:
        """
        Insert a new signal row from the anomaly engine.
        Returns the new signal_id.
        """
        cur = self._c.execute(
            """
            INSERT OR IGNORE INTO soma_intel_signal
                (ticker, date, priority, anomaly_score, features,
                 corroboration_count, half_life_days, status, horizon, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
            """,
            (ticker, date, priority, round(anomaly_score, 4), features_json,
             corroboration_count, half_life_days, horizon, notes),
        )
        return cur.lastrowid

    # ── Belief sweep helpers ──────────────────────────────────────────────────

    def list_superseded_beliefs_before(self, cutoff_ts: str) -> list[dict]:
        """
        Return superseded beliefs (superseded_by IS NOT NULL) with ts < cutoff_ts.
        Ordered ts ASC (oldest first, matches prune order).
        Returns dicts with keys: belief_id, subject_node_id, predicate, ts.
        """
        rows = self._c.execute(
            """
            SELECT belief_id, subject_node_id, predicate, ts
            FROM soma_intel_belief
            WHERE superseded_by IS NOT NULL
              AND ts < ?
            ORDER BY ts ASC
            """,
            (cutoff_ts,),
        ).fetchall()
        return [dict(r) for r in rows]

    def delete_beliefs_by_ids(self, belief_ids: list[int]) -> int:
        """
        Delete beliefs by primary key. Batches in groups of 500 to stay within
        SQLite limits. Returns total rows deleted.
        """
        if not belief_ids:
            return 0
        deleted = 0
        for i in range(0, len(belief_ids), 500):
            batch = belief_ids[i : i + 500]
            placeholders = ",".join("?" * len(batch))
            self._c.execute(
                f"DELETE FROM soma_intel_belief WHERE belief_id IN ({placeholders})",
                batch,
            )
            deleted += len(batch)
        return deleted

    def count_beliefs_active(self) -> int:
        """Count active (non-superseded) beliefs across all predicates."""
        return self._c.execute(
            "SELECT COUNT(*) FROM soma_intel_belief WHERE superseded_by IS NULL"
        ).fetchone()[0]

    def count_beliefs_superseded(self) -> int:
        """Count superseded (non-active) beliefs."""
        return self._c.execute(
            "SELECT COUNT(*) FROM soma_intel_belief WHERE superseded_by IS NOT NULL"
        ).fetchone()[0]

    # ── Platform management ───────────────────────────────────────────────────

    def list_platforms(
        self,
        filter_ids: Optional[list[str]] = None,
    ) -> list[dict]:
        """
        Return platform rows as dicts. Keys: platform_id, name, adoption_metric,
        curve_K, curve_r, curve_t0, wrights_law_rate, position, last_fit_ts.

        Args:
            filter_ids: if provided, restrict to these platform_id values.
        """
        if filter_ids:
            placeholders = ",".join("?" * len(filter_ids))
            rows = self._c.execute(
                f"SELECT * FROM soma_intel_platform "
                f"WHERE platform_id IN ({placeholders}) ORDER BY platform_id",
                filter_ids,
            ).fetchall()
        else:
            rows = self._c.execute(
                "SELECT * FROM soma_intel_platform ORDER BY platform_id"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_platform(self, platform_id: str) -> Optional[dict]:
        """Return a single platform row as dict, or None if not found."""
        row = self._c.execute(
            "SELECT * FROM soma_intel_platform WHERE platform_id=?",
            (platform_id,),
        ).fetchone()
        return dict(row) if row else None

    def upsert_platform(
        self,
        platform_id: str,
        name: str,
        adoption_metric: str,
        curve_K: Optional[float],
        curve_r: Optional[float],
        curve_t0: Optional[str],
        wrights_law_rate: Optional[float],
        position: Optional[str],
    ) -> None:
        """
        INSERT OR REPLACE a platform row (full upsert — all fields).
        Sets last_fit_ts=NULL (updated later by scurve_fitter).
        """
        self._c.execute(
            """
            INSERT OR REPLACE INTO soma_intel_platform
              (platform_id, name, adoption_metric, curve_K, curve_r, curve_t0,
               wrights_law_rate, position, last_fit_ts)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (platform_id, name, adoption_metric, curve_K, curve_r, curve_t0,
             wrights_law_rate, position),
        )

    def update_platform_curve(
        self,
        platform_id: str,
        K: float,
        r: float,
        t0: str,
        position: str,
        last_fit_ts: str,
    ) -> None:
        """Update fitted curve parameters on an existing platform row."""
        self._c.execute(
            """
            UPDATE soma_intel_platform
            SET curve_K     = ?,
                curve_r     = ?,
                curve_t0    = ?,
                position    = ?,
                last_fit_ts = ?
            WHERE platform_id = ?
            """,
            (K, r, t0, position, last_fit_ts, platform_id),
        )

    def clear_platforms(self) -> None:
        """Delete all rows from soma_intel_platform. Used by --force re-seed."""
        self._c.execute("DELETE FROM soma_intel_platform")

    # ── S-curve history ───────────────────────────────────────────────────────

    def list_scurve_history(self, platform_id: str) -> list[dict]:
        """
        Return all scurve history rows for a platform, ordered by date ASC.
        Keys: date, metric_value (and others from the table).
        """
        rows = self._c.execute(
            """
            SELECT date, metric_value, cumulative_units, unit_cost, source
            FROM soma_intel_scurve_history
            WHERE platform_id = ?
            ORDER BY date ASC
            """,
            (platform_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def insert_scurve_history_row(
        self,
        platform_id: str,
        date: str,
        metric_value: float,
        source: str,
        cumulative_units: Optional[float] = None,
        unit_cost: Optional[float] = None,
    ) -> None:
        """INSERT OR IGNORE a single scurve history row (idempotent by PK)."""
        self._c.execute(
            """
            INSERT OR IGNORE INTO soma_intel_scurve_history
              (platform_id, date, metric_value, cumulative_units, unit_cost, source)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (platform_id, date, metric_value, cumulative_units, unit_cost, source),
        )

    def count_scurve_history(self, platform_id: str) -> int:
        """Count scurve history rows for a given platform_id."""
        return self._c.execute(
            "SELECT COUNT(*) FROM soma_intel_scurve_history WHERE platform_id=?",
            (platform_id,),
        ).fetchone()[0]

    def scurve_history_date_range(
        self, platform_id: str
    ) -> tuple[Optional[str], Optional[str]]:
        """Return (min_date, max_date) for a platform's scurve history, or (None, None)."""
        row = self._c.execute(
            """
            SELECT MIN(date) AS min_d, MAX(date) AS max_d
            FROM soma_intel_scurve_history WHERE platform_id=?
            """,
            (platform_id,),
        ).fetchone()
        return (row["min_d"], row["max_d"]) if row else (None, None)

    def clear_scurve_history(self) -> None:
        """Delete all rows from soma_intel_scurve_history. Used by --force re-seed."""
        self._c.execute("DELETE FROM soma_intel_scurve_history")

    # ── Edge management (ingest helpers) ─────────────────────────────────────

    def count_edges_by_source_type(self, source_type: str) -> int:
        """Count edges with a specific source_type value."""
        return self._c.execute(
            "SELECT COUNT(*) FROM soma_intel_edge WHERE source_type=?",
            (source_type,),
        ).fetchone()[0]

    def count_edges_by_source_types(self, source_types: list[str]) -> int:
        """Count edges whose source_type is any of the provided values (IN clause)."""
        if not source_types:
            return 0
        placeholders = ",".join("?" * len(source_types))
        return self._c.execute(
            f"SELECT COUNT(*) FROM soma_intel_edge WHERE source_type IN ({placeholders})",
            source_types,
        ).fetchone()[0]

    def delete_edges_by_source_type(self, source_type: str) -> int:
        """
        Delete all edges with a given source_type. Returns rows deleted.
        Warning: destructive — caller is responsible for --force guard.
        """
        self._c.execute(
            "DELETE FROM soma_intel_edge WHERE source_type=?",
            (source_type,),
        )
        return self._c.execute("SELECT changes()").fetchone()[0]

    # ── Universe bootstrap ────────────────────────────────────────────────────

    def universe_is_loaded(self) -> bool:
        """Return True if soma_intel_universe has at least one row."""
        row = self._c.execute(
            "SELECT 1 FROM soma_intel_universe LIMIT 1"
        ).fetchone()
        return row is not None

    def count_active_universe(self) -> int:
        """Count active rows in soma_intel_universe."""
        return self._c.execute(
            "SELECT COUNT(*) FROM soma_intel_universe WHERE active=1"
        ).fetchone()[0]

    def load_universe_entry(
        self,
        ticker: str,
        source: str,
        platform_tags: list,
        added_ts: str,
    ) -> None:
        """
        INSERT OR UPDATE a universe row from the initial bulk load (load_universe.py).

        Differs from upsert_universe_ticker: simpler signature, no promotion fields.
        Does not commit — caller must call store.commit() after the batch.
        """
        self._c.execute(
            """
            INSERT INTO soma_intel_universe
              (ticker, source, platform_tags, added_ts, active)
            VALUES (?, ?, ?, ?, 1)
            ON CONFLICT(ticker) DO UPDATE SET
              source        = excluded.source,
              platform_tags = excluded.platform_tags,
              active        = 1
            """,
            (ticker, source, json.dumps(platform_tags), added_ts),
        )

    # ── Node listing (edge extractor) ─────────────────────────────────────────

    def list_nodes_prioritized(self, limit: int = 200) -> list[dict]:
        """
        Return up to `limit` nodes sorted by type priority (company first, then
        platform, regime, security, person, thesis, concept, other).

        Keys: node_id, node_type, name.
        Used by edge_extractor to build the LLM node-context list.
        """
        rows = self._c.execute(
            """
            SELECT node_id, node_type, name FROM soma_intel_node
            ORDER BY
              CASE node_type
                WHEN 'company'  THEN 0
                WHEN 'platform' THEN 1
                WHEN 'regime'   THEN 2
                WHEN 'security' THEN 3
                WHEN 'person'   THEN 4
                WHEN 'thesis'   THEN 5
                WHEN 'concept'  THEN 6
                ELSE 7
              END,
              node_id ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Node type stats ───────────────────────────────────────────────────────

    def node_type_counts(self) -> list[dict]:
        """
        Return list of dicts with keys node_type, c — count per type ordered DESC.
        Used by ingest_oracle summary display.
        """
        rows = self._c.execute(
            """
            SELECT node_type, COUNT(*) AS c
            FROM soma_intel_node GROUP BY node_type ORDER BY c DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]

    def list_company_nodes(self) -> list[dict]:
        """
        Return all company nodes as list of dicts with keys:
        node_id, name, metadata (raw JSON string).
        Used by anomaly.py to build the sector map.
        """
        rows = self._c.execute(
            """
            SELECT node_id, name, metadata
            FROM soma_intel_node
            WHERE node_type = 'company'
            ORDER BY node_id
            """
        ).fetchall()
        return [dict(r) for r in rows]

    # ── SOMA base-table stats (read-only, for bridge summary display) ─────────

    def count_soma_raw_intelligence(self, source_type: str) -> int:
        """
        Count rows in soma's raw_intelligence table by source_type.
        Read-only query against the same soma.db — NOT a graph operation.
        Used exclusively by soma_intel_bridge for stats display.
        """
        try:
            return self._c.execute(
                "SELECT COUNT(*) FROM raw_intelligence WHERE source_type=?",
                (source_type,),
            ).fetchone()[0]
        except Exception:
            return -1  # table may not exist in test envs

    def count_soma_events(self, event_type: str) -> int:
        """
        Count rows in soma's events table by event_type.
        Read-only query against the same soma.db — NOT a graph operation.
        Used exclusively by soma_intel_bridge for stats display.
        """
        try:
            return self._c.execute(
                "SELECT COUNT(*) FROM events WHERE event_type=?",
                (event_type,),
            ).fetchone()[0]
        except Exception:
            return -1  # table may not exist in test envs

    # ── Audit log (migration 022) ─────────────────────────────────────────────

    def record_audit(
        self,
        edge_id: int,
        auditor: str,
        decision: str,
        rationale: Optional[str] = None,
        prior_audit_id: Optional[int] = None,
    ) -> int:
        """
        Append an immutable audit row to soma_intel_audit_log (§K.2).

        Also updates edge.audit_status + audit_ts on the edge row.
        Returns the new audit_id.

        Args:
            edge_id:        edge being audited.
            auditor:        'user' | 'claude_adversarial' | 'meta_learner'.
            decision:       'approved' | 'rejected' | 'corrected' | 're_audited'.
            rationale:      optional free text.
            prior_audit_id: if re-auditing a previously audited edge, chain via this.

        Raises:
            ValueError: if decision is not one of the four valid values.
        """
        _valid_decisions = {"approved", "rejected", "corrected", "re_audited"}
        if decision not in _valid_decisions:
            raise ValueError(
                f"decision must be one of {_valid_decisions}, got {decision!r}"
            )

        now = self._now_iso()

        # Append to immutable log
        cur = self._c.execute(
            """
            INSERT INTO soma_intel_audit_log
              (edge_id, auditor, decision, rationale, ts, prior_audit_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (edge_id, auditor, decision, rationale, now, prior_audit_id),
        )
        audit_id: int = cur.lastrowid  # type: ignore[assignment]

        # Mirror decision onto the edge row for fast filtering
        edge_audit_status = decision if decision != "re_audited" else "approved"
        self._c.execute(
            """
            UPDATE soma_intel_edge
            SET audit_status = ?,
                audit_ts     = ?,
                audit_notes  = ?
            WHERE edge_id = ?
            """,
            (edge_audit_status, now, f"[{auditor}] {rationale or ''}", edge_id),
        )
        self._c.commit()
        log.debug("record_audit: edge %d → %s by %s (audit_id=%d)",
                  edge_id, decision, auditor, audit_id)
        return audit_id

    def list_audit_log(
        self,
        edge_id: Optional[int] = None,
        limit: int = 100,
    ) -> list[dict]:
        """
        Return audit log rows, optionally filtered by edge_id.
        Ordered by ts DESC (most recent first).
        """
        if edge_id is not None:
            rows = self._c.execute(
                """
                SELECT * FROM soma_intel_audit_log
                WHERE edge_id=? ORDER BY ts DESC LIMIT ?
                """,
                (edge_id, limit),
            ).fetchall()
        else:
            rows = self._c.execute(
                "SELECT * FROM soma_intel_audit_log ORDER BY ts DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ── Edge audit helpers (used by audit_engine.py) ──────────────────────────

    def list_edges_for_audit(
        self,
        min_confidence:      float = 0.30,
        audit_status_filter: Optional[list[str]] = None,
        limit:               int   = 5000,
    ) -> list[dict]:
        """
        Return edges eligible for audit: confidence >= min_confidence,
        optionally filtered to specific audit_status values.
        Returns dicts with all soma_intel_edge columns.
        """
        if audit_status_filter:
            placeholders = ",".join("?" * len(audit_status_filter))
            rows = self._c.execute(
                f"""
                SELECT * FROM soma_intel_edge
                WHERE confidence >= ?
                  AND audit_status IN ({placeholders})
                ORDER BY confidence ASC, ts DESC
                LIMIT ?
                """,
                [min_confidence, *audit_status_filter, limit],
            ).fetchall()
        else:
            rows = self._c.execute(
                """
                SELECT * FROM soma_intel_edge
                WHERE confidence >= ?
                ORDER BY confidence ASC, ts DESC
                LIMIT ?
                """,
                (min_confidence, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_edge(self, edge_id: int) -> Optional[dict]:
        """Return a single edge row as dict, or None if not found."""
        row = self._c.execute(
            "SELECT * FROM soma_intel_edge WHERE edge_id=?", (edge_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_last_audit_ts_map(self) -> dict[int, str]:
        """
        Return {edge_id → most_recent_audit_ts} for all edges that have at
        least one audit log entry. Used by audit_engine queue builder.
        """
        rows = self._c.execute(
            """
            SELECT edge_id, MAX(ts) AS last_ts
            FROM soma_intel_audit_log
            GROUP BY edge_id
            """
        ).fetchall()
        return {r["edge_id"]: r["last_ts"] for r in rows}

    def update_edge_audit_status(
        self,
        edge_id:      int,
        audit_status: str,
        audit_ts:     str,
        audit_notes:  Optional[str] = None,
    ) -> None:
        """Update the audit_status, audit_ts, and audit_notes on an edge."""
        self._c.execute(
            """
            UPDATE soma_intel_edge
            SET audit_status = ?, audit_ts = ?, audit_notes = ?
            WHERE edge_id = ?
            """,
            (audit_status, audit_ts, audit_notes, edge_id),
        )

    def audit_coverage_stats(self) -> list[dict]:
        """
        Return [{audit_status, n}] for all edges grouped by audit_status.
        Used by audit_engine --stats.
        """
        rows = self._c.execute(
            """
            SELECT audit_status, COUNT(*) AS n
            FROM soma_intel_edge
            GROUP BY audit_status
            ORDER BY n DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]

    def edge_confidence_band_counts(self) -> list[dict]:
        """
        Return [{band, n}] showing count of edges per confidence band.
        Bands: low (<0.55), mid (0.55-0.75), high (0.75-0.95), top (≥0.95).
        """
        rows = self._c.execute(
            """
            SELECT
              CASE
                WHEN confidence < 0.55 THEN 'low'
                WHEN confidence < 0.75 THEN 'mid'
                WHEN confidence < 0.95 THEN 'high'
                ELSE 'top'
              END AS band,
              COUNT(*) AS n
            FROM soma_intel_edge
            WHERE confidence >= 0.30
            GROUP BY band
            ORDER BY band
            """
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Source calibration (migration 022) ────────────────────────────────────

    def upsert_source_calibration(
        self,
        source_id: str,
        multiplier: float,
        brier_score: Optional[float],
        n_observations: int,
        last_updated: str,
    ) -> None:
        """Upsert a calibration row for a source. Used by calibration.py (§K.3)."""
        self._c.execute(
            """
            INSERT INTO soma_intel_source_calibration
              (source_id, multiplier, brier_score, n_observations, last_updated)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(source_id) DO UPDATE SET
              multiplier     = excluded.multiplier,
              brier_score    = excluded.brier_score,
              n_observations = excluded.n_observations,
              last_updated   = excluded.last_updated
            """,
            (source_id, multiplier, brier_score, n_observations, last_updated),
        )
        self._c.commit()

    def get_source_calibration(self, source_id: str) -> Optional[dict]:
        """Return calibration row for a source_id, or None."""
        row = self._c.execute(
            "SELECT * FROM soma_intel_source_calibration WHERE source_id=?",
            (source_id,),
        ).fetchone()
        return dict(row) if row else None

    def list_source_calibrations(self) -> list[dict]:
        """Return all source calibration rows ordered by multiplier ASC (worst first)."""
        rows = self._c.execute(
            "SELECT * FROM soma_intel_source_calibration ORDER BY multiplier ASC"
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Regime + Baseline (migration 021, populated by regime.py + baseline.py) ──

    def upsert_regime_row(
        self,
        date: str,
        trend_state: str,
        vol_state: str,
        macro_state: str,
        composite_label: str,
        confidence: float,
        features: dict,
    ) -> None:
        """
        UPSERT one daily regime row to soma_intel_regime.
        Idempotent: running twice for the same date is safe.
        """
        self._c.execute(
            """
            INSERT INTO soma_intel_regime
              (date, trend_state, vol_state, macro_state, composite_label,
               confidence, features)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
              trend_state     = excluded.trend_state,
              vol_state       = excluded.vol_state,
              macro_state     = excluded.macro_state,
              composite_label = excluded.composite_label,
              confidence      = excluded.confidence,
              features        = excluded.features
            """,
            (date, trend_state, vol_state, macro_state, composite_label,
             confidence, json.dumps(features)),
        )

    def get_regime_row(self, date: str) -> Optional[dict]:
        """Return the regime row for a specific date, or None."""
        row = self._c.execute(
            "SELECT * FROM soma_intel_regime WHERE date=?",
            (date,),
        ).fetchone()
        if row is None:
            return None
        d = dict(row)
        d["features"] = json.loads(d["features"] or "{}")
        return d

    def list_regime_rows(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> list[dict]:
        """
        Return regime rows, optionally filtered by date range.
        Ordered by date ASC. Parses 'features' JSON column.
        """
        clauses: list[str] = []
        params: list[Any] = []
        if start_date:
            clauses.append("date >= ?")
            params.append(start_date)
        if end_date:
            clauses.append("date <= ?")
            params.append(end_date)
        sql = "SELECT * FROM soma_intel_regime"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY date ASC"
        if limit:
            sql += f" LIMIT {int(limit)}"
        rows = self._c.execute(sql, params).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["features"] = json.loads(d["features"] or "{}")
            result.append(d)
        return result

    def upsert_baseline(
        self,
        ticker: str,
        regime_label: str,
        feature: str,
        mean: float,
        stdev: float,
        n_days: int,
        is_provisional: int,
        last_updated: str,
    ) -> None:
        """
        UPSERT one baseline row (ticker × regime × feature).
        Called by baseline.py after computing regime-conditional statistics.
        """
        self._c.execute(
            """
            INSERT INTO soma_intel_baseline
              (ticker, regime_label, feature, mean, stdev, n_days,
               is_provisional, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker, regime_label, feature) DO UPDATE SET
              mean           = excluded.mean,
              stdev          = excluded.stdev,
              n_days         = excluded.n_days,
              is_provisional = excluded.is_provisional,
              last_updated   = excluded.last_updated
            """,
            (ticker, regime_label, feature, mean, stdev, n_days,
             is_provisional, last_updated),
        )

    def get_baseline(
        self,
        ticker: str,
        regime_label: str,
        feature: str,
    ) -> Optional[dict]:
        """Return baseline row for (ticker, regime_label, feature), or None."""
        row = self._c.execute(
            """
            SELECT * FROM soma_intel_baseline
            WHERE ticker=? AND regime_label=? AND feature=?
            """,
            (ticker, regime_label, feature),
        ).fetchone()
        return dict(row) if row else None

    def list_baselines_for_ticker(
        self,
        ticker: str,
        regime_label: Optional[str] = None,
    ) -> list[dict]:
        """
        Return baseline rows for a ticker, optionally filtered by regime_label.
        """
        if regime_label:
            rows = self._c.execute(
                """
                SELECT * FROM soma_intel_baseline
                WHERE ticker=? AND regime_label=?
                """,
                (ticker, regime_label),
            ).fetchall()
        else:
            rows = self._c.execute(
                "SELECT * FROM soma_intel_baseline WHERE ticker=?",
                (ticker,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ── Price history (Migration 023 — backtest harness P5.3) ─────────────────

    def upsert_price(
        self,
        ticker: str,
        date:   str,
        close:  float,
        volume: Optional[float] = None,
    ) -> None:
        """
        Insert or replace a daily closing price row.
        Idempotent: if (ticker, date) already exists, it is replaced.
        """
        self._c.execute(
            """
            INSERT OR REPLACE INTO soma_intel_price_history (ticker, date, close, volume)
            VALUES (?, ?, ?, ?)
            """,
            (ticker, date, close, volume),
        )

    def get_price_series(
        self,
        ticker:     str,
        start_date: str,
        end_date:   str,
    ) -> list[dict]:
        """
        Return list of {date, close, volume} dicts for ticker between start_date
        and end_date inclusive, ordered by date ascending.
        Returns [] if no data.
        """
        rows = self._c.execute(
            """
            SELECT date, close, volume
            FROM soma_intel_price_history
            WHERE ticker=? AND date >= ? AND date <= ?
            ORDER BY date ASC
            """,
            (ticker, start_date, end_date),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_forward_return(
        self,
        ticker:        str,
        signal_date:   str,
        horizon_days:  int,
    ) -> Optional[float]:
        """
        Compute the forward return for ticker from signal_date over horizon_days
        calendar days (not trading days — uses nearest available close on or
        after the target date).

        Returns (forward_close / signal_close - 1) as a decimal, or None if
        either the signal_date close or the forward close is missing.

        Note: horizon_days here is a calendar-day offset. For a 60-trading-day
        backtest, pass ~84 calendar days (60 * 252/365 ≈ 84). The backtest
        harness uses the spec's 60 trading-day convention: caller passes
        horizon_days=84 or uses get_forward_return_trading() which counts
        actual trading days from the price series.
        """
        from datetime import date as _date, timedelta

        # Signal-date close
        signal_row = self._c.execute(
            """
            SELECT close FROM soma_intel_price_history
            WHERE ticker=? AND date=?
            """,
            (ticker, signal_date),
        ).fetchone()
        if signal_row is None:
            return None
        signal_close = signal_row["close"]

        # Forward close: nearest available close on or after signal_date + horizon
        target_dt  = _date.fromisoformat(signal_date) + timedelta(days=horizon_days)
        target_str = target_dt.isoformat()

        fwd_row = self._c.execute(
            """
            SELECT close FROM soma_intel_price_history
            WHERE ticker=? AND date >= ?
            ORDER BY date ASC LIMIT 1
            """,
            (ticker, target_str),
        ).fetchone()
        if fwd_row is None:
            return None

        return (fwd_row["close"] / signal_close) - 1.0

    def count_price_history_rows(self, ticker: Optional[str] = None) -> int:
        """Count price history rows, optionally filtered to a single ticker."""
        if ticker:
            return self._c.execute(
                "SELECT COUNT(*) FROM soma_intel_price_history WHERE ticker=?",
                (ticker,),
            ).fetchone()[0]
        return self._c.execute(
            "SELECT COUNT(*) FROM soma_intel_price_history"
        ).fetchone()[0]

    def count_price_history_tickers(self) -> int:
        """Count distinct tickers with at least one price row."""
        return self._c.execute(
            "SELECT COUNT(DISTINCT ticker) FROM soma_intel_price_history"
        ).fetchone()[0]

    def get_price_date_range(self, ticker: str) -> Optional[tuple[str, str]]:
        """Return (min_date, max_date) for a ticker, or None if no data."""
        row = self._c.execute(
            "SELECT MIN(date), MAX(date) FROM soma_intel_price_history WHERE ticker=?",
            (ticker,),
        ).fetchone()
        if row[0] is None:
            return None
        return (row[0], row[1])

    # ── Meta-learner threshold history (Migration 025) ─────────────────────────

    def get_cell_threshold(
        self,
        cell_key:       str,
        default_threshold: float,
    ) -> float:
        """
        Return the most recent adjusted P1 threshold for a meta-learner cell,
        or `default_threshold` if no history exists for this cell.

        cell_key format: "<regime_composite_label>|<sector>|<dominant_feature>"
        Example: "bull_low_easing|ai_compute|f3_rvol_z"

        Args:
            cell_key:          The 3-axis cell key.
            default_threshold: Base threshold to return when no history.

        Returns:
            float: Effective threshold for this cell.
        """
        try:
            row = self._c.execute(
                """
                SELECT new_threshold
                FROM soma_intel_threshold_history
                WHERE cell_key = ?
                ORDER BY applied_ts DESC
                LIMIT 1
                """,
                (cell_key,),
            ).fetchone()
            return float(row[0]) if row else default_threshold
        except Exception:
            return default_threshold

    def append_threshold_adjustment(
        self,
        cell_key:        str,
        prior_threshold: float,
        new_threshold:   float,
        adjustment:      float,
        reason:          str,
    ) -> None:
        """
        Append a threshold adjustment record (append-only — no UPDATE/DELETE allowed).

        Args:
            cell_key:        3-axis cell key.
            prior_threshold: Threshold before adjustment.
            new_threshold:   Threshold after adjustment.
            adjustment:      Delta applied (±0.1 typically).
            reason:          Human-readable reason (e.g. "false_negatives:5").
        """
        from datetime import datetime, timezone
        applied_ts = datetime.now(timezone.utc).isoformat()
        self._c.execute(
            """
            INSERT INTO soma_intel_threshold_history
              (cell_key, prior_threshold, new_threshold, adjustment, reason, applied_ts)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (cell_key, prior_threshold, new_threshold, adjustment, reason, applied_ts),
        )
        self._conn.commit()
