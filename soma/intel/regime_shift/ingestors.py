"""
SOMA-INTEL Phase 7 §D.3 — Likelihood Input Ingestors

Four ingestor functions, one per likelihood input. Each returns a z-score (float)
or None if the data source is unavailable for the target date. All are idempotent
and side-effect-free (no DB writes — orchestrator handles persistence).

Input statuses (see tasks/PHASE7_D3A_DATA_INVENTORY_2026-05-06.md):
  macro        — COMPUTABLE from soma_intel_regime.features in DB
  sentiment    — MISSING (stub, D.3.A.2 follow-on)
  cross_asset  — COMPUTABLE: cache-first (oracle/cache/cross_asset_prices.csv),
                 live Yahoo fallback in non-strict mode (D.3.A.2.a)
  transcript   — MISSING (stub, D.3.A.2 follow-on)
"""

from __future__ import annotations

import csv
import json
import logging
import math
import os
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# Minimum data points required for z-score computation. Below this threshold
# the z-score is undefined; return None rather than a spurious value.
_MIN_ZSCORE_POINTS: int = 30

# Yahoo Finance fetch headers (mirrors regime.py)
_YF_BASE    = "https://query1.finance.yahoo.com/v8/finance/chart/{}?interval=1d&range=5y"
_YF_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible)"}

# ── Cross-asset cache path (D.3.A.2.a) ───────────────────────────────────────

def _resolve_dabeiba_root() -> Path:
    """3-tier fallback: $DABEIBA_ROOT env → __file__ walk-up → error."""
    env = os.environ.get("DABEIBA_ROOT")
    if env:
        return Path(env)
    here = Path(__file__).resolve()
    # parents: [0]=regime_shift, [1]=intel, [2]=soma, [3]=shared, [4]=DABEIBA
    root = here.parents[4]
    if (root / "oracle").exists():
        return root
    raise RuntimeError(
        "Cannot locate DABEIBA root. Set $DABEIBA_ROOT env var."
    )

_CROSS_ASSET_CACHE_PATH: Path = (
    _resolve_dabeiba_root() / "oracle" / "cache" / "cross_asset_prices.csv"
)

# ── Internal helpers ───────────────────────────────────────────────────────────

def _zscore_series(values: list[float], idx: int) -> Optional[float]:
    """
    Z-score of values[idx] relative to the full series.

    Returns None if fewer than _MIN_ZSCORE_POINTS values are available,
    or if standard deviation is effectively zero (constant series).
    """
    if len(values) < _MIN_ZSCORE_POINTS:
        return None
    n = len(values)
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / n
    std = math.sqrt(variance)
    if std < 1e-9:
        return 0.0
    return (values[idx] - mean) / std


def _fetch_yahoo_closes(ticker: str, timeout: int = 15) -> dict[date, float]:
    """
    Fetch Yahoo Finance daily close prices. Returns {date: close} or empty dict.
    Same pattern as regime.py — stdlib urllib only, no new dependencies.
    """
    try:
        url = _YF_BASE.format(ticker)
        req = urllib.request.Request(url, headers=_YF_HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.load(r)
        result = data["chart"]["result"][0]
        timestamps  = result["timestamp"]
        adj_closes  = result["indicators"]["adjclose"][0]["adjclose"]
        out: dict[date, float] = {}
        import datetime
        for ts, close in zip(timestamps, adj_closes):
            if close is None:
                continue
            d = datetime.datetime.utcfromtimestamp(ts).date()
            out[d] = float(close)
        return out
    except Exception as e:
        log.warning("Yahoo fetch failed for %s: %s", ticker, e)
        return {}


def _get_close_near(prices: dict[date, float], target: date, window: int = 5) -> Optional[float]:
    """Return close at or up to `window` days before target (handles non-trading days)."""
    for offset in range(window):
        d = target - timedelta(days=offset)
        if d in prices:
            return prices[d]
    return None


# ── Cross-asset cache reader (D.3.A.2.a) ─────────────────────────────────────

def _read_cross_asset_cache(
    cutoff_date: date,
    cache_path: Optional[Path] = None,
) -> Optional[dict[str, dict[date, float]]]:
    """
    Read oracle/cache/cross_asset_prices.csv and return prices up to cutoff_date.

    Look-ahead discipline: only dates <= cutoff_date are returned. This mirrors
    the macro ingestor's in-memory bounded filtering.

    Returns:
        {ticker: {date: close}} for all tickers in the CSV, filtered to
        dates <= cutoff_date. Returns None if cache file is missing or unreadable.
    """
    path = cache_path or _CROSS_ASSET_CACHE_PATH
    if not path.exists():
        log.debug("_read_cross_asset_cache: cache not found at %s", path)
        return None

    try:
        prices: dict[str, dict[date, float]] = {}
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None:
                return None
            tickers = [col for col in reader.fieldnames if col != "date"]
            for t in tickers:
                prices[t] = {}
            for row in reader:
                try:
                    row_date = date.fromisoformat(row["date"])
                except (KeyError, ValueError):
                    continue
                # Look-ahead guard: exclude future rows
                if row_date > cutoff_date:
                    continue
                for t in tickers:
                    try:
                        prices[t][row_date] = float(row[t])
                    except (KeyError, ValueError):
                        pass
        return prices if prices else None
    except Exception as exc:
        log.warning("_read_cross_asset_cache: failed to read %s: %s", path, exc)
        return None


# ── Ingestor 1: Macro divergence (AVAILABLE) ─────────────────────────────────

def ingest_macro_z(target_date: str, store) -> Optional[float]:
    """
    Compute yield-curve + VIX-term-structure z-score for target_date.

    Data source: soma_intel_regime.features in DB.
    Features used: y2y10_spread, vix_delta_5d.

    Computation:
      yield_curve_z = zscore(y2y10_spread series)
      vix_term_z    = zscore(vix_delta_5d series)
      macro_z       = max(|yield_curve_z|, |vix_term_z|)

    Returns macro_z (always positive — magnitude), or None if insufficient data.
    """
    try:
        rows = store.list_regime_rows()  # returns list of dicts sorted by date
        if not rows:
            log.warning("ingest_macro_z: no regime rows in DB")
            return None

        spreads:   list[float] = []
        vix_deltas: list[float] = []
        target_spread_idx: Optional[int] = None
        target_vix_idx:    Optional[int] = None

        for i, row in enumerate(rows):
            features = row.get("features") or {}
            if isinstance(features, str):
                features = json.loads(features)

            spread    = features.get("y2y10_spread")
            vix_delta = features.get("vix_delta_5d")

            if spread is not None:
                spreads.append(float(spread))
                if row["date"] == target_date:
                    target_spread_idx = len(spreads) - 1

            if vix_delta is not None:
                vix_deltas.append(float(vix_delta))
                if row["date"] == target_date:
                    target_vix_idx = len(vix_deltas) - 1

        if target_spread_idx is None and target_vix_idx is None:
            log.warning("ingest_macro_z: target date %s not found in regime table", target_date)
            return None

        yield_curve_z: Optional[float] = None
        vix_term_z:    Optional[float] = None

        if target_spread_idx is not None:
            yield_curve_z = _zscore_series(spreads, target_spread_idx)

        if target_vix_idx is not None:
            vix_term_z = _zscore_series(vix_deltas, target_vix_idx)

        if yield_curve_z is None and vix_term_z is None:
            log.warning("ingest_macro_z: insufficient data for z-score on %s", target_date)
            return None

        # Magnitude: max of absolute z-scores from available inputs
        candidates = [abs(z) for z in [yield_curve_z, vix_term_z] if z is not None]
        macro_z = max(candidates)
        log.debug(
            "ingest_macro_z(%s): yield_curve_z=%.3f  vix_term_z=%s  macro_z=%.3f",
            target_date,
            yield_curve_z or float("nan"),
            f"{vix_term_z:.3f}" if vix_term_z is not None else "None",
            macro_z,
        )
        return macro_z

    except Exception as e:
        log.warning("ingest_macro_z failed for %s: %s", target_date, e)
        return None


# ── Ingestor 2: Sentiment AAII (STUB — D.3.A.2 follow-on) ────────────────────

def ingest_sentiment_z(target_date: str, store) -> Optional[float]:
    """
    Return AAII bull-minus-bear z-score for target_date.

    STATUS: Data source not available on disk (D.3.A.2 follow-on).
    The soma_intel_regime.features.aaii_bull_bear field is None in all 522 rows.

    D.3.A.2 follow-on: wire AAII CSV from aaii.com/sentiment-survey/raw.
    Weekly frequency — use the survey week that covers target_date.

    Returns None (neutral — LLR=0) until wired.
    """
    log.debug(
        "ingest_sentiment_z(%s): AAII data not yet wired (D.3.A.2 follow-on) — returning None",
        target_date,
    )
    return None


# ── Ingestor 3: Cross-asset stress (AVAILABLE via live fetch) ─────────────────

def ingest_cross_asset_z(
    target_date: str,
    store,
    bt_strict_mode: bool = False,
    _cache_path: Optional[Path] = None,  # override for testing
) -> Optional[float]:
    """
    Compute cross-asset correlation breakdown z-score for target_date.

    Data sourcing (D.3.A.2.a):
      bt_strict_mode=True  (backtest): read from cache only. Cache miss → None
                                        (input silenced). NEVER falls back to live.
      bt_strict_mode=False (live runs): try cache first; on cache miss → live Yahoo
                                        fetch (backwards-compatible with pre-D.3.A.2.a).

    Methodology:
      1. Fetch 5y daily closes for SPY, TLT, GLD, DX-Y.NYB (4 series).
      2. Compute daily returns for each.
      3. For each date in the series, compute 20-day rolling average pairwise
         absolute correlation across all 6 pairs (SPY/TLT, SPY/GLD, SPY/DXY,
         TLT/GLD, TLT/DXY, GLD/DXY).
      4. Z-score today's avg_corr relative to its trailing 252-day mean/std.

    High z-score = correlations breaking down or spiking unusually = stress signal.
    Returns None if data is unavailable or insufficient history for target_date.
    """
    TICKERS = ["SPY", "TLT", "GLD", "DX-Y.NYB"]
    ROLLING_CORR_WINDOW = 20    # trading days for pairwise correlation
    ROLLING_Z_WINDOW    = 252   # trading days for z-score baseline

    try:
        target = date.fromisoformat(target_date)
    except ValueError:
        log.warning("ingest_cross_asset_z: invalid date %s", target_date)
        return None

    # ── Data acquisition: cache-first ────────────────────────────────────────
    all_prices: Optional[dict[str, dict[date, float]]] = None

    cache_prices = _read_cross_asset_cache(
        cutoff_date=target,
        cache_path=_cache_path,
    )

    if cache_prices is not None and all(
        len(cache_prices.get(t, {})) > 0 for t in TICKERS
    ):
        all_prices = cache_prices
        log.debug("ingest_cross_asset_z(%s): using cache (%d dates for SPY)",
                  target_date, len(cache_prices.get("SPY", {})))
    elif bt_strict_mode:
        # Hard rule: never fall back to live in strict mode
        log.warning(
            "ingest_cross_asset_z(%s): cache miss in bt_strict_mode — returning None "
            "(look-ahead discipline: no live fetch allowed in backtest)",
            target_date,
        )
        return None
    else:
        # Live fallback for non-backtest runs
        log.info("ingest_cross_asset_z(%s): cache miss — falling back to Yahoo Finance", target_date)
        all_prices = {}
        for ticker in TICKERS:
            prices = _fetch_yahoo_closes(ticker)
            if not prices:
                log.warning("ingest_cross_asset_z: failed to fetch %s — returning None", ticker)
                return None
            all_prices[ticker] = prices

    # Build aligned date list: dates where all 4 tickers have data
    all_dates = sorted(
        set.intersection(*[set(p.keys()) for p in all_prices.values()])
    )
    if len(all_dates) < ROLLING_CORR_WINDOW + ROLLING_Z_WINDOW:
        log.warning(
            "ingest_cross_asset_z: insufficient aligned dates (%d) for %s",
            len(all_dates), target_date,
        )
        return None

    # Check target date is in or near the series
    # (look back up to 5 trading days)
    target_idx: Optional[int] = None
    for offset in range(5):
        check = target - timedelta(days=offset)
        if check in set(all_dates):
            target_idx = all_dates.index(check)
            break

    if target_idx is None:
        log.warning(
            "ingest_cross_asset_z: target date %s not in aligned series", target_date
        )
        return None

    if target_idx < ROLLING_CORR_WINDOW + ROLLING_Z_WINDOW - 1:
        log.warning(
            "ingest_cross_asset_z: not enough history before %s (idx=%d)",
            target_date, target_idx,
        )
        return None

    # Compute daily returns matrix
    returns: dict[str, list[float]] = {t: [] for t in TICKERS}
    for i in range(1, len(all_dates)):
        d_prev = all_dates[i - 1]
        d_curr = all_dates[i]
        for ticker in TICKERS:
            p_prev = all_prices[ticker].get(d_prev)
            p_curr = all_prices[ticker].get(d_curr)
            if p_prev and p_curr and p_prev > 0:
                returns[ticker].append((p_curr - p_prev) / p_prev)
            else:
                returns[ticker].append(0.0)
    # returns[ticker][i] corresponds to all_dates[i+1]
    # target_idx in dates → target_idx-1 in returns

    def _corr(x: list[float], y: list[float]) -> float:
        n = len(x)
        if n < 2:
            return 0.0
        mx = sum(x) / n
        my = sum(y) / n
        num = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
        dx  = math.sqrt(sum((xi - mx) ** 2 for xi in x))
        dy  = math.sqrt(sum((yi - my) ** 2 for yi in y))
        if dx < 1e-10 or dy < 1e-10:
            return 0.0
        return num / (dx * dy)

    # Build rolling avg_corr series: index i → end of window at returns index i
    pairs = [
        (TICKERS[a], TICKERS[b])
        for a in range(len(TICKERS))
        for b in range(a + 1, len(TICKERS))
    ]  # 6 pairs

    avg_corr_series: list[float] = []
    n_ret = len(returns[TICKERS[0]])
    for end in range(ROLLING_CORR_WINDOW - 1, n_ret):
        start = end - ROLLING_CORR_WINDOW + 1
        corrs = []
        for ta, tb in pairs:
            xa = returns[ta][start:end + 1]
            xb = returns[tb][start:end + 1]
            corrs.append(abs(_corr(xa, xb)))
        avg_corr_series.append(sum(corrs) / len(corrs))

    # avg_corr_series[i] corresponds to all_dates[i + ROLLING_CORR_WINDOW]
    # (first available avg_corr is at date index ROLLING_CORR_WINDOW)
    target_corr_idx = (target_idx - 1) - (ROLLING_CORR_WINDOW - 1)
    # target_idx-1 because returns are offset by 1

    if target_corr_idx < 0 or target_corr_idx >= len(avg_corr_series):
        log.warning(
            "ingest_cross_asset_z: target_corr_idx %d out of range for %s",
            target_corr_idx, target_date,
        )
        return None

    # Z-score of today's avg_corr vs trailing 252 days
    z_start = max(0, target_corr_idx - ROLLING_Z_WINDOW + 1)
    window_corrs = avg_corr_series[z_start:target_corr_idx + 1]
    z = _zscore_series(window_corrs, len(window_corrs) - 1)

    if z is None:
        log.warning(
            "ingest_cross_asset_z: insufficient z-score window (%d points) for %s",
            len(window_corrs), target_date,
        )
        return None

    log.debug(
        "ingest_cross_asset_z(%s): avg_corr=%.4f  z=%.3f",
        target_date, avg_corr_series[target_corr_idx], z,
    )
    return z


# ── Ingestor 4: Transcript topic drift (STUB — D.3.A.2 follow-on) ────────────

def ingest_transcript_drift_z(target_date: str, store) -> Optional[float]:
    """
    Return PRISM topic drift z-score for target_date.

    STATUS: Data source not available (D.3.A.2 follow-on).
    PRISM logs in shared/soma/logs/ contain category/relevance per file but no
    drift score. The soma_intel_regime.features.transcript_tone field is None
    in all regime rows.

    D.3.A.2 follow-on: extend PRISM engine to compute rolling Jensen-Shannon
    divergence between the current 30-day topic window and the prior 90-day
    baseline. Write drift_z to a new soma_intel_transcript_drift table or the
    PRISM log JSON. This ingestor then reads from that source.

    Returns None (neutral — LLR=0) until wired.
    """
    log.debug(
        "ingest_transcript_drift_z(%s): transcript drift not yet wired (D.3.A.2 follow-on) — returning None",
        target_date,
    )
    return None
