#!/usr/bin/env python3
"""
SOMA-INTEL Step 1.4 — Universe Manager

Scans the knowledge graph and soma_intel_universe to:
  - Compute a signal score for every co_* node (edge count × source weight)
  - Classify each universe ticker: HEALTHY | TITAN_ONLY | DARK | DEMOTE_CANDIDATE
  - Classify each non-universe co_* node: PROMOTE_CANDIDATE | GHOST
  - Optionally apply changes: promote new tickers, demote auto-added stale tickers,
    and refresh promotion_score + promotion_source on all rows

Signal score formula:
  score = Σ (edge_count[source_type] × SOURCE_WEIGHTS[source_type])
        + (distinct_source_count - 1) × DIVERSITY_BONUS

Source weights (ascending signal quality):
  oracle_titan  1.0   — baseline: everyone with a GF cache file gets this
  oracle_cobalt 1.5   — on-chain market data
  wiki          2.0   — curated intelligence articles
  article       2.0
  manual        2.0
  10k           1.5
  derived       1.5
  news          2.5   — live press signal
  transcript    3.0   — direct primary-source intelligence
  sitrep        3.0   — MUSKONOMY / daily briefing

Promotion threshold:  score ≥ PROMOTE_THRESHOLD (default 4.0)
Demotion threshold:   auto_added=1 AND score ≤ DEMOTE_THRESHOLD (default 0.5)
  — Manually-curated tickers (auto_added=0) are NEVER auto-demoted.

Usage:
  python3 soma/intel/universe_manager.py          # dry run: full report
  python3 soma/intel/universe_manager.py --apply  # write promotions/demotions/score updates
  python3 soma/intel/universe_manager.py --report-only  # compact summary only
  python3 soma/intel/universe_manager.py --ticker NVDA   # single-ticker diagnosis
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ── Path bootstrap ────────────────────────────────────────────────────────────
_HERE    = Path(__file__).resolve().parent
_DABEIBA = _HERE.parent.parent.parent
for _p in [str(_DABEIBA), str(_DABEIBA / "shared")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from soma.intel.store import IntelStore

# ── Config ────────────────────────────────────────────────────────────────────
DB_PATH = (
    Path(os.environ["SOMA_DB_PATH"])
    if "SOMA_DB_PATH" in os.environ
    else _DABEIBA / "shared" / "soma" / "data" / "soma.db"
)

UNIVERSE_JSON = _HERE / "universe_v1.json"

# Signal weights (per edge, by source_type)
SOURCE_WEIGHTS: dict[str, float] = {
    "oracle_titan":  1.0,
    "oracle_cobalt": 1.5,
    "oracle_spectre":1.0,
    "wiki":          2.0,
    "article":       2.0,
    "manual":        2.0,
    "10k":           1.5,
    "derived":       1.5,
    "news":          2.5,
    "transcript":    3.0,
    "sitrep":        3.0,
}
_DEFAULT_WEIGHT  = 1.0   # for unknown source types
DIVERSITY_BONUS  = 1.0   # per distinct source_type beyond the first

PROMOTE_THRESHOLD = 4.0   # score ≥ this → PROMOTE_CANDIDATE
DEMOTE_THRESHOLD  = 0.5   # score ≤ this AND auto_added=1 → DEMOTE_CANDIDATE


# ════════════════════════════════════════════════════════════════════════════
# Data models
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class TickerSignal:
    """Per-ticker signal density computed from the graph."""
    ticker:          str
    node_id:         str                        # co_TICKER
    in_universe:     bool
    auto_added:      bool
    tier:            str                        # core / watchlist / etf_loothrough
    edge_counts:     dict[str, int] = field(default_factory=dict)   # source_type → count
    score:           float = 0.0
    status:          str   = ""                 # filled by _classify()
    # ETF membership
    etf_member_of:   list[str] = field(default_factory=list)        # [ARKK, ARKG, ...]

    @property
    def source_diversity(self) -> int:
        return len(self.edge_counts)

    @property
    def promotion_source_str(self) -> str:
        """Compact string for soma_intel_universe.promotion_source column."""
        parts = [f"{st}×{cnt}" for st, cnt in sorted(self.edge_counts.items())]
        return ", ".join(parts) if parts else "none"


# Status constants
STATUS_HEALTHY          = "HEALTHY"           # in universe, multi-source signal
STATUS_TITAN_ONLY       = "TITAN_ONLY"        # in universe, oracle_titan baseline only
STATUS_DARK             = "DARK"              # in universe, zero edges (guard)
STATUS_DEMOTE_CANDIDATE = "DEMOTE_CANDIDATE"  # auto_added=1, score below threshold
STATUS_PROMOTE_CANDIDATE= "PROMOTE_CANDIDATE" # not in universe, score ≥ threshold
STATUS_GHOST            = "GHOST"             # not in universe, below threshold


# ════════════════════════════════════════════════════════════════════════════
# Signal computation
# ════════════════════════════════════════════════════════════════════════════

def _compute_signal_score(edge_counts: dict[str, int]) -> float:
    """Weighted signal score from edge_counts dict."""
    if not edge_counts:
        return 0.0
    base = sum(
        cnt * SOURCE_WEIGHTS.get(st, _DEFAULT_WEIGHT)
        for st, cnt in edge_counts.items()
    )
    diversity_bonus = (len(edge_counts) - 1) * DIVERSITY_BONUS
    return round(base + diversity_bonus, 3)


def _load_etf_membership(universe_json: Path) -> dict[str, list[str]]:
    """ticker → list of ETFs it appears in (from universe_v1.json etf_holdings)."""
    if not universe_json.exists():
        return {}
    data = json.loads(universe_json.read_text())
    mapping: dict[str, list[str]] = {}
    for etf, holdings in data.get("etf_holdings", {}).items():
        for h in holdings:
            t = h.get("ticker", "").upper()
            if t:
                mapping.setdefault(t, []).append(etf)
    return mapping


def compute_all_signals(store: IntelStore) -> dict[str, TickerSignal]:
    """
    For every co_* node in soma_intel_node, compute edge counts + signal score.
    Cross-references universe membership from soma_intel_universe.

    Returns dict of ticker → TickerSignal.
    """
    # Load universe membership via IntelStore
    universe_map: dict[str, tuple[bool, str]] = {
        r["ticker"]: (bool(r["auto_added"]), r["tier"] or "core")
        for r in store.list_universe(active_only=True)
    }

    # Load ETF membership from universe_v1.json
    etf_map = _load_etf_membership(UNIVERSE_JSON)

    # Load all co_* nodes via IntelStore
    co_nodes = store.list_nodes_by_type("company")

    # Load edge source-type counts per company node via IntelStore
    node_edges: dict[str, dict[str, int]] = store.edge_source_counts_for_companies()

    # Build TickerSignal for each co_* node
    signals: dict[str, TickerSignal] = {}
    for node in co_nodes:
        node_id = node.node_id
        ticker  = node_id[3:]  # strip "co_"

        in_uni, auto_added, tier = False, False, "core"
        if ticker in universe_map:
            in_uni     = True
            auto_added = universe_map[ticker][0]
            tier       = universe_map[ticker][1]

        edge_counts = node_edges.get(node_id, {})
        score       = _compute_signal_score(edge_counts)

        sig = TickerSignal(
            ticker       = ticker,
            node_id      = node_id,
            in_universe  = in_uni,
            auto_added   = auto_added,
            tier         = tier,
            edge_counts  = edge_counts,
            score        = score,
            etf_member_of= etf_map.get(ticker, []),
        )
        sig.status = _classify(sig)
        signals[ticker] = sig

    return signals


def _classify(sig: TickerSignal) -> str:
    """Assign a status string to a TickerSignal."""
    if sig.in_universe:
        if sig.score == 0.0:
            return STATUS_DARK
        if sig.auto_added and sig.score <= DEMOTE_THRESHOLD:
            return STATUS_DEMOTE_CANDIDATE
        # "TITAN_ONLY" if the only source is oracle_titan with no diversity
        if sig.edge_counts.keys() <= {"oracle_titan", "oracle_spectre"}:
            return STATUS_TITAN_ONLY
        return STATUS_HEALTHY
    else:
        if sig.score >= PROMOTE_THRESHOLD:
            return STATUS_PROMOTE_CANDIDATE
        return STATUS_GHOST


# ════════════════════════════════════════════════════════════════════════════
# DB writer
# ════════════════════════════════════════════════════════════════════════════

def apply_changes(
    store: IntelStore,
    signals: dict[str, TickerSignal],
    verbose: bool = False,
) -> dict[str, int]:
    """
    Write promotion/demotion/score-update changes to soma_intel_universe.

    Rules:
    - PROMOTE_CANDIDATE → UPSERT (activate if inactive, insert if new; tier='watchlist')
    - DEMOTE_CANDIDATE  → UPDATE active=0  (auto_added=1 only; never demotes manual tickers)
    - All tickers       → UPDATE promotion_score + promotion_source where row exists

    Counts are measured via SQLite changes() after each statement for accuracy.
    """
    now   = datetime.now(timezone.utc).isoformat()
    stats = {"promoted": 0, "demoted": 0, "score_updated": 0}

    for sig in signals.values():
        if sig.status == STATUS_PROMOTE_CANDIDATE:
            n = store.upsert_universe_ticker(
                ticker       = sig.ticker,
                source       = "universe_manager",
                platform_tags= sig.etf_member_of,
                added_ts     = now,
                score        = sig.score,
                promo_source = sig.promotion_source_str,
                tier         = "watchlist",
                auto_added   = True,
            )
            stats["promoted"] += n
            if verbose and n:
                print(f"  PROMOTE  {sig.ticker:<10} score={sig.score:.2f}  "
                      f"sources={sig.promotion_source_str}")

        elif sig.status == STATUS_DEMOTE_CANDIDATE:
            n = store.demote_universe_ticker(sig.ticker)
            stats["demoted"] += n
            if verbose and n:
                print(f"  DEMOTE   {sig.ticker:<10} score={sig.score:.2f}  "
                      f"(auto_added, below threshold)")

        # Refresh score + source on every ticker that has a universe row (active or not)
        n = store.refresh_universe_score(sig.ticker, sig.score, sig.promotion_source_str)
        stats["score_updated"] += n

    store.commit()
    return stats


# ════════════════════════════════════════════════════════════════════════════
# Report printer
# ════════════════════════════════════════════════════════════════════════════

_STATUS_ORDER = {
    STATUS_PROMOTE_CANDIDATE: 0,
    STATUS_DEMOTE_CANDIDATE:  1,
    STATUS_DARK:              2,
    STATUS_HEALTHY:           3,
    STATUS_TITAN_ONLY:        4,
    STATUS_GHOST:             5,
}


def print_report(
    signals: dict[str, TickerSignal],
    ticker_filter: Optional[str] = None,
    compact: bool = False,
) -> None:
    """Print universe signal density report."""

    if ticker_filter:
        sig = signals.get(ticker_filter.upper())
        if not sig:
            print(f"Ticker not found as co_* node: {ticker_filter}")
            return
        _print_single(sig)
        return

    # Group by status
    by_status: dict[str, list[TickerSignal]] = {}
    for sig in signals.values():
        by_status.setdefault(sig.status, []).append(sig)

    # Summary
    total_universe   = sum(1 for s in signals.values() if s.in_universe)
    total_co_nodes   = len(signals)
    promote_count    = len(by_status.get(STATUS_PROMOTE_CANDIDATE, []))
    demote_count     = len(by_status.get(STATUS_DEMOTE_CANDIDATE, []))
    healthy_count    = len(by_status.get(STATUS_HEALTHY, []))
    titan_only_count = len(by_status.get(STATUS_TITAN_ONLY, []))
    dark_count       = len(by_status.get(STATUS_DARK, []))
    ghost_count      = len(by_status.get(STATUS_GHOST, []))

    print(f"\n{'='*60}")
    print(f"SOMA-INTEL Universe Manager Report")
    print(f"{'='*60}")
    print(f"  co_* nodes in graph:   {total_co_nodes}")
    print(f"  Active universe rows:  {total_universe}")
    print(f"")
    print(f"  HEALTHY          (multi-source signal):  {healthy_count}")
    print(f"  TITAN_ONLY       (baseline, no enrich):  {titan_only_count}")
    print(f"  DARK             (zero edges — guard):   {dark_count}")
    print(f"  PROMOTE_CANDIDATE (score ≥ {PROMOTE_THRESHOLD:.1f}):         {promote_count}")
    print(f"  DEMOTE_CANDIDATE  (auto, score ≤ {DEMOTE_THRESHOLD:.1f}):    {demote_count}")
    print(f"  GHOST            (not in universe):      {ghost_count}")

    if compact:
        print()
        return

    # Promote candidates (most interesting first)
    promotes = sorted(by_status.get(STATUS_PROMOTE_CANDIDATE, []),
                      key=lambda x: -x.score)
    if promotes:
        print(f"\n{'─'*60}")
        print(f"PROMOTE CANDIDATES ({len(promotes)})")
        print(f"  (not in universe, score ≥ {PROMOTE_THRESHOLD})")
        print(f"{'─'*60}")
        for sig in promotes:
            etf_s = f"  ETF:{','.join(sig.etf_member_of)}" if sig.etf_member_of else ""
            print(f"  {sig.ticker:<12} score={sig.score:>6.2f}  {sig.promotion_source_str}{etf_s}")

    # Demote candidates
    demotes = sorted(by_status.get(STATUS_DEMOTE_CANDIDATE, []),
                     key=lambda x: x.score)
    if demotes:
        print(f"\n{'─'*60}")
        print(f"DEMOTE CANDIDATES ({len(demotes)})  [auto_added=1 only]")
        print(f"{'─'*60}")
        for sig in demotes:
            print(f"  {sig.ticker:<12} score={sig.score:>6.2f}  {sig.promotion_source_str}")

    # Dark (should be empty)
    darks = by_status.get(STATUS_DARK, [])
    if darks:
        print(f"\n{'─'*60}")
        print(f"DARK — in universe but ZERO edges ({len(darks)})")
        print(f"{'─'*60}")
        for sig in darks:
            print(f"  {sig.ticker}")

    # Top healthy tickers by score
    healthy = sorted(by_status.get(STATUS_HEALTHY, []),
                     key=lambda x: -x.score)
    if healthy:
        print(f"\n{'─'*60}")
        print(f"TOP HEALTHY — highest signal scores (top 20)")
        print(f"{'─'*60}")
        for sig in healthy[:20]:
            print(f"  {sig.ticker:<12} score={sig.score:>6.2f}  {sig.promotion_source_str}")

    # Titan-only tickers (just count, no list — too many)
    titan_only = by_status.get(STATUS_TITAN_ONLY, [])
    if titan_only:
        print(f"\n{'─'*60}")
        print(f"TITAN_ONLY — baseline only, no enrichment: {len(titan_only)} tickers")
        print(f"  (run ingest_wiki + ingest_oracle to enrich)")

    print()


def _print_single(sig: TickerSignal) -> None:
    """Print detailed single-ticker diagnosis."""
    print(f"\n{'='*60}")
    print(f"  Ticker:    {sig.ticker}")
    print(f"  Node ID:   {sig.node_id}")
    print(f"  Status:    {sig.status}")
    print(f"  Score:     {sig.score:.3f}  (diversity={sig.source_diversity})")
    print(f"  Universe:  {sig.in_universe}  (tier={sig.tier}, auto_added={sig.auto_added})")
    if sig.etf_member_of:
        print(f"  ETF member of: {', '.join(sig.etf_member_of)}")
    print(f"\n  Edge counts by source:")
    if sig.edge_counts:
        for st, cnt in sorted(sig.edge_counts.items()):
            weight   = SOURCE_WEIGHTS.get(st, _DEFAULT_WEIGHT)
            contrib  = cnt * weight
            print(f"    {st:<20} {cnt:>4} edges  × {weight:.1f} = {contrib:.1f}")
    else:
        print("    (no edges)")
    print(f"\n  Promotion source: {sig.promotion_source_str}")
    print()


# ════════════════════════════════════════════════════════════════════════════
# Main
# ════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="SOMA-INTEL universe signal density manager"
    )
    parser.add_argument("--apply",       action="store_true",
                        help="Write promotions/demotions/score updates to DB")
    parser.add_argument("--report-only", action="store_true",
                        help="Print compact summary only (no detail lists)")
    parser.add_argument("--ticker",      default="",
                        help="Diagnose a single ticker (e.g. --ticker NVDA)")
    parser.add_argument("--verbose",     action="store_true",
                        help="Show each change during --apply")
    parser.add_argument("--promote-threshold", type=float, default=PROMOTE_THRESHOLD,
                        help=f"Score threshold for promotion (default {PROMOTE_THRESHOLD})")
    parser.add_argument("--demote-threshold",  type=float, default=DEMOTE_THRESHOLD,
                        help=f"Score threshold for demotion (default {DEMOTE_THRESHOLD})")
    args = parser.parse_args()

    # Allow CLI override of thresholds (rebind module-level names)
    import soma.intel.universe_manager as _self
    _self.PROMOTE_THRESHOLD = args.promote_threshold
    _self.DEMOTE_THRESHOLD  = args.demote_threshold

    dry_run = not args.apply
    if dry_run and not args.ticker:
        print("DRY RUN — pass --apply to write changes")

    with IntelStore(db_path=DB_PATH) as store:
        print("Computing signal density..." if not args.ticker else "", end="", flush=True)
        signals = compute_all_signals(store)
        if not args.ticker:
            print(f" {len(signals)} co_* nodes scored.")

        print_report(
            signals,
            ticker_filter=args.ticker or None,
            compact=args.report_only,
        )

        if args.apply and not args.ticker:
            print("Applying changes...")
            stats = apply_changes(store, signals, verbose=args.verbose)
            print(f"  Promoted:      {stats['promoted']}")
            print(f"  Demoted:       {stats['demoted']}")
            print(f"  Score updated: {stats['score_updated']}")
            print()


if __name__ == "__main__":
    main()
