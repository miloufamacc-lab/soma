"""
draft_store.py
SQLite-backed store for social pipeline drafts.

Usage:
    from pathlib import Path
    from shared.social_tools.draft_store import DraftStore

    store = DraftStore(Path("cipher/pipelines/darkframe/darkframe.db"))
    draft_id = store.save_draft(
        pipeline="darkframe",
        post_text="tesla's inference bill will exceed their cloud bill by 2026.",
        pillar="AI_COMPUTE",
        topic_domain="robotics",
    )
    store.mark_approved(draft_id)
    store.close()

Schema:
    drafts          — one row per draft, tracks full lifecycle
    saturation_logs — Grok saturation results linked to a draft
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS drafts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at   TEXT NOT NULL,
    pipeline     TEXT NOT NULL,
    pillar       TEXT,
    topic_domain TEXT,
    post_text    TEXT NOT NULL,
    gate_results TEXT,               -- JSON blob of gate output
    status       TEXT NOT NULL DEFAULT 'draft',  -- draft|approved|posted|killed
    posted_at    TEXT,
    post_url     TEXT,
    notes        TEXT
);

CREATE TABLE IF NOT EXISTS saturation_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    draft_id        INTEGER REFERENCES drafts(id),
    query           TEXT,
    results_summary TEXT,
    decision        TEXT,
    logged_at       TEXT
);
"""

_VALID_STATUSES = {"draft", "approved", "posted", "killed"}


# ---------------------------------------------------------------------------
# DraftStore class
# ---------------------------------------------------------------------------

class DraftStore:
    """
    Thread-safe (single-connection) SQLite store for draft content.
    Pass the full path to the pipeline's .db file.
    Never use Path.home() — always pass an explicit absolute path.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def save_draft(
        self,
        pipeline: str,
        post_text: str,
        pillar: str | None = None,
        topic_domain: str | None = None,
        gate_results: dict | None = None,
        notes: str | None = None,
    ) -> int:
        """
        Insert a new draft. Returns the new draft id.

        Args:
            pipeline:     Pipeline name (e.g. "darkframe", "drycapital", "linkedin").
            post_text:    The draft post content.
            pillar:       Content pillar tag (e.g. "AI_COMPUTE", "ENERGY_TRANSITION").
            topic_domain: Topic domain (e.g. "robotics", "macro").
            gate_results: Dict of gate evaluation results (will be JSON-serialised).
            notes:        Free-text notes for the operator.

        Returns:
            Integer draft id.
        """
        gate_json = json.dumps(gate_results) if gate_results else None
        cur = self._conn.execute(
            """
            INSERT INTO drafts
                (created_at, pipeline, pillar, topic_domain, post_text, gate_results, status, notes)
            VALUES (?, ?, ?, ?, ?, ?, 'draft', ?)
            """,
            (_now(), pipeline, pillar, topic_domain, post_text, gate_json, notes),
        )
        self._conn.commit()
        return cur.lastrowid

    def mark_approved(self, draft_id: int) -> None:
        """Approve a draft — moves it to the queue."""
        self._conn.execute(
            "UPDATE drafts SET status = 'approved' WHERE id = ?", (draft_id,)
        )
        self._conn.commit()

    def mark_posted(self, draft_id: int, post_url: str | None = None) -> None:
        """Mark a draft as posted. Records the timestamp and URL."""
        self._conn.execute(
            "UPDATE drafts SET status = 'posted', posted_at = ?, post_url = ? WHERE id = ?",
            (_now(), post_url, draft_id),
        )
        self._conn.commit()

    def mark_killed(self, draft_id: int, reason: str | None = None) -> None:
        """Kill a draft (rejected, will not be used)."""
        self._conn.execute(
            "UPDATE drafts SET status = 'killed', notes = ? WHERE id = ?",
            (reason, draft_id),
        )
        self._conn.commit()

    def log_saturation(
        self,
        draft_id: int,
        query: str,
        results_summary: str,
        decision: str,
    ) -> None:
        """Append a Grok saturation check result to a draft."""
        self._conn.execute(
            """
            INSERT INTO saturation_logs (draft_id, query, results_summary, decision, logged_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (draft_id, query, results_summary, decision, _now()),
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def list_drafts(
        self,
        pipeline: str | None = None,
        status: str | None = None,
    ) -> list[dict]:
        """
        Return drafts as a list of dicts, newest first.
        Optionally filter by pipeline name or status.
        """
        query = "SELECT * FROM drafts WHERE 1=1"
        params: list = []
        if pipeline:
            query += " AND pipeline = ?"
            params.append(pipeline)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC"
        cur = self._conn.execute(query, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def get_draft(self, draft_id: int) -> dict | None:
        """Return a single draft by id, or None if not found."""
        cur = self._conn.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,))
        cols = [d[0] for d in cur.description]
        row = cur.fetchone()
        return dict(zip(cols, row)) if row else None

    def get_pillar_history(
        self,
        n_days: int,
        pipeline: str | None = None,
    ) -> list[dict]:
        """
        Return pillar usage summary for approved/posted drafts in the last n_days.
        Useful for checking which pillars have been used recently.

        Returns list of dicts: [{pillar, count, last_used}, ...]
        """
        cutoff = (datetime.now(timezone.utc) - timedelta(days=n_days)).isoformat()
        query = """
            SELECT pillar, COUNT(*) AS count, MAX(created_at) AS last_used
            FROM drafts
            WHERE created_at >= ?
              AND status IN ('approved', 'posted')
        """
        params: list = [cutoff]
        if pipeline:
            query += " AND pipeline = ?"
            params.append(pipeline)
        query += " GROUP BY pillar ORDER BY last_used DESC"
        rows = self._conn.execute(query, params).fetchall()
        return [{"pillar": r[0], "count": r[1], "last_used": r[2]} for r in rows]

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    def __enter__(self) -> "DraftStore":
        return self

    def __exit__(self, *_) -> None:
        self.close()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    """Current UTC timestamp as ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()
