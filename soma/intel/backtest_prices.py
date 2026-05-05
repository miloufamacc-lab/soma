#!/usr/bin/env python3
"""
SOMA-INTEL P5.3.a — Backtest Price History Loader

Populates soma_intel_price_history (Migration 023) with daily close prices
for the 290 universe tickers across the backtest window (default: 522 days).

── Data source strategy ──────────────────────────────────────────────────────
Priority 1: oracle/cache/<TICKER>_price_series.json
  Expected format: {"prices": [{"date": "YYYY-MM-DD", "close": 123.45, "volume": 1e7}, ...]}

Priority 2: oracle/cache/<TICKER>_quote.json (single current price only)
  Provides a single price point — NOT sufficient for backtesting.

Priority 3: --download flag (requires explicit user approval)
  If --download is passed AND yfinance is installed, download full history.
  DO NOT call any external API without the --download flag.
  See OPUS_BRIEF_P5_3a_data_gap.md for the approval decision.

── Acceptance gate ──────────────────────────────────────────────────────────
Spec §P5.3.a requires ≥70% of 290 universe tickers with ≥522 days of data.
If this gate cannot be met after --load, write gap report and stop cleanly.
The backtest harness will still run; signals for tickers with missing prices
will be scored as 'data_unavailable'.

── Usage ─────────────────────────────────────────────────────────────────────
  python3 soma/intel/backtest_prices.py --load              # load from oracle/cache
  python3 soma/intel/backtest_prices.py --download          # also pull from yfinance
  python3 soma/intel/backtest_prices.py --status            # coverage report
  python3 soma/intel/backtest_prices.py --test-ticker NVDA  # spot-check
  python3 soma/intel/backtest_prices.py --migrate           # apply migration 023 only
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

_HERE    = Path(__file__).resolve().parent
_DABEIBA = _HERE.parent.parent.parent
for _p in [str(_DABEIBA), str(_DABEIBA / "shared")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from soma.intel.store import IntelStore

log = logging.getLogger("soma.intel.backtest_prices")
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

DB_PATH    = Path(os.environ.get("SOMA_DB_PATH",
             str(_DABEIBA / "shared" / "soma" / "data" / "soma.db")))
CACHE_DIR  = _DABEIBA / "oracle" / "cache"
TASKS_DIR  = _DABEIBA / "tasks"
MIGRATIONS = _DABEIBA / "shared" / "soma" / "migrations"

# Backtest window: 522 days of regime history (2024-05-06 → 2026-05-05)
# Hold-out: last 60 calendar days reserved for OOS validation.
BACKTEST_START = "2024-05-06"
BACKTEST_END   = "2026-05-05"
MIN_DAYS_FOR_COVERAGE = 522
COVERAGE_TARGET = 0.70   # ≥70% of universe must meet this threshold


# ══════════════════════════════════════════════════════════════════════════════
# Migration helper
# ══════════════════════════════════════════════════════════════════════════════

def apply_migration_023(store: IntelStore) -> bool:
    """
    Apply migration 023 if not already applied.
    Returns True if newly applied, False if already present.
    """
    existing = store._c.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name='soma_intel_price_history'"
    ).fetchone()
    if existing:
        log.debug("Migration 023 already applied (table exists).")
        return False

    sql_path = MIGRATIONS / "023_soma_intel_price_history.sql"
    sql = sql_path.read_text()
    # Strip schema_version inserts if table doesn't exist yet in this DB
    lines = [ln for ln in sql.splitlines() if "schema_version" not in ln]
    store._c.executescript("\n".join(lines))
    store.commit()
    log.info("Migration 023 applied: soma_intel_price_history created.")
    return True


# ══════════════════════════════════════════════════════════════════════════════
# Oracle cache loaders
# ══════════════════════════════════════════════════════════════════════════════

def _load_price_series_from_cache(ticker: str) -> list[dict]:
    """
    Try to load price series from oracle/cache/<ticker>_price_series.json.
    Expected: {"prices": [{"date": "YYYY-MM-DD", "close": float, "volume": float?}, ...]}
    Returns [] if file absent or malformed.
    """
    path = CACHE_DIR / f"{ticker}_price_series.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
        prices = data.get("prices", [])
        if not isinstance(prices, list):
            log.warning(f"{ticker}: malformed price_series.json (prices not a list)")
            return []
        out = []
        for row in prices:
            if "date" not in row or "close" not in row:
                continue
            try:
                out.append({
                    "date":   str(row["date"]),
                    "close":  float(row["close"]),
                    "volume": float(row["volume"]) if row.get("volume") is not None else None,
                })
            except (ValueError, TypeError):
                pass
        return out
    except Exception as exc:
        log.warning(f"{ticker}: error reading price_series.json: {exc}")
        return []


def _load_quote_as_single_price(ticker: str) -> list[dict]:
    """
    Fallback: extract a single current price from oracle/cache/<ticker>_quote.json.
    Returns a list with at most 1 entry — NOT sufficient for backtesting, but
    recorded so the ticker appears in the gap report with its coverage count.
    """
    path = CACHE_DIR / f"{ticker}_quote.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
        price = data.get("Price") or data.get("Current Price")
        ts    = data.get("timestamp") or data.get("Price Updated Time")
        if price is None:
            return []
        # Parse date from timestamp if possible
        try:
            from datetime import datetime
            if isinstance(ts, str):
                d = ts[:10]   # YYYY-MM-DD prefix
                date.fromisoformat(d)   # validate
            else:
                d = date.today().isoformat()
        except Exception:
            d = date.today().isoformat()
        return [{"date": d, "close": float(price), "volume": None}]
    except Exception:
        return []


# ══════════════════════════════════════════════════════════════════════════════
# Optional yfinance downloader (guarded by --download flag)
# ══════════════════════════════════════════════════════════════════════════════

def _download_yfinance(
    tickers: list[str],
    start:   str,
    end:     str,
) -> dict[str, list[dict]]:
    """
    Download daily close prices via yfinance.
    Returns {ticker: [{date, close, volume}, ...]} for successfully fetched tickers.
    Silently skips tickers that fail.
    Raises ImportError if yfinance is not installed.
    """
    import yfinance as yf   # explicit import here so ImportError is clear
    import pandas as pd

    log.info(f"Downloading {len(tickers)} tickers via yfinance "
             f"({start} → {end}) ...")
    out: dict[str, list[dict]] = {}

    # Batch download for efficiency
    batch_size = 50
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i + batch_size]
        try:
            df = yf.download(
                batch,
                start=start,
                end=end,
                auto_adjust=True,
                threads=True,
                progress=False,
            )
            if df.empty:
                continue

            # Handle single vs multi-ticker result
            if len(batch) == 1:
                ticker = batch[0]
                closes  = df["Close"]
                volumes = df["Volume"] if "Volume" in df.columns else None
                rows = []
                for idx in closes.index:
                    c = closes.loc[idx]
                    v = volumes.loc[idx] if volumes is not None else None
                    if pd.isna(c):
                        continue
                    rows.append({
                        "date":   idx.strftime("%Y-%m-%d"),
                        "close":  float(c),
                        "volume": float(v) if v is not None and not pd.isna(v) else None,
                    })
                out[ticker] = rows
            else:
                close_df  = df["Close"]
                volume_df = df["Volume"] if "Volume" in df.columns else None
                for ticker in batch:
                    if ticker not in close_df.columns:
                        continue
                    series = close_df[ticker]
                    vol_s  = volume_df[ticker] if volume_df is not None else None
                    rows = []
                    for idx in series.index:
                        c = series.loc[idx]
                        v = vol_s.loc[idx] if vol_s is not None else None
                        if pd.isna(c):
                            continue
                        rows.append({
                            "date":   idx.strftime("%Y-%m-%d"),
                            "close":  float(c),
                            "volume": float(v) if v is not None and not pd.isna(v) else None,
                        })
                    if rows:
                        out[ticker] = rows
        except Exception as exc:
            log.warning(f"yfinance batch {i//batch_size + 1} failed: {exc}")
            continue

    log.info(f"yfinance: fetched {len(out)} tickers.")
    return out


# ══════════════════════════════════════════════════════════════════════════════
# Main loader
# ══════════════════════════════════════════════════════════════════════════════

def load_prices(
    store:    IntelStore,
    download: bool = False,
    dry_run:  bool = False,
) -> dict:
    """
    Load price history for all active universe tickers.

    1. Try oracle/cache/<ticker>_price_series.json first.
    2. Fall back to quote file (single price point only).
    3. If --download: pull missing tickers via yfinance.

    Returns stats dict with coverage information.
    """
    # Ensure table exists
    apply_migration_023(store)

    # Get universe
    tickers = [r["ticker"] for r in store.list_universe(active_only=True)]
    log.info(f"Universe: {len(tickers)} active tickers")

    loaded:       dict[str, int]   = {}   # ticker → rows loaded
    from_cache:   list[str]        = []
    from_quote:   list[str]        = []
    missing:      list[str]        = []

    for ticker in tickers:
        # Priority 1: price series file
        rows = _load_price_series_from_cache(ticker)
        if rows:
            if not dry_run:
                for r in rows:
                    store.upsert_price(ticker, r["date"], r["close"], r.get("volume"))
            loaded[ticker] = len(rows)
            from_cache.append(ticker)
            continue

        # Priority 2: quote file (single price only)
        rows = _load_quote_as_single_price(ticker)
        if rows:
            if not dry_run:
                for r in rows:
                    store.upsert_price(ticker, r["date"], r["close"])
            loaded[ticker] = len(rows)
            from_quote.append(ticker)
            continue

        # No data found
        missing.append(ticker)

    if not dry_run and (from_cache or from_quote):
        store.commit()

    # If --download, fetch missing tickers via yfinance
    dl_loaded: dict[str, int] = {}
    if download and missing:
        try:
            dl_data = _download_yfinance(missing, BACKTEST_START, BACKTEST_END)
            for ticker, rows in dl_data.items():
                if rows:
                    if not dry_run:
                        for r in rows:
                            store.upsert_price(ticker, r["date"], r["close"], r.get("volume"))
                    dl_loaded[ticker] = len(rows)
                    missing.remove(ticker)
            if not dry_run and dl_loaded:
                store.commit()
        except ImportError:
            log.warning("yfinance not installed — skipping download. "
                        "Install with: pip install yfinance pandas --break-system-packages")

    # Coverage check
    meeting_threshold = sum(
        1 for t, n in {**loaded, **dl_loaded}.items()
        if n >= MIN_DAYS_FOR_COVERAGE
    )
    coverage_pct = meeting_threshold / len(tickers) if tickers else 0.0

    return {
        "total_universe":       len(tickers),
        "from_price_series":    len(from_cache),
        "from_quote_only":      len(from_quote),
        "downloaded":           len(dl_loaded),
        "missing":              len(missing),
        "meeting_threshold":    meeting_threshold,
        "coverage_pct":         coverage_pct,
        "gap_tickers":          missing,
        "quote_only_tickers":   from_quote,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Gap report writer
# ══════════════════════════════════════════════════════════════════════════════

def write_gap_report(stats: dict, run_date: str) -> Path:
    """Write tasks/backtest_price_gaps.md with missing tickers."""
    TASKS_DIR.mkdir(exist_ok=True)
    out = TASKS_DIR / "backtest_price_gaps.md"

    lines = [
        f"# Backtest Price Gap Report — {run_date}",
        "",
        "Generated by `backtest_prices.py`. Lists tickers that need manual",
        "price data acquisition before the backtest can reach the §P5.3.a",
        "≥70% coverage acceptance gate.",
        "",
        "## Coverage summary",
        "",
        f"- Universe size: {stats['total_universe']}",
        f"- From price_series files: {stats['from_price_series']}",
        f"- From quote only (1 price point): {stats['from_quote_only']}",
        f"- Downloaded via yfinance: {stats['downloaded']}",
        f"- Missing entirely: {stats['missing']}",
        f"- Meeting ≥{MIN_DAYS_FOR_COVERAGE}d threshold: {stats['meeting_threshold']}",
        f"- Coverage: {stats['coverage_pct']*100:.1f}% (target ≥70%)",
        "",
        f"## Status: {'GREEN ✓' if stats['coverage_pct'] >= COVERAGE_TARGET else 'BELOW TARGET — see OPUS_BRIEF_P5_3a_data_gap.md'}",
        "",
        "## Fix",
        "",
        "To reach the ≥70% target, run:",
        "```bash",
        "# First install yfinance:",
        "pip install yfinance pandas --break-system-packages",
        "# Then download:",
        "python3 shared/soma/intel/backtest_prices.py --download",
        "```",
        "",
        "## Missing tickers (need download or manual price file)",
        "",
    ]

    if stats["gap_tickers"]:
        lines.append(f"({len(stats['gap_tickers'])} tickers):")
        lines.append("")
        lines.extend([f"- {t}" for t in sorted(stats["gap_tickers"])])
    else:
        lines.append("_(none — all tickers have at least 1 price point)_")

    if stats["quote_only_tickers"]:
        lines += [
            "",
            "## Quote-only tickers (1 price point, not sufficient for backtest)",
            f"({len(stats['quote_only_tickers'])} tickers — run --download to fix):",
            "",
        ]
        lines.extend([f"- {t}" for t in sorted(stats["quote_only_tickers"])])

    out.write_text("\n".join(lines) + "\n")
    return out


# ══════════════════════════════════════════════════════════════════════════════
# Coverage status report
# ══════════════════════════════════════════════════════════════════════════════

def print_status(store: IntelStore) -> None:
    """Print current price history coverage to stdout."""
    apply_migration_023(store)
    tickers = [r["ticker"] for r in store.list_universe(active_only=True)]
    total_rows = store.count_price_history_rows()
    distinct   = store.count_price_history_tickers()
    meeting    = 0
    for t in tickers:
        n = store.count_price_history_rows(ticker=t)
        if n >= MIN_DAYS_FOR_COVERAGE:
            meeting += 1

    print(f"\nPrice history coverage:")
    print(f"  Total rows:        {total_rows:,}")
    print(f"  Distinct tickers:  {distinct} / {len(tickers)}")
    print(f"  Meeting ≥{MIN_DAYS_FOR_COVERAGE}d:    {meeting} ({meeting/len(tickers)*100:.1f}%)")
    print(f"  Target:            ≥70% ({int(len(tickers)*0.7)} tickers)")
    status = "GREEN" if meeting / len(tickers) >= COVERAGE_TARGET else "BELOW TARGET"
    print(f"  Status:            {status}")


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="SOMA-INTEL backtest price loader (P5.3.a)"
    )
    grp = parser.add_mutually_exclusive_group()
    grp.add_argument("--load",         action="store_true",
                     help="Load prices from oracle/cache (dry run by default)")
    grp.add_argument("--download",     action="store_true",
                     help="Load from cache + download missing via yfinance")
    grp.add_argument("--status",       action="store_true",
                     help="Print current coverage stats")
    grp.add_argument("--migrate",      action="store_true",
                     help="Apply migration 023 only, no loading")
    grp.add_argument("--test-ticker",  metavar="TICKER",
                     help="Spot-check: print price range for one ticker")
    parser.add_argument("--apply",     action="store_true",
                        help="Write to DB (default: dry run for --load)")
    args = parser.parse_args()

    with IntelStore(db_path=DB_PATH) as store:

        if args.migrate:
            applied = apply_migration_023(store)
            print(f"Migration 023: {'applied' if applied else 'already present'}")
            return

        if args.status:
            print_status(store)
            return

        if args.test_ticker:
            apply_migration_023(store)
            rng = store.get_price_date_range(args.test_ticker)
            n   = store.count_price_history_rows(ticker=args.test_ticker)
            if rng:
                print(f"{args.test_ticker}: {n} rows  ({rng[0]} → {rng[1]})")
                # Test forward return
                fr = store.get_forward_return(args.test_ticker, rng[0], 84)
                if fr is not None:
                    print(f"  Forward return from {rng[0]} +84d: {fr:+.2%}")
                else:
                    print(f"  Forward return: N/A (insufficient data)")
            else:
                print(f"{args.test_ticker}: no price data in DB")
            return

        # --load or --download
        dry_run  = not args.apply
        download = args.download

        if dry_run and (args.load or download):
            print("DRY RUN — pass --apply to write to DB\n")

        print("[backtest_prices] Loading price history ...")
        stats = load_prices(store, download=download, dry_run=dry_run)

        print(f"\n  From price_series files:  {stats['from_price_series']}")
        print(f"  From quote (1 pt only):   {stats['from_quote_only']}")
        print(f"  Downloaded (yfinance):    {stats['downloaded']}")
        print(f"  Missing entirely:         {stats['missing']}")
        print(f"  Meeting ≥{MIN_DAYS_FOR_COVERAGE}d coverage:  {stats['meeting_threshold']} "
              f"({stats['coverage_pct']*100:.1f}%)")

        if not dry_run:
            rpt = write_gap_report(stats, date.today().isoformat())
            print(f"\n  Gap report: {rpt}")

        if stats["coverage_pct"] < COVERAGE_TARGET:
            print(f"\nWARN coverage {stats['coverage_pct']*100:.1f}% < {COVERAGE_TARGET*100:.0f}% target.")
            print("     See OPUS_BRIEF_P5_3a_data_gap.md for the resolution path.")
            if not download:
                print("     Run --download (after installing yfinance) to resolve.")
        else:
            print(f"\nCoverage GREEN ({stats['coverage_pct']*100:.1f}% ≥ 70%)")

        if dry_run:
            print("\nDRY RUN complete — pass --apply to write.")
        else:
            print("\nbacktest_prices: OK")


if __name__ == "__main__":
    main()
