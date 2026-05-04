"""
HORIZON Technical Lens — Price Action Intelligence (Weight: 12%)
Pipeline: SOMA/HORIZON | Module: SOMA

Reads from:
    - Live price data via yfinance (matching ORACLE's established pattern)
    - MANTIS v2_regime.py momentum calculations (63-day lookback)

Produces:
    - Per-ticker technical signal (TRENDING_UP / NEUTRAL / BREAKING_DOWN / OVERSOLD)
    - Volatility regime (LOW / NORMAL / HIGH / EXTREME)
    - Drawdown from 252-day high-water mark
    - 50/200-day moving average positioning

CFA grounding: "Momentum is the premier market anomaly" — CFA L2 Quantitative Methods.
MANTIS uses 63-day trailing momentum as the CFA-prescribed factor.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Optional

from ..horizon_dataclasses import (
    Direction,
    HoldingSignal,
    LensName,
    LensResult,
)


# ─── Technical Thresholds ───────────────────────────────────────────────────

# Momentum (63-day return, annualized-ish)
_MOM_STRONG_POSITIVE = 0.15    # >15% 63d return
_MOM_POSITIVE = 0.03           # >3%
_MOM_NEGATIVE = -0.03          # <-3%
_MOM_STRONG_NEGATIVE = -0.15   # <-15%

# Volatility regime (20d realized vol vs 90d median)
_VOL_LOW_RATIO = 0.7           # 20d vol < 70% of 90d median
_VOL_HIGH_RATIO = 1.3          # 20d vol > 130% of 90d median
_VOL_EXTREME_RATIO = 2.0       # 20d vol > 200% of 90d median

# Drawdown from 252-day HWM
_DD_MINOR = -0.10              # <10% drawdown
_DD_MODERATE = -0.20           # <20% drawdown
_DD_SEVERE = -0.35             # <35% drawdown
_DD_EXTREME = -0.50            # <50% drawdown

# Price history days needed
_HISTORY_DAYS = 300            # ~252 trading days + buffer


class TechnicalLens:
    """Technical analytical lens — price action analysis for HORIZON.

    Usage:
        with TechnicalLens() as lens:
            result = lens.analyze(tickers=["TSLA", "MSTR"])
    """

    def __init__(self):
        pass  # No DB needed — pure price data

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    # ── Main analysis ────────────────────────────────────────────────

    def analyze(self, tickers: list[str] | None = None) -> LensResult:
        """Run the technical lens analysis for specified tickers.

        Fetches live price data via yfinance and computes:
            - 63-day momentum (CFA factor)
            - 20-day realized vol vs 90-day median
            - Drawdown from 252-day HWM
            - 50/200-day MA positioning

        Args:
            tickers: List of ticker symbols to analyze.

        Returns:
            LensResult with per-holding and portfolio-level technical signal.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        tickers = [t.upper() for t in (tickers or [])]

        if not tickers:
            return self._empty_result(now_iso, "No tickers specified")

        # 1. Fetch price data
        price_data = self._fetch_prices(tickers)
        if not price_data:
            return self._empty_result(now_iso, "Failed to fetch price data via yfinance")

        # 2. Compute per-holding signals
        holding_signals = []
        ticker_signals = []
        warnings = []

        for ticker in tickers:
            if ticker not in price_data or price_data[ticker] is None:
                warnings.append(f"{ticker}: price data unavailable")
                continue

            closes = price_data[ticker]
            if len(closes) < 63:
                warnings.append(f"{ticker}: insufficient price history ({len(closes)} days)")
                continue

            # Compute all technical indicators
            indicators = self._compute_indicators(closes)

            # Compute holding signal
            h_signal, h_direction, h_rationale = self._compute_holding_signal(
                ticker, indicators
            )

            holding_signals.append(HoldingSignal(
                ticker=ticker,
                signal=h_signal,
                direction=h_direction,
                confidence=self._holding_confidence(indicators),
                rationale=h_rationale,
                data_points=indicators,
            ))
            ticker_signals.append(h_signal)

        # 3. Portfolio-level signal (equal-weighted)
        if ticker_signals:
            portfolio_signal = sum(ticker_signals) / len(ticker_signals)
        else:
            portfolio_signal = 0.0
        portfolio_signal = max(-1.0, min(1.0, portfolio_signal))

        # 4. Confidence
        confidence = self._portfolio_confidence(holding_signals)

        # 5. Build result
        drivers = []
        for h in holding_signals:
            mom = h.data_points.get("momentum_63d", 0)
            dd = h.data_points.get("dd_from_hwm", 0)
            drivers.append(f"{h.ticker}: mom={mom:+.1%}, DD={dd:+.1%}")

        return LensResult(
            lens_name=LensName.TECHNICAL,
            timestamp=now_iso,
            signal=portfolio_signal,
            direction=self._signal_to_direction(portfolio_signal),
            confidence=confidence,
            rationale=self._build_rationale(holding_signals, portfolio_signal),
            holding_signals=holding_signals,
            data_freshness_hours=0.0,  # Live data
            key_drivers=drivers[:3],
            warnings=warnings,
            raw_data={
                "n_tickers": len(holding_signals),
                "portfolio_signal": portfolio_signal,
                "data_source": "yfinance (live)",
            },
        )

    # ── Price fetching ───────────────────────────────────────────────

    def _fetch_prices(self, tickers: list[str]) -> dict:
        """Fetch price history via yfinance (matching ORACLE's pattern).

        Returns: {ticker: [list of close prices, oldest first]}
        """
        try:
            import yfinance as yf
        except ImportError:
            print("[HORIZON/Technical] yfinance not installed")
            return {}

        result = {}
        for ticker in tickers:
            try:
                t = yf.Ticker(ticker)
                hist = t.history(period=f"{_HISTORY_DAYS}d")
                if hist is not None and not hist.empty and "Close" in hist.columns:
                    result[ticker] = hist["Close"].tolist()
                else:
                    result[ticker] = None
            except Exception as e:
                print(f"[HORIZON/Technical] Failed to fetch {ticker}: {e}")
                result[ticker] = None

        return result

    # ── Indicator computation ────────────────────────────────────────

    def _compute_indicators(self, closes: list[float]) -> dict:
        """Compute all technical indicators from a price series.

        Args:
            closes: List of closing prices, oldest first.

        Returns:
            Dict with all computed indicators.
        """
        n = len(closes)
        current = closes[-1]

        # ── 63-day momentum (CFA factor, matching MANTIS) ────────────
        if n >= 63:
            mom_63d = (closes[-1] / closes[-63] - 1)
        else:
            mom_63d = 0.0

        # ── 20-day realized volatility ───────────────────────────────
        if n >= 21:
            returns_20d = [
                math.log(closes[i] / closes[i - 1])
                for i in range(n - 20, n)
                if closes[i - 1] > 0
            ]
            vol_20d = (
                (sum(r ** 2 for r in returns_20d) / len(returns_20d)) ** 0.5
                * (252 ** 0.5)
                if returns_20d else 0.0
            )
        else:
            vol_20d = 0.0

        # ── 90-day median volatility ─────────────────────────────────
        if n >= 91:
            # Compute rolling 20d vol for last 90 days, take median
            rolling_vols = []
            for end in range(n - 70, n + 1, 5):  # Sample every 5 days
                if end >= 21:
                    window_returns = [
                        math.log(closes[i] / closes[i - 1])
                        for i in range(end - 20, end)
                        if closes[i - 1] > 0
                    ]
                    if window_returns:
                        v = (sum(r ** 2 for r in window_returns) / len(window_returns)) ** 0.5 * (252 ** 0.5)
                        rolling_vols.append(v)
            vol_90d_median = sorted(rolling_vols)[len(rolling_vols) // 2] if rolling_vols else vol_20d
        else:
            vol_90d_median = vol_20d

        vol_ratio = vol_20d / vol_90d_median if vol_90d_median > 0 else 1.0

        # ── Vol regime classification ────────────────────────────────
        if vol_ratio > _VOL_EXTREME_RATIO:
            vol_regime = "EXTREME_VOL"
        elif vol_ratio > _VOL_HIGH_RATIO:
            vol_regime = "HIGH_VOL"
        elif vol_ratio < _VOL_LOW_RATIO:
            vol_regime = "LOW_VOL"
        else:
            vol_regime = "NORMAL_VOL"

        # ── Drawdown from 252-day HWM ────────────────────────────────
        lookback = min(252, n)
        hwm = max(closes[-lookback:])
        dd_from_hwm = (current / hwm - 1) if hwm > 0 else 0.0

        # ── 50-day and 200-day moving averages ───────────────────────
        ma_50 = sum(closes[-50:]) / 50 if n >= 50 else current
        ma_200 = sum(closes[-200:]) / 200 if n >= 200 else current

        above_50 = current > ma_50
        above_200 = current > ma_200
        golden_cross = ma_50 > ma_200  # 50 > 200 = bullish
        death_cross = ma_50 < ma_200   # 50 < 200 = bearish

        # ── Trend classification ─────────────────────────────────────
        if above_50 and above_200 and golden_cross:
            trend = "STRONG_UPTREND"
        elif above_50 and golden_cross:
            trend = "UPTREND"
        elif not above_50 and not above_200 and death_cross:
            trend = "STRONG_DOWNTREND"
        elif not above_50 and death_cross:
            trend = "DOWNTREND"
        else:
            trend = "MIXED"

        return {
            "current_price": current,
            "momentum_63d": mom_63d,
            "vol_20d": vol_20d,
            "vol_90d_median": vol_90d_median,
            "vol_ratio": vol_ratio,
            "vol_regime": vol_regime,
            "dd_from_hwm": dd_from_hwm,
            "hwm_252d": hwm,
            "ma_50": ma_50,
            "ma_200": ma_200,
            "above_ma50": above_50,
            "above_ma200": above_200,
            "golden_cross": golden_cross,
            "death_cross": death_cross,
            "trend": trend,
            "n_days": n,
        }

    # ── Signal computation ───────────────────────────────────────────

    def _compute_holding_signal(
        self, ticker: str, indicators: dict
    ) -> tuple[float, Direction, str]:
        """Compute technical signal for a single holding.

        Returns: (signal, direction, rationale)
        """
        signal = 0.0

        # ── Momentum component (±0.4 max) ────────────────────────────
        mom = indicators.get("momentum_63d", 0)
        if mom > _MOM_STRONG_POSITIVE:
            signal += 0.4
        elif mom > _MOM_POSITIVE:
            signal += 0.2
        elif mom < _MOM_STRONG_NEGATIVE:
            signal -= 0.4
        elif mom < _MOM_NEGATIVE:
            signal -= 0.2

        # ── Drawdown component (±0.3 max) ────────────────────────────
        dd = indicators.get("dd_from_hwm", 0)
        if dd < _DD_EXTREME:
            signal -= 0.1  # So oversold it might bounce (contrarian)
        elif dd < _DD_SEVERE:
            signal -= 0.3
        elif dd < _DD_MODERATE:
            signal -= 0.2
        elif dd < _DD_MINOR:
            signal -= 0.1
        else:
            signal += 0.1  # Near highs = trend intact

        # ── Trend / MA component (±0.2 max) ──────────────────────────
        trend = indicators.get("trend", "MIXED")
        if trend == "STRONG_UPTREND":
            signal += 0.2
        elif trend == "UPTREND":
            signal += 0.1
        elif trend == "STRONG_DOWNTREND":
            signal -= 0.2
        elif trend == "DOWNTREND":
            signal -= 0.1

        # ── Vol regime modifier (±0.1 max) ───────────────────────────
        vol_regime = indicators.get("vol_regime", "NORMAL_VOL")
        if vol_regime == "EXTREME_VOL":
            signal -= 0.1  # Extreme vol = uncertainty, bias toward caution
        elif vol_regime == "LOW_VOL":
            signal += 0.05  # Low vol = stable, slight positive

        signal = max(-1.0, min(1.0, signal))
        direction = self._signal_to_direction(signal)

        rationale = (
            f"{ticker}: Mom(63d)={mom:+.1%}, DD={dd:+.1%} from HWM, "
            f"trend={trend}, vol={vol_regime}. "
            f"Price ${indicators['current_price']:,.2f} "
            f"(MA50=${indicators['ma_50']:,.2f}, MA200=${indicators['ma_200']:,.2f}). "
            f"Signal: {signal:+.2f} ({direction.value})."
        )

        return signal, direction, rationale

    # ── Confidence ───────────────────────────────────────────────────

    def _holding_confidence(self, indicators: dict) -> float:
        """Compute confidence for a single holding's technical signal."""
        confidence = 0.60  # Base (technical is noisier than fundamental)

        # Clear trend = higher confidence
        trend = indicators.get("trend", "MIXED")
        if trend in ("STRONG_UPTREND", "STRONG_DOWNTREND"):
            confidence += 0.15
        elif trend in ("UPTREND", "DOWNTREND"):
            confidence += 0.1
        elif trend == "MIXED":
            confidence -= 0.1

        # Extreme vol = lower confidence (noise)
        vol_regime = indicators.get("vol_regime", "NORMAL_VOL")
        if vol_regime == "EXTREME_VOL":
            confidence -= 0.15
        elif vol_regime == "HIGH_VOL":
            confidence -= 0.05

        # More data = higher confidence
        n_days = indicators.get("n_days", 0)
        if n_days >= 252:
            confidence += 0.05
        elif n_days < 100:
            confidence -= 0.1

        return max(0.1, min(1.0, confidence))

    def _portfolio_confidence(self, holdings: list[HoldingSignal]) -> float:
        if not holdings:
            return 0.0
        return sum(h.confidence for h in holdings) / len(holdings)

    # ── Helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _signal_to_direction(signal: float) -> Direction:
        if signal <= -0.6:
            return Direction.STRONG_SELL
        if signal <= -0.2:
            return Direction.SELL
        if signal >= 0.6:
            return Direction.STRONG_BUY
        if signal >= 0.2:
            return Direction.BUY
        return Direction.NEUTRAL

    def _build_rationale(self, holdings: list[HoldingSignal], portfolio_signal: float) -> str:
        parts = []
        for h in holdings:
            mom = h.data_points.get("momentum_63d", 0)
            dd = h.data_points.get("dd_from_hwm", 0)
            parts.append(f"{h.ticker} (mom={mom:+.1%}, DD={dd:+.1%})")
        direction = self._signal_to_direction(portfolio_signal)
        return (
            f"Portfolio technical signal: {portfolio_signal:+.2f} ({direction.value}). "
            f"Holdings: {'; '.join(parts)}."
        )

    def _empty_result(self, timestamp: str, reason: str) -> LensResult:
        return LensResult(
            lens_name=LensName.TECHNICAL,
            timestamp=timestamp,
            signal=0.0,
            direction=Direction.NEUTRAL,
            confidence=0.0,
            rationale=f"Technical lens unavailable: {reason}",
            warnings=[reason],
        )
