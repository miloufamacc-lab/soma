"""
SOMA-INTEL Phase 7 D.3.A.2.a — Cross-Asset Price Cache Builder

One-time script that fetches SPY, TLT, GLD, DX-Y.NYB daily closes from
Yahoo Finance and writes oracle/cache/cross_asset_prices.csv.

Usage:
    python3 -m shared.soma.intel.regime_shift.build_cross_asset_cache \
        --start 2024-01-01 --end 2026-05-06 [--overwrite]

CSV format:
    date,SPY,TLT,GLD,DX-Y.NYB
    2024-01-02,469.33,92.45,188.96,102.11
    ...

After this runs once, the backtest no longer needs live Yahoo fetches.
The ingestor reads from this file in bt_strict_mode=True.

Path rule: uses $DABEIBA_ROOT env var → __file__ walk-up (never Path.home()).
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import sys
import time
import urllib.request
from datetime import date, datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# ── Path resolution (same pattern as phi4_adapter.py) ────────────────────────

def _resolve_dabeiba_root() -> Path:
    """3-tier fallback: $DABEIBA_ROOT env → __file__ walk-up → error."""
    env = os.environ.get("DABEIBA_ROOT")
    if env:
        return Path(env)
    here = Path(__file__).resolve()
    # shared/soma/intel/regime_shift/build_cross_asset_cache.py
    # parents: [0]=regime_shift, [1]=intel, [2]=soma, [3]=shared, [4]=DABEIBA
    root = here.parents[4]
    if (root / "oracle").exists():
        return root
    raise RuntimeError(
        "Cannot locate DABEIBA root. Set $DABEIBA_ROOT env var."
    )

_DABEIBA_ROOT = _resolve_dabeiba_root()
_CACHE_PATH   = _DABEIBA_ROOT / "oracle" / "cache" / "cross_asset_prices.csv"

# ── Constants ─────────────────────────────────────────────────────────────────

TICKERS = ["SPY", "TLT", "GLD", "DX-Y.NYB"]

_YF_BASE    = "https://query1.finance.yahoo.com/v8/finance/chart/{}?interval=1d&range=10y"
_YF_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible)"}

# ── Yahoo Finance fetch ───────────────────────────────────────────────────────

def _fetch_yahoo_closes(ticker: str, retries: int = 2, timeout: int = 20) -> dict[date, float]:
    """
    Fetch daily close prices from Yahoo Finance.
    Returns {date: close} sorted ascending, or empty dict on failure.
    """
    url = _YF_BASE.format(ticker)
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=_YF_HEADERS)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.load(r)
            result = data["chart"]["result"][0]
            timestamps = result["timestamp"]
            adj_closes = result["indicators"]["adjclose"][0]["adjclose"]
            out: dict[date, float] = {}
            for ts, close in zip(timestamps, adj_closes):
                if close is None:
                    continue
                d = datetime.utcfromtimestamp(ts).date()
                out[d] = float(close)
            log.info("Fetched %s: %d prices", ticker, len(out))
            return out
        except Exception as exc:
            log.warning("Yahoo fetch attempt %d/%d for %s failed: %s",
                        attempt + 1, retries + 1, ticker, exc)
            if attempt < retries:
                time.sleep(2)
    return {}


# ── Cache builder ─────────────────────────────────────────────────────────────

def build_cache(
    start_date: str,
    end_date: str,
    output_path: Optional[str] = None,
    overwrite: bool = False,
) -> dict:
    """
    Fetch SPY/TLT/GLD/DX-Y.NYB from Yahoo Finance and write to CSV.

    Args:
        start_date:   ISO date string, first date to include (e.g. '2024-01-01').
        end_date:     ISO date string, last date to include (e.g. '2026-05-06').
        output_path:  Override default cache path (for testing).
        overwrite:    If False, refuses to overwrite existing file.

    Returns:
        {
          "tickers": list[str],
          "dates_written": int,
          "output_path": str,
          "fetched_ts": str,
        }
    """
    out_path = Path(output_path) if output_path else _CACHE_PATH
    _start = date.fromisoformat(start_date)
    _end   = date.fromisoformat(end_date)

    # ── Idempotency guard ─────────────────────────────────────────────────────
    if out_path.exists() and not overwrite:
        log.error(
            "Cache already exists at %s. Use --overwrite to replace it.", out_path
        )
        raise FileExistsError(
            f"Cache exists at {out_path}. Pass overwrite=True or --overwrite."
        )

    # ── Fetch all tickers ─────────────────────────────────────────────────────
    all_prices: dict[str, dict[date, float]] = {}
    for ticker in TICKERS:
        prices = _fetch_yahoo_closes(ticker)
        if not prices:
            raise RuntimeError(
                f"Failed to fetch {ticker} after retries. "
                f"Consider substituting UUP for DX-Y.NYB if that ticker 404s."
            )
        all_prices[ticker] = prices

    # ── Align dates: only dates where ALL 4 tickers have data ────────────────
    date_sets = [set(p.keys()) for p in all_prices.values()]
    aligned = sorted(
        d for d in set.intersection(*date_sets)
        if _start <= d <= _end
    )

    if not aligned:
        raise RuntimeError(
            f"No aligned dates found in [{start_date}, {end_date}] across all tickers."
        )

    log.info(
        "Aligned dates in [%s, %s]: %d (before date filter), writing to %s",
        start_date, end_date, len(aligned), out_path,
    )

    # ── Write CSV ─────────────────────────────────────────────────────────────
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["date"] + TICKERS)
        for d in aligned:
            row = [d.isoformat()] + [f"{all_prices[t][d]:.4f}" for t in TICKERS]
            writer.writerow(row)

    fetched_ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    log.info("Cache written: %d dates × %d tickers → %s", len(aligned), len(TICKERS), out_path)

    return {
        "tickers":       TICKERS,
        "dates_written": len(aligned),
        "output_path":   str(out_path),
        "fetched_ts":    fetched_ts,
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    )
    parser = argparse.ArgumentParser(
        description="Build cross-asset price cache for SOMA-INTEL backtests."
    )
    parser.add_argument("--start", required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--end",   required=True, help="End date YYYY-MM-DD")
    parser.add_argument("--output", default=None,  help="Override output CSV path")
    parser.add_argument("--overwrite", action="store_true",
                        help="Overwrite existing cache file")
    args = parser.parse_args()

    try:
        result = build_cache(
            start_date=args.start,
            end_date=args.end,
            output_path=args.output,
            overwrite=args.overwrite,
        )
        print(
            f"\nCache built successfully:\n"
            f"  Tickers:       {', '.join(result['tickers'])}\n"
            f"  Dates written: {result['dates_written']}\n"
            f"  Output path:   {result['output_path']}\n"
            f"  Fetched at:    {result['fetched_ts']}\n"
        )
    except FileExistsError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
