#!/usr/bin/env python3
"""
ticker_context.py — Equity Context Pre-fetch for transcript-to-intel
=====================================================================

Bridges Market Intelligence (internal: ORACLE) VAULT data into the
transcript-to-intel skill (Phase 0.75). Extracts ticker mentions from a
transcript, pulls latest VAULT snapshot per ticker, emits JSON + a
scratchpad-ready markdown block.

Part of Cross-Skill Integration Link 4 (April 17, 2026).

Usage
-----
  python3 ticker_context.py extract --transcript <file> [--output <json>]
  python3 ticker_context.py format  --input <json>

CLI subcommands
---------------
  extract  Scan transcript file, detect tickers, query VAULT, write JSON.
  format   Read JSON, print the scratchpad-ready markdown block to stdout.

Ticker detection (scope: ALL mentions)
--------------------------------------
  - $CASHTAG       e.g. $TSLA, $MSFT, $BRK.B
  - Parens pattern e.g. "Tesla (TSLA)", "Apple (AAPL)"
  - Caps run       e.g. "TSLA is..."   (filtered: len 2-5, excludes
                                         common English ALLCAPS noise)

Only tickers actually present in VAULT are returned — unknowns are
auto-filtered (no VAULT row -> no context key).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Dict, List, Set


# ── Import bridge to ORACLE VAULT ─────────────────────────────────────────
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_THIS_DIR, "..", ".."))
_ORACLE_DIR = os.path.join(_PROJECT_ROOT, "oracle")
if _ORACLE_DIR not in sys.path:
    sys.path.insert(0, _ORACLE_DIR)

try:
    from vault.oracle_vault import OracleVault  # type: ignore
    _VAULT_AVAILABLE = True
except ImportError:
    _VAULT_AVAILABLE = False


# ── Ticker detection ──────────────────────────────────────────────────────
_CASHTAG_RE = re.compile(r"\$([A-Z]{1,5}(?:\.[A-Z])?)\b")
_PARENS_RE = re.compile(r"\(([A-Z]{1,5}(?:\.[A-Z])?)\)")
_CAPSRUN_RE = re.compile(r"\b([A-Z]{2,5})\b")

# Common ALLCAPS words that are NOT tickers (false-positive shield).
_STOP_TOKENS: Set[str] = {
    "A", "I", "AI", "AN", "AT", "BE", "BY", "DO", "GO", "HE", "IF", "IN",
    "IS", "IT", "ME", "MY", "NO", "OF", "OK", "ON", "OR", "SO", "TO", "UP",
    "US", "WE",
    "AND", "ARE", "BUT", "FOR", "HAS", "NOT", "NOW", "OFF", "OUR", "OUT",
    "THE", "WAS", "WHO", "WHY", "YES", "YET", "YOU",
    "CEO", "CFO", "COO", "CTO", "CMO", "CNBC", "CNN", "BBC", "NBC", "FOX",
    "GDP", "CPI", "PPI", "FED", "FOMC", "ECB", "BOJ", "PBOC", "SEC", "FCC",
    "FDIC", "FDA", "EPA", "IRS", "NATO", "OPEC", "WTO", "IMF", "DOJ", "DOE",
    "USA", "USD", "EUR", "GBP", "JPY", "CAD", "YOY", "QOQ", "MOM", "YTD",
    "ETF", "IPO", "IRA", "SPAC", "CAGR", "ROE", "ROI", "ROIC", "EBITDA",
    "EPS", "NAV", "AUM", "LTM", "NTM", "TAM", "SAM", "SOM",
    "API", "APIs", "SDK", "GPU", "CPU", "LLM", "AGI", "AWS", "GCP", "SAAS",
    "PAAS", "IAAS", "UI", "UX", "HTML", "CSS", "JSON", "XML", "SQL", "HTTP",
    "HTTPS", "URL", "IOT", "IIOT", "VR", "AR", "XR", "ML", "NLP", "RAG",
    "BUY", "SELL", "HOLD", "LONG", "SHORT", "PUT", "CALL",
    "YEAH", "OKAY", "SURE", "REAL", "HUGE", "BIG", "TOP",
    # Common non-ticker abbreviations / words that appear ALLCAPS in transcripts
    "ARB", "ARBS", "IP", "LA", "NY", "SF", "DC", "UK", "EU", "UN", "EV", "EVS",
    "IG", "HY", "TV", "PR", "HR", "HQ", "R&D", "VC", "PE", "LP", "GP",
    "QSR", "QE", "QT", "CB", "FX", "TA", "DCF",
    "YOLO", "FOMO", "FUD", "DD", "ATH", "ATL", "HODL", "NGMI", "WAGMI",
    "BBQ", "DIY", "FAQ", "ETA", "ASAP", "TBD", "TBA", "RIP", "RSVP",
}


def extract_tickers(text: str) -> List[str]:
    """Detect all candidate tickers in text. Returns deduped, uppercase list."""
    if not text:
        return []
    found: Set[str] = set()

    for m in _CASHTAG_RE.finditer(text):
        found.add(m.group(1).upper())

    for m in _PARENS_RE.finditer(text):
        token = m.group(1).upper()
        if token not in _STOP_TOKENS:
            found.add(token)

    for m in _CAPSRUN_RE.finditer(text):
        token = m.group(1).upper()
        if token in _STOP_TOKENS:
            continue
        # Require length >=2; single letters blocked by regex already.
        found.add(token)

    return sorted(found)


# ── VAULT query ───────────────────────────────────────────────────────────
def fetch_vault_context(tickers: List[str]) -> Dict[str, dict]:
    """Return {ticker: snapshot_dict} for tickers present in VAULT."""
    if not _VAULT_AVAILABLE:
        return {}
    if not tickers:
        return {}
    try:
        with OracleVault() as vault:
            return vault.get_latest_snapshot(tickers)
    except Exception as e:
        sys.stderr.write(f"[ticker_context] VAULT query failed: {e}\n")
        return {}


# ── Scratchpad formatter ──────────────────────────────────────────────────
def format_scratchpad_block(context: Dict[str, dict]) -> str:
    """Render VAULT context as a markdown block for the Phase 1 scratchpad."""
    if not context:
        return (
            "## ORACLE CONTEXT SNAPSHOT\n"
            "_No VAULT-covered tickers detected in transcript._\n"
        )
    lines = ["## ORACLE CONTEXT SNAPSHOT"]
    # Use the freshest date across the returned rows (they are per-ticker
    # latest, but dates can differ slightly if runs were partial).
    dates = [row.get("date") for row in context.values() if row.get("date")]
    if dates:
        lines.append(f"_VAULT as of: {max(dates)}_\n")

    for ticker in sorted(context.keys()):
        row = context[ticker]
        fv = row.get("dcf_fair_value")
        px = row.get("price_usd")
        up = row.get("implied_upside")
        vd = row.get("dcf_verdict") or "--"
        gf = row.get("gf_score")

        def _fmt(val, prefix="", suffix="", ndp=2):
            if val is None:
                return "--"
            try:
                return f"{prefix}{float(val):.{ndp}f}{suffix}"
            except (TypeError, ValueError):
                return str(val)

        lines.append(
            f"- **{ticker}** | "
            f"Price {_fmt(px, '$')} | "
            f"DCF FV {_fmt(fv, '$')} | "
            f"Upside {_fmt(up, '', '%')} | "
            f"Verdict {vd} | "
            f"GF {_fmt(gf, '', '', 0)}"
        )
    return "\n".join(lines) + "\n"


# ── CLI ───────────────────────────────────────────────────────────────────
def _cmd_extract(args) -> int:
    with open(args.transcript, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    candidates = extract_tickers(text)
    context = fetch_vault_context(candidates)
    payload = {
        "transcript": os.path.basename(args.transcript),
        "candidates_detected": candidates,
        "vault_covered": sorted(context.keys()),
        "context": context,
        "scratchpad_block": format_scratchpad_block(context),
    }
    out_path = args.output or (os.path.splitext(args.transcript)[0]
                               + ".ticker_context.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    print(f"Wrote {out_path}")
    print(f"  Detected: {len(candidates)} candidates")
    print(f"  VAULT-covered: {len(context)}")
    return 0


def _cmd_format(args) -> int:
    with open(args.input, "r", encoding="utf-8") as f:
        payload = json.load(f)
    sys.stdout.write(payload.get("scratchpad_block")
                     or format_scratchpad_block(payload.get("context", {})))
    return 0


def _cmd_lookup(args) -> int:
    """Phase 5.4 — cache-first lookup for Phase 4g.

    Reads the ticker_context.json cache produced by Phase 0.75 and prints
    the snapshot for a single ticker. Exits 0 on CACHE HIT, 1 on CACHE MISS
    (caller falls through to live VAULT query). Stays silent on stdout when
    the cache is missing so callers can pipe output straight to the deck.
    """
    path = args.cache
    if not os.path.exists(path):
        sys.stderr.write(
            f"[ticker_context] CACHE MISS — {path} not found; "
            "run Phase 0.75 (`ticker_context.py extract`) or fall through to live query.\n"
        )
        return 1
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    ticker = args.ticker.upper()
    context = payload.get("context", {})
    hit = context.get(ticker)
    if not hit:
        sys.stderr.write(
            f"[ticker_context] CACHE MISS for {ticker} — "
            "not in Phase 0.75 vault_covered; fall through to live VAULT query.\n"
        )
        return 1
    # Print a 4g-style single-line snapshot (same fields the live path prints).
    fv = hit.get("dcf_fair_value")
    px = hit.get("price_usd")
    up = hit.get("implied_upside")
    vd = hit.get("dcf_verdict") or "--"
    gf = hit.get("gf_score")
    date = hit.get("date") or payload.get("vault_as_of") or "--"
    print(
        f"CACHE HIT: Date: {date} | Ticker: {ticker} | "
        f"DCF FV: ${fv} | Price: ${px} | Upside: {up}% | "
        f"Verdict: {vd} | GF Score: {gf}"
    )
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Equity context pre-fetch for transcript-to-intel.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ext = sub.add_parser("extract", help="Scan transcript + query VAULT.")
    p_ext.add_argument("--transcript", required=True, help="Path to transcript file.")
    p_ext.add_argument("--output", help="Output JSON path (default: <transcript>.ticker_context.json).")
    p_ext.set_defaults(func=_cmd_extract)

    p_fmt = sub.add_parser("format", help="Print scratchpad block from JSON.")
    p_fmt.add_argument("--input", required=True, help="Path to JSON from extract.")
    p_fmt.set_defaults(func=_cmd_format)

    # Phase 5.4 — Phase 4g reads the Phase 0.75 cache via this subcommand.
    p_look = sub.add_parser(
        "cache-lookup",
        help="Cache-first snapshot lookup (Phase 4g). Exit 1 on cache miss.",
    )
    p_look.add_argument("--cache", default="ticker_context.json",
                        help="Phase 0.75 JSON cache (default: ticker_context.json)")
    p_look.add_argument("--ticker", required=True, help="Ticker to look up.")
    p_look.set_defaults(func=_cmd_lookup)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
