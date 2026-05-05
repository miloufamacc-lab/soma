#!/usr/bin/env python3
"""
SOMA-INTEL Phase 2 Step 2.1 — Regime Classifier (deterministic v2a)

Implements the 3-axis regime classifier from OPUS_DELIVERABLES.md §B.1–B.3.

Axes (LOCKED — do not change without Opus escalation, §F rule #4):
  Trend : bull | transition | bear
  Vol   : low  | med        | high
  Macro : easing | neutral  | tightening

Composite label: "<trend>_<vol>_<macro>"  e.g. "bull_low_easing"

Data sources (stdlib urllib only — no new dependencies):
  - FRED API (free, no key):  VIX, 10y yield, 2y yield, TIPS 10y real yield, HY spread
  - Yahoo Finance v8 (free):  SPY (S&P 500 proxy), DX-Y.NYB (DXY proxy), BTC-USD

Fallback: if a series is unavailable, that axis is marked confidence=0.5 and the
          classifier still emits a row (spec §R3 hard rule: never skip).

CLI:
  python3 regime.py --backfill          # fill last 730 days
  python3 regime.py --today             # today only
  python3 regime.py --start 2024-01-01  # custom range
  python3 regime.py --dry-run           # print only, no DB write
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import os
import sys
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

# ── Path bootstrap ─────────────────────────────────────────────────────────────
_HERE    = Path(__file__).resolve().parent
_DABEIBA = _HERE.parent.parent.parent
for _p in [str(_DABEIBA), str(_DABEIBA / "shared")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from soma.intel.store import IntelStore

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ── DB path ────────────────────────────────────────────────────────────────────
DB_PATH = (
    Path(os.environ["SOMA_DB_PATH"])
    if "SOMA_DB_PATH" in os.environ
    else _DABEIBA / "shared" / "soma" / "data" / "soma.db"
)

# ── Series fetch buffer: extra days before backfill start for MA computation ──
_FETCH_BUFFER_DAYS = 260   # enough for 200d MA + 60d macro delta

# ── Regime thresholds (LOCKED §B.2 + §I.1 — do not tweak, escalate to Opus) ──
_VIX_LOW     = 15.0   # ≤15 → low vol
_VIX_HIGH    = 22.0   # >22 → high vol
_MACRO_BPS   = 0.25   # ±25bps (0.25 percentage points) for easing/tightening
_TREND_DAYS  = 200    # S&P 200d MA
_TREND_DUR   = 60     # minimum duration (days) for trend state to persist

# ══════════════════════════════════════════════════════════════════════════════
# Data fetching (stdlib only — no new deps)
# ══════════════════════════════════════════════════════════════════════════════

_FRED_BASE = "https://fred.stlouisfed.org/graph/fredgraph.csv?id="
_YF_BASE   = "https://query1.finance.yahoo.com/v8/finance/chart/{}?interval=1d&range=5y"
_YF_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible)"}


def _fetch_fred(series_id: str) -> pd.DataFrame:
    """
    Fetch a FRED daily series as a DataFrame with columns [date, value].
    Returns empty DataFrame on failure.
    """
    try:
        url = f"{_FRED_BASE}{series_id}"
        with urllib.request.urlopen(url, timeout=15) as r:
            raw = r.read().decode()
        df = pd.read_csv(io.StringIO(raw), parse_dates=["observation_date"])
        df = df.rename(columns={"observation_date": "date"})
        col = [c for c in df.columns if c != "date"][0]
        df = df.rename(columns={col: "value"})
        df = df[df["value"] != "."].copy()
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df = df.dropna(subset=["value"])
        df["date"] = pd.to_datetime(df["date"]).dt.date
        return df.set_index("date").sort_index()
    except Exception as e:
        log.warning("FRED fetch failed for %s: %s", series_id, e)
        return pd.DataFrame(columns=["value"])


def _fetch_yahoo(ticker: str) -> pd.DataFrame:
    """
    Fetch Yahoo Finance daily close prices as DataFrame with columns [date, close].
    Returns empty DataFrame on failure.
    """
    try:
        url = _YF_BASE.format(ticker)
        req = urllib.request.Request(url, headers=_YF_HEADERS)
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.load(r)
        result = data["chart"]["result"][0]
        timestamps  = result["timestamp"]
        closes_adj  = result["indicators"]["adjclose"][0]["adjclose"]
        df = pd.DataFrame({
            "date":  pd.to_datetime(timestamps, unit="s").date,
            "close": [float(c) if c is not None else float("nan") for c in closes_adj],
        })
        df = df.dropna(subset=["close"])
        df["date"] = pd.to_datetime(df["date"]).dt.date
        return df.set_index("date").sort_index()
    except Exception as e:
        log.warning("Yahoo Finance fetch failed for %s: %s", ticker, e)
        return pd.DataFrame(columns=["close"])


# ══════════════════════════════════════════════════════════════════════════════
# Market data bundle
# ══════════════════════════════════════════════════════════════════════════════

class MarketData:
    """
    Container for all 13 input series (§B.1).
    Fetched once, then reused across the backfill date range.
    """

    def __init__(self) -> None:
        log.info("Fetching market data series...")
        self.vix     = _fetch_fred("VIXCLS")["value"]           # VIX level
        self.y10     = _fetch_fred("DGS10")["value"]            # 10y yield
        self.y2      = _fetch_fred("DGS2")["value"]             # 2y yield
        self.tips10  = _fetch_fred("DFII10")["value"]           # 10y real yield
        self.hy      = _fetch_fred("BAMLH0A0HYM2EY")["value"]  # HY OAS spread
        self.spy     = _fetch_yahoo("SPY")["close"]             # S&P 500 proxy
        self.dxy     = _fetch_yahoo("DX-Y.NYB")["close"]       # DXY proxy
        self.btc     = _fetch_yahoo("BTC-USD")["close"]        # BTC/USD

        ok_count = sum(1 for s in [
            self.vix, self.y10, self.y2, self.tips10, self.hy,
            self.spy, self.dxy, self.btc
        ] if len(s) > 0)
        log.info("Market data loaded: %d/8 series available", ok_count)

    def get_val(self, series: pd.Series, d: date, window: int = 5) -> Optional[float]:
        """
        Get value for a date. Looks back up to `window` days for the most recent
        available trading day (FRED/Yahoo may lag weekends).
        Returns None if no data within window.
        """
        for offset in range(window):
            candidate = d - timedelta(days=offset)
            if candidate in series.index:
                val = series[candidate]
                return float(val) if pd.notna(val) else None
        return None

    def get_series_window(
        self,
        series: pd.Series,
        end_date: date,
        n_days: int,
    ) -> Optional[pd.Series]:
        """
        Return `n_days` of a series ending at or before end_date.
        Returns None if fewer than n_days//2 points available (too sparse).
        """
        start = end_date - timedelta(days=n_days * 2)  # wide window for calendar gaps
        mask = (series.index >= start) & (series.index <= end_date)
        sub = series[mask]
        if len(sub) < n_days // 2:
            return None
        return sub.tail(n_days)


# ══════════════════════════════════════════════════════════════════════════════
# Axis classifiers
# ══════════════════════════════════════════════════════════════════════════════

def _trend_axis(md: MarketData, d: date) -> tuple[str, float]:
    """
    Classify trend using S&P 500 200d slope + 60d duration filter.

    Returns (state, axis_confidence).
    state: 'bull' | 'bear' | 'transition'
    axis_confidence: [0.5, 1.0] — 0.5 if data unavailable.
    """
    if len(md.spy) == 0:
        return "transition", 0.5

    spy_window = md.get_series_window(md.spy, d, _TREND_DAYS + 60)
    if spy_window is None or len(spy_window) < 100:
        return "transition", 0.5

    # Current price vs 200d MA
    current_price = md.get_val(md.spy, d)
    if current_price is None:
        return "transition", 0.5

    ma200 = spy_window.iloc[-_TREND_DAYS:].mean() if len(spy_window) >= _TREND_DAYS else spy_window.mean()

    # 200d slope (linear regression coefficient normalised by price)
    recent = spy_window.iloc[-_TREND_DAYS:] if len(spy_window) >= _TREND_DAYS else spy_window
    x = np.arange(len(recent))
    if len(x) < 10:
        return "transition", 0.5
    slope_raw = np.polyfit(x, recent.values, 1)[0]
    # Normalise: slope as fraction of current price per day
    slope_pct = slope_raw / current_price if current_price > 0 else 0.0

    # Duration filter: check if this sign has held for 60d
    dur_window = md.get_series_window(md.spy, d, _TREND_DUR + _TREND_DAYS)
    sustained = False
    if dur_window is not None and len(dur_window) >= _TREND_DUR:
        # Is current price > 200d MA for last 60 days?
        dur_prices = dur_window.iloc[-_TREND_DUR:]
        dur_ma     = dur_window.iloc[-(_TREND_DAYS + _TREND_DUR):-_TREND_DUR].mean() \
                     if len(dur_window) >= (_TREND_DAYS + _TREND_DUR) else ma200
        fraction_above = (dur_prices > dur_ma).mean()
        if fraction_above >= 0.75:
            sustained = True  # bull sustained
        elif fraction_above <= 0.25:
            sustained = True  # bear sustained (flipped below)

    above_200d  = current_price > ma200
    positive_slope = slope_pct > 0

    # State logic
    if above_200d and positive_slope:
        state = "bull" if sustained else "transition"
    elif not above_200d and not positive_slope:
        state = "bear" if sustained else "transition"
    else:
        state = "transition"

    # Confidence: distance from MA as fraction (clamp to [0.5, 0.95])
    dist_pct = abs(current_price - ma200) / ma200 if ma200 > 0 else 0
    confidence = min(0.95, 0.5 + dist_pct * 2)
    return state, confidence


def _vol_axis(md: MarketData, d: date) -> tuple[str, float]:
    """
    Classify vol using VIX terciles from trailing 252 trading days.

    Returns (state, axis_confidence).
    state: 'low' | 'med' | 'high'
    """
    if len(md.vix) == 0:
        return "med", 0.5

    vix_now = md.get_val(md.vix, d)
    if vix_now is None:
        return "med", 0.5

    # Use fixed thresholds from spec §B.2: ≤15 = low, >22 = high
    if vix_now <= _VIX_LOW:
        state = "low"
    elif vix_now > _VIX_HIGH:
        state = "high"
    else:
        state = "med"

    # Confidence: distance from nearest threshold as fraction of threshold range
    range_size = _VIX_HIGH - _VIX_LOW  # 7
    if state == "low":
        dist = (_VIX_LOW - vix_now) / range_size
    elif state == "high":
        dist = (vix_now - _VIX_HIGH) / range_size
    else:
        # In "med": centre is 18.5; distance from centre / half-range
        mid = (_VIX_LOW + _VIX_HIGH) / 2
        dist = abs(vix_now - mid) / (range_size / 2)

    confidence = min(0.95, 0.5 + dist * 0.45)
    return state, confidence


def _macro_axis(md: MarketData, d: date) -> tuple[str, float]:
    """
    Classify macro using 2y yield ∆60d with ±25bps thresholds (spec §B.2).

    Returns (state, axis_confidence).
    state: 'easing' | 'neutral' | 'tightening'
    """
    if len(md.y2) == 0:
        return "neutral", 0.5

    y2_now = md.get_val(md.y2, d)
    y2_60d_ago = md.get_val(md.y2, d - timedelta(days=60), window=10)

    if y2_now is None or y2_60d_ago is None:
        return "neutral", 0.5

    delta = y2_now - y2_60d_ago  # in percentage points

    if delta <= -_MACRO_BPS:
        state = "easing"
    elif delta >= _MACRO_BPS:
        state = "tightening"
    else:
        state = "neutral"

    # Confidence: magnitude of move vs threshold
    confidence = min(0.95, 0.5 + abs(delta) / _MACRO_BPS * 0.25)
    return state, confidence


# ══════════════════════════════════════════════════════════════════════════════
# Per-day classification
# ══════════════════════════════════════════════════════════════════════════════

def _classify_day(md: MarketData, d: date) -> dict:
    """
    Classify a single date. Returns a dict matching the soma_intel_regime schema.
    """
    trend_state, trend_conf = _trend_axis(md, d)
    vol_state,   vol_conf   = _vol_axis(md, d)
    macro_state, macro_conf = _macro_axis(md, d)

    composite_label = f"{trend_state}_{vol_state}_{macro_state}"

    # Overall confidence = product of per-axis confidences
    confidence = trend_conf * vol_conf * macro_conf

    # Build feature snapshot (13 spec inputs, best-effort)
    vix_now    = md.get_val(md.vix,    d)
    vix_5d_ago = md.get_val(md.vix,    d - timedelta(days=5),  window=7)
    y10_now    = md.get_val(md.y10,    d)
    y10_20d    = md.get_val(md.y10,    d - timedelta(days=20), window=7)
    y2_now     = md.get_val(md.y2,     d)
    y2_60d     = md.get_val(md.y2,     d - timedelta(days=60), window=10)
    tips_now   = md.get_val(md.tips10, d)
    hy_now     = md.get_val(md.hy,     d)
    dxy_now    = md.get_val(md.dxy,    d)
    dxy_20d    = md.get_val(md.dxy,    d - timedelta(days=20), window=7)
    spy_now    = md.get_val(md.spy,    d)
    btc_now    = md.get_val(md.btc,    d)
    btc_50d    = md.get_series_window(md.btc, d, 50)

    features = {
        "vix_level":          vix_now,
        "vix_delta_5d":       (vix_now - vix_5d_ago)  if vix_now  is not None and vix_5d_ago  is not None else None,
        "y10_level":          y10_now,
        "y10_delta_20d":      (y10_now - y10_20d)     if y10_now  is not None and y10_20d     is not None else None,
        "y2_level":           y2_now,
        "y2y10_spread":       (y10_now - y2_now)      if y10_now  is not None and y2_now      is not None else None,
        "y2_delta_60d":       (y2_now  - y2_60d)      if y2_now   is not None and y2_60d      is not None else None,
        "tips10_level":       tips_now,
        "hy_spread":          hy_now,
        "dxy_delta_20d":      (dxy_now - dxy_20d)     if dxy_now  is not None and dxy_20d     is not None else None,
        "spy_price":          spy_now,
        "btc_50d_trend":      (float((btc_50d.iloc[-1] > btc_50d.mean()))
                                if btc_50d is not None and len(btc_50d) >= 10 else None),
        # Sentiment/breadth not available via free sources — marked None
        "aaii_bull_bear":     None,   # not available: weekly AAII survey
        "breadth_pct_200d":   None,   # not available: % S&P stocks > 200d MA
        "sector_dispersion":  None,   # not available: cross-sectional vol
        "transcript_tone":    None,   # ORACLE-internal
        "news_tone":          None,   # ORACLE-internal
    }

    return {
        "date":            d.isoformat(),
        "trend_state":     trend_state,
        "vol_state":       vol_state,
        "macro_state":     macro_state,
        "composite_label": composite_label,
        "confidence":      round(confidence, 4),
        "features":        features,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Backfill runner
# ══════════════════════════════════════════════════════════════════════════════

def run_backfill(
    start_date: date,
    end_date: date,
    dry_run: bool,
    verbose: bool,
) -> dict:
    """
    Classify every date in [start_date, end_date] and upsert to soma_intel_regime.
    Skips weekends. Idempotent.

    Returns stats dict: {classified, written, skipped_weekend}.
    """
    md    = MarketData()
    stats = {"classified": 0, "written": 0, "skipped_weekend": 0}

    dates = []
    d = start_date
    while d <= end_date:
        if d.weekday() < 5:  # Mon–Fri
            dates.append(d)
        else:
            stats["skipped_weekend"] += 1
        d += timedelta(days=1)

    with IntelStore(db_path=DB_PATH) as store:
        for d in dates:
            row = _classify_day(md, d)
            stats["classified"] += 1

            if verbose or (stats["classified"] % 100 == 0):
                log.info(
                    "%s  %-20s  conf=%.3f",
                    d.isoformat(), row["composite_label"], row["confidence"]
                )

            if not dry_run:
                store.upsert_regime_row(
                    date            = row["date"],
                    trend_state     = row["trend_state"],
                    vol_state       = row["vol_state"],
                    macro_state     = row["macro_state"],
                    composite_label = row["composite_label"],
                    confidence      = row["confidence"],
                    features        = row["features"],
                )
                store.commit()
                stats["written"] += 1

    return stats


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="SOMA-INTEL regime classifier — deterministic 3-axis (§B.1–B.3)"
    )
    parser.add_argument("--backfill", action="store_true",
                        help="Backfill last 730 calendar days")
    parser.add_argument("--today", action="store_true",
                        help="Classify today only")
    parser.add_argument("--start", metavar="YYYY-MM-DD",
                        help="Custom start date (use with --end)")
    parser.add_argument("--end", metavar="YYYY-MM-DD",
                        help="Custom end date (default: today)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print only, do not write to DB")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    today = date.today()
    dry_run = args.dry_run

    if dry_run:
        log.info("DRY RUN — pass without --dry-run to write to DB")

    if args.backfill:
        start = today - timedelta(days=730)
        end   = today
    elif args.today:
        start = end = today
    elif args.start:
        start = date.fromisoformat(args.start)
        end   = date.fromisoformat(args.end) if args.end else today
    else:
        parser.print_help()
        return

    log.info("Classifying %s → %s  (dry_run=%s)", start.isoformat(), end.isoformat(), dry_run)
    stats = run_backfill(start, end, dry_run=dry_run, verbose=args.verbose)

    print(f"\nRegime backfill complete:")
    print(f"  Dates classified:   {stats['classified']}")
    print(f"  Written to DB:      {stats['written']}")
    print(f"  Weekends skipped:   {stats['skipped_weekend']}")

    if not dry_run:
        with IntelStore(db_path=DB_PATH) as store:
            total = len(store.list_regime_rows())
        print(f"  DB total rows now:  {total}")

        # Sanity check: most common composite label
        with IntelStore(db_path=DB_PATH) as store:
            rows = store.list_regime_rows()
        from collections import Counter
        label_counts = Counter(r["composite_label"] for r in rows)
        top3 = label_counts.most_common(3)
        print(f"\nTop 3 composite labels:")
        for label, cnt in top3:
            print(f"  {label:<25} {cnt} days ({cnt/len(rows)*100:.1f}%)")


if __name__ == "__main__":
    main()
