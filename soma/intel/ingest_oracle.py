#!/usr/bin/env python3
"""
SOMA-INTEL Step 1.2 — ORACLE Pipeline Ingestor

Reads structured data from three ORACLE sub-pipelines and writes to soma.db:

  TITAN (equity):
    - oracle/cache/<TICKER>_summary.json (374 files)
    - Upserts/enriches co_TICKER nodes with GF valuation + sector metadata
    - Creates cn_<sector> + cn_<industry> concept nodes
    - is_a edges: co_TICKER → cn_<sector>

  COBALT (blockchain):
    - oracle/cobalt_cache/a2a33c1963db.json (CoinGecko prices: BTC/ETH/SOL)
    - oracle/cobalt_cache/636cf54387b6.json (DeFiLlama top protocols)
    - Upserts sec_BTC, sec_ETH, sec_SOL with market data
    - Top-10 DeFi protocol nodes (cn_defi_<slug>)
    - belongs_to_platform edges: crypto assets → pl_blockchain

  SPECTRE (geopolitical):
    - Static taxonomy from spectre_engine.py (no live data needed)
    - Upserts 6 risk-category + 8 region rg_* regime nodes

Idempotency:
  Nodes: upsert (safe to re-run).
  Edges: --apply without --force skips if oracle edges already exist.
         --force deletes all source_type='oracle_titan'/'oracle_cobalt'/'oracle_spectre' edges first.

Usage:
  python3 soma/intel/ingest_oracle.py               # dry run
  python3 soma/intel/ingest_oracle.py --apply        # write to DB
  python3 soma/intel/ingest_oracle.py --apply --force   # wipe + re-ingest oracle edges
  python3 soma/intel/ingest_oracle.py --apply --pipeline titan   # single pipeline
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, Optional

# ── Path bootstrap ────────────────────────────────────────────────────────────
_HERE    = Path(__file__).resolve().parent
_DABEIBA = _HERE.parent.parent.parent
for _p in [str(_DABEIBA), str(_DABEIBA / "shared")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from soma.intel.store import IntelStore

# ── Config ────────────────────────────────────────────────────────────────────
ORACLE_DIR      = _DABEIBA / "oracle"
TITAN_CACHE     = ORACLE_DIR / "cache"
COBALT_CACHE    = ORACLE_DIR / "cobalt_cache"

DB_PATH = (
    Path(os.environ["SOMA_DB_PATH"])
    if "SOMA_DB_PATH" in os.environ
    else _DABEIBA / "shared" / "soma" / "data" / "soma.db"
)

log = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _slugify(text: str) -> str:
    """'Consumer Cyclical' → 'consumer-cyclical'"""
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower().strip()).strip("-")


# ════════════════════════════════════════════════════════════════════════════
# TITAN — Equity ingest
# ════════════════════════════════════════════════════════════════════════════

_TITAN_VALUATION_CONFIDENCE = {
    "Significantly Undervalued": 0.85,
    "Modestly Undervalued":      0.80,
    "Fairly Valued":             0.75,
    "Modestly Overvalued":       0.80,
    "Significantly Overvalued":  0.85,
}


def _ingest_titan(store: IntelStore, dry_run: bool, verbose: bool, write_edges: bool = True) -> dict:
    """Read oracle/cache/*_summary.json → nodes + is_a edges."""
    stats = {
        "tickers":        0,
        "sector_nodes":   0,
        "industry_nodes": 0,
        "edges_is_a":     0,
        "skipped":        0,
    }

    # Build sector/industry node sets to avoid re-upserting
    seen_sectors:    set[str] = set()
    seen_industries: set[str] = set()

    files = sorted(TITAN_CACHE.glob("*_summary.json"))
    for f in files:
        ticker = f.stem.replace("_summary", "").upper()
        try:
            raw = json.loads(f.read_text())
            if not raw or not isinstance(raw, dict):
                stats["skipped"] += 1
                continue
            s = raw.get("summary")
            if not s or not isinstance(s, dict):
                stats["skipped"] += 1
                continue
            gen = s.get("general", {})
        except (json.JSONDecodeError, KeyError, TypeError):
            stats["skipped"] += 1
            continue

        company_name  = gen.get("company", ticker)
        sector        = gen.get("sector", "")
        industry      = gen.get("group", "")          # e.g. "Auto Manufacturers"
        gf_valuation  = gen.get("gf_valuation", "")
        gf_score      = gen.get("gf_score")
        risk          = gen.get("risk_assessment", "")
        supersector   = gen.get("supersector", "")

        # ── Upsert sector concept node ────────────────────────────────────
        if sector and sector not in seen_sectors:
            sec_node_id = f"cn_{_slugify(sector)}"
            if verbose:
                print(f"  [sector] {sec_node_id} — {sector}")
            if not dry_run:
                store.upsert_node(
                    sec_node_id, "concept", sector,
                    aliases=[sector, _slugify(sector)],
                    metadata={"supersector": supersector, "oracle_source": "titan"},
                )
            seen_sectors.add(sector)
            stats["sector_nodes"] += 1

        # ── Upsert industry group node ────────────────────────────────────
        if industry and industry not in seen_industries:
            ind_node_id = f"cn_{_slugify(industry)}"
            if verbose:
                print(f"  [industry] {ind_node_id} — {industry}")
            if not dry_run:
                store.upsert_node(
                    ind_node_id, "concept", industry,
                    aliases=[industry, _slugify(industry)],
                    metadata={"parent_sector": sector, "oracle_source": "titan"},
                )
            seen_industries.add(industry)
            stats["industry_nodes"] += 1

        # ── Upsert/enrich company node ────────────────────────────────────
        node_id = f"co_{ticker}"
        meta = {
            "gf_valuation":  gf_valuation,
            "gf_score":      gf_score,
            "sector":        sector,
            "industry":      industry,
            "risk":          risk,
            "oracle_source": "titan",
        }
        if verbose:
            print(f"  [company] {node_id} — {company_name} | {gf_valuation} | GF={gf_score}")
        if not dry_run:
            store.upsert_node(
                node_id, "company", company_name,
                aliases=[ticker, company_name],
                metadata=meta,
            )
        stats["tickers"] += 1

        # ── is_a edge: co_TICKER → cn_<sector> ───────────────────────────
        if sector:
            sec_node_id = f"cn_{_slugify(sector)}"
            conf = _TITAN_VALUATION_CONFIDENCE.get(gf_valuation, 0.75)
            source_id = f"oracle_titan:cache/{f.name}"
            if verbose:
                print(f"  [edge:is_a] {node_id} → {sec_node_id}")
            if not dry_run and write_edges:
                store.upsert_edge(
                    src         = node_id,
                    dst         = sec_node_id,
                    edge_type   = "is_a",
                    confidence  = conf,
                    source_id   = source_id,
                    evidence    = f"{ticker} classified as {sector} by GuruFocus",
                    source_type = "oracle_titan",
                )
            stats["edges_is_a"] += 1

    return stats


# ════════════════════════════════════════════════════════════════════════════
# COBALT — Blockchain asset ingest
# ════════════════════════════════════════════════════════════════════════════

_CRYPTO_ASSETS = {
    "bitcoin":  {"node_id": "sec_BTC",  "name": "Bitcoin (BTC)",
                 "ticker": "BTC",  "aliases": ["BTC", "Bitcoin"]},
    "ethereum": {"node_id": "sec_ETH",  "name": "Ethereum (ETH)",
                 "ticker": "ETH",  "aliases": ["ETH", "Ethereum"]},
    "solana":   {"node_id": "sec_SOL",  "name": "Solana (SOL)",
                 "ticker": "SOL",  "aliases": ["SOL", "Solana"]},
}

_DEFILLAMA_CACHE = COBALT_CACHE / "636cf54387b6.json"
_COINGECKO_CACHE = COBALT_CACHE / "a2a33c1963db.json"
_TOP_DEFI_LIMIT  = 10   # top-N protocols by TVL


def _ingest_cobalt(store: IntelStore, dry_run: bool, verbose: bool, write_edges: bool = True) -> dict:
    """Upsert BTC/ETH/SOL nodes + top DeFi protocols."""
    stats = {
        "crypto_nodes":   0,
        "defi_nodes":     0,
        "edges_platform": 0,
    }

    # ── CoinGecko prices ─────────────────────────────────────────────────────
    cg_data: dict = {}
    if _COINGECKO_CACHE.exists():
        try:
            cg_data = json.loads(_COINGECKO_CACHE.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    for cg_key, asset in _CRYPTO_ASSETS.items():
        price_info = cg_data.get(cg_key, {})
        meta = {
            "ticker":        asset["ticker"],
            "asset_class":   "crypto",
            "usd_price":     price_info.get("usd"),
            "market_cap":    price_info.get("usd_market_cap"),
            "vol_24h":       price_info.get("usd_24h_vol"),
            "change_24h":    price_info.get("usd_24h_change"),
            "oracle_source": "cobalt",
        }
        if verbose:
            print(f"  [crypto] {asset['node_id']} — {asset['name']} @ ${price_info.get('usd', '?')}")
        if not dry_run:
            store.upsert_node(
                asset["node_id"], "security", asset["name"],
                aliases=asset["aliases"],
                metadata=meta,
            )
            # belongs_to_platform → pl_blockchain
            if write_edges:
                store.upsert_edge(
                    src         = asset["node_id"],
                    dst         = "pl_blockchain",
                    edge_type   = "belongs_to_platform",
                    confidence  = 0.99,
                    source_id   = f"oracle_cobalt:cobalt_cache/{_COINGECKO_CACHE.name}",
                    evidence    = f"{asset['ticker']} is a native blockchain asset",
                    source_type = "oracle_cobalt",
                )
        stats["crypto_nodes"]   += 1
        if write_edges:
            stats["edges_platform"] += 1

    # ── DeFiLlama top protocols ───────────────────────────────────────────────
    if _DEFILLAMA_CACHE.exists():
        try:
            protocols: list = json.loads(_DEFILLAMA_CACHE.read_text())
        except (json.JSONDecodeError, OSError):
            protocols = []

        # sort by TVL descending, take top N
        protocols_sorted = sorted(
            (p for p in protocols if isinstance(p, dict) and p.get("tvl")),
            key=lambda x: x.get("tvl", 0),
            reverse=True,
        )[:_TOP_DEFI_LIMIT]

        for p in protocols_sorted:
            name     = p.get("name", "")
            symbol   = (p.get("symbol") or "").upper()
            category = p.get("category", "DeFi")
            tvl      = p.get("tvl", 0)
            slug     = _slugify(name)
            node_id  = f"cn_defi_{slug}"

            meta = {
                "protocol":      name,
                "symbol":        symbol,
                "category":      category,
                "tvl_usd":       tvl,
                "oracle_source": "cobalt_defillama",
            }
            aliases = [name]
            if symbol:
                aliases.append(symbol)

            if verbose:
                print(f"  [defi] {node_id} — {name} ({category}) TVL=${tvl/1e9:.1f}B")
            if not dry_run:
                store.upsert_node(
                    node_id, "concept", name,
                    aliases=aliases,
                    metadata=meta,
                )
            stats["defi_nodes"] += 1

    return stats


# ════════════════════════════════════════════════════════════════════════════
# SPECTRE — Regime taxonomy ingest
# ════════════════════════════════════════════════════════════════════════════

_SPECTRE_CATEGORIES = {
    "conflict":   "Geopolitical Conflict & Military Action",
    "sanctions":  "Trade Sanctions & Export Controls",
    "trade":      "Global Trade & Supply Chain",
    "election":   "Electoral & Political Transition",
    "energy":     "Energy & Commodity Risk",
    "monetary":   "Central Bank & Monetary Policy",
}

_SPECTRE_REGIONS = {
    "US":     "United States",
    "EU":     "European Union",
    "CN":     "China",
    "RU":     "Russia",
    "ME":     "Middle East",
    "ASIA":   "Asia-Pacific",
    "LATAM":  "Latin America",
    "AFRICA": "Africa",
}


def _ingest_spectre(store: IntelStore, dry_run: bool, verbose: bool) -> dict:
    """Upsert risk-category and region regime nodes from SPECTRE taxonomy."""
    stats = {"category_nodes": 0, "region_nodes": 0}

    for cat_id, cat_name in _SPECTRE_CATEGORIES.items():
        node_id = f"rg_{cat_id}"
        if verbose:
            print(f"  [regime:category] {node_id} — {cat_name}")
        if not dry_run:
            store.upsert_node(
                node_id, "regime", cat_name,
                aliases=[cat_id, cat_name],
                metadata={"regime_type": "risk_category", "oracle_source": "spectre"},
            )
        stats["category_nodes"] += 1

    for reg_id, reg_name in _SPECTRE_REGIONS.items():
        node_id = f"rg_{reg_id.lower()}"
        if verbose:
            print(f"  [regime:region] {node_id} — {reg_name}")
        if not dry_run:
            store.upsert_node(
                node_id, "regime", reg_name,
                aliases=[reg_id, reg_name, reg_id.lower()],
                metadata={"regime_type": "region", "oracle_source": "spectre"},
            )
        stats["region_nodes"] += 1

    return stats


# ════════════════════════════════════════════════════════════════════════════
# Main
# ════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest ORACLE pipeline data into SOMA-INTEL graph")
    parser.add_argument("--apply",    action="store_true", help="Write to DB (default: dry run)")
    parser.add_argument("--force",    action="store_true", help="Wipe oracle edges before re-ingest")
    parser.add_argument("--verbose",  action="store_true", help="Show per-node/edge detail")
    parser.add_argument("--pipeline", choices=["titan", "cobalt", "spectre", "all"],
                        default="all", help="Which pipeline to run (default: all)")
    args = parser.parse_args()

    dry_run = not args.apply
    run_all = args.pipeline == "all"

    if dry_run:
        print("DRY RUN — pass --apply to write to DB")

    # Count source files
    titan_files  = len(list(TITAN_CACHE.glob("*_summary.json"))) if TITAN_CACHE.exists() else 0
    cobalt_files = len(list(COBALT_CACHE.glob("*.json")))        if COBALT_CACHE.exists() else 0
    print(f"\nSource inventory:")
    print(f"  TITAN  cache files:  {titan_files}")
    print(f"  COBALT cache files:  {cobalt_files}")
    print(f"  SPECTRE taxonomy:    {len(_SPECTRE_CATEGORIES)} categories + {len(_SPECTRE_REGIONS)} regions")

    if dry_run:
        # Just show projections
        print(f"\nProjected writes (dry run):")
        if run_all or args.pipeline == "titan":
            print(f"  TITAN:   ~{titan_files} company nodes + ~11 sector + ~? industry nodes + ~{titan_files} is_a edges")
        if run_all or args.pipeline == "cobalt":
            print(f"  COBALT:  3 crypto nodes + {_TOP_DEFI_LIMIT} DeFi nodes + 3 platform edges")
        if run_all or args.pipeline == "spectre":
            print(f"  SPECTRE: {len(_SPECTRE_CATEGORIES)} category + {len(_SPECTRE_REGIONS)} region regime nodes")
        print("\nDRY RUN complete — pass --apply to execute.")
        return

    _ORACLE_SOURCE_TYPES = ["oracle_titan", "oracle_cobalt", "oracle_spectre"]

    with IntelStore(db_path=DB_PATH) as store:
        # Guard / force-wipe
        existing = store._c.execute(
            "SELECT COUNT(*) FROM soma_intel_edge WHERE source_type IN (?,?,?)",
            _ORACLE_SOURCE_TYPES,
        ).fetchone()[0]

        if existing > 0 and not args.force:
            print(f"\nWARNING: {existing} oracle edges already in DB. Upserting nodes only.")
            print("  Pass --force to wipe + re-ingest edges.")
        elif args.force and existing > 0:
            print(f"\n--force: deleting {existing} existing oracle edges...")
            for st in _ORACLE_SOURCE_TYPES:
                store._c.execute("DELETE FROM soma_intel_edge WHERE source_type=?", (st,))
            store._c.commit()
            print("  Deleted.")

        skip_edges = (existing > 0 and not args.force)

        all_stats: dict[str, dict] = {}
        write_edges = not skip_edges

        if run_all or args.pipeline == "titan":
            print("\n[TITAN] Ingesting equity data...")
            t_stats = _ingest_titan(
                store, dry_run=False, verbose=args.verbose, write_edges=write_edges
            )
            all_stats["titan"] = t_stats
            edge_note = f"is_a edges: {t_stats['edges_is_a']}" if write_edges else "edges: skipped (--force to re-ingest)"
            print(f"  Companies: {t_stats['tickers']}  Sectors: {t_stats['sector_nodes']}  "
                  f"Industries: {t_stats['industry_nodes']}  {edge_note}  "
                  f"Skipped: {t_stats['skipped']}")

        if run_all or args.pipeline == "cobalt":
            print("\n[COBALT] Ingesting blockchain data...")
            c_stats = _ingest_cobalt(
                store, dry_run=False, verbose=args.verbose, write_edges=write_edges
            )
            all_stats["cobalt"] = c_stats
            edge_note = f"platform edges: {c_stats['edges_platform']}" if write_edges else "edges: skipped"
            print(f"  Crypto nodes: {c_stats['crypto_nodes']}  DeFi nodes: {c_stats['defi_nodes']}  {edge_note}")

        if run_all or args.pipeline == "spectre":
            print("\n[SPECTRE] Ingesting regime taxonomy...")
            s_stats = _ingest_spectre(store, dry_run=False, verbose=args.verbose)
            all_stats["spectre"] = s_stats
            print(f"  Categories: {s_stats['category_nodes']}  Regions: {s_stats['region_nodes']}")

        # DB summary
        node_count  = store._c.execute("SELECT COUNT(*) FROM soma_intel_node").fetchone()[0]
        edge_oracle = store._c.execute(
            "SELECT COUNT(*) FROM soma_intel_edge WHERE source_type IN (?,?,?)",
            _ORACLE_SOURCE_TYPES,
        ).fetchone()[0]
        edge_total  = store._c.execute("SELECT COUNT(*) FROM soma_intel_edge").fetchone()[0]

        nt = store._c.execute(
            "SELECT node_type, COUNT(*) c FROM soma_intel_node GROUP BY node_type ORDER BY c DESC"
        ).fetchall()

        print(f"\nDB totals:")
        print(f"  soma_intel_node:    {node_count}")
        print(f"  oracle edges:       {edge_oracle}")
        print(f"  total edges:        {edge_total}")
        print("  Node types:")
        for r in nt:
            print(f"    {r[0]:<12} {r[1]}")

    print("\ningest_oracle: OK")


if __name__ == "__main__":
    main()
