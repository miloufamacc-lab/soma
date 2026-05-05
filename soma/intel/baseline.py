#!/usr/bin/env python3
"""
SOMA-INTEL Phase 4 Step 4.3 — Regime-Conditional Baseline Builder

For each ticker × each observed regime, computes mean + stdev of 5 features:
  ret_5d:       5-day price return  (Close[t] / Close[t-5] - 1)
  ret_20d:      20-day price return (Close[t] / Close[t-20] - 1)
  ret_60d:      60-day price return (Close[t] / Close[t-60] - 1)
  realized_vol: 20d rolling stdev of daily log-returns, annualized (× √252)
  volume:       raw daily share volume

These are stored in soma_intel_baseline(ticker, regime_label, feature, mean,
stdev, n_days, is_provisional, last_updated).

For regimes with n_days < 30 (too sparse for reliable stats), falls back to the
nearest neighbour regime by Hamming distance on the 3 axes (trend, vol, macro).
Those rows are flagged is_provisional=1.

Data source: Yahoo Finance v8 API (urllib stdlib, no API key, 2-year history).

Usage:
  python3 soma/intel/baseline.py               # dry run — print stats, no DB write
  python3 soma/intel/baseline.py --apply       # write to soma_intel_baseline
  python3 soma/intel/baseline.py --ticker AAPL TSLA   # limit to named tickers
  python3 soma/intel/baseline.py --verbose
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import urllib.request
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

NOW            = datetime.now(timezone.utc).isoformat()
MIN_DAYS       = 30        # minimum observations per regime to mark non-provisional
FETCH_RANGE    = "730d"    # 2-year window — covers the full regime backfill window
FETCH_INTERVAL = "1d"
FETCH_DELAY    = 0.15      # seconds between Yahoo Finance requests
FEATURES       = ["ret_5d", "ret_20d", "ret_60d", "realized_vol", "volume"]

# ══════════════════════════════════════════════════════════════════════════════
# Axis parsing + Hamming distance
# ══════════════════════════════════════════════════════════════════════════════

def _parse_axes(composite_label: str) -> tuple[str, str, str]:
    """
    Split "bull_low_easing" → ("bull", "low", "easing").
    Trend is always the first token, vol second, macro third.
    """
    parts = composite_label.split("_", 2)
    if len(parts) != 3:
        raise ValueError(f"Unexpected composite_label format: {composite_label!r}")
    return parts[0], parts[1], parts[2]


def _hamming(a: str, b: str) -> int:
    """Hamming distance between two composite regime labels (0-3)."""
    ax_a = _parse_axes(a)
    ax_b = _parse_axes(b)
    return sum(x != y for x, y in zip(ax_a, ax_b))


def _nearest_regime(target: str, candidates: list[str]) -> Optional[str]:
    """
    Return the candidate regime label closest in Hamming distance to `target`.
    Returns None if candidates is empty or target itself is the only option.
    """
    others = [c for c in candidates if c != target]
    if not others:
        return None
    return min(others, key=lambda c: _hamming(target, c))


# ══════════════════════════════════════════════════════════════════════════════
# Yahoo Finance price fetch
# ══════════════════════════════════════════════════════════════════════════════

def _fetch_ohlcv(ticker: str) -> Optional[dict]:
    """
    Returns dict: {date_str → {"close": float, "volume": int}} for up to 2 years.
    Returns None on network/parse error.
    """
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        f"?range={FETCH_RANGE}&interval={FETCH_INTERVAL}&includePrePost=false"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            data = json.loads(r.read())
        result = data["chart"]["result"]
        if not result:
            return None
        r0     = result[0]
        ts     = r0["timestamp"]
        quote  = r0["indicators"]["quote"][0]
        closes = quote.get("close", [])
        vols   = quote.get("volume", [])
        out = {}
        for i, epoch in enumerate(ts):
            cl = closes[i] if i < len(closes) else None
            vl = vols[i]   if i < len(vols)   else None
            if cl is None:
                continue
            dt_str = datetime.utcfromtimestamp(epoch).strftime("%Y-%m-%d")
            out[dt_str] = {"close": float(cl), "volume": int(vl) if vl else 0}
        return out if out else None
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════════════════
# Feature computation
# ══════════════════════════════════════════════════════════════════════════════

def _compute_features(ohlcv: dict) -> dict[str, dict[str, float]]:
    """
    Given date→{close, volume} dict, return date→{ret_5d, ret_20d, ret_60d,
    realized_vol, volume} for dates where all features can be computed.

    realized_vol = stdev of log-returns over trailing 20 days × sqrt(252).
    """
    try:
        import pandas as pd
        import numpy as np
    except ImportError:
        raise RuntimeError("pandas/numpy required — pip install pandas numpy")

    if len(ohlcv) < 65:   # need ≥60 days lag + buffer
        return {}

    dates  = sorted(ohlcv.keys())
    closes = [ohlcv[d]["close"]  for d in dates]
    vols   = [ohlcv[d]["volume"] for d in dates]

    s_close = pd.Series(closes, index=pd.to_datetime(dates))
    s_vol   = pd.Series(vols,   index=pd.to_datetime(dates))

    log_ret = np.log(s_close / s_close.shift(1))

    ret_5d       = s_close / s_close.shift(5)  - 1
    ret_20d      = s_close / s_close.shift(20) - 1
    ret_60d      = s_close / s_close.shift(60) - 1
    realized_vol = log_ret.rolling(20).std() * math.sqrt(252)

    result = {}
    for dt_idx, dt_val in zip(s_close.index, dates):
        r5  = ret_5d.get(dt_idx)
        r20 = ret_20d.get(dt_idx)
        r60 = ret_60d.get(dt_idx)
        rv  = realized_vol.get(dt_idx)
        vol = s_vol.get(dt_idx)
        if any(v is None or (isinstance(v, float) and math.isnan(v))
               for v in [r5, r20, r60, rv, vol]):
            continue
        result[dt_val] = {
            "ret_5d":       float(r5),
            "ret_20d":      float(r20),
            "ret_60d":      float(r60),
            "realized_vol": float(rv),
            "volume":       float(vol),
        }
    return result


# ══════════════════════════════════════════════════════════════════════════════
# Stats helpers
# ══════════════════════════════════════════════════════════════════════════════

def _mean_stdev(values: list[float]) -> tuple[float, float]:
    n = len(values)
    if n == 0:
        return 0.0, 0.0
    mu = sum(values) / n
    if n == 1:
        return mu, 0.0
    var = sum((v - mu) ** 2 for v in values) / (n - 1)
    return mu, math.sqrt(var)


# ══════════════════════════════════════════════════════════════════════════════
# Per-ticker baseline computation
# ══════════════════════════════════════════════════════════════════════════════

def _build_ticker_baselines(
    ticker:       str,
    ohlcv:        dict,
    regime_map:   dict[str, str],    # date → composite_label
    all_regimes:  list[str],         # all known composite labels in DB
    verbose:      bool,
) -> list[dict]:
    """
    Returns list of dicts ready for store.upsert_baseline(), one per
    (ticker, regime_label, feature).
    """
    features_by_date = _compute_features(ohlcv)
    if not features_by_date:
        if verbose:
            print(f"    {ticker}: insufficient price data for feature computation")
        return []

    # Group feature values by regime
    regime_buckets: dict[str, dict[str, list[float]]] = {}
    for date_str, feat_vals in features_by_date.items():
        regime = regime_map.get(date_str)
        if regime is None:
            continue
        if regime not in regime_buckets:
            regime_buckets[regime] = {f: [] for f in FEATURES}
        for f in FEATURES:
            v = feat_vals.get(f)
            if v is not None and not math.isnan(v) and not math.isinf(v):
                regime_buckets[regime][f].append(v)

    if not regime_buckets:
        return []

    # First pass: compute raw stats per observed regime
    raw_stats: dict[str, dict[str, tuple[float, float, int]]] = {}
    # raw_stats[regime][feature] = (mean, stdev, n_days)
    for regime, feat_lists in regime_buckets.items():
        raw_stats[regime] = {}
        for feat, vals in feat_lists.items():
            mu, sd = _mean_stdev(vals)
            raw_stats[regime][feat] = (mu, sd, len(vals))

    # All regimes present in the DB (to find Hamming neighbours)
    all_regime_set = set(all_regimes)

    # Second pass: for each regime × feature, apply Hamming fallback if n < 30
    rows = []
    for regime, feat_map in raw_stats.items():
        for feat in FEATURES:
            mu, sd, n = feat_map.get(feat, (0.0, 0.0, 0))
            is_provisional = 0

            if n < MIN_DAYS:
                # Find nearest neighbour regime that has ≥ MIN_DAYS observations
                neighbours = sorted(
                    [r for r in all_regime_set if r != regime],
                    key=lambda r: _hamming(regime, r)
                )
                fallback_found = False
                for nb in neighbours:
                    nb_stats = raw_stats.get(nb, {}).get(feat)
                    if nb_stats is None:
                        continue
                    nb_mu, nb_sd, nb_n = nb_stats
                    if nb_n >= MIN_DAYS:
                        mu, sd, n = nb_mu, nb_sd, nb_n
                        is_provisional = 1
                        fallback_found = True
                        break
                if not fallback_found and n == 0:
                    continue  # no usable data at all — skip

            rows.append({
                "ticker":        ticker,
                "regime_label":  regime,
                "feature":       feat,
                "mean":          round(mu, 8),
                "stdev":         round(sd, 8),
                "n_days":        n,
                "is_provisional": is_provisional,
                "last_updated":  NOW,
            })

    return rows


# ══════════════════════════════════════════════════════════════════════════════
# Runner
# ══════════════════════════════════════════════════════════════════════════════

def run_baseline(
    store:     IntelStore,
    tickers:   Optional[list[str]],
    dry_run:   bool,
    verbose:   bool,
) -> dict:
    """
    Fetch price data, compute regime-conditional baselines, write to DB.
    Returns summary stats dict.
    """
    # Load regime map: date → composite_label
    regime_rows  = store.list_regime_rows()
    regime_map   = {r["date"]: r["composite_label"] for r in regime_rows}
    all_regimes  = sorted(set(regime_map.values()))

    if not regime_map:
        print("ERROR: soma_intel_regime is empty — run regime.py --backfill first")
        return {}

    print(f"  Regime map loaded: {len(regime_map)} dates, {len(all_regimes)} distinct labels")
    print(f"  Labels: {', '.join(all_regimes[:6])}{'...' if len(all_regimes) > 6 else ''}\n")

    # Tickers to process
    if tickers:
        work_tickers = tickers
    else:
        work_tickers = sorted(store.list_active_universe_tickers())

    total   = len(work_tickers)
    written = 0
    errors  = 0
    skipped = 0

    for idx, ticker in enumerate(work_tickers, 1):
        prefix = f"  [{idx:>3}/{total}] {ticker:<12}"

        ohlcv = _fetch_ohlcv(ticker)
        if ohlcv is None:
            print(f"{prefix}  SKIP (fetch failed)")
            errors += 1
            time.sleep(FETCH_DELAY)
            continue

        rows = _build_ticker_baselines(ticker, ohlcv, regime_map, all_regimes, verbose)
        if not rows:
            print(f"{prefix}  SKIP (no computable baselines — insufficient data)")
            skipped += 1
            time.sleep(FETCH_DELAY)
            continue

        provisional = sum(1 for r in rows if r["is_provisional"])
        print(
            f"{prefix}  {len(rows):>3} rows  "
            f"({provisional} provisional)  "
            f"regimes={len(set(r['regime_label'] for r in rows))}"
        )

        if not dry_run:
            for row in rows:
                store.upsert_baseline(
                    ticker        = row["ticker"],
                    regime_label  = row["regime_label"],
                    feature       = row["feature"],
                    mean          = row["mean"],
                    stdev         = row["stdev"],
                    n_days        = row["n_days"],
                    is_provisional= row["is_provisional"],
                    last_updated  = row["last_updated"],
                )
            store.commit()   # commit per-ticker so partial runs are safe / resumable
            written += len(rows)

        time.sleep(FETCH_DELAY)

    return {
        "tickers_attempted": total,
        "tickers_with_data": total - errors - skipped,
        "tickers_skipped":   skipped,
        "tickers_errored":   errors,
        "rows_written":      written,
        "all_regimes":       all_regimes,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="SOMA-INTEL baseline builder — regime-conditional feature statistics per ticker"
    )
    parser.add_argument("--apply",   action="store_true",
                        help="Write results to soma_intel_baseline (default: dry run)")
    parser.add_argument("--ticker",  nargs="+", metavar="TICKER",
                        help="Limit to specific tickers (e.g. AAPL TSLA)")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    dry_run = not args.apply
    if dry_run:
        print("DRY RUN — pass --apply to write results to soma_intel_baseline\n")

    with IntelStore(db_path=DB_PATH) as store:
        print("[Baseline Builder] Computing regime-conditional feature statistics...\n")
        stats = run_baseline(
            store,
            tickers = args.ticker,
            dry_run = dry_run,
            verbose = args.verbose,
        )

        if not stats:
            sys.exit(1)

        print(f"\n  Tickers attempted:  {stats['tickers_attempted']}")
        print(f"  Tickers with data:  {stats['tickers_with_data']}")
        print(f"  Tickers skipped:    {stats['tickers_skipped']}")
        print(f"  Tickers errored:    {stats['tickers_errored']}")
        print(f"  Baseline rows:      {stats['rows_written']}")
        print(f"  Regimes covered:    {len(stats['all_regimes'])}")

    if dry_run:
        print("\nDRY RUN complete — pass --apply to write.")
    else:
        print("\nbaseline: OK")


if __name__ == "__main__":
    main()
