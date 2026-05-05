#!/usr/bin/env python3
"""
SOMA-INTEL Phase 4 Step 4.4 — Anomaly Engine

Computes 5-feature anomaly scores per ticker per day and writes confirmed
signals (P1/P2/P3/P-X) to soma_intel_signal via the confirm.py gate.

Features (§C.1):
  f1 = 5d return z-score   vs (regime, ticker) baseline
  f2 = 20d return z-score  vs (regime, ticker) baseline
  f3 = realized-vol z-score vs (regime, ticker) baseline
  f4 = volume z-score      vs (regime, ticker) baseline
  f5 = sector-relative 5d return z-score  (cross-sectional)

anomaly_score = sqrt(f1² + f2² + f3² + f4² + f5²)

Gate: confirm.py classifies each score into P1/P2/P3/P-X/None per §I.1.

Data sources:
  - Yahoo Finance v8 API (price + volume, last 90 days)
  - soma_intel_regime  (today's composite_label)
  - soma_intel_baseline (mean/stdev per ticker × regime × feature)
  - soma_intel_node    (sector assignments via metadata.sector)

Usage:
  python3 soma/intel/anomaly.py --today             # dry run for today
  python3 soma/intel/anomaly.py --today --apply     # write signals
  python3 soma/intel/anomaly.py --date 2026-04-01   # specific date (dry run)
  python3 soma/intel/anomaly.py --date 2026-04-01 --apply
  python3 soma/intel/anomaly.py --today --ticker AAPL TSLA  # subset
  python3 soma/intel/anomaly.py --today --verbose
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

_HERE    = Path(__file__).resolve().parent
_DABEIBA = _HERE.parent.parent.parent
for _p in [str(_DABEIBA), str(_DABEIBA / "shared")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from soma.intel.store import IntelStore
from soma.intel.confirm import (
    classify_signal,
    compute_novelty,
    count_corroborations,
    has_exclusion_edge,
)

DB_PATH = (
    Path(os.environ["SOMA_DB_PATH"])
    if "SOMA_DB_PATH" in os.environ
    else _DABEIBA / "shared" / "soma" / "data" / "soma.db"
)

NOW          = datetime.now(timezone.utc).isoformat()
FETCH_DELAY  = 0.12   # seconds between Yahoo Finance calls


# ══════════════════════════════════════════════════════════════════════════════
# Price data fetch
# ══════════════════════════════════════════════════════════════════════════════

def _fetch_price_history(ticker: str, days: int = 90) -> Optional[dict]:
    """
    Returns {date_str: {close, volume}} for up to `days` calendar days.
    Returns None on any fetch error.
    """
    period = f"{days}d"
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        f"?range={period}&interval=1d&includePrePost=false"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
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
# Feature extraction from price history
# ══════════════════════════════════════════════════════════════════════════════

def _extract_features(ohlcv: dict, target_date: str) -> Optional[dict]:
    """
    Compute {ret_5d, ret_20d, realized_vol, volume} for `target_date`.
    Returns None if there is insufficient history.

    realized_vol = 20d rolling stdev of daily log-returns × sqrt(252).
    """
    try:
        import numpy as np
    except ImportError:
        return None

    sorted_dates = sorted(d for d in ohlcv if d <= target_date)
    if len(sorted_dates) < 22:
        return None

    closes = [ohlcv[d]["close"]  for d in sorted_dates]
    vols   = [ohlcv[d]["volume"] for d in sorted_dates]

    c = np.array(closes, dtype=float)
    log_ret = np.diff(np.log(c))   # length = len(c) - 1

    def _ret(n: int) -> Optional[float]:
        if len(c) < n + 1:
            return None
        r = c[-1] / c[-(n + 1)] - 1.0
        return float(r) if not math.isnan(r) else None

    def _realized_vol(window: int = 20) -> Optional[float]:
        if len(log_ret) < window:
            return None
        rv = float(np.std(log_ret[-window:], ddof=1)) * math.sqrt(252)
        return rv if not math.isnan(rv) else None

    r5  = _ret(5)
    r20 = _ret(20)
    rv  = _realized_vol(20)
    vol = float(vols[-1]) if vols else None

    if any(v is None for v in [r5, r20, rv, vol]):
        return None

    return {"ret_5d": r5, "ret_20d": r20, "realized_vol": rv, "volume": vol}


# ══════════════════════════════════════════════════════════════════════════════
# Z-score helpers
# ══════════════════════════════════════════════════════════════════════════════

def _zscore(value: float, mean: float, stdev: float) -> float:
    """Safe z-score, capped at ±10 to prevent absurd outliers."""
    if stdev <= 0:
        return 0.0
    z = (value - mean) / stdev
    return max(-10.0, min(10.0, z))


def _anomaly_score(f1: float, f2: float, f3: float, f4: float, f5: float) -> float:
    return math.sqrt(f1**2 + f2**2 + f3**2 + f4**2 + f5**2)


# ══════════════════════════════════════════════════════════════════════════════
# Sector map builder
# ══════════════════════════════════════════════════════════════════════════════

def _load_sector_map(store: IntelStore) -> dict[str, str]:
    """
    Returns {ticker → sector_name} by reading soma_intel_node metadata.sector.
    Falls back to 'Unknown' for tickers without node records.
    """
    rows = store.list_company_nodes()
    sector_map: dict[str, str] = {}
    for row in rows:
        node_id  = row["node_id"]
        meta_raw = row.get("metadata")
        if not meta_raw:
            continue
        try:
            meta = json.loads(meta_raw)
        except (json.JSONDecodeError, TypeError):
            continue
        sector = meta.get("sector", "Unknown")
        # node_id is "co_TICKER" → strip prefix
        ticker = node_id[3:] if node_id.startswith("co_") else node_id
        sector_map[ticker] = sector
    return sector_map


def _compute_sector_stats(
    ticker_features: dict[str, dict],
    sector_map:      dict[str, str],
) -> dict[str, tuple[float, float]]:
    """
    Returns {sector → (mean_ret_5d, stdev_ret_5d)} from cross-sectional data.
    Minimum 3 members per sector to compute meaningful stats.
    """
    from collections import defaultdict
    buckets: dict[str, list[float]] = defaultdict(list)
    for ticker, feats in ticker_features.items():
        sector = sector_map.get(ticker, "Unknown")
        if feats.get("ret_5d") is not None:
            buckets[sector].append(feats["ret_5d"])

    stats: dict[str, tuple[float, float]] = {}
    for sector, vals in buckets.items():
        if len(vals) < 3:
            continue
        mu = sum(vals) / len(vals)
        sd = math.sqrt(sum((v - mu)**2 for v in vals) / (len(vals) - 1)) if len(vals) > 1 else 0.0
        stats[sector] = (mu, sd)
    return stats


# ══════════════════════════════════════════════════════════════════════════════
# Main runner
# ══════════════════════════════════════════════════════════════════════════════

def run_anomaly(
    store:      IntelStore,
    target_date: str,
    tickers:    Optional[list[str]],
    dry_run:    bool,
    verbose:    bool,
) -> list[dict]:
    """
    For each ticker, compute anomaly score vs (regime, baseline) and apply
    confirmation gate.  Returns list of signal dicts.
    """
    # ── 1. Regime for target_date ─────────────────────────────────────────────
    regime_row = store.get_regime_row(target_date)
    if regime_row is None:
        print(f"ERROR: no regime row for {target_date}. Run regime.py first.")
        return []
    regime_label = regime_row["composite_label"]
    print(f"  Date: {target_date}  Regime: {regime_label}\n")

    # ── 2. Universe ───────────────────────────────────────────────────────────
    work_tickers = tickers if tickers else sorted(store.list_active_universe_tickers())
    total = len(work_tickers)

    # ── 3. Sector map ─────────────────────────────────────────────────────────
    sector_map = _load_sector_map(store)

    # ── 4. Load baselines for this regime ─────────────────────────────────────
    # {ticker → {feature → (mean, stdev)}}
    baseline_cache: dict[str, dict[str, tuple[float, float]]] = {}

    # ── 5. Fetch price data + compute features for all tickers ────────────────
    print(f"  Fetching price data for {total} tickers...")
    ticker_raw_features: dict[str, dict] = {}

    for idx, ticker in enumerate(work_tickers, 1):
        ohlcv = _fetch_price_history(ticker, days=90)
        if ohlcv is None:
            if verbose:
                print(f"    [{idx:>3}/{total}] {ticker:<12}  SKIP (fetch failed)")
            time.sleep(FETCH_DELAY)
            continue
        feats = _extract_features(ohlcv, target_date)
        if feats is not None:
            ticker_raw_features[ticker] = feats
        time.sleep(FETCH_DELAY)

    print(f"  Got features for {len(ticker_raw_features)}/{total} tickers\n")

    # ── 6. Sector stats (cross-sectional) ─────────────────────────────────────
    sector_stats = _compute_sector_stats(ticker_raw_features, sector_map)

    # ── 7. Daily caps for confirmation gate ───────────────────────────────────
    daily_p1 = store.count_active_signals_for_date(target_date, "P1")
    daily_p2 = store.count_active_signals_for_date(target_date, "P2")

    # ── 8. Score each ticker ──────────────────────────────────────────────────
    signals: list[dict] = []

    for ticker, raw in ticker_raw_features.items():
        # Load baseline (lazy)
        if ticker not in baseline_cache:
            rows = store.list_baselines_for_ticker(ticker, regime_label=regime_label)
            if not rows:
                # Try without regime filter (any provisional)
                rows = store.list_baselines_for_ticker(ticker)
            baseline_cache[ticker] = {
                r["feature"]: (r["mean"], r["stdev"])
                for r in rows
                if r["regime_label"] == regime_label or not rows
            }

        blines = baseline_cache[ticker]
        if not blines:
            if verbose:
                print(f"    {ticker:<12}  SKIP (no baseline)")
            continue

        # f1–f4: z-scores vs baseline
        def _bz(feature: str, value: float) -> float:
            if feature not in blines:
                return 0.0
            mu, sd = blines[feature]
            return _zscore(value, mu, sd)

        f1 = _bz("ret_5d",       raw["ret_5d"])
        f2 = _bz("ret_20d",      raw["ret_20d"])
        f3 = _bz("realized_vol", raw["realized_vol"])
        f4 = _bz("volume",       raw["volume"])

        # f5: sector-relative 5d return z-score
        sector = sector_map.get(ticker, "Unknown")
        s_stats = sector_stats.get(sector)
        if s_stats and s_stats[1] > 0:
            f5 = _zscore(raw["ret_5d"], s_stats[0], s_stats[1])
        else:
            f5 = 0.0   # sector too small for reliable stat

        score = _anomaly_score(f1, f2, f3, f4, f5)

        # Skip if below noise floor
        if score < 1.5:
            continue

        # Confirmation gate inputs
        n_corr     = count_corroborations(store, ticker, target_date)
        exclusion  = has_exclusion_edge(store, ticker, target_date)
        edge_count = store.count_ticker_edges(ticker)
        novelty    = compute_novelty(store, ticker, "anomaly", target_date)

        priority, half_life, notes = classify_signal(
            anomaly_score        = score,
            n_corroborations     = n_corr,
            ticker_edge_count    = edge_count,
            has_exclusion        = exclusion,
            regime_label         = regime_label,
            novelty_score        = novelty,
            daily_p1_count       = daily_p1,
            daily_p2_count       = daily_p2,
        )

        if priority is None:
            continue

        features_json = json.dumps({
            "f1_ret5d_z":   round(f1, 4),
            "f2_ret20d_z":  round(f2, 4),
            "f3_rvol_z":    round(f3, 4),
            "f4_volume_z":  round(f4, 4),
            "f5_sector_z":  round(f5, 4),
            "anomaly_score": round(score, 4),
            "regime":        regime_label,
            "sector":        sector,
        })

        sig = {
            "ticker":              ticker,
            "date":                target_date,
            "priority":            priority,
            "anomaly_score":       round(score, 4),
            "features_json":       features_json,
            "corroboration_count": n_corr,
            "half_life_days":      half_life,
            "notes":               notes,
            "horizon":             "tactical",
        }
        signals.append(sig)

        if priority == "P1":
            daily_p1 += 1
        elif priority == "P2":
            daily_p2 += 1

        print(
            f"  {priority}  {ticker:<12}  z={score:.2f}  "
            f"f1={f1:+.2f} f2={f2:+.2f} f3={f3:+.2f} f4={f4:+.2f} f5={f5:+.2f}"
            + (f"  corr={n_corr}" if priority in ("P1", "P2") else "")
        )

        if verbose:
            print(f"     notes: {notes}")

        # Write to DB
        if not dry_run:
            store.insert_anomaly_signal(
                ticker              = sig["ticker"],
                date                = sig["date"],
                priority            = sig["priority"],
                anomaly_score       = sig["anomaly_score"],
                features_json       = sig["features_json"],
                corroboration_count = sig["corroboration_count"],
                half_life_days      = sig["half_life_days"],
                notes               = sig["notes"],
                horizon             = sig["horizon"],
            )

    if not dry_run:
        store.commit()

    return signals


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="SOMA-INTEL anomaly engine — per-ticker regime-conditional signal detection"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--today",  action="store_true",
                       help="Run for today's date")
    group.add_argument("--date",   metavar="YYYY-MM-DD",
                       help="Run for a specific date")
    parser.add_argument("--apply",   action="store_true",
                        help="Write signals to soma_intel_signal (default: dry run)")
    parser.add_argument("--ticker",  nargs="+", metavar="TICKER",
                        help="Limit to specific tickers")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    target_date = date.today().isoformat() if args.today else args.date
    dry_run     = not args.apply

    if dry_run:
        print(f"DRY RUN ({target_date}) — pass --apply to write signals\n")

    with IntelStore(db_path=DB_PATH) as store:
        print(f"[Anomaly Engine] {target_date}\n")
        signals = run_anomaly(
            store,
            target_date = target_date,
            tickers     = args.ticker,
            dry_run     = dry_run,
            verbose     = args.verbose,
        )

        p1 = [s for s in signals if s["priority"] == "P1"]
        p2 = [s for s in signals if s["priority"] == "P2"]
        p3 = [s for s in signals if s["priority"] == "P3"]
        px = [s for s in signals if s["priority"] == "P-X"]

        print(f"\n  Signals fired:  P1={len(p1)}  P2={len(p2)}  P3={len(p3)}  P-X={len(px)}")
        if p1:
            print("\n  P1 signals:")
            for s in sorted(p1, key=lambda x: -x["anomaly_score"]):
                print(f"    {s['ticker']:<12}  z={s['anomaly_score']:.2f}  {s['notes'][:60]}")

    if dry_run:
        print("\nDRY RUN complete — pass --apply to write.")
    else:
        print("\nanomaly: OK")


if __name__ == "__main__":
    main()
