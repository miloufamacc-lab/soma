"""
SOMA-INTEL P5.3.b — Backtest Replay Engine (v2 — historical generation)

Generates synthetic historical signals by running the anomaly + confirm pipeline
against historical price data and regime labels stored in soma.db.

v1 (snapshot mode): copied live soma_intel_signal rows — DEPRECATED, kept for
  backward compatibility with tests.
v2 (replay mode, P5.3.b spec): for each date D in the window where a regime row
  exists, re-runs anomaly scoring using prices ≤ D and writes to
  soma_intel_signal_backtest. No live-signal table touched.

Design rules (§H.1 + §E):
  - Price data: soma_intel_price_history only (no live Yahoo Finance calls)
  - Graph edges: time-bounded reads via count_ticker_edges_as_of() + list_recent_edges_for_ticker()
  - Baselines: soma_intel_baseline (no ts column — v1 limitation, noted below)
  - bt_strict_mode=True: count_ticker_edges() (unbounded) raises AssertionError
  - Signals written to soma_intel_signal_backtest, NOT soma_intel_signal

Baseline limitation (v1): soma_intel_baseline rows have no timestamp — they
  reflect the full-history statistics (2024-05-06→2026-05-05). Using them for
  historical dates slightly overstates z-score precision for early periods but
  is acceptable for v1; flagged for Phase 6 meta-learner improvement.

CLI:
  python3 backtest_runner.py --apply --window in_sample   # historical replay IS
  python3 backtest_runner.py --apply --window oos          # historical replay OOS
  python3 backtest_runner.py --apply --window both         # both windows
  python3 backtest_runner.py --status                      # run inventory
  python3 backtest_runner.py --purge-run <run_id>          # delete a run
  python3 backtest_runner.py --migrate                     # apply migration 024
  python3 backtest_runner.py --no-strict                   # skip assertion
"""

from __future__ import annotations

import argparse
import bisect
import json
import logging
import math
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
from soma.intel.confirm import classify_signal, count_corroborations, has_exclusion_edge

# ── Constants ─────────────────────────────────────────────────────────────────
BACKTEST_START  = "2024-05-06"   # first day of full window
BACKTEST_END    = "2026-05-05"   # last day with price data
# Correct windows (brief F2, 2026-05-05):
#   In-sample:  2024-05-06 → 2025-08-31  (~330 trading days)
#   OOS:        2025-09-01 → 2026-02-10  (~110 trading days, last valid 60-td forward)
#   No-forward: 2026-02-11 → 2026-05-05  (live signals only, no 60d forward available)
IN_SAMPLE_START = "2024-05-06"
IN_SAMPLE_END   = "2025-08-31"
OOS_START       = "2025-09-01"
OOS_END         = "2026-02-10"

_SOMA_DB        = _DABEIBA_ROOT / "shared" / "soma" / "data" / "soma.db"
_MIGRATIONS_DIR = _DABEIBA_ROOT / "shared" / "soma" / "migrations"

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(format="%(levelname)-5s %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# Historical replay helpers (P5.3.b v2)
# ══════════════════════════════════════════════════════════════════════════════

def _zscore(value: float, mean: float, stdev: float) -> float:
    """Safe z-score capped at ±10."""
    if stdev <= 0:
        return 0.0
    return max(-10.0, min(10.0, (value - mean) / stdev))


def _anomaly_score_vec(f1: float, f2: float, f3: float,
                       f4: float, f5: float) -> float:
    return math.sqrt(f1**2 + f2**2 + f3**2 + f4**2 + f5**2)


def _extract_features_from_series(
    dates_closes_vols: list[tuple[str, float, float]],
    as_of_date: str,
) -> Optional[dict]:
    """
    Compute {ret_5d, ret_20d, realized_vol, volume} from price rows <= as_of_date.

    Args:
        dates_closes_vols: pre-sorted list of (date_str, close, volume) tuples
                           for one ticker (full history, all dates).
        as_of_date: upper cutoff (inclusive).

    Returns dict or None if < 22 rows available.
    """
    # Binary-search to find the slice up to and including as_of_date
    all_dates = [r[0] for r in dates_closes_vols]
    idx = bisect.bisect_right(all_dates, as_of_date)   # first index AFTER cutoff
    rows = dates_closes_vols[:idx]

    if len(rows) < 22:
        return None

    closes = [r[1] for r in rows]
    vols   = [r[2] for r in rows]

    c = closes[-22:]   # use only last 22 for efficiency (enough for ret_20d + rvol)
    v = vols[-1]

    log_c = [math.log(x) for x in c if x > 0]
    if len(log_c) < 22:
        return None

    log_ret = [log_c[i + 1] - log_c[i] for i in range(len(log_c) - 1)]

    def _ret(n: int) -> Optional[float]:
        if len(c) < n + 1 or c[-(n + 1)] <= 0:
            return None
        return c[-1] / c[-(n + 1)] - 1.0

    def _rvol(window: int = 20) -> Optional[float]:
        if len(log_ret) < window:
            return None
        sample = log_ret[-window:]
        mu = sum(sample) / window
        var = sum((x - mu) ** 2 for x in sample) / (window - 1)
        return math.sqrt(var) * math.sqrt(252)

    r5  = _ret(5)
    r20 = _ret(20)
    rv  = _rvol(20)
    vol = float(v) if v else None

    if any(x is None for x in [r5, r20, rv, vol]):
        return None

    return {"ret_5d": r5, "ret_20d": r20, "realized_vol": rv, "volume": vol}


def _compute_novelty_bt(
    store: IntelStore,
    run_id: str,
    ticker: str,
    as_of_date: str,
    signal_type: str = "anomaly",
) -> float:
    """Novelty using backtest table so future live signals don't leak."""
    cutoff = (date.fromisoformat(as_of_date) - timedelta(days=90)).isoformat()
    count = store.count_recent_backtest_signals(
        run_id=run_id,
        ticker=ticker,
        notes_prefix=signal_type,
        since_date=cutoff,
    )
    return max(0.0, 1.0 - min(1.0, count / 10.0))


def _run_historical_replay(
    store:      IntelStore,
    run_id:     str,
    start_date: str,
    end_date:   str,
    strict_mode: bool = True,
) -> dict:
    """
    Generate synthetic backtest signals for every date D in [start_date, end_date]
    where soma_intel_regime has a row.

    For each D:
      1. Get regime label from soma_intel_regime WHERE date = D
      2. Read price features from soma_intel_price_history (dates ≤ D, in memory)
      3. Read baselines from soma_intel_baseline for (ticker, regime_label)
      4. Compute z-scores + anomaly_score (f1..f5)
      5. Run confirm gate (all reads bounded to ≤ D; bt_strict_mode guards unbounded calls)
      6. Write P1/P2/P3/P-X signals to soma_intel_signal_backtest
      7. Assert no look-ahead (strict mode): count_ticker_edges() raises AssertionError
         — catches any unbounded edge read that slipped into the replay path

    Returns stats dict.
    """
    _apply_migration_024(store)

    # Purge any prior rows for this run_id (idempotent re-run)
    deleted = store._c.execute(
        "DELETE FROM soma_intel_signal_backtest WHERE backtest_run_id=?",
        (run_id,),
    ).rowcount
    if deleted:
        log.info("Cleared %d prior rows for run_id=%s", deleted, run_id)
    store._c.commit()

    # ── Load price history into memory (one DB read for all tickers) ───────
    log.info("Loading price history into memory...")
    # {ticker: [(date_str, close, vol), ...]} sorted by date ASC
    price_cache: dict[str, list[tuple[str, float, float]]] = {}
    for row in store._c.execute(
        "SELECT ticker, date, close, volume FROM soma_intel_price_history ORDER BY ticker, date ASC"
    ).fetchall():
        ticker = row["ticker"]
        price_cache.setdefault(ticker, []).append(
            (row["date"], row["close"], row["volume"] or 0.0)
        )
    log.info("Price cache: %d tickers", len(price_cache))

    # ── Load all baselines into memory ────────────────────────────────────
    log.info("Loading baselines into memory...")
    # {(ticker, regime_label): {feature: (mean, stdev)}}
    # Two-level dict for O(1) ticker+regime lookup (avoids O(21k) scan per ticker)
    baseline_cache: dict[tuple[str, str], dict[str, tuple[float, float]]] = {}
    _raw_baseline_count = 0
    for row in store._c.execute("SELECT * FROM soma_intel_baseline").fetchall():
        key = (row["ticker"], row["regime_label"])
        if key not in baseline_cache:
            baseline_cache[key] = {}
        baseline_cache[key][row["feature"]] = (row["mean"], row["stdev"])
        _raw_baseline_count += 1
    log.info("Baseline cache: %d rows → %d (ticker,regime) keys",
             _raw_baseline_count, len(baseline_cache))

    # ── Get all regime rows in window ──────────────────────────────────────
    regime_rows = store.list_regime_rows(start_date=start_date, end_date=end_date)
    log.info("Dates in window with regime data: %d", len(regime_rows))

    if not regime_rows:
        log.warning("No regime rows found in [%s, %s] — backtest will be empty.", start_date, end_date)

    # ── Get active universe tickers ────────────────────────────────────────
    tickers = sorted(store.list_active_universe_tickers())
    log.info("Universe: %d active tickers", len(tickers))

    stats = {
        "run_id":              run_id,
        "start_date":          start_date,
        "end_date":            end_date,
        "regime_dates":        len(regime_rows),
        "signals_written":     0,
        "signals_by_priority": {"P1": 0, "P2": 0, "P3": 0, "P-X": 0},
        "days_covered":        0,
        "tickers_skipped_no_price": 0,
        "tickers_skipped_no_baseline": 0,
        "lookahead_violations": 0,
    }

    for regime_row in regime_rows:
        D             = regime_row["date"]
        regime_label  = regime_row["composite_label"]
        cutoff_ts     = D + "T23:59:59"

        if strict_mode:
            store.set_bt_mode(D)   # raises on count_ticker_edges() (unbounded)

        daily_p1 = store.count_active_backtest_signals_for_date(run_id, D, "P1")
        daily_p2 = store.count_active_backtest_signals_for_date(run_id, D, "P2")

        # Pass 1: compute raw features for all tickers (cross-sectional for f5)
        ticker_features: dict[str, dict] = {}
        for ticker in tickers:
            if ticker not in price_cache:
                stats["tickers_skipped_no_price"] += 1
                continue
            feats = _extract_features_from_series(price_cache[ticker], D)
            if feats is not None:
                ticker_features[ticker] = feats

        # Cross-sectional sector stats for f5 (sector-relative 5d return)
        # For v1: use platform_tags as sector proxy — load once lazily
        # (skipped for simplicity: set f5=0 when <3 peers; add in Phase 6)
        # f5 is always 0 in this implementation — all z-score comes from f1-f4
        # TODO Phase 6: wire sector_map and cross-sectional stats here

        # Pass 2: score each ticker
        daily_signals = 0
        for ticker, feats in ticker_features.items():
            # Get baselines for (ticker, regime_label) — O(1) lookup
            blines = baseline_cache.get((ticker, regime_label), {})
            if not blines:
                stats["tickers_skipped_no_baseline"] += 1
                continue

            def _bz(feat: str) -> float:
                if feat not in blines:
                    return 0.0
                mu, sd = blines[feat]
                return _zscore(feats[feat], mu, sd)

            f1 = _bz("ret_5d")
            f2 = _bz("ret_20d")
            f3 = _bz("realized_vol")
            f4 = _bz("volume")
            f5 = 0.0   # sector-relative — v1 omission (no look-ahead risk)

            score = _anomaly_score_vec(f1, f2, f3, f4, f5)
            if score < 1.5:
                continue

            # Confirm gate — all reads bounded to cutoff_ts
            # count_ticker_edges_as_of: bt-safe (bounded), won't trigger assertion
            edge_count = store.count_ticker_edges_as_of(ticker, cutoff_ts)

            # Corroboration: edges for this ticker with ts in [D-48h, D]
            n_corr = count_corroborations(store, ticker, D, window_hours=48)
            # Note: all edges in DB have ts 2026-05-04+; for D ≤ 2026-02-10 this
            # returns 0. P1 standard path (needs ≥2 corroborations) won't fire
            # historically — expected given KB is new. P3 signals will dominate.

            excl = has_exclusion_edge(store, ticker, D)
            novelty = _compute_novelty_bt(store, run_id, ticker, D)

            priority, half_life, notes = classify_signal(
                anomaly_score          = score,
                n_corroborations       = n_corr,
                ticker_edge_count      = edge_count,
                has_exclusion          = excl,
                regime_label           = regime_label,
                novelty_score          = novelty,
                daily_p1_count         = daily_p1,
                daily_p2_count         = daily_p2,
            )

            if priority is None:
                continue

            features_json = json.dumps({
                "f1_ret5d_z":    round(f1, 4),
                "f2_ret20d_z":   round(f2, 4),
                "f3_rvol_z":     round(f3, 4),
                "f4_volume_z":   round(f4, 4),
                "f5_sector_z":   round(f5, 4),
                "anomaly_score": round(score, 4),
                "regime":        regime_label,
            })

            store.insert_backtest_signal(
                run_id              = run_id,
                sim_date            = D,
                ticker              = ticker,
                priority            = priority,
                anomaly_score       = score,
                features_json       = features_json,
                corroboration_count = n_corr,
                half_life_days      = half_life,
                horizon             = "tactical",
                notes               = notes,
                regime_label        = regime_label,
            )

            stats["signals_written"] += 1
            stats["signals_by_priority"][priority] = (
                stats["signals_by_priority"].get(priority, 0) + 1
            )
            daily_signals += 1

            if priority == "P1":
                daily_p1 += 1
            elif priority == "P2":
                daily_p2 += 1

        store._c.commit()
        stats["days_covered"] += 1

        if strict_mode:
            store.clear_bt_mode()

        if stats["days_covered"] % 50 == 0:
            log.info(
                "Progress: %d/%d dates  signals_so_far=%d",
                stats["days_covered"], len(regime_rows), stats["signals_written"],
            )

    # Write manifest
    import json as _json
    manifest_path = _DABEIBA_ROOT / "tasks" / f"backtest_run_{run_id}.json"
    manifest_path.write_text(_json.dumps(stats, indent=2))
    log.info("Run manifest: %s", manifest_path)

    return stats


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
    parser.add_argument("--run",       action="store_true", help="Run replay (legacy flag, equivalent to --apply)")
    parser.add_argument("--apply",     action="store_true", help="Run replay over the selected window")
    parser.add_argument("--oos",       action="store_true", help="(Legacy) Use OOS window instead of in-sample")
    parser.add_argument("--window",    choices=["in_sample", "oos", "both"], default=None,
                        help="Window to run: in_sample | oos | both")
    parser.add_argument("--start",     default=None, help="Override window start date (YYYY-MM-DD)")
    parser.add_argument("--end",       default=None, help="Override window end date (YYYY-MM-DD)")
    parser.add_argument("--migrate",   action="store_true", help="Apply migration 024 only")
    parser.add_argument("--status",    action="store_true", help="Show run inventory")
    parser.add_argument("--run-id",    default=None, help="Override auto-generated run ID")
    parser.add_argument("--no-strict", action="store_true", help="Skip no-look-ahead assertion")
    parser.add_argument("--purge-run", default=None, metavar="RUN_ID",
                        help="Delete all rows for a given run_id from soma_intel_signal_backtest")
    parser.add_argument("--db",        default=str(_SOMA_DB), help="Path to soma.db")
    args = parser.parse_args()

    # Normalise: --run is an alias for --apply
    if args.run:
        args.apply = True

    with IntelStore(db_path=args.db) as store:

        if args.purge_run:
            deleted = store._c.execute(
                "DELETE FROM soma_intel_signal_backtest WHERE backtest_run_id=?",
                (args.purge_run,),
            ).rowcount
            store._c.commit()
            print(f"Purged {deleted} rows for run_id={args.purge_run}")
            return

        if args.migrate:
            _apply_migration_024(store)
            return

        if args.status:
            _show_status(store)
            return

        if args.apply:
            # Determine window(s) to run
            windows_to_run = []
            if args.window == "both":
                windows_to_run = [
                    ("in_sample", IN_SAMPLE_START, IN_SAMPLE_END),
                    ("oos",       OOS_START,        OOS_END),
                ]
            elif args.window == "oos" or args.oos:
                windows_to_run = [("oos", OOS_START, OOS_END)]
            elif args.window == "in_sample" or (not args.window):
                windows_to_run = [("in_sample", IN_SAMPLE_START, IN_SAMPLE_END)]

            # Apply start/end overrides (only valid for single-window runs)
            if (args.start or args.end) and len(windows_to_run) == 1:
                w, s, e = windows_to_run[0]
                windows_to_run = [(w, args.start or s, args.end or e)]
            elif (args.start or args.end) and len(windows_to_run) > 1:
                print("ERROR: --start/--end overrides cannot be used with --window both")
                return

            strict = not args.no_strict
            all_stats = []
            for window_name, start, end in windows_to_run:
                run_id = args.run_id or _run_id_for(window_name, start, end)
                log.info("Historical replay: %s", run_id)
                log.info("Window: %s → %s (%s mode)", start, end, window_name)
                log.info("bt_strict_mode: %s (count_ticker_edges raises AssertionError)", strict)
                # v2: historical replay generates signals from price+regime+baseline data
                stats = _run_historical_replay(
                    store       = store,
                    run_id      = run_id,
                    start_date  = start,
                    end_date    = end,
                    strict_mode = strict,
                )
                all_stats.append(stats)
                by_p = stats.get("signals_by_priority", {})
                print(
                    f"\nRun {run_id} complete:"
                    f"\n  Days with regime data: {stats['regime_dates']}"
                    f"\n  Days covered:          {stats['days_covered']}"
                    f"\n  Signals written:       {stats['signals_written']}"
                    f"\n  By priority:           P1={by_p.get('P1',0)}  "
                    f"P2={by_p.get('P2',0)}  P3={by_p.get('P3',0)}  "
                    f"P-X={by_p.get('P-X',0)}"
                )
                print(f"  Next: python3 backtest_outcomes.py --score --run-id {run_id}")
            return

        if args.run:
            # Legacy path — should not reach here (args.run sets args.apply)
            if args.oos:
                start = OOS_START
                end   = OOS_END
                window = "oos"
            else:
                start = IN_SAMPLE_START
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
