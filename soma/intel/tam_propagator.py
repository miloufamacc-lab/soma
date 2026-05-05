#!/usr/bin/env python3
"""
SOMA-INTEL Phase 4 Step 4.3 — TAM Propagator

Weights each ticker's signal score by its best platform's S-curve position
and writes a tam_score belief to soma_intel_belief.

Algorithm:
  For each ticker with ≥1 belongs_to_platform edge:
    1. Look up each platform's position from soma_intel_platform
    2. Find the platform with the highest position multiplier (best runway)
    3. tam_score = signal_score × best_multiplier × (1 + 0.10 × extra_platforms)
       extra_platforms = platform_count − 1 (convergence bonus; 0.10 per P5.1 — was 0.15)
    4. Write soma_intel_belief: predicate='tam_score', supersedes prior

Position multipliers (reflect TAM growth optionality) — Option B, approved 2026-05-05:
  pre-takeoff   → 2.0×   (strong runway, early mover advantage)
  acceleration  → 1.7×   (momentum, TAM expanding rapidly)
  inflection    → 1.3×   (at peak growth rate, high visibility)
  deceleration  → 1.0×   (neutral — past peak growth, market maturing)
  saturation    → 0.8×   (crowded, limited organic TAM expansion)

Usage:
  python3 soma/intel/tam_propagator.py           # dry run
  python3 soma/intel/tam_propagator.py --apply   # write to DB
  python3 soma/intel/tam_propagator.py --top 20  # show top N tickers
  python3 soma/intel/tam_propagator.py --verbose
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_HERE    = Path(__file__).resolve().parent
_DABEIBA = _HERE.parent.parent.parent
for _p in [str(_DABEIBA), str(_DABEIBA / "shared")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from soma.intel.store import IntelStore

DB_PATH = (
    Path(os.environ["SOMA_DB_PATH"])
    if "SOMA_DB_PATH" in os.environ
    else _DABEIBA / "shared" / "soma" / "data" / "soma.db"
)

NOW = datetime.now(timezone.utc).isoformat()

# ── Position → TAM multiplier ──────────────────────────────────────────────────
POSITION_MULTIPLIERS: dict[str, float] = {
    "pre-takeoff":  2.0,   # Option B — approved 2026-05-05
    "acceleration": 1.7,
    "inflection":   1.3,
    "deceleration": 1.0,
    "saturation":   0.8,
}
DEFAULT_MULTIPLIER  = 1.0
CONVERGENCE_BONUS   = 0.10   # +10% per additional platform beyond the first (narrowed from 0.15 per P5.1 / 2026-05-04 OPUS decision)
MIN_SIGNAL_SCORE    = 0.01   # skip tickers with no meaningful signal belief


# ══════════════════════════════════════════════════════════════════════════════
# Data loaders
# ══════════════════════════════════════════════════════════════════════════════

def _load_platform_positions(store: IntelStore) -> dict[str, str]:
    """platform_id → position label (or 'unknown' if not yet fitted)."""
    return store.list_platform_positions()


def _load_ticker_platforms(store: IntelStore) -> dict[str, list[str]]:
    """ticker → list of platform_ids (from active belongs_to_platform edges)."""
    return store.get_ticker_platforms()


def _load_signal_scores(store: IntelStore) -> dict[str, float]:
    """ticker → signal_score from active belief (0.0 if missing)."""
    beliefs = store.get_active_beliefs("signal_score")
    out: dict[str, float] = {}
    for b in beliefs:
        node_id = b["subject_node_id"]
        if node_id.startswith("co_"):
            ticker = node_id[3:]
            try:
                out[ticker] = float(b["value"])
            except (ValueError, TypeError):
                pass
    return out


# ══════════════════════════════════════════════════════════════════════════════
# Score calculation
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class TAMScore:
    ticker:          str
    signal_score:    float
    platforms:       list[str]
    best_platform:   str
    best_position:   str
    best_mult:       float
    conv_bonus:      float
    tam_score:       float
    confidence:      float


def compute_tam_scores(
    ticker_platforms: dict[str, list[str]],
    signal_scores:    dict[str, float],
    platform_pos:     dict[str, str],
) -> list[TAMScore]:
    results: list[TAMScore] = []

    for ticker, platforms in ticker_platforms.items():
        sig = signal_scores.get(ticker, 0.0)
        if sig < MIN_SIGNAL_SCORE:
            continue

        # Find best platform multiplier
        best_pl   = platforms[0]
        best_pos  = platform_pos.get(best_pl, "unknown")
        best_mult = POSITION_MULTIPLIERS.get(best_pos, DEFAULT_MULTIPLIER)

        for pl in platforms[1:]:
            pos  = platform_pos.get(pl, "unknown")
            mult = POSITION_MULTIPLIERS.get(pos, DEFAULT_MULTIPLIER)
            if mult > best_mult:
                best_mult = mult
                best_pl   = pl
                best_pos  = pos

        # Convergence bonus
        extra    = max(0, len(platforms) - 1)
        conv_b   = extra * CONVERGENCE_BONUS
        tam      = round(sig * best_mult * (1.0 + conv_b), 4)

        # Confidence: min(0.95, tam_score / 60.0) — 60 ≈ NVDA-class max
        conf = round(min(0.95, tam / 60.0), 4)

        results.append(TAMScore(
            ticker        = ticker,
            signal_score  = round(sig, 4),
            platforms     = platforms,
            best_platform = best_pl,
            best_position = best_pos,
            best_mult     = best_mult,
            conv_bonus    = round(conv_b, 3),
            tam_score     = tam,
            confidence    = conf,
        ))

    return sorted(results, key=lambda s: s.tam_score, reverse=True)


# ══════════════════════════════════════════════════════════════════════════════
# DB write
# ══════════════════════════════════════════════════════════════════════════════

def _write_tam_belief(store: IntelStore, ts: TAMScore) -> None:
    """Upsert a tam_score belief for this ticker, superseding the prior."""
    node_id = f"co_{ts.ticker}"
    store.upsert_belief(
        node_id    = node_id,
        predicate  = "tam_score",
        value      = f"{ts.tam_score:.4f}",
        confidence = ts.confidence,
        source_id  = "tam_propagator",
    )


# ══════════════════════════════════════════════════════════════════════════════
# Runner
# ══════════════════════════════════════════════════════════════════════════════

def run_tam(
    store:   IntelStore,
    dry_run: bool,
    verbose: bool,
    top_n:   int,
) -> dict:
    platform_pos     = _load_platform_positions(store)
    ticker_platforms = _load_ticker_platforms(store)
    signal_scores    = _load_signal_scores(store)

    scores = compute_tam_scores(ticker_platforms, signal_scores, platform_pos)

    # Print top-N table
    print(f"\n  {'Ticker':<8} {'TAM':>7}  {'Sig':>6}  {'Mult':>5}  "
          f"{'Conv+':>5}  {'BestPlatform':<22}  Position")
    print("  " + "─" * 78)
    for s in scores[:top_n]:
        print(
            f"  {s.ticker:<8} {s.tam_score:>7.2f}  {s.signal_score:>6.2f}  "
            f"{s.best_mult:>5.1f}  {s.conv_bonus:>5.2f}  "
            f"{s.best_platform:<22}  {s.best_position}"
        )

    if not dry_run:
        for s in scores:
            _write_tam_belief(store, s)
        store.commit()

    return {
        "tickers_scored":  len(scores),
        "beliefs_written": len(scores) if not dry_run else 0,
        "top_ticker":      scores[0].ticker if scores else "—",
        "top_tam":         scores[0].tam_score if scores else 0.0,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="SOMA-INTEL TAM propagator — S-curve weighted signal scores"
    )
    parser.add_argument("--apply",   action="store_true",
                        help="Write tam_score beliefs to DB (default: dry run)")
    parser.add_argument("--top",     type=int, default=20, metavar="N",
                        help="Show top N tickers (default: 20)")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    dry_run = not args.apply
    if dry_run:
        print("DRY RUN — pass --apply to write to DB\n")

    with IntelStore(db_path=DB_PATH) as store:
        print("[TAM Propagator] Computing TAM-adjusted scores...")
        stats = run_tam(store, dry_run=dry_run, verbose=args.verbose, top_n=args.top)

        print(f"\n  Tickers scored:   {stats['tickers_scored']}")
        print(f"  Beliefs written:  {stats['beliefs_written']}")
        print(f"  Top ticker:       {stats['top_ticker']}  TAM={stats['top_tam']:.2f}")

        if not dry_run:
            total_tam = store.count_active_beliefs("tam_score")
            print(f"\nDB: {total_tam} active tam_score beliefs")

    if dry_run:
        print("\nDRY RUN complete — pass --apply to write.")
    else:
        print("\ntam_propagator: OK")


if __name__ == "__main__":
    main()
