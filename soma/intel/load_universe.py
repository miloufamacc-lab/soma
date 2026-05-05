#!/usr/bin/env python3
"""
SOMA-INTEL Step 0.2 — Universe Builder + Loader

Reads:
  - oracle/curated/security_master.json  → 199 core tickers
  - oracle/curated/{arkk,arkg,xle,smh}_constituents.json → ETF look-through

Writes:
  - soma/intel/universe_v1.json          → canonical universe file
  - soma_intel_universe table in soma.db → loaded via IntelStore

Platform tag rules (LOCKED per OPUS_DELIVERABLES §D.1 / BUILD_PLAN §0.2):
  pl_ai:            NVDA AMD MSFT GOOGL META AVGO PLTR SMCI ASML TSM TSLA
  pl_robotics:      TSLA ABB FANUY ISRG IRBT
  pl_energy_storage:TSLA ENPH FSLR ALB LIT
  pl_multi_omics:   ILMN PACB EXAS CRSP NTLA BEAM
  pl_blockchain:    COIN MSTR MARA RIOT BLOK

A ticker may carry multiple tags (e.g. TSLA gets 3).

Usage:
  python3 soma/intel/load_universe.py          # generate + load
  python3 soma/intel/load_universe.py --dry-run # generate only, no DB write
  python3 soma/intel/load_universe.py --regen  # force rebuild of universe_v1.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── Path bootstrap ────────────────────────────────────────────────────────────
_HERE = Path(__file__).resolve().parent
_DABEIBA = _HERE.parent.parent.parent
for _p in [str(_DABEIBA), str(_DABEIBA / "shared")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from soma.intel.store import IntelStore

# ── Paths ─────────────────────────────────────────────────────────────────────
ORACLE_CURATED  = _DABEIBA / "oracle" / "curated"
SECURITY_MASTER = ORACLE_CURATED / "security_master.json"
ETF_FILES = {
    "ARKK": ORACLE_CURATED / "arkk_constituents.json",
    "ARKG": ORACLE_CURATED / "arkg_constituents.json",
    "XLE":  ORACLE_CURATED / "xle_constituents.json",
    "SMH":  ORACLE_CURATED / "smh_constituents.json",
}
UNIVERSE_OUT = _HERE / "universe_v1.json"

DB_PATH = (
    Path(os.environ["SOMA_DB_PATH"])
    if "SOMA_DB_PATH" in os.environ
    else _DABEIBA / "shared" / "soma" / "data" / "soma.db"
)

# ── Platform tag rules (LOCKED — see §F, do not modify without Opus review) ──
_PLATFORM_TAGS: dict[str, list[str]] = {
    "pl_ai":             ["NVDA", "AMD", "MSFT", "GOOGL", "META", "AVGO",
                          "PLTR", "SMCI", "ASML", "TSM", "TSLA"],
    "pl_robotics":       ["TSLA", "ABB", "FANUY", "ISRG", "IRBT"],
    "pl_energy_storage": ["TSLA", "ENPH", "FSLR", "ALB", "LIT"],
    "pl_multi_omics":    ["ILMN", "PACB", "EXAS", "CRSP", "NTLA", "BEAM"],
    "pl_blockchain":     ["COIN", "MSTR", "MARA", "RIOT", "BLOK"],
}

# Reverse map: ticker → list of platform_ids it belongs to
_TICKER_TO_PLATFORMS: dict[str, list[str]] = {}
for _pl, _tickers in _PLATFORM_TAGS.items():
    for _t in _tickers:
        _TICKER_TO_PLATFORMS.setdefault(_t, []).append(_pl)


def _get_platform_tags(ticker: str) -> list[str]:
    return sorted(_TICKER_TO_PLATFORMS.get(ticker.upper(), []))


# ── Build universe dict ───────────────────────────────────────────────────────

def build_universe() -> dict:
    """Read source files and build the universe_v1 dict."""
    sm = json.loads(SECURITY_MASTER.read_text())
    securities = sm["securities"]

    core: list[dict] = []
    for ticker, meta in securities.items():
        core.append({
            "ticker":        ticker,
            "name":          meta.get("company", ""),
            "sector":        meta.get("sector", ""),
            "cad_symbol":    meta.get("cad_symbol"),
            "security_no":   meta.get("security_no"),
            "source":        meta.get("source", "security_master"),
            "platform_tags": _get_platform_tags(ticker),
        })

    # ETF look-through
    etf_holdings: dict[str, list[dict]] = {}
    total_etf = 0
    for etf_ticker, path in ETF_FILES.items():
        positions = json.loads(path.read_text()).get("positions", [])
        etf_holdings[etf_ticker] = [
            {
                "ticker": p["ticker"],
                "name":   p.get("name", ""),
                "weight": p.get("weight"),
                "platform_tags": _get_platform_tags(p["ticker"]),
            }
            for p in positions
        ]
        total_etf += len(positions)

    now = datetime.now(timezone.utc).isoformat()
    # next refresh in 90 days (quarterly)
    from datetime import timedelta
    refresh_due = (datetime.now(timezone.utc) + timedelta(days=90)).date().isoformat()

    return {
        "_meta": {
            "version":             "v1.0",
            "generated_ts":        now,
            "next_refresh_due":    refresh_due,
            "total_tickers":       len(core),
            "etf_holdings_count":  total_etf,
            "platform_tag_rules":  _PLATFORM_TAGS,
        },
        "core":         core,
        "etf_holdings": etf_holdings,
    }


# ── Load into DB ──────────────────────────────────────────────────────────────

def load_to_db(universe: dict, db_path: str | Path) -> int:
    """Upsert all core tickers into soma_intel_universe. Returns row count."""
    loaded = 0
    with IntelStore(db_path=db_path) as store:
        # universe_is_loaded() confirms tables exist (no-op probe, no raw SQL)
        _ = store.universe_is_loaded()

        now = datetime.now(timezone.utc).isoformat()
        for entry in universe["core"]:
            store.load_universe_entry(
                ticker=entry["ticker"],
                source=entry["source"],
                platform_tags=entry["platform_tags"],
                added_ts=now,
            )
            loaded += 1

        store.commit()
    return loaded


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Build and load SOMA-INTEL universe v1")
    parser.add_argument("--dry-run", action="store_true",
                        help="Generate universe_v1.json only; skip DB write")
    parser.add_argument("--regen", action="store_true",
                        help="Force rebuild of universe_v1.json even if it exists")
    args = parser.parse_args()

    # Build or load
    if UNIVERSE_OUT.exists() and not args.regen:
        print(f"Loading existing {UNIVERSE_OUT.name} (use --regen to rebuild)")
        universe = json.loads(UNIVERSE_OUT.read_text())
    else:
        print("Building universe from source files...")
        universe = build_universe()
        UNIVERSE_OUT.write_text(json.dumps(universe, indent=2, ensure_ascii=False))
        print(f"Written: {UNIVERSE_OUT}")

    meta = universe["_meta"]
    print(f"  Core tickers:       {meta['total_tickers']}")
    print(f"  ETF holdings total: {meta['etf_holdings_count']}")
    for etf, holdings in universe["etf_holdings"].items():
        print(f"    {etf}: {len(holdings)} positions")

    if args.dry_run:
        print("--dry-run: skipping DB write.")
        return

    print(f"\nLoading into soma_intel_universe ({DB_PATH})...")
    loaded = load_to_db(universe, DB_PATH)
    print(f"  Loaded: {loaded} rows")

    # Verify
    with IntelStore(db_path=DB_PATH) as store:
        count = store.count_active_universe()
    print(f"  DB count (active): {count}")
    assert count == meta["total_tickers"], \
        f"Mismatch: {count} in DB vs {meta['total_tickers']} expected"
    print("universe_v1 load: OK")


if __name__ == "__main__":
    main()
