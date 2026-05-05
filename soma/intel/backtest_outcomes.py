"""
SOMA-INTEL P5.3.c — Backtest Outcome Scorer

For each signal in soma_intel_signal_backtest (written by backtest_runner.py),
computes a 60-calendar-day forward return and scores the signal as hit, miss,
or data_unavailable.

Direction inference (from regime composite_label):
  bull*        → direction = long   → hit if forward_return > 0
  bear*        → direction = short  → hit if forward_return < 0
  transition*  → direction = absolute → hit if |forward_return| > TRANSITION_THRESHOLD

Scoring rules:
  - data_unavailable: price data absent for ticker/date in soma_intel_price_history
  - hit:  direction prediction was correct (see above)
  - miss: direction prediction was wrong

TRANSITION_THRESHOLD defaults to 0.02 (2%). Configurable via --threshold.

CLI:
  python3 backtest_outcomes.py --score --run-id in_sample_20240506_20260305
  python3 backtest_outcomes.py --score --run-id oos_20260306_20260505
  python3 backtest_outcomes.py --summary --run-id <RUN_ID>
  python3 backtest_outcomes.py --summary --all
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ── Path bootstrap ─────────────────────────────────────────────────────────────
_HERE         = Path(__file__).resolve().parent
_DABEIBA_ROOT = _HERE.parent.parent.parent
for _p in [str(_DABEIBA_ROOT), str(_DABEIBA_ROOT / "shared")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from soma.intel.store import IntelStore

# ── Constants ─────────────────────────────────────────────────────────────────
FORWARD_HORIZON_DAYS   = 60      # calendar days
TRANSITION_THRESHOLD   = 0.02    # 2% absolute move = hit for transition regime

_SOMA_DB = _DABEIBA_ROOT / "shared" / "soma" / "data" / "soma.db"

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(format="%(levelname)-5s %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)


# ── Direction inference ────────────────────────────────────────────────────────

def _trend_state(regime_label: Optional[str]) -> str:
    """
    Extract trend state from composite_label (format: {trend}_{vol}_{macro}).
    Returns 'bull' | 'bear' | 'transition' | 'unknown'.
    """
    if not regime_label:
        return "unknown"
    first = regime_label.split("_")[0].lower()
    if first in ("bull", "bear", "transition"):
        return first
    return "unknown"


def _infer_direction(regime_label: Optional[str]) -> str:
    """
    Map regime trend state → trade direction.
    bull → long | bear → short | transition/unknown → absolute
    """
    state = _trend_state(regime_label)
    return {"bull": "long", "bear": "short"}.get(state, "absolute")


# ── Outcome scoring ────────────────────────────────────────────────────────────

def _score_signal(
    forward_return: Optional[float],
    direction_label: str,
    transition_threshold: float = TRANSITION_THRESHOLD,
) -> str:
    """
    Return 'hit', 'miss', or 'data_unavailable'.

    Args:
        forward_return:      60d fwd return (None = unavailable).
        direction_label:     'long' | 'short' | 'absolute'
        transition_threshold: abs return floor for 'absolute' hits.
    """
    if forward_return is None:
        return "data_unavailable"

    if direction_label == "long":
        return "hit" if forward_return > 0 else "miss"
    elif direction_label == "short":
        return "hit" if forward_return < 0 else "miss"
    else:  # absolute
        return "hit" if abs(forward_return) > transition_threshold else "miss"


# ── Core scoring loop ──────────────────────────────────────────────────────────

def score_run(
    store: IntelStore,
    run_id: str,
    horizon_days: int = FORWARD_HORIZON_DAYS,
    transition_threshold: float = TRANSITION_THRESHOLD,
    force: bool = False,
) -> dict:
    """
    Score all unsorted rows for run_id.

    If force=True, re-scores rows that already have an outcome.
    Returns a stats dict.
    """
    if force:
        pending = store._c.execute(
            "SELECT * FROM soma_intel_signal_backtest "
            "WHERE backtest_run_id=? ORDER BY sim_date, bt_id",
            (run_id,),
        ).fetchall()
    else:
        pending = store._c.execute(
            "SELECT * FROM soma_intel_signal_backtest "
            "WHERE backtest_run_id=? AND outcome IS NULL "
            "ORDER BY sim_date, bt_id",
            (run_id,),
        ).fetchall()

    if not pending:
        log.info("No unscored rows for run_id=%s (use --force to re-score).", run_id)
        return {"run_id": run_id, "scored": 0}

    log.info("Scoring %d signals for run_id=%s ...", len(pending), run_id)

    scored_ts = datetime.now(timezone.utc).isoformat()
    stats = {
        "run_id":           run_id,
        "total":            len(pending),
        "hit":              0,
        "miss":             0,
        "data_unavailable": 0,
        "scored":           0,
    }

    for row in pending:
        ticker   = row["ticker"]
        sim_date = row["sim_date"]
        bt_id    = row["bt_id"]

        # Forward return from price history
        fwd_return = store.get_forward_return(
            ticker       = ticker,
            signal_date  = sim_date,
            horizon_days = horizon_days,
        )

        direction = _infer_direction(row["regime_label"])
        outcome   = _score_signal(fwd_return, direction, transition_threshold)

        store._c.execute(
            """
            UPDATE soma_intel_signal_backtest
            SET forward_return=?, direction_label=?, outcome=?, scored_ts=?
            WHERE bt_id=?
            """,
            (fwd_return, direction, outcome, scored_ts, bt_id),
        )

        stats[outcome] += 1
        stats["scored"] += 1

    store._c.commit()
    log.info(
        "Scored: hit=%d  miss=%d  data_unavailable=%d",
        stats["hit"], stats["miss"], stats["data_unavailable"],
    )
    return stats


# ── Summary report ─────────────────────────────────────────────────────────────

def _precision(hits: int, total_scored: int) -> float:
    """Precision = hits / (hits + misses). Excludes data_unavailable."""
    if total_scored == 0:
        return float("nan")
    return hits / total_scored


def print_summary(store: IntelStore, run_ids: Optional[list[str]] = None) -> None:
    """Print per-run precision table. If run_ids is None, show all runs."""
    if run_ids:
        placeholders = ",".join("?" * len(run_ids))
        rows = store._c.execute(
            f"""
            SELECT
                backtest_run_id,
                priority,
                COUNT(*) AS total,
                SUM(CASE WHEN outcome='hit'  THEN 1 ELSE 0 END) AS hits,
                SUM(CASE WHEN outcome='miss' THEN 1 ELSE 0 END) AS misses,
                SUM(CASE WHEN outcome='data_unavailable' THEN 1 ELSE 0 END) AS unavail
            FROM soma_intel_signal_backtest
            WHERE backtest_run_id IN ({placeholders})
            GROUP BY backtest_run_id, priority
            ORDER BY backtest_run_id, priority
            """,
            run_ids,
        ).fetchall()
    else:
        rows = store._c.execute(
            """
            SELECT
                backtest_run_id,
                priority,
                COUNT(*) AS total,
                SUM(CASE WHEN outcome='hit'  THEN 1 ELSE 0 END) AS hits,
                SUM(CASE WHEN outcome='miss' THEN 1 ELSE 0 END) AS misses,
                SUM(CASE WHEN outcome='data_unavailable' THEN 1 ELSE 0 END) AS unavail
            FROM soma_intel_signal_backtest
            GROUP BY backtest_run_id, priority
            ORDER BY backtest_run_id, priority
            """
        ).fetchall()

    if not rows:
        print("No scored signals found.")
        return

    # §E precision targets from spec
    STOP_SHIP_THRESHOLD = 0.40   # P1 precision below this = stop-ship
    TARGET_PRECISION    = 0.60   # P1 target

    print(f"\n{'Run ID':<40} {'Priority':<10} {'Total':>6} {'Hits':>6} "
          f"{'Misses':>7} {'N/A':>6} {'Precision':>10} {'Status':>10}")
    print("-" * 100)

    for r in rows:
        hits   = r["hits"]   or 0
        misses = r["misses"] or 0
        unavail= r["unavail"] or 0
        scored = hits + misses
        prec   = _precision(hits, scored)

        if scored == 0:
            status = "no_data"
        elif r["priority"] in ("P1", "HIGH") and prec < STOP_SHIP_THRESHOLD:
            status = "STOP_SHIP"
        elif r["priority"] in ("P1", "HIGH") and prec >= TARGET_PRECISION:
            status = "ON_TARGET"
        else:
            status = "BELOW_TGT" if prec < TARGET_PRECISION else "OK"

        prec_str = f"{prec:.1%}" if scored > 0 else "N/A"
        print(
            f"{r['backtest_run_id']:<40} {r['priority']:<10} {r['total']:>6} "
            f"{hits:>6} {misses:>7} {unavail:>6} {prec_str:>10} {status:>10}"
        )
    print()

    # Highlight STOP_SHIP
    stop_ships = [r for r in rows
                  if r["priority"] in ("P1", "HIGH")
                  and (r["hits"] or 0) + (r["misses"] or 0) > 0
                  and _precision(r["hits"] or 0, (r["hits"] or 0) + (r["misses"] or 0))
                      < STOP_SHIP_THRESHOLD]
    if stop_ships:
        print(f"  ** STOP-SHIP: {len(stop_ships)} P1/HIGH group(s) below {STOP_SHIP_THRESHOLD:.0%} precision **")


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="SOMA-INTEL backtest outcome scorer (P5.3.c)"
    )
    parser.add_argument("--score",     action="store_true", help="Score a run")
    parser.add_argument("--summary",   action="store_true", help="Print precision summary")
    parser.add_argument("--all",       action="store_true", help="Apply to all runs")
    parser.add_argument("--run-id",    default=None,        help="Run ID to score/summarize")
    parser.add_argument("--force",     action="store_true", help="Re-score already-scored rows")
    parser.add_argument("--horizon",   type=int, default=FORWARD_HORIZON_DAYS,
                        help=f"Forward horizon in calendar days (default {FORWARD_HORIZON_DAYS})")
    parser.add_argument("--threshold", type=float, default=TRANSITION_THRESHOLD,
                        help=f"Abs return threshold for transition regime hits (default {TRANSITION_THRESHOLD})")
    parser.add_argument("--db",        default=str(_SOMA_DB), help="Path to soma.db")
    args = parser.parse_args()

    with IntelStore(db_path=args.db) as store:

        if args.score:
            if args.all:
                run_ids = [
                    r["backtest_run_id"]
                    for r in store._c.execute(
                        "SELECT DISTINCT backtest_run_id FROM soma_intel_signal_backtest"
                    ).fetchall()
                ]
            elif args.run_id:
                run_ids = [args.run_id]
            else:
                parser.error("--score requires --run-id or --all")
                return

            for rid in run_ids:
                stats = score_run(
                    store                = store,
                    run_id               = rid,
                    horizon_days         = args.horizon,
                    transition_threshold = args.threshold,
                    force                = args.force,
                )
                print(f"  {rid}: scored={stats.get('scored',0)} "
                      f"hit={stats.get('hit',0)} "
                      f"miss={stats.get('miss',0)} "
                      f"data_unavailable={stats.get('data_unavailable',0)}")

            if not args.all:
                print(f"\n  Next step: python3 backtest_report.py --run-id {run_ids[0]}")
            return

        if args.summary:
            if args.all:
                print_summary(store, run_ids=None)
            elif args.run_id:
                print_summary(store, run_ids=[args.run_id])
            else:
                print_summary(store, run_ids=None)
            return

        parser.print_help()


if __name__ == "__main__":
    main()
