#!/usr/bin/env python3
"""
SOMA-INTEL Phase 2 Step 2.2 — Signal Propagator

Time-decayed aggregate signal score per active universe ticker.

Algorithm:
  For each co_TICKER node in the active universe:
    1. Gather all incident edges (outgoing + incoming), skip superseded
    2. Per edge: decay_weight = confidence × 0.5^(age_days / half_life_days)
    3. raw_score = Σ decay_weight
    4. corroboration = |distinct source_types with weight > 0|
    5. Map to priority (HIGH ≥ 10.0, MEDIUM ≥ 4.0, LOW < 4.0)
    6. anomaly_score = min(1.0, raw_score / 30.0)
    7. Upsert soma_intel_signal: insert on first run, reconfirm on same-day re-run

Tickers below MIN_SCORE_THRESHOLD are skipped (no signal row written).
The convergence_engine's rows (notes != 'signal_propagator:*') are untouched.

Usage:
  python3 soma/intel/signal_propagator.py           # dry run, top 15
  python3 soma/intel/signal_propagator.py --apply   # write to DB
  python3 soma/intel/signal_propagator.py --ticker NVDA PLTR   # single / few
  python3 soma/intel/signal_propagator.py --top 25  # show more rows
  python3 soma/intel/signal_propagator.py --verbose  # per-ticker breakdown
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

# ── Path bootstrap ─────────────────────────────────────────────────────────────
_HERE    = Path(__file__).resolve().parent
_DABEIBA = _HERE.parent.parent.parent
for _p in [str(_DABEIBA), str(_DABEIBA / "shared")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from soma.intel.store import IntelStore

# ── DB path ────────────────────────────────────────────────────────────────────
DB_PATH = (
    Path(os.environ["SOMA_DB_PATH"])
    if "SOMA_DB_PATH" in os.environ
    else _DABEIBA / "shared" / "soma" / "data" / "soma.db"
)

TODAY = date.today().isoformat()
NOW   = datetime.now(timezone.utc).isoformat()

# ── Config (tunable via CLI for experiments) ───────────────────────────────────
MIN_SCORE_THRESHOLD = 0.05   # tickers below this → no signal row
TOP_EDGE_LIMIT      = 5      # max edges in features JSON

# Priority thresholds (raw decayed score)
PRIORITY_HIGH   = 10.0
PRIORITY_MEDIUM =  4.0

# Horizon placeholder (§J spec: tactical | thematic | structural).
# All propagated signals default to 'thematic' until horizon track modules
# (horizon_tactical.py, horizon_thematic.py, horizon_structural.py) are built.
# NEVER map priority → horizon — they are orthogonal axes per spec.
HORIZON_PLACEHOLDER = "thematic"

# Tag embedded in notes field — lets convergence_engine rows coexist cleanly
PROPAGATOR_TAG = "signal_propagator"


# ══════════════════════════════════════════════════════════════════════════════
# Score calculation
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class EdgeContribution:
    edge_id:     int
    src:         str
    dst:         str
    edge_type:   str
    source_type: str
    confidence:  float
    half_life:   float
    age_days:    float
    weight:      float   # confidence × 0.5^(age_days / half_life)


@dataclass
class TickerScore:
    ticker:           str
    raw_score:        float
    corroboration:    int                     # distinct source_types with contribution > 0
    edge_count:       int
    source_breakdown: dict[str, float]        # source_type → total decayed weight
    top_edges:        list[EdgeContribution]  # highest-weight edges (≤ TOP_EDGE_LIMIT)
    avg_half_life:    float                   # weighted-average half_life_days


def _age_days(ts_str: str) -> float:
    """ISO 8601 edge timestamp → fractional days from today (floor at 0)."""
    try:
        edge_date = date.fromisoformat(ts_str[:10])
        return max(0.0, float((date.today() - edge_date).days))
    except (ValueError, TypeError):
        return 0.0


def _decay(confidence: float, age_days: float, half_life: float) -> float:
    """Exponential half-life decay: w = confidence × 2^(−age/half_life)."""
    if half_life <= 0:
        return confidence
    return confidence * (0.5 ** (age_days / half_life))


def score_ticker(
    store: IntelStore,
    ticker: str,
    verbose: bool = False,
) -> Optional[TickerScore]:
    """
    Compute the time-decayed aggregate signal score for a single ticker.
    Returns None if score < MIN_SCORE_THRESHOLD.
    """
    node_id = f"co_{ticker}"

    # Collect all non-superseded edges incident to this company node via IntelStore
    edges = store.neighbors(node_id)

    if not edges:
        return None

    contributions: list[EdgeContribution] = []
    source_weights: dict[str, float]      = {}

    for edge in edges:
        hl  = float(edge.half_life_days) if edge.half_life_days else 30.0
        age = _age_days(edge.ts)
        w   = _decay(edge.confidence, age, hl)
        st  = edge.source_type or "unknown"

        ec = EdgeContribution(
            edge_id     = edge.edge_id,
            src         = edge.src_node_id,
            dst         = edge.dst_node_id,
            edge_type   = edge.edge_type,
            source_type = st,
            confidence  = edge.confidence,
            half_life   = hl,
            age_days    = age,
            weight      = w,
        )
        contributions.append(ec)
        source_weights[st] = source_weights.get(st, 0.0) + w

    raw_score = sum(c.weight for c in contributions)
    if raw_score < MIN_SCORE_THRESHOLD:
        return None

    total_w = raw_score or 1.0
    avg_hl  = sum(c.weight * c.half_life for c in contributions) / total_w

    top = sorted(contributions, key=lambda c: c.weight, reverse=True)[:TOP_EDGE_LIMIT]

    return TickerScore(
        ticker           = ticker,
        raw_score        = raw_score,
        corroboration    = len(source_weights),
        edge_count       = len(contributions),
        source_breakdown = {
            k: round(v, 4)
            for k, v in sorted(source_weights.items(), key=lambda x: -x[1])
        },
        top_edges     = top,
        avg_half_life = round(avg_hl, 1),
    )


# ── Priority / anomaly helpers ─────────────────────────────────────────────────

def _priority(score: float) -> str:
    if score >= PRIORITY_HIGH:
        return "HIGH"
    if score >= PRIORITY_MEDIUM:
        return "MEDIUM"
    return "LOW"


def _anomaly(score: float) -> float:
    """Soft-cap normalisation: score=30 (NVDA-class) → 1.0."""
    return round(min(1.0, score / 30.0), 4)


def _features_json(ts: TickerScore) -> str:
    return json.dumps({
        "propagated_score":   round(ts.raw_score, 4),
        "source_breakdown":   ts.source_breakdown,
        "edge_count":         ts.edge_count,
        "corroboration":      ts.corroboration,
        "avg_half_life_days": ts.avg_half_life,
        "top_edges": [
            {
                "src":    e.src,
                "dst":    e.dst,
                "type":   e.edge_type,
                "source": e.source_type,
                "w":      round(e.weight, 4),
            }
            for e in ts.top_edges
        ],
    })


# ══════════════════════════════════════════════════════════════════════════════
# DB write — upsert soma_intel_signal
# ══════════════════════════════════════════════════════════════════════════════

def _upsert_signal(store: IntelStore, ts: TickerScore) -> str:
    """
    Insert or reconfirm a propagated signal row for (ticker, TODAY).
    Returns 'inserted' | 'reconfirmed'.
    """
    pri          = _priority(ts.raw_score)
    anom         = _anomaly(ts.raw_score)
    features_str = _features_json(ts)
    hl_days      = int(round(ts.avg_half_life))
    notes        = (
        f"{PROPAGATOR_TAG}: score={ts.raw_score:.3f} "
        f"corr={ts.corroboration} edges={ts.edge_count}"
    )

    # Check for an existing propagated row for (ticker, date) via IntelStore
    existing = store.get_signal(ts.ticker, TODAY, PROPAGATOR_TAG)

    if existing:
        store.update_signal(
            signal_id    = existing["signal_id"],
            priority     = pri,
            anomaly_score= anom,
            features     = features_str,
            corroboration= ts.corroboration,
            half_life    = hl_days,
            horizon      = HORIZON_PLACEHOLDER,
            notes        = notes,
        )
        return "reconfirmed"

    store.insert_signal(
        ticker        = ts.ticker,
        date          = TODAY,
        priority      = pri,
        anomaly_score = anom,
        features      = features_str,
        corroboration = ts.corroboration,
        half_life     = hl_days,
        horizon       = HORIZON_PLACEHOLDER,
        notes         = notes,
    )
    return "inserted"


# ══════════════════════════════════════════════════════════════════════════════
# Propagator runner
# ══════════════════════════════════════════════════════════════════════════════

def run_propagator(
    store:   IntelStore,
    tickers: Optional[list[str]],
    dry_run: bool,
    verbose: bool,
    top_n:   int,
) -> dict:
    stats = {
        "tickers_scored":  0,
        "signals_written": 0,
        "reconfirmed":     0,
        "skipped_low":     0,
    }

    # Universe source
    if tickers:
        ticker_list = tickers
    else:
        ticker_list = store.list_active_universe_tickers()

    all_scores: list[TickerScore] = []

    for ticker in ticker_list:
        ts = score_ticker(store, ticker, verbose=False)
        if ts is None:
            stats["skipped_low"] += 1
            continue

        stats["tickers_scored"] += 1
        all_scores.append(ts)

        if verbose:
            bkd = "  ".join(f"{k}={v:.1f}" for k, v in list(ts.source_breakdown.items())[:3])
            print(
                f"  {ticker:<8} score={ts.raw_score:6.2f}  "
                f"corr={ts.corroboration}  edges={ts.edge_count}  {bkd}"
            )

        if not dry_run:
            outcome = _upsert_signal(store, ts)
            if outcome == "reconfirmed":
                stats["reconfirmed"] += 1
            else:
                stats["signals_written"] += 1

    if not dry_run:
        store.commit()

    # Top-N summary table
    top = sorted(all_scores, key=lambda s: s.raw_score, reverse=True)[:top_n]
    if top:
        print(f"\n  {'Ticker':<8} {'Score':>7}  {'Pri':<7}  {'Corr':>4}  "
              f"{'Edges':>5}  Top source")
        print("  " + "─" * 68)
        for s in top:
            pri = _priority(s.raw_score)
            top_src = next(iter(s.source_breakdown), "—")
            top_w   = s.source_breakdown.get(top_src, 0.0)
            print(
                f"  {s.ticker:<8} {s.raw_score:>7.2f}  {pri:<7}  "
                f"{s.corroboration:>4}  {s.edge_count:>5}  {top_src}={top_w:.1f}"
            )

    return stats


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="SOMA-INTEL signal propagator — time-decayed score per ticker"
    )
    parser.add_argument("--apply",   action="store_true",
                        help="Write to DB (default: dry run)")
    parser.add_argument("--ticker",  nargs="+", metavar="TICKER",
                        help="Score specific tickers only")
    parser.add_argument("--top",     type=int, default=15, metavar="N",
                        help="Show top N by score (default: 15)")
    parser.add_argument("--min-score", type=float, default=None, metavar="S",
                        help=f"Override MIN_SCORE_THRESHOLD (default: {MIN_SCORE_THRESHOLD})")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    dry_run = not args.apply
    if args.min_score is not None:
        import soma.intel.signal_propagator as _self
        _self.MIN_SCORE_THRESHOLD = args.min_score

    if dry_run:
        print("DRY RUN — pass --apply to write to DB\n")

    with IntelStore(db_path=DB_PATH) as store:
        print("[Signal Propagator] Scoring universe tickers...")
        stats = run_propagator(
            store,
            tickers = args.ticker,
            dry_run = dry_run,
            verbose = args.verbose,
            top_n   = args.top,
        )

        print(f"\n  Tickers scored:  {stats['tickers_scored']}")
        print(f"  Signals written: {stats['signals_written']}")
        print(f"  Reconfirmed:     {stats['reconfirmed']}")
        print(f"  Skipped (low):   {stats['skipped_low']}")

        # DB snapshot
        print("\nDB snapshot:")
        for table in ("soma_intel_edge", "soma_intel_node",
                      "soma_intel_signal", "soma_intel_belief"):
            cnt = store.count_table(table)
            print(f"  {table:<30} {cnt}")

    if dry_run:
        print("\nDRY RUN complete — pass --apply to write.")
    else:
        print("\nsignal_propagator: OK")


if __name__ == "__main__":
    main()
