"""
HORIZON Fundamental Lens — Valuation Intelligence (Weight: 15%)
Pipeline: SOMA/HORIZON | Module: SOMA

Reads from Synthesis (SOMA):
    - valuations (fair_value, current_price, implied_upside per ticker)
    - valuation history (trend over last 5 data points)

Produces:
    - Per-ticker valuation signal (OVERVALUED / FAIR / UNDERVALUED)
    - Portfolio-level fundamental attractiveness
    - Margin of safety assessment

Gemini additions:
    - TSLA revenue mix shift (Energy/AI vs. Auto) flagged in rationale
    - MSTR as BTC-to-NAV tracker with leverage/dilution risk

CFA grounding: "Margin of safety is the central concept of investment.
The larger the margin of safety, the more confident the position." — CFA L3
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from ..horizon_dataclasses import (
    Direction,
    HoldingSignal,
    LensName,
    LensResult,
)
from ..soma_bridge import SomaBridge


# ─── Fundamental Signal Thresholds ──────────────────────────────────────────

_DEEP_UNDERVALUED = 0.40     # >40% implied upside
_UNDERVALUED = 0.15          # >15% implied upside
_FAIR_LOWER = -0.10          # Between -10% and +15%
_OVERVALUED = -0.10          # More than 10% overvalued
_DEEP_OVERVALUED = -0.30     # More than 30% overvalued

# Valuation trend sensitivity
_TREND_IMPROVING_THRESHOLD = 0.03   # >3% improvement across data points
_TREND_DETERIORATING_THRESHOLD = -0.03


class FundamentalLens:
    """Fundamental analytical lens — valuation assessment for HORIZON.

    Usage:
        with FundamentalLens() as lens:
            result = lens.analyze(tickers=["TSLA", "MSTR"])
    """

    def __init__(self, db_path=None):
        self.db_path = db_path
        self._bridge: Optional[SomaBridge] = None

    def __enter__(self):
        self._bridge = SomaBridge(self.db_path)
        self._bridge.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._bridge:
            self._bridge.__exit__(exc_type, exc_val, exc_tb)
            self._bridge = None
        return False

    # ── Main analysis ────────────────────────────────────────────────

    def analyze(self, tickers: list[str] | None = None) -> LensResult:
        """Run the fundamental lens analysis for specified tickers.

        Args:
            tickers: List of ticker symbols to analyze. If None, analyzes all.

        Returns:
            LensResult with per-holding and portfolio-level fundamental signal.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        tickers = [t.upper() for t in (tickers or [])]

        # 1. Read latest valuations from SOMA
        all_valuations = self._bridge.get_latest_valuations()
        if not all_valuations:
            return self._empty_result(now_iso, "No valuation data in SOMA")

        # 2. Filter to requested tickers (if specified)
        if tickers:
            valuations = [v for v in all_valuations if v["ticker"] in tickers]
        else:
            valuations = all_valuations

        if not valuations:
            return self._empty_result(
                now_iso, f"No valuations found for tickers: {tickers}"
            )

        # 3. Check data freshness
        is_fresh, age_hours = self._bridge.is_fresh("valuations", max_age_hours=96)

        # 4. Read valuation history for trend analysis
        history = self._get_valuation_history(tickers, limit=5)

        # 5. Compute per-holding signals
        holding_signals = []
        ticker_signals = []  # (signal, weight) for portfolio-level calc

        for val in valuations:
            ticker = val["ticker"]
            fair_value = val.get("fair_value", 0)
            current_price = val.get("current_price", 0)
            implied_upside = val.get("implied_upside", 0)
            exec_score = val.get("execution_score")

            # Compute holding signal
            h_signal, h_direction, h_rationale, h_data = self._compute_holding_signal(
                ticker, fair_value, current_price, implied_upside,
                exec_score, history.get(ticker, [])
            )
            holding_signals.append(HoldingSignal(
                ticker=ticker,
                signal=h_signal,
                direction=h_direction,
                confidence=self._holding_confidence(implied_upside, age_hours),
                rationale=h_rationale,
                data_points=h_data,
            ))
            ticker_signals.append(h_signal)

        # 6. Compute portfolio-level signal (equal-weighted across holdings)
        if ticker_signals:
            portfolio_signal = sum(ticker_signals) / len(ticker_signals)
        else:
            portfolio_signal = 0.0
        portfolio_signal = max(-1.0, min(1.0, portfolio_signal))

        # 7. Compute portfolio-level confidence
        confidence = self._portfolio_confidence(holding_signals, age_hours)

        # 8. Build drivers list
        drivers = self._build_drivers(holding_signals)

        # 9. Build rationale
        rationale = self._build_rationale(holding_signals, portfolio_signal)

        return LensResult(
            lens_name=LensName.FUNDAMENTAL,
            timestamp=now_iso,
            signal=portfolio_signal,
            direction=self._signal_to_direction(portfolio_signal),
            confidence=confidence,
            rationale=rationale,
            holding_signals=holding_signals,
            data_freshness_hours=age_hours if age_hours != float("inf") else 9999.0,
            key_drivers=drivers[:3],
            warnings=self._build_warnings(valuations, age_hours, is_fresh),
            raw_data={
                "n_tickers_analyzed": len(valuations),
                "portfolio_signal": portfolio_signal,
                "valuation_date": valuations[0].get("date") if valuations else None,
            },
        )

    # ── Per-holding signal computation ───────────────────────────────

    def _compute_holding_signal(
        self,
        ticker: str,
        fair_value: float,
        current_price: float,
        implied_upside: float,
        exec_score: float | None,
        history: list[dict],
    ) -> tuple[float, Direction, str, dict]:
        """Compute fundamental signal for a single holding.

        Returns: (signal, direction, rationale, data_points)
        """
        # ── Base signal from implied upside ──────────────────────────
        # Maps implied_upside to [-1.0, +1.0] signal
        # >40% upside → +1.0, >15% → ~+0.5, 0% → 0.0, <-10% → ~-0.5, <-30% → -1.0
        if implied_upside >= _DEEP_UNDERVALUED:
            signal = min(1.0, 0.6 + (implied_upside - _DEEP_UNDERVALUED) * 1.0)
        elif implied_upside >= _UNDERVALUED:
            signal = 0.2 + (implied_upside - _UNDERVALUED) / (_DEEP_UNDERVALUED - _UNDERVALUED) * 0.4
        elif implied_upside >= _FAIR_LOWER:
            # Fair value range: -10% to +15%
            signal = (implied_upside - _FAIR_LOWER) / (_UNDERVALUED - _FAIR_LOWER) * 0.4 - 0.2
        elif implied_upside >= _DEEP_OVERVALUED:
            signal = -0.2 - (abs(implied_upside) - abs(_FAIR_LOWER)) / (abs(_DEEP_OVERVALUED) - abs(_FAIR_LOWER)) * 0.4
        else:
            signal = max(-1.0, -0.6 - (abs(implied_upside) - abs(_DEEP_OVERVALUED)) * 1.0)

        signal = max(-1.0, min(1.0, signal))

        # ── Valuation trend adjustment (±0.15) ──────────────────────
        trend = self._compute_trend(history)
        if trend > _TREND_IMPROVING_THRESHOLD:
            signal += 0.15
            trend_desc = "IMPROVING"
        elif trend < _TREND_DETERIORATING_THRESHOLD:
            signal -= 0.15
            trend_desc = "DETERIORATING"
        else:
            trend_desc = "STABLE"

        # ── Execution score adjustment (±0.1) ────────────────────────
        if exec_score is not None:
            if exec_score > 0.8:
                signal += 0.1
            elif exec_score < 0.4:
                signal -= 0.1

        signal = max(-1.0, min(1.0, signal))
        direction = self._signal_to_direction(signal)

        # ── Ticker-specific context (Gemini flags) ───────────────────
        context = ""
        if ticker == "TSLA":
            context = (
                " Note: TSLA fair value reflects traditional auto metrics; "
                "Energy/AI-Robotics revenue mix shift may not be fully captured."
            )
        elif ticker == "MSTR":
            context = (
                " Note: MSTR functions as leveraged BTC proxy; fair value "
                "tracks BTC NAV. Convertible debt basis risk not in ORACLE model."
            )

        rationale = (
            f"{ticker}: Fair value ${fair_value:,.2f} vs. current ${current_price:,.2f} "
            f"→ {implied_upside:+.1%} implied upside. "
            f"Trend: {trend_desc}. Signal: {signal:+.2f} ({direction.value})."
            f"{context}"
        )

        data_points = {
            "fair_value": fair_value,
            "current_price": current_price,
            "implied_upside": implied_upside,
            "execution_score": exec_score,
            "valuation_trend": trend_desc,
            "trend_value": trend,
        }

        return signal, direction, rationale, data_points

    # ── Trend computation ────────────────────────────────────────────

    def _compute_trend(self, history: list[dict]) -> float:
        """Compute valuation trend from historical data points.

        Returns the average change in implied_upside across data points.
        Positive = improving (more upside), negative = deteriorating.
        """
        if len(history) < 2:
            return 0.0

        upsides = [h.get("implied_upside", 0) for h in history]
        # Average change between consecutive points
        changes = [upsides[i] - upsides[i + 1] for i in range(len(upsides) - 1)]
        return sum(changes) / len(changes) if changes else 0.0

    def _get_valuation_history(self, tickers: list[str], limit: int = 5) -> dict:
        """Get historical valuation data points per ticker.

        Returns: {ticker: [list of valuation dicts, newest first]}
        """
        result = {}
        if not self._bridge or not self._bridge.conn:
            return result

        for ticker in tickers:
            try:
                rows = self._bridge.conn.execute(
                    """SELECT DISTINCT date, fair_value, current_price, implied_upside,
                              execution_score
                       FROM valuations
                       WHERE ticker = ?
                       GROUP BY date
                       ORDER BY id DESC
                       LIMIT ?""",
                    (ticker, limit),
                ).fetchall()
                result[ticker] = [dict(r) for r in rows]
            except Exception:
                result[ticker] = []

        return result

    # ── Confidence computation ───────────────────────────────────────

    def _holding_confidence(self, implied_upside: float, age_hours: float) -> float:
        """Compute confidence for a single holding's fundamental signal."""
        confidence = 0.65  # Base
        # Higher confidence when upside is extreme (clear signal)
        if abs(implied_upside) > 0.5:
            confidence += 0.15
        elif abs(implied_upside) > 0.25:
            confidence += 0.1
        # Lower confidence when close to fair value (ambiguous)
        elif abs(implied_upside) < 0.05:
            confidence -= 0.15
        # Age discount
        if age_hours > 72:
            confidence -= 0.15
        elif age_hours > 48:
            confidence -= 0.1
        return max(0.1, min(1.0, confidence))

    def _portfolio_confidence(self, holdings: list[HoldingSignal], age_hours: float) -> float:
        """Compute portfolio-level confidence from holding signals."""
        if not holdings:
            return 0.0
        # Average of holding confidences, with bonus for agreement
        avg_conf = sum(h.confidence for h in holdings) / len(holdings)
        # Check if holdings agree
        directions = [h.direction_sign() if hasattr(h, 'direction_sign') else 0 for h in holdings]
        # Use signal sign instead
        signs = [1 if h.signal > 0.2 else (-1 if h.signal < -0.2 else 0) for h in holdings]
        if len(set(signs)) == 1 and signs[0] != 0:
            avg_conf += 0.1  # All holdings agree
        return max(0.1, min(1.0, avg_conf))

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

    def _build_drivers(self, holdings: list[HoldingSignal]) -> list[str]:
        """Extract top drivers from holding signals."""
        drivers = []
        for h in holdings:
            upside = h.data_points.get("implied_upside", 0)
            drivers.append(f"{h.ticker}: {upside:+.1%} implied upside ({h.direction.value})")
        return drivers

    def _build_rationale(self, holdings: list[HoldingSignal], portfolio_signal: float) -> str:
        """Build portfolio-level rationale string."""
        parts = []
        for h in holdings:
            fv = h.data_points.get("fair_value", 0)
            cp = h.data_points.get("current_price", 0)
            up = h.data_points.get("implied_upside", 0)
            parts.append(f"{h.ticker} (FV=${fv:,.0f} vs ${cp:,.0f}, {up:+.1%})")
        holdings_summary = "; ".join(parts)
        direction = self._signal_to_direction(portfolio_signal)
        return (
            f"Portfolio fundamental signal: {portfolio_signal:+.2f} ({direction.value}). "
            f"Holdings: {holdings_summary}."
        )

    def _build_warnings(self, valuations: list[dict], age_hours: float, is_fresh: bool) -> list[str]:
        warnings = []
        if not is_fresh:
            warnings.append(f"Valuation data is {age_hours:.0f}h old — consider running ORACLE")
        for v in valuations:
            if v.get("execution_score") is None:
                warnings.append(f"{v['ticker']}: execution score missing")
        return warnings

    def _empty_result(self, timestamp: str, reason: str) -> LensResult:
        return LensResult(
            lens_name=LensName.FUNDAMENTAL,
            timestamp=timestamp,
            signal=0.0,
            direction=Direction.NEUTRAL,
            confidence=0.0,
            rationale=f"Fundamental lens unavailable: {reason}",
            warnings=[reason],
        )
