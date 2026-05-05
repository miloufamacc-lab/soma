#!/usr/bin/env python3
"""
SOMA-INTEL Step 1.1 — Wiki Article Ingestor

Walks wiki/compiled/**/*.md, parses YAML frontmatter, and writes to soma.db:

  Nodes — one per article:
    entity_type=company  + ticker   → node_id=co_<TICKER>   node_type=company
    entity_type=company  + no ticker→ node_id=co_<slug>     node_type=company
    entity_type=person              → node_id=pn_<slug>     node_type=person
    entity_type=concept (finance)   → node_id=th_<slug>     node_type=thesis
    entity_type=concept (other)     → node_id=cn_<slug>     node_type=concept
    everything else                 → node_id=cn_<slug>     node_type=concept

  Edges per article:
    concept_links → mentioned_in    (src=article_node → dst=linked_node)
    company×platform_tags → belongs_to_platform (co_TICKER → pl_<X>)

Platform nodes (pl_ai, pl_robotics, pl_energy_storage, pl_multi_omics, pl_blockchain)
are upserted as node_type="platform" before any article ingest.

Idempotency:
  Nodes: upsert (safe to re-run).
  Edges: --apply without --force skips if wiki edges already exist in DB.
         --force deletes all edges with source_type='wiki' then re-inserts.

Usage:
  python3 soma/intel/ingest_wiki.py               # dry run — reports what would happen
  python3 soma/intel/ingest_wiki.py --apply        # write nodes + edges
  python3 soma/intel/ingest_wiki.py --apply --force  # wipe wiki edges, re-ingest all
  python3 soma/intel/ingest_wiki.py --apply --verbose  # show per-article detail
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

# ── Path bootstrap ────────────────────────────────────────────────────────────
_HERE     = Path(__file__).resolve().parent
_DABEIBA  = _HERE.parent.parent.parent
for _p in [str(_DABEIBA), str(_DABEIBA / "shared")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from soma.intel.store import IntelStore

try:
    import yaml
    _YAML_OK = True
except ImportError:
    _YAML_OK = False

# ── Config ────────────────────────────────────────────────────────────────────
WIKI_ROOT    = _DABEIBA / "wiki"
COMPILED_DIR = WIKI_ROOT / "compiled"

DB_PATH = (
    Path(os.environ["SOMA_DB_PATH"])
    if "SOMA_DB_PATH" in os.environ
    else _DABEIBA / "shared" / "soma" / "data" / "soma.db"
)

log = logging.getLogger(__name__)

# ── Platform nodes to pre-upsert ─────────────────────────────────────────────
_PLATFORM_NODES: dict[str, str] = {
    "pl_ai":             "AI & Machine Learning Platform",
    "pl_robotics":       "Robotics & Automation Platform",
    "pl_energy_storage": "Energy Storage & Clean-Tech Platform",
    "pl_multi_omics":    "Multi-Omics & Genomics Platform",
    "pl_blockchain":     "Blockchain & Digital Assets Platform",
}

# ── Node-type / node-id derivation ───────────────────────────────────────────

_FINANCE_DOMAINS = frozenset({"finance"})
_COMPANY_TYPES   = frozenset({"company", "company_private"})
_PERSON_TYPES    = frozenset({"person"})

def _slug_from_path(path: Path) -> str:
    """Extract slug = filename stem (no extension)."""
    return path.stem


def _derive_node(entity_type: str, slug: str, domain: str, ticker: str) -> tuple[str, str]:
    """
    Return (node_id, node_type) from article metadata.

    node_type values: company | person | thesis | concept | platform
    """
    et = (entity_type or "").strip('"').lower()
    d  = (domain or "").strip('"').lower()
    t  = (ticker or "").strip().upper()

    if et in _COMPANY_TYPES:
        nid = f"co_{t}" if t else f"co_{slug}"
        return nid, "company"

    if et in _PERSON_TYPES:
        return f"pn_{slug}", "person"

    if et == "concept":
        if d in _FINANCE_DOMAINS:
            return f"th_{slug}", "thesis"
        return f"cn_{slug}", "concept"

    # qna, transcript, transcript_qna, topic, sector, protocol, report, etc.
    return f"cn_{slug}", "concept"


# ── Frontmatter parser ───────────────────────────────────────────────────────

_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _clean_yaml_value(v: Any) -> Any:
    """Convert [INJECTED_BY_PIPELINE] placeholders to None."""
    if isinstance(v, str) and "INJECTED_BY_PIPELINE" in v:
        return None
    if isinstance(v, list):
        cleaned = [_clean_yaml_value(i) for i in v]
        return [i for i in cleaned if i is not None]
    return v


def _parse_frontmatter(text: str) -> Optional[dict]:
    """
    Extract and parse YAML frontmatter block.
    Returns None if no frontmatter present.
    Falls back to a simple key: value regex parser if PyYAML not available.
    """
    m = _FM_RE.match(text)
    if not m:
        return None
    fm_text = m.group(1)

    if _YAML_OK:
        try:
            raw = yaml.safe_load(fm_text) or {}
        except yaml.YAMLError:
            return None
        return {k: _clean_yaml_value(v) for k, v in raw.items()}

    # Fallback: line-by-line simple parser for scalar values only
    result: dict = {}
    for line in fm_text.splitlines():
        if ":" in line and not line.startswith(" "):
            key, _, val = line.partition(":")
            result[key.strip()] = val.strip().strip('"')
    return result


# ── Article dataclass ─────────────────────────────────────────────────────────

@dataclass
class WikiArticle:
    path: Path
    slug: str
    node_id: str
    node_type: str
    title: str
    entity_type: str
    domain: str
    ticker: str
    aliases: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    concept_links: list[str] = field(default_factory=list)
    confidence: float = 0.70
    review_status: str = "auto"
    freshness_policy: str = "static"

    @property
    def source_id(self) -> str:
        rel = self.path.relative_to(WIKI_ROOT)
        return f"wiki:{rel.as_posix()}"

    @property
    def metadata(self) -> dict:
        return {
            "entity_type":      self.entity_type,
            "domain":           self.domain,
            "tags":             self.tags,
            "review_status":    self.review_status,
            "freshness_policy": self.freshness_policy,
            "wiki_path":        self.source_id,
        }


# ── Scanner ───────────────────────────────────────────────────────────────────

def _scan_articles() -> tuple[list[WikiArticle], list[Path]]:
    """
    Walk COMPILED_DIR, parse all non-MOC .md files.

    Returns:
        articles   — successfully parsed WikiArticle list
        skipped    — paths that had no parseable frontmatter
    """
    articles: list[WikiArticle] = []
    skipped: list[Path] = []

    for path in sorted(COMPILED_DIR.rglob("*.md")):
        # skip Maps-of-Content
        if path.stem.startswith("MOC_"):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            skipped.append(path)
            continue

        fm = _parse_frontmatter(text)
        if not fm:
            skipped.append(path)
            continue

        slug        = _slug_from_path(path)
        entity_type = (fm.get("entity_type") or "concept")
        domain      = (fm.get("domain") or "")
        ticker      = (fm.get("ticker") or "")
        title       = (fm.get("title") or slug)
        node_id, node_type = _derive_node(entity_type, slug, domain, ticker)

        # aliases: may be list or None
        raw_aliases = fm.get("aliases") or []
        if isinstance(raw_aliases, list):
            aliases = [str(a) for a in raw_aliases if a]
        else:
            aliases = []

        # tags
        raw_tags = fm.get("tags") or []
        tags = [str(t) for t in raw_tags if t] if isinstance(raw_tags, list) else []

        # concept_links
        raw_links = fm.get("concept_links") or []
        concept_links = [str(l) for l in raw_links if l] if isinstance(raw_links, list) else []

        # confidence
        try:
            confidence = float(fm.get("confidence") or 0.70)
        except (TypeError, ValueError):
            confidence = 0.70
        confidence = max(0.0, min(1.0, confidence))

        articles.append(WikiArticle(
            path            = path,
            slug            = slug,
            node_id         = node_id,
            node_type       = node_type,
            title           = str(title),
            entity_type     = str(entity_type),
            domain          = str(domain),
            ticker          = ticker.upper() if ticker else "",
            aliases         = aliases,
            tags            = tags,
            concept_links   = concept_links,
            confidence      = confidence,
            review_status   = str(fm.get("review_status") or "auto"),
            freshness_policy= str(fm.get("freshness_policy") or "static"),
        ))

    return articles, skipped


# ── Platform tag map (mirrors load_universe.py) ───────────────────────────────

def _load_platform_tags() -> dict[str, list[str]]:
    """Read platform_tag_rules from universe_v1.json."""
    ufile = _HERE / "universe_v1.json"
    if ufile.exists():
        data = json.loads(ufile.read_text())
        return data.get("_meta", {}).get("platform_tag_rules", {})
    return {}


# ── Core ingest logic ─────────────────────────────────────────────────────────

def ingest(
    articles: list[WikiArticle],
    store: IntelStore,
    slug_to_node_id: dict[str, str],
    platform_tags: dict[str, list[str]],
    ticker_to_platforms: dict[str, list[str]],
    dry_run: bool,
    verbose: bool,
) -> dict:
    """
    Upsert nodes and write edges for all articles.
    Returns a stats dict.
    """
    stats = {
        "nodes_upserted":    0,
        "edges_mentioned_in": 0,
        "edges_platform":    0,
        "links_unresolved":  0,
    }

    # 1. Upsert platform nodes
    for pl_id, pl_name in _PLATFORM_NODES.items():
        if verbose:
            print(f"  [platform] {pl_id} — {pl_name}")
        if not dry_run:
            store.upsert_node(
                pl_id, "platform", pl_name,
                aliases=[pl_id],
                metadata={"platform_id": pl_id},
            )

    # 2. Upsert article nodes
    for art in articles:
        if verbose:
            print(f"  [node] {art.node_id} ({art.node_type}) — {art.title}")
        if not dry_run:
            store.upsert_node(
                art.node_id,
                art.node_type,
                art.title,
                aliases=art.aliases,
                metadata=art.metadata,
            )
        stats["nodes_upserted"] += 1

    # 3. Edges: concept_links → mentioned_in
    for art in articles:
        for link_slug in art.concept_links:
            dst = slug_to_node_id.get(link_slug)
            if dst is None:
                stats["links_unresolved"] += 1
                if verbose:
                    print(f"  [unresolved] {art.slug} → '{link_slug}'")
                continue
            if verbose:
                print(f"  [edge:mentioned_in] {art.node_id} → {dst}")
            if not dry_run:
                store.upsert_edge(
                    src        = art.node_id,
                    dst        = dst,
                    edge_type  = "mentioned_in",
                    confidence = art.confidence,
                    source_id  = art.source_id,
                    evidence   = f"concept_links in {art.source_id}",
                    source_type= "wiki",
                )
            stats["edges_mentioned_in"] += 1

    # 4. Edges: company × platform_tags → belongs_to_platform
    for art in articles:
        if art.node_type != "company" or not art.ticker:
            continue
        platforms = ticker_to_platforms.get(art.ticker, [])
        for pl_id in platforms:
            if verbose:
                print(f"  [edge:platform] {art.node_id} → {pl_id}")
            if not dry_run:
                store.upsert_edge(
                    src        = art.node_id,
                    dst        = pl_id,
                    edge_type  = "belongs_to_platform",
                    confidence = 0.95,
                    source_id  = art.source_id,
                    evidence   = f"Platform tag from universe_v1 rules: {art.ticker} ∈ {pl_id}",
                    source_type= "wiki",
                )
            stats["edges_platform"] += 1

    return stats


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest wiki articles into SOMA-INTEL graph")
    parser.add_argument("--apply",   action="store_true", help="Write to DB (default: dry run)")
    parser.add_argument("--force",   action="store_true", help="Delete all wiki edges then re-insert")
    parser.add_argument("--verbose", action="store_true", help="Print per-node/edge detail")
    args = parser.parse_args()

    dry_run = not args.apply
    if dry_run:
        print("DRY RUN — pass --apply to write to DB")

    # Scan articles
    articles, skipped = _scan_articles()
    print(f"\nScanned wiki/compiled/:")
    print(f"  Articles parsed:  {len(articles)}")
    print(f"  Skipped (no FM):  {len(skipped)}")

    # Node-type breakdown
    from collections import Counter
    nt_counts = Counter(a.node_type for a in articles)
    for nt, cnt in sorted(nt_counts.items()):
        print(f"    {nt:<12} {cnt}")

    # Build slug → node_id index
    slug_to_node_id: dict[str, str] = {a.slug: a.node_id for a in articles}

    # Platform tags
    platform_tags      = _load_platform_tags()
    ticker_to_platforms: dict[str, list[str]] = {}
    for pl_id, tickers in platform_tags.items():
        for t in tickers:
            ticker_to_platforms.setdefault(t.upper(), []).append(pl_id)

    # Preview stats
    total_links = sum(len(a.concept_links) for a in articles)
    total_platform_edges = sum(
        len(ticker_to_platforms.get(a.ticker, []))
        for a in articles if a.node_type == "company" and a.ticker
    )
    print(f"\nProjected writes:")
    print(f"  Platform nodes:      {len(_PLATFORM_NODES)}")
    print(f"  Article nodes:       {len(articles)}")
    print(f"  concept_link edges:  {total_links} (some slugs may not resolve)")
    print(f"  platform edges:      {total_platform_edges}")
    print(f"  Total edges:         {total_links + total_platform_edges}")

    if dry_run:
        print("\nDRY RUN complete — no DB writes. Pass --apply to execute.")
        return

    with IntelStore(db_path=DB_PATH) as store:
        # Guard: check existing wiki edges
        existing_wiki = store.count_edges_by_source_type("wiki")

        if existing_wiki > 0 and not args.force:
            print(f"\nWARNING: {existing_wiki} wiki edges already in DB.")
            print("  Pass --force to wipe + re-ingest, or --apply without --force to skip.")
            print("\nUpserting nodes only (idempotent)...")
            # Upsert nodes only — skip edge creation
            for pl_id, pl_name in _PLATFORM_NODES.items():
                store.upsert_node(pl_id, "platform", pl_name,
                                  aliases=[pl_id],
                                  metadata={"platform_id": pl_id})
            for art in articles:
                store.upsert_node(art.node_id, art.node_type, art.title,
                                  aliases=art.aliases, metadata=art.metadata)
            print(f"  Nodes upserted: {len(articles) + len(_PLATFORM_NODES)}")
            return

        if args.force and existing_wiki > 0:
            print(f"\n--force: deleting {existing_wiki} existing wiki edges...")
            store.delete_edges_by_source_type("wiki")
            store.commit()
            print(f"  Deleted.")

        print(f"\nIngesting...")
        stats = ingest(
            articles          = articles,
            store             = store,
            slug_to_node_id   = slug_to_node_id,
            platform_tags     = platform_tags,
            ticker_to_platforms = ticker_to_platforms,
            dry_run           = False,
            verbose           = args.verbose,
        )

        # Verify
        node_count = store.count_table("soma_intel_node")
        edge_count = store.count_edges_by_source_type("wiki")

    print(f"\nResults:")
    print(f"  Nodes upserted:          {stats['nodes_upserted'] + len(_PLATFORM_NODES)}")
    print(f"  mentioned_in edges:      {stats['edges_mentioned_in']}")
    print(f"  belongs_to_platform:     {stats['edges_platform']}")
    print(f"  Unresolved concept_links:{stats['links_unresolved']}")
    print(f"\nDB totals:")
    print(f"  soma_intel_node:  {node_count}")
    print(f"  wiki edges:       {edge_count}")
    print("\ningest_wiki: OK")


if __name__ == "__main__":
    main()
