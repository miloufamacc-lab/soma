#!/usr/bin/env python3
"""
SOMA-INTEL Phase 3 Step 3.1 — Signal Sweep

Daily maintenance pass over soma_intel_signal and soma_intel_belief.
Keeps the signal table clean as data ages and prevents belief table bloat.

Three passes:

  PASS 1 — Expiry
    Marks signals as 'expired' when age_days > EXPIRY_MULTIPLIER × half_life_days.
    Applies to all non-expired signals regardless of source.
    Protects: 'reconfirmed' signals get one extra half_life of grace.

  PASS 2 — Belief pruning
    Deletes soma_intel_belief rows that are:
      - superseded (superseded_by IS NOT NULL), AND
      - older than BELIEF_PRUNE_DAYS
    Active beliefs (superseded_by IS NULL) are never pruned.

  PASS 3 — Reconfirmation
    For active propagated signals not updated today, re-scores the ticker
    using signal_propagator.score_ticker():
      - score >= MIN_SCORE_THRESHOLD → refresh row (reconfirmation_count + 1)
      - score < MIN_SCORE_THRESHOLD → expire (score collapsed)
    Skips convergence signals (managed by convergence_engine).

All passes are dry-run by default. Pass --apply to commit.

Usage:
  python3 soma/intel/signal_sweep.py               # dry run, all passes
  python3 soma/intel/signal_sweep.py --apply        # write to DB
  python3 soma/intel/signal_sweep.py --apply --no-reconfirm  # expiry + prune only
  python3 soma/intel/signal_sweep.py --apply --pass 1         # single pass
  python3 soma/intel/signal_sweep.py --ticker NVDA TSLA       # targeted sweep
  python3 soma/intel/signal_sweep.py --verbose
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

# ── Path bootstrap ─────────────────────────────────────────────────────────────
_HERE    = Path(__file__).resolve().parent
_DABEIBA = _HERE.parent.parent.parent
for _p in [str(_DABEIBA), str(_DABEIBA / "shared")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from soma.intel.store import IntelStore
from soma.intel.signal_propagator import (
    score_ticker,
    _upsert_signal,
    MIN_SCORE_THRESHOLD,
    PROPAGATOR_TAG,
)

# ── DB path ────────────────────────────────────────────────────────────────────
DB_PATH = (
    Path(os.environ["SOMA_DB_PATH"])
    if "SOMA_DB_PATH" in os.environ
    else _DABEIBA / "shared" / "soma" / "data" / "soma.db"
)

TODAY = date.today().isoformat()
NOW   = datetime.now(timezone.utc).isoformat()

# ── Config ─────────────────────────────────────────────────────────────────────
EXPIRY_MULTIPLIER  = 2.0    # signals expire at 2× their stored half_life_days
GRACE_MULTIPLIER   = 1.0    # reconfirmed signals get +1× half_life grace period
BELIEF_PRUNE_DAYS  = 90     # delete superseded beliefs older than this many days
CONVERGENCE_TAG    = "convergence"   # substring in notes → skip reconfirm (Pass 3)


# ══════════════════════════════════════════════════════════════════════════════
# Pass 1 — Expiry
# ══════════════════════════════════════════════════════════════════════════════

def run_pass_1(
    store: IntelStore,
    tickers: Optional[list[str]],
    dry_run: bool,
    verbose: bool,
) -> dict:
    """Expire signals whose age exceeds EXPIRY_MULTIPLIER × half_life_days."""
    stats = {"expired": 0, "checked": 0}

    rows = store.list_signals_active(tickers=tickers)

    today_dt = date.today()

    for r in rows:
        stats["checked"] += 1
        signal_date = date.fromisoformat(r["date"])
        age_days    = (today_dt - signal_date).days
        hl          = r["half_life_days"] or 30
        threshold   = hl * EXPIRY_MULTIPLIER

        # Reconfirmed signals get extra grace
        if r["status"] == "reconfirmed":
            threshold += hl * GRACE_MULTIPLIER

        if age_days > threshold:
            if verbose:
                print(
                    f"  [P1:expire] {r['ticker']:<8} date={r['date']}"
                    f"  age={age_days}d  threshold={threshold:.0f}d"
                    f"  hl={hl}d  status={r['status']}"
                )
            if not dry_run:
                store.expire_signal(r["signal_id"])
            stats["expired"] += 1

    if not dry_run:
        store.commit()

    return stats


# ══════════════════════════════════════════════════════════════════════════════
# Pass 2 — Belief pruning
# ══════════════════════════════════════════════════════════════════════════════

def run_pass_2(
    store: IntelStore,
    dry_run: bool,
    verbose: bool,
) -> dict:
    """Delete superseded beliefs older than BELIEF_PRUNE_DAYS."""
    stats = {"pruned": 0, "checked": 0}

    cutoff = (date.today() - timedelta(days=BELIEF_PRUNE_DAYS)).isoformat()

    rows = store.list_superseded_beliefs_before(cutoff)

    stats["checked"] = len(rows)

    if verbose and rows:
        oldest = rows[0]["ts"][:10] if rows else "—"
        print(f"  [P2] {len(rows)} superseded beliefs older than {cutoff} (oldest: {oldest})")

    if not dry_run and rows:
        ids = [r["belief_id"] for r in rows]
        store.delete_beliefs_by_ids(ids)
        store.commit()

    stats["pruned"] = len(rows)
    return stats


# ══════════════════════════════════════════════════════════════════════════════
# Pass 3 — Reconfirmation
# ══════════════════════════════════════════════════════════════════════════════

def run_pass_3(
    store: IntelStore,
    tickers: Optional[list[str]],
    dry_run: bool,
    verbose: bool,
) -> dict:
    """Re-score active propagated signals not updated today; refresh or expire."""
    stats = {"reconfirmed": 0, "expired_low": 0, "skipped_today": 0, "checked": 0}

    # Active propagated signals NOT updated today
    rows = store.list_active_signals_not_today(
        today=TODAY,
        notes_prefix=PROPAGATOR_TAG,
        tickers=tickers,
    )

    stats["checked"] = len(rows)

    for r in rows:
        ticker = r["ticker"]
        ts     = score_ticker(store, ticker)

        if ts is None:
            # Score collapsed below threshold — expire
            if verbose:
                print(f"  [P3:expire] {ticker:<8} score<{MIN_SCORE_THRESHOLD} → expired")
            if not dry_run:
                store.expire_signal(r["signal_id"])
            stats["expired_low"] += 1
        else:
            # Refresh the existing signal row
            if verbose:
                print(
                    f"  [P3:reconfirm] {ticker:<8} score={ts.raw_score:.2f}"
                    f"  prev_date={r['date']}"
                )
            if not dry_run:
                # _upsert_signal checks for today's propagator row and inserts if missing,
                # or updates reconfirmation_count if already present.
                # Since this signal's date != today, it will insert a fresh today row.
                _upsert_signal(store, ts)
                # Also expire the old (stale-date) row
                store.expire_signal(r["signal_id"])
            stats["reconfirmed"] += 1

    if not dry_run:
        store._c.commit()

    return stats


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="SOMA-INTEL signal sweep — expire, prune, reconfirm"
    )
    parser.add_argument("--apply",          action="store_true",
                        help="Write to DB (default: dry run)")
    parser.add_argument("--no-reconfirm",   action="store_true",
                        help="Skip Pass 3 (expiry + prune only)")
    parser.add_argument("--pass",           dest="only_pass",
                        choices=["1", "2", "3", "all"], default="all",
                        help="Run only one pass (default: all)")
    parser.add_argument("--ticker",         nargs="+", metavar="TICKER",
                        help="Restrict Pass 1 + Pass 3 to specific tickers")
    parser.add_argument("--expiry-mult",    type=float, default=EXPIRY_MULTIPLIER,
                        metavar="X",
                        help=f"Expiry multiplier (default: {EXPIRY_MULTIPLIER})")
    parser.add_argument("--prune-days",     type=int, default=BELIEF_PRUNE_DAYS,
                        metavar="N",
                        help=f"Belief prune cutoff in days (default: {BELIEF_PRUNE_DAYS})")
    parser.add_argument("--verbose",        action="store_true")
    args = parser.parse_args()

    dry_run  = not args.apply
    run_all  = args.only_pass == "all"

    # Apply CLI overrides
    import soma.intel.signal_sweep as _self
    _self.EXPIRY_MULTIPLIER = args.expiry_mult
    _self.BELIEF_PRUNE_DAYS = args.prune_days

    if dry_run:
        print("DRY RUN — pass --apply to write to DB\n")

    with IntelStore(db_path=DB_PATH) as store:

        if run_all or args.only_pass == "1":
            print("[Pass 1] Signal expiry check...")
            p1 = run_pass_1(store, tickers=args.ticker,
                            dry_run=dry_run, verbose=args.verbose)
            print(f"  Checked: {p1['checked']}  Expired: {p1['expired']}")

        if run_all or args.only_pass == "2":
            print("\n[Pass 2] Superseded belief pruning...")
            p2 = run_pass_2(store, dry_run=dry_run, verbose=args.verbose)
            print(f"  Checked: {p2['checked']}  Pruned:  {p2['pruned']}")

        if (run_all or args.only_pass == "3") and not args.no_reconfirm:
            print("\n[Pass 3] Reconfirmation sweep...")
            p3 = run_pass_3(store, tickers=args.ticker,
                            dry_run=dry_run, verbose=args.verbose)
            print(f"  Checked: {p3['checked']}  "
                  f"Reconfirmed: {p3['reconfirmed']}  "
                  f"Expired (low score): {p3['expired_low']}")
        elif args.no_reconfirm:
            print("\n[Pass 3] Skipped (--no-reconfirm)")

        # DB snapshot
        print("\nDB snapshot:")
        for col, cnt in [
            ("active signals",      store.count_signals_by_status("active")),
            ("reconfirmed signals", store.count_signals_by_status("reconfirmed")),
            ("expired signals",     store.count_signals_by_status("expired")),
            ("active beliefs",      store.count_beliefs_active()),
            ("superseded beliefs",  store.count_beliefs_superseded()),
        ]:
            print(f"  {col:<22} {cnt}")

    if dry_run:
        print("\nDRY RUN complete — pass --apply to write.")
    else:
        print("\nsignal_sweep: OK")


if __name__ == "__main__":
    main()
