"""
wiki_reader.py — single read-only bridge from DABEIBA modules to the wiki knowledge base.

Phase 2.1 of the Wiki/SOMA wiring plan. Every module that wants to enrich a
prompt with wiki context imports from here rather than reaching into
`wiki/indexes/articles.sqlite` or shelling out to `wiki_search.py`.

Design goals:
  - Zero wiki-package imports (no dependency on wiki_common.py).
  - Fail-open: if the index is missing or a query fails, return [] with a
    warning. Never crash the caller.
  - Path overridable via $WIKI_DB_PATH for testing.
  - Return rich dicts: title, slug, domain, ticker, entity_type, excerpt,
    tags (best-effort), confidence (0..1 normalized BM25).

Public API:
    get_wiki_articles(query, top_k=5, domain=None)       -> list[dict]
    format_wiki_context(articles, max_chars=2000)        -> str  (prompt block)

Typical caller pattern:
    from shared.soma.wiki_reader import get_wiki_articles, format_wiki_context
    articles = get_wiki_articles("PLTR AI Palantir", top_k=5)
    wiki_block = format_wiki_context(articles)
    # inject wiki_block as a system-context section of the LLM prompt

Python 3.9+.
"""

from __future__ import annotations

import logging
import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("soma.wiki_reader")

# ---------------------------------------------------------------------------
# DB path resolution — mirrors wiki/tools/wiki_search.py
# ---------------------------------------------------------------------------


def _resolve_wiki_db_path() -> Path:
    """Priority: $WIKI_DB_PATH > $DABEIBA_ROOT/wiki/indexes/articles.sqlite > ~/Desktop/DABEIBA/..."""
    env = os.environ.get("WIKI_DB_PATH")
    if env:
        return Path(env)
    dab = os.environ.get("DABEIBA_ROOT")
    if dab:
        return Path(dab) / "wiki" / "indexes" / "articles.sqlite"
    default = Path.home() / "Desktop" / "DABEIBA" / "wiki" / "indexes" / "articles.sqlite"
    if default.exists():
        return default
    # Walk up from this file as last-resort
    here = Path(__file__).resolve()
    for parent in here.parents:
        if parent.name == "DABEIBA":
            return parent / "wiki" / "indexes" / "articles.sqlite"
    return default


WIKI_DB_PATH = _resolve_wiki_db_path()


# ---------------------------------------------------------------------------
# FTS5 query sanitization
# ---------------------------------------------------------------------------

_FTS5_STRIP = re.compile(r'["\(\)\*\.\,\;\:\!\?]')
_MULTISPACE = re.compile(r"\s+")
# Tokens shorter than 2 chars or longer than 40 are dropped (noise/pathological input).
_MIN_TOKEN = 2
_MAX_TOKEN = 40
# Basic English stop words — keep this tiny; FTS5 already handles the heavy lifting.
_STOP_WORDS = frozenset({
    "a", "an", "the", "of", "to", "in", "on", "at", "for", "and", "or", "is",
    "are", "was", "were", "be", "been", "being", "had", "have", "has", "by",
    "with", "as", "this", "that", "it", "its", "from", "but",
})


def _sanitize_query(q: str, mode: str = "broad") -> str:
    """Strip FTS5 specials and build a safe query string.

    mode='broad' (default): tokens joined with OR — higher recall, good for
      auto-generated queries from raw notes.
    mode='narrow': tokens joined with spaces (implicit AND) — higher precision,
      only when the caller knows exactly what to match.
    """
    if not q:
        return ""
    cleaned = _FTS5_STRIP.sub(" ", q).strip()
    cleaned = _MULTISPACE.sub(" ", cleaned).strip()
    if not cleaned:
        return ""
    if mode == "narrow":
        return cleaned
    tokens = [
        t for t in cleaned.split(" ")
        if _MIN_TOKEN <= len(t) <= _MAX_TOKEN and t.lower() not in _STOP_WORDS
    ]
    if not tokens:
        return ""
    # Cap at 15 tokens to keep the FTS5 query plan fast.
    return " OR ".join(tokens[:15])


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_wiki_articles(
    query: str,
    top_k: int = 5,
    domain: Optional[str] = None,
    db_path: Optional[str] = None,
    mode: str = "broad",
) -> list[dict[str, Any]]:
    """
    Run a full-text search over the wiki FTS5 index.

    Args:
        query: free-text query. Tickers, keywords, and topic words all work.
        top_k: max articles to return (default 5).
        domain: optional filter — e.g. 'companies', 'doctrines', 'concepts'.
        db_path: override path (tests). Default resolves via $WIKI_DB_PATH.

    Returns:
        list of dicts, each:
            {
                'slug':        str,
                'title':       str,
                'domain':      str,
                'entity_type': str,
                'ticker':      str | None,
                'tags':        list[str],
                'excerpt':     str,   # BM25 snippet with >>>/<<< highlight
                'confidence':  float, # 0..1, higher = more relevant
            }
        Returns [] on any failure (missing index, empty query, bad SQL).
    """
    path = Path(db_path) if db_path else WIKI_DB_PATH

    if not path.is_file():
        logger.warning("wiki_reader: index not found at %s — returning [].", path)
        return []

    safe_q = _sanitize_query(query, mode=mode)
    if not safe_q:
        return []

    try:
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row

        sql = """
            SELECT slug, title, domain, entity_type, ticker, tags,
                   snippet(articles_fts, 6, '>>>', '<<<', '...', 40) AS excerpt,
                   rank
            FROM articles_fts
            WHERE articles_fts MATCH ?
        """
        params: list[Any] = [safe_q]
        if domain:
            sql += " AND domain = ?"
            params.append(domain)
        sql += " ORDER BY rank LIMIT ?"
        params.append(top_k)

        rows = conn.execute(sql, params).fetchall()
        conn.close()

        if not rows:
            return []

        # BM25 rank in SQLite FTS5 is negative — lower is better. Normalize to 0..1
        # confidence where the top hit = 1.0. Empty-weight guard.
        ranks = [abs(float(r["rank"])) for r in rows]
        rmax = max(ranks) if ranks else 1.0
        if rmax <= 0:
            rmax = 1.0

        out: list[dict[str, Any]] = []
        for r in rows:
            rank_val = abs(float(r["rank"]))
            confidence = round(rank_val / rmax, 3)
            tags_raw = r["tags"] or ""
            # Tags are stored as space-separated or comma-separated string; handle both.
            tags = [t for t in re.split(r"[,\s]+", tags_raw) if t]
            out.append({
                "slug": r["slug"],
                "title": r["title"],
                "domain": r["domain"],
                "entity_type": r["entity_type"],
                "ticker": r["ticker"] or None,
                "tags": tags,
                "excerpt": r["excerpt"] or "",
                "confidence": confidence,
            })
        return out

    except sqlite3.OperationalError as e:
        logger.warning("wiki_reader: FTS5 query failed (%s) — returning [].", e)
        return []
    except Exception as e:
        logger.warning("wiki_reader: unexpected error (%s) — returning [].", e)
        return []


def format_wiki_context(
    articles: list[dict[str, Any]],
    max_chars: int = 2000,
    header: str = "## WIKI PRIORS",
) -> str:
    """
    Format a list of wiki articles into a compact markdown block suitable
    for injection into an LLM prompt as system context.

    Truncates at `max_chars` to preserve prompt budget.
    Returns empty string if articles is empty.
    """
    if not articles:
        return ""

    lines = [header, ""]
    for a in articles:
        slug = a.get("slug", "?")
        title = a.get("title", "?")
        conf = a.get("confidence", 0.0)
        excerpt = (a.get("excerpt") or "").replace("\n", " ").strip()
        ticker = a.get("ticker")
        tic_tag = f" [{ticker}]" if ticker else ""
        lines.append(f"- **{title}**{tic_tag} (`{slug}`, conf={conf})")
        if excerpt:
            lines.append(f"  {excerpt}")
    block = "\n".join(lines)
    if len(block) > max_chars:
        block = block[: max_chars - 3].rstrip() + "..."
    return block


# ---------------------------------------------------------------------------
# CLI smoke test: `python -m shared.soma.wiki_reader "PLTR AI"`
# ---------------------------------------------------------------------------

if __name__ == "__main__":  # pragma: no cover
    import sys

    logging.basicConfig(level=logging.INFO)
    q = " ".join(sys.argv[1:]) or "Palantir"
    results = get_wiki_articles(q, top_k=5)
    print(f"query: {q!r}")
    print(f"db:    {WIKI_DB_PATH}")
    print(f"hits:  {len(results)}")
    for r in results:
        print(f"  [{r['confidence']:.2f}] {r['title']} ({r['slug']})")
        if r["excerpt"]:
            print(f"        {r['excerpt'][:120]}")
    print()
    print(format_wiki_context(results))
