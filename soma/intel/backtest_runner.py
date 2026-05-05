"""
SOMA-INTEL P5.3.b — Backtest Replay Engine

Reads historical signals from soma_intel_signal (already generated during
live runs) and snapshots them into soma_intel_signal_backtest tagged with
the backtest run ID.

Design rules:
  - No re-simulation: signals were generated in real time; this engine is a
    scoring harness, not a signal re-generator.
  - No-look-ahead (bt_strict_mode=True): for each signal on date D, asserts
    that no regime row with date > D and no edge row with ts > D exists that
    could have influenced signal generation.
  - In-sample window: BACKTEST_START → IN_SAMPLE_END (462 days).
  - OOS holdout:      OOS_START      → BACKTEST_END   (60 days, --oos flag).

CLI:
  python3 backtest_runner.py --run              # replay in-sample window
  python3 backtest_runner.py --run --oos        # replay OOS window
  python3 backtest_runner.py --status           # show run inventory
  python3 backtest_runner.py --migrate          # apply migration 024 only
  python3 backtest_runner.py --run-id MYID      # override run ID
  python3 backtest_runner.py --no-strict        # skip look-ahead assertion
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

# ── Path bootstrap ─────────────────────────────────────────────────────────────
# File lives at <DABEIBA>/shared/soma/intel/backtest_runner.py
# → parent = intel/, parent = soma/, parent = shared/, parent = DABEIBA/
_HERE         = Path(__file__).resolve().parent
_DABEIBA_ROOT = _HERE.parent.parent.parent
for _p in [str(_DABEIBA_ROOT), str(_DABEIBA_ROOT / "shared")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from soma.intel.store import IntelStore

# ── Constants ─────────────────────────────────────────────────────────────────
BACKTEST_START  = "2024-05-06"   # first day of full window (522 calendar days)
BACKTEST_END    = "2026-05-05"   # last day of full window
OOS_START       = "2026-03-06"   # first day of OOS holdout (last 60 calendar days)
IN_SAMPLE_END   = "2026-03-05"   # last in-sample day (462 days)

_SOMA_DB        = _DABEIBA_ROOT / "shared" / "soma" / "data" / "soma.db"
_MIGRATIONS_DIR = _DABEIBA_ROOT / "shared" / "soma" / "migrations"

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(format="%(levelname)-5s %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)


# ── Migration helper ──────────────────────────────────────────────────────────

def _apply_migration_024(store: IntelStore) -> None:
    """Apply migration 024 idempotently (checks for table existence first)."""
    exists = store._c.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name='soma_intel_signal_backtest'"
    ).fetchone()
    if exists:
        log.info("Migration 024 already applied — soma_intel_signal_backtest exists.")
        return
    sql_path = _MIGRATIONS_DIR / "024_soma_intel_signal_backtest.sql"
    if not sql_path.exists():
        raise FileNotFoundError(f"Migration file not found: {sql_path}")
    sql = sql_path.read_text()
    lines = [ln for ln in sql.splitlines() if "schema_version" not in ln]
    store._c.executescript("\n".join(lines))
    store._c.commit()
    log.info("Migration 024 applied: soma_intel_signal_backtest created.")


# ── No-look-ahead assertion ───────────────────────────────────────────────────

def _assert_no_lookahead(store: IntelStore, sim_date: str, signal_id: int) -> bool:
    """
    Assert that no regime row with date > sim_date exists that could have
    influenced a signal generated on sim_date.

    For signals, we check:
      1. soma_intel_regime: the regime row used must have date <= sim_date.
         If the newest regime row has date > sim_date, that's a violation.
      2. soma_intel_edge: edges used have ts <= sim_date + "T23:59:59".

    Returns True if clean, False if a violation is detected.
    In strict mode (called from runner) a violation triggers a WARNING and
    marks lookahead_clean=0 — it does NOT halt the run (hard stop would require
    re-generating signals, which is out of scope).
    """
    cutoff_ts = sim_date + "T23:59:59"

    # Check 1: regime rows newer than sim_date
    future_regime = store._c.execute(
        "SELECT COUNT(*) AS n FROM soma_intel_regime WHERE date > ?",
        (sim_date,),
    ).fetchone()
    if future_regime and future_regime["n"] > 0:
        log.warning(
            "LOOKAHEAD signal_id=%d sim_date=%s: %d regime row(s) exist after sim_date",
            signal_id, sim_date, future_regime["n"],
        )
        return False

    # Check 2: edge rows newer than sim_date
    future_edges = store._c.execute(
        "SELECT COUNT(*) AS n FROM soma_intel_edge WHERE ts > ?",
        (cutoff_ts,),
    ).fetchone()
    if future_edges and future_edges["n"] > 0:
        log.warning(
            "LOOKAHEAD signal_id=%d sim_date=%s: %d edge(s) exist after sim_date",
            signal_id, sim_date, future_edges["n"],
        )
        return False

    return True


# ── Core replay logic ─────────────────────────────────────────────────────────

def _get_regime_label(store: IntelStore, sim_date: str) -> Optional[str]:
    """Return the composite_label for sim_date, or None if not in DB."""
    row = store._c.execute(
        "SELECT composite_label FROM soma_intel_regime WHERE date=?",
        (sim_date,),
    ).fetchone()
    return row["composite_label"] if row else None


def _run_id_for(window: str, start: str, end: str) -> str:
    """Generate a deterministic run ID from window name + date range."""
    s = start.replace("-", "")
    e = end.replace("-", "")
    return f"{window}_{s}_{e}"


def _replay_window(
    store: IntelStore,
    run_id: str,
    start_date: str,
    end_date: str,
    strict_mode: bool = True,
) -> dict:
    """
    Snapshot all signals in [start_date, end_date] into soma_intel_signal_backtest.

    Returns stats dict.
    """
    _apply_migration_024(store)

    # Delete any prior rows for this run_id (idempotent re-run)
    deleted = store._c.execute(
        "DELETE FROM soma_intel_signal_backtest WHERE backtest_run_id=?",
        (run_id,),
    ).rowcount
    if deleted:
        log.info("Cleared %d prior rows for run_id=%s", deleted, run_id)
    store._c.commit()

    # Pull all signals in the window, ordered by date then signal_id
    rows = store._c.execute(
        """
        SELECT * FROM soma_intel_signal
        WHERE date >= ? AND date <= ?
        ORDER BY date ASC, signal_id ASC
        """,
        (start_date, end_date),
    ).fetchall()

    stats = {
        "run_id":          run_id,
        "start_date":      start_date,
        "end_date":        end_date,
        "signals_found":   len(rows),
        "signals_written": 0,
        "lookahead_violations": 0,
        "days_covered":    0,
    }

    days_seen: set[str] = set()
    insert_sql = """
        INSERT INTO soma_intel_signal_backtest (
            backtest_run_id, sim_date,
            signal_id, ticker, date, priority, anomaly_score, features,
            corroboration_count, half_life_days, reconfirmation_count,
            status, horizon, notes, regime_label, lookahead_clean
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    for row in rows:
        sim_date = row["date"]
        sid      = row["signal_id"]

        # No-look-ahead check (strict mode: warn + mark; never halt)
        clean = 1
        if strict_mode:
            clean = int(_assert_no_lookahead(store, sim_date, sid))
            if not clean:
                stats["lookahead_violations"] += 1

        regime_label = _get_regime_label(store, sim_date)
        days_seen.add(sim_date)

        store._c.execute(insert_sql, (
            run_id, sim_date,
            sid,
            row["ticker"],
            row["date"],
            row["priority"],
            row["anomaly_score"],
            row["features"],
            row["corroboration_count"],
            row["half_life_days"],
            row["reconfirmation_count"],
            row["status"],
            row["horizon"],
            row["notes"],
            regime_label,
            clean,
        ))
        stats["signals_written"] += 1

    store._c.commit()
    stats["days_covered"] = len(days_seen)

    # Write run manifest
    manifest_path = _DABEIBA_ROOT / "tasks" / f"backtest_run_{run_id}.json"
    manifest_path.write_text(json.dumps(stats, indent=2))
    log.info("Run manifest: %s", manifest_path)

    return stats


# ── Status report ─────────────────────────────────────────────────────────────

def _show_status(store: IntelStore) -> None:
    """Print a summary of all backtest runs in the DB."""
    try:
        runs = store._c.execute(
            """
            SELECT backtest_run_id,
                   MIN(sim_date) AS first_day,
                   MAX(sim_date) AS last_day,
                   COUNT(*) AS total_signals,
                   SUM(CASE WHEN outcome='hit'  THEN 1 ELSE 0 END) AS hits,
                   SUM(CASE WHEN outcome='miss' THEN 1 ELSE 0 END) AS misses,
                   SUM(CASE WHEN outcome='data_unavailable' THEN 1 ELSE 0 END) AS unavail,
                   SUM(CASE WHEN lookahead_clean=0 THEN 1 ELSE 0 END) AS violations
            FROM soma_intel_signal_backtest
            GROUP BY backtest_run_id
            ORDER BY first_day
            """
        ).fetchall()
    except Exception:
        print("soma_intel_signal_backtest table not found — run --migrate first.")
        return

    if not runs:
        print("No backtest runs in DB yet.")
        return

    print(f"\n{'Run ID':<40} {'Days':>5} {'Signals':>8} {'Hits':>6} "
          f"{'Misses':>6} {'N/A':>6} {'Violations':>10}")
    print("-" * 90)
    for r in runs:
        # Derive day count from date range (rough)
        try:
            d1 = date.fromisoformat(r["first_day"])
            d2 = date.fromisoformat(r["last_day"])
            ndays = (d2 - d1).days + 1
        except Exception:
            ndays = "?"
        print(
            f"{r['backtest_run_id']:<40} {ndays:>5} {r['total_signals']:>8} "
            f"{(r['hits'] or 0):>6} {(r['misses'] or 0):>6} "
            f"{(r['unavail'] or 0):>6} {(r['violations'] or 0):>10}"
        )
    print()


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="SOMA-INTEL backtest replay engine (P5.3.b)"
    )
    parser.add_argument("--run",      action="store_true", help="Run replay over in-sample window")
    parser.add_argument("--oos",      action="store_true", help="Use OOS window instead of in-sample")
    parser.add_argument("--migrate",  action="store_true", help="Apply migration 024 only")
    parser.add_argument("--status",   action="store_true", help="Show run inventory")
    parser.add_argument("--run-id",   default=None,        help="Override auto-generated run ID")
    parser.add_argument("--no-strict",action="store_true", help="Skip no-look-ahead assertion")
    parser.add_argument("--db",       default=str(_SOMA_DB), help="Path to soma.db")
    args = parser.parse_args()

    with IntelStore(db_path=args.db) as store:

        if args.migrate:
            _apply_migration_024(store)
            return

        if args.status:
            _show_status(store)
            return

        if args.run:
            if args.oos:
                start = OOS_START
                end   = BACKTEST_END
                window = "oos"
            else:
                start = BACKTEST_START
                end   = IN_SAMPLE_END
                window = "in_sample"

            run_id = args.run_id or _run_id_for(window, start, end)
            strict = not args.no_strict

            log.info("Backtest run: %s", run_id)
            log.info("Window: %s → %s (%s mode)", start, end, window)
            log.info("bt_strict_mode: %s", strict)

            stats = _replay_window(
                store       = store,
                run_id      = run_id,
                start_date  = start,
                end_date    = end,
                strict_mode = strict,
            )

            print(f"\nBacktest run complete:")
            print(f"  Run ID:          {stats['run_id']}")
            print(f"  Window:          {stats['start_date']} → {stats['end_date']}")
            print(f"  Days covered:    {stats['days_covered']}")
            print(f"  Signals written: {stats['signals_written']}")
            print(f"  Look-ahead violations: {stats['lookahead_violations']}")
            if stats["lookahead_violations"]:
                print("  WARNING: look-ahead violations found — see log output above.")
            print(f"\n  Next step: python3 backtest_outcomes.py --score --run-id {stats['run_id']}")
            return

        parser.print_help()


if __name__ == "__main__":
    main()
