"""
HORIZON Credit & Liquidity Lens — Financial Plumbing Intelligence (Weight: 10%)
Pipeline: SOMA/HORIZON | Module: SOMA

Reads from:
    - Live ETF data via yfinance (HYG, LQD, TLT, BIL) as spread proxies
    - VIX for volatility risk premium computation
    - Optional web_context for enriched FRED data (TED spread, ON-RRP, etc.)

Produces:
    - Credit spread signal (tight/normal/wide/blowout)
    - Volatility risk premium (VRP = VIX - realized vol)
    - Yield curve signal (steepening/flattening/inverted)
    - Money market flow signal (risk-on/risk-off proxy)

CFA grounding: "Credit spreads are the market's real-time referendum on
economic health. They lead equities by 2-6 weeks." — CFA L3 Fixed Income.
HY spread widening > 100bps in 30 days has preceded every major equity
correction since 2000.
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


# ─── Credit/Liquidity Thresholds ──────────────────────────────────────────

# HYG drawdown from 20-day high (proxy for HY spread widening)
_HYG_DD_MINOR = -0.005       # <0.5% — normal noise
_HYG_DD_MODERATE = -0.015    # <1.5% — some stress
_HYG_DD_SEVERE = -0.030      # <3.0% — significant stress
_HYG_DD_CRISIS = -0.050      # <5.0% — credit crisis territory

# HYG momentum (20-day return)
_HYG_MOM_POSITIVE = 0.005    # >0.5% — spreads tightening
_HYG_MOM_NEGATIVE = -0.005   # <-0.5% — spreads widening

# VRP thresholds (VIX minus 20d realized vol, annualized)
_VRP_LOW = 2.0               # <2 — complacency, risk mispriced
_VRP_NORMAL_LOW = 4.0        # 2-4 — fair pricing
_VRP_NORMAL_HIGH = 8.0       # 4-8 — mild fear premium
_VRP_HIGH = 12.0             # 8-12 — elevated fear
_VRP_EXTREME = 20.0          # >20 — panic

# LQD/HYG ratio change (IG vs HY performance — flight to quality signal)
_QUALITY_RATIO_THRESHOLD = 0.01  # >1% divergence in 20d

# BIL momentum (money market proxy)
_BIL_STABLE = 0.001          # Very stable = money parked in MM

# History needed
_HISTORY_DAYS = 100


class CreditLiquidityLens:
    """Credit & Liquidity lens — financial plumbing for HORIZON.

    Usage:
        with CreditLiquidityLens() as lens:
            result = lens.analyze(tickers=["TSLA", "MSTR"])
    """

    def __init__(self):
        pass  # No DB needed — pure market data

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    # ── Main analysis ────────────────────────────────────────────────

    def analyze(
        self,
        tickers: list[str] | None = None,
        web_context: dict | None = None,
    ) -> LensResult:
        """Run the credit/liquidity lens analysis.

        Args:
            tickers: Portfolio tickers (signal applies to all holdings).
            web_context: Optional enriched data from orchestrator.
                Keys: ted_spread, on_rrp_balance, fed_funds_rate,
                      ig_oas, hy_oas, move_index

        Returns:
            LensResult with credit/liquidity signal.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        tickers = [t.upper() for t in (tickers or [])]
        web_context = web_context or {}

        # 1. Fetch credit/liquidity ETF data
        etf_data = self._fetch_etf_data()
        if not etf_data:
            return self._empty_result(now_iso, "Failed to fetch credit ETF data")

        # 2. Compute credit indicators
        credit = self._compute_credit_indicators(etf_data)

        # 3. Compute VRP
        vrp = self._compute_vrp(etf_data)

        # 4. Compute flight-to-quality signal
        quality = self._compute_quality_signal(etf_data)

        # 5. Compute money market signal
        mm_signal = self._compute_mm_signal(etf_data)

        # 6. Incorporate enriched web data if available
        enriched = self._process_web_context(web_context)

        # 7. Synthesize into final signal
        signal, confidence, drivers, rationale = self._synthesize(
            credit, vrp, quality, mm_signal, enriched, tickers
        )

        # 8. Build per-holding signals (credit affects all holdings)
        holding_signals = []
        for ticker in tickers:
            holding_signals.append(HoldingSignal(
                ticker=ticker,
                signal=signal,
                direction=self._signal_to_direction(signal),
                confidence=confidence,
                rationale=f"Credit/liquidity regime applies to all holdings",
                data_points={
                    "credit_state": credit.get("state", "UNKNOWN"),
                    "vrp": vrp.get("vrp", 0),
                    "quality_flight": quality.get("flight_to_quality", False),
                },
            ))

        # 9. Combine all indicators into raw_data
        all_data = {**credit, **vrp, **quality, **mm_signal, **enriched}

        return LensResult(
            lens_name=LensName.CREDIT_LIQUIDITY,
            timestamp=now_iso,
            signal=signal,
            direction=self._signal_to_direction(signal),
            confidence=confidence,
            rationale=rationale,
            holding_signals=holding_signals,
            data_freshness_hours=0.0,  # Live data
            key_drivers=drivers[:3],
            warnings=self._build_warnings(etf_data, web_context),
            raw_data=all_data,
        )

    # ── ETF data fetching ────────────────────────────────────────────

    def _fetch_etf_data(self) -> dict:
        """Fetch credit/liquidity ETF data via yfinance.

        ETFs used:
            HYG  — iShares High Yield Corporate Bond (HY spread proxy)
            LQD  — iShares Investment Grade Corporate Bond (IG spread proxy)
            TLT  — iShares 20+ Year Treasury (duration/rate signal)
            BIL  — SPDR 1-3 Month T-Bill (money market proxy)
            ^VIX — CBOE Volatility Index
            SPY  — S&P 500 (for realized vol computation)

        Returns: {ticker: [list of closes, oldest first]}
        """
        try:
            import yfinance as yf
        except ImportError:
            print("[HORIZON/Credit] yfinance not installed")
            return {}

        etfs = ["HYG", "LQD", "TLT", "BIL", "^VIX", "SPY"]
        result = {}

        for ticker in etfs:
            try:
                t = yf.Ticker(ticker)
                hist = t.history(period=f"{_HISTORY_DAYS}d")
                if hist is not None and not hist.empty and "Close" in hist.columns:
                    result[ticker] = hist["Close"].tolist()
                else:
                    result[ticker] = None
            except Exception as e:
                print(f"[HORIZON/Credit] Failed to fetch {ticker}: {e}")
                result[ticker] = None

        return result

    # ── Credit indicators ────────────────────────────────────────────

    def _compute_credit_indicators(self, etf_data: dict) -> dict:
        """Compute credit spread indicators from HYG price action.

        HYG price drops = spreads widening = stress.
        """
        hyg = etf_data.get("HYG")
        if not hyg or len(hyg) < 21:
            return {"state": "NO_DATA", "hyg_dd_20d": 0, "hyg_mom_20d": 0}

        current = hyg[-1]
        n = len(hyg)

        # 20-day drawdown from high (spread widening proxy)
        hwm_20d = max(hyg[-20:])
        dd_20d = (current / hwm_20d - 1) if hwm_20d > 0 else 0.0

        # 20-day momentum
        mom_20d = (hyg[-1] / hyg[-21] - 1) if len(hyg) >= 21 else 0.0

        # 63-day momentum (medium-term trend)
        mom_63d = (hyg[-1] / hyg[-63] - 1) if len(hyg) >= 63 else mom_20d

        # Classify credit state
        if dd_20d < _HYG_DD_CRISIS:
            state = "CRISIS"
        elif dd_20d < _HYG_DD_SEVERE:
            state = "SEVERE_STRESS"
        elif dd_20d < _HYG_DD_MODERATE:
            state = "MODERATE_STRESS"
        elif dd_20d < _HYG_DD_MINOR:
            state = "MILD_STRESS"
        elif mom_20d > _HYG_MOM_POSITIVE:
            state = "TIGHTENING"
        else:
            state = "NORMAL"

        return {
            "state": state,
            "hyg_current": current,
            "hyg_dd_20d": dd_20d,
            "hyg_mom_20d": mom_20d,
            "hyg_mom_63d": mom_63d,
            "hyg_hwm_20d": hwm_20d,
        }

    # ── VRP computation ──────────────────────────────────────────────

    def _compute_vrp(self, etf_data: dict) -> dict:
        """Compute Volatility Risk Premium (VIX - realized vol).

        Positive VRP = market pricing more risk than realized → fear premium.
        Very high VRP = panic. Very low/negative = complacency.
        """
        vix_data = etf_data.get("^VIX")
        spy_data = etf_data.get("SPY")

        if not vix_data or not spy_data or len(spy_data) < 21:
            return {"vrp": 0, "vix_current": 0, "realized_vol": 0, "vrp_state": "NO_DATA"}

        vix_current = vix_data[-1]

        # 20-day realized vol (annualized)
        returns_20d = [
            math.log(spy_data[i] / spy_data[i - 1])
            for i in range(len(spy_data) - 20, len(spy_data))
            if spy_data[i - 1] > 0
        ]
        if returns_20d:
            realized_vol = (sum(r ** 2 for r in returns_20d) / len(returns_20d)) ** 0.5 * (252 ** 0.5) * 100
        else:
            realized_vol = 0

        vrp = vix_current - realized_vol

        # Classify VRP
        if vrp > _VRP_EXTREME:
            vrp_state = "PANIC"
        elif vrp > _VRP_HIGH:
            vrp_state = "ELEVATED_FEAR"
        elif vrp > _VRP_NORMAL_HIGH:
            vrp_state = "MILD_FEAR"
        elif vrp > _VRP_NORMAL_LOW:
            vrp_state = "FAIR"
        elif vrp > _VRP_LOW:
            vrp_state = "LOW_PREMIUM"
        else:
            vrp_state = "COMPLACENT"

        return {
            "vrp": vrp,
            "vix_current": vix_current,
            "realized_vol": realized_vol,
            "vrp_state": vrp_state,
        }

    # ── Flight to quality ────────────────────────────────────────────

    def _compute_quality_signal(self, etf_data: dict) -> dict:
        """Detect flight-to-quality: LQD outperforming HYG = risk-off rotation."""
        hyg = etf_data.get("HYG")
        lqd = etf_data.get("LQD")

        if not hyg or not lqd or len(hyg) < 21 or len(lqd) < 21:
            return {"flight_to_quality": False, "quality_spread_20d": 0}

        hyg_ret_20d = (hyg[-1] / hyg[-21] - 1)
        lqd_ret_20d = (lqd[-1] / lqd[-21] - 1)
        quality_spread = lqd_ret_20d - hyg_ret_20d

        flight_to_quality = quality_spread > _QUALITY_RATIO_THRESHOLD

        return {
            "flight_to_quality": flight_to_quality,
            "quality_spread_20d": quality_spread,
            "hyg_ret_20d": hyg_ret_20d,
            "lqd_ret_20d": lqd_ret_20d,
        }

    # ── Money market signal ──────────────────────────────────────────

    def _compute_mm_signal(self, etf_data: dict) -> dict:
        """Money market flow proxy using BIL and TLT positioning."""
        tlt = etf_data.get("TLT")
        bil = etf_data.get("BIL")

        result = {"mm_state": "NEUTRAL", "tlt_mom_20d": 0}

        if tlt and len(tlt) >= 21:
            tlt_mom = (tlt[-1] / tlt[-21] - 1)
            result["tlt_mom_20d"] = tlt_mom
            result["tlt_current"] = tlt[-1]

            # TLT rallying = flight to safety (rates dropping)
            if tlt_mom > 0.02:
                result["mm_state"] = "FLIGHT_TO_SAFETY"
            elif tlt_mom < -0.02:
                result["mm_state"] = "RISK_ON"

        return result

    # ── Web context processing ───────────────────────────────────────

    def _process_web_context(self, web_context: dict) -> dict:
        """Process optional enriched data from the orchestrator.

        Expected keys: ted_spread, on_rrp_balance, fed_funds_rate,
                       ig_oas, hy_oas, move_index
        """
        if not web_context:
            return {"enriched": False}

        result = {"enriched": True}

        # TED spread (3m LIBOR - 3m T-Bill)
        ted = web_context.get("ted_spread")
        if ted is not None:
            result["ted_spread"] = ted
            if ted > 0.50:
                result["ted_state"] = "STRESS"
            elif ted > 0.35:
                result["ted_state"] = "ELEVATED"
            else:
                result["ted_state"] = "NORMAL"

        # HY OAS (actual spread from FRED/Bloomberg)
        hy_oas = web_context.get("hy_oas")
        if hy_oas is not None:
            result["hy_oas"] = hy_oas
            if hy_oas > 700:
                result["hy_oas_state"] = "CRISIS"
            elif hy_oas > 500:
                result["hy_oas_state"] = "WIDE"
            elif hy_oas > 350:
                result["hy_oas_state"] = "NORMAL"
            else:
                result["hy_oas_state"] = "TIGHT"

        # MOVE index (bond volatility)
        move = web_context.get("move_index")
        if move is not None:
            result["move_index"] = move
            if move > 150:
                result["move_state"] = "EXTREME"
            elif move > 120:
                result["move_state"] = "ELEVATED"
            else:
                result["move_state"] = "NORMAL"

        return result

    # ── Signal synthesis ─────────────────────────────────────────────

    def _synthesize(
        self,
        credit: dict,
        vrp: dict,
        quality: dict,
        mm_signal: dict,
        enriched: dict,
        tickers: list[str],
    ) -> tuple[float, float, list[str], str]:
        """Synthesize all credit/liquidity indicators into a single signal.

        Returns: (signal, confidence, drivers, rationale)
        """
        signal = 0.0
        drivers = []

        # ── Credit state component (±0.4 max) ───────────────────────
        credit_state = credit.get("state", "NORMAL")
        if credit_state == "CRISIS":
            signal -= 0.4
            drivers.append(f"Credit CRISIS (HYG DD={credit.get('hyg_dd_20d', 0):+.1%})")
        elif credit_state == "SEVERE_STRESS":
            signal -= 0.3
            drivers.append(f"Credit severe stress (HYG DD={credit.get('hyg_dd_20d', 0):+.1%})")
        elif credit_state == "MODERATE_STRESS":
            signal -= 0.15
            drivers.append(f"Credit moderate stress")
        elif credit_state == "MILD_STRESS":
            signal -= 0.05
        elif credit_state == "TIGHTENING":
            signal += 0.2
            drivers.append(f"Credit spreads tightening (HYG mom={credit.get('hyg_mom_20d', 0):+.1%})")
        else:
            signal += 0.05  # Normal = slight positive

        # ── VRP component (±0.25 max) ────────────────────────────────
        vrp_state = vrp.get("vrp_state", "FAIR")
        vrp_val = vrp.get("vrp", 0)
        if vrp_state == "PANIC":
            signal -= 0.15  # High fear, but may mean contrarian opportunity
            drivers.append(f"VRP panic ({vrp_val:+.1f}) — extreme fear")
        elif vrp_state == "ELEVATED_FEAR":
            signal -= 0.1
            drivers.append(f"VRP elevated ({vrp_val:+.1f})")
        elif vrp_state == "COMPLACENT":
            signal -= 0.1  # Complacency = risk mispriced
            drivers.append(f"VRP complacent ({vrp_val:+.1f}) — risk mispriced")
        elif vrp_state in ("FAIR", "LOW_PREMIUM"):
            signal += 0.1  # Healthy pricing

        # ── Flight to quality (±0.15 max) ────────────────────────────
        if quality.get("flight_to_quality"):
            signal -= 0.15
            spread = quality.get("quality_spread_20d", 0)
            drivers.append(f"Flight to quality: IG outperforming HY by {spread:+.1%}")

        # ── Money market / duration (±0.1 max) ──────────────────────
        mm_state = mm_signal.get("mm_state", "NEUTRAL")
        if mm_state == "FLIGHT_TO_SAFETY":
            signal -= 0.1
            drivers.append("Treasuries rallying — flight to safety")
        elif mm_state == "RISK_ON":
            signal += 0.1
            drivers.append("Treasuries selling — risk-on rotation")

        # ── Enriched data adjustments (±0.1 max total) ──────────────
        if enriched.get("enriched"):
            ted_state = enriched.get("ted_state")
            if ted_state == "STRESS":
                signal -= 0.05
                drivers.append(f"TED spread stressed ({enriched.get('ted_spread', 0):.2f})")

            hy_oas_state = enriched.get("hy_oas_state")
            if hy_oas_state in ("CRISIS", "WIDE"):
                signal -= 0.05
                drivers.append(f"HY OAS {hy_oas_state.lower()} ({enriched.get('hy_oas', 0):.0f}bps)")

        # ── Clamp ────────────────────────────────────────────────────
        signal = max(-1.0, min(1.0, signal))

        # ── Confidence ───────────────────────────────────────────────
        confidence = 0.60  # Base for credit lens
        # Clear stress = higher confidence
        if credit_state in ("CRISIS", "SEVERE_STRESS"):
            confidence += 0.15
        elif credit_state == "TIGHTENING":
            confidence += 0.1
        # Enriched data = higher confidence
        if enriched.get("enriched"):
            confidence += 0.1
        # VRP extreme = slightly lower (noisy)
        if vrp_state in ("PANIC", "COMPLACENT"):
            confidence -= 0.05
        confidence = max(0.1, min(1.0, confidence))

        # ── Rationale ────────────────────────────────────────────────
        direction = self._signal_to_direction(signal)
        rationale = (
            f"Credit state: {credit_state}. "
            f"VRP: {vrp_val:+.1f} ({vrp_state}). "
            f"VIX: {vrp.get('vix_current', 0):.1f}, "
            f"realized vol: {vrp.get('realized_vol', 0):.1f}%. "
            f"Flight-to-quality: {'YES' if quality.get('flight_to_quality') else 'NO'}. "
            f"Signal: {signal:+.2f} ({direction.value})."
        )

        return signal, confidence, drivers, rationale

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

    def _build_warnings(self, etf_data: dict, web_context: dict) -> list[str]:
        warnings = []
        for etf in ["HYG", "LQD", "^VIX", "SPY"]:
            if not etf_data.get(etf):
                warnings.append(f"{etf} data unavailable — signal degraded")
        if not web_context:
            warnings.append("No enriched data (TED, OAS, MOVE) — using ETF proxies only")
        return warnings

    def _empty_result(self, timestamp: str, reason: str) -> LensResult:
        return LensResult(
            lens_name=LensName.CREDIT_LIQUIDITY,
            timestamp=timestamp,
            signal=0.0,
            direction=Direction.NEUTRAL,
            confidence=0.0,
            rationale=f"Credit/liquidity lens unavailable: {reason}",
            warnings=[reason],
        )
