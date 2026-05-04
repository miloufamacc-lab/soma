"""
HORIZON Bitcoin On-Chain Lens — Crypto-Specific Intelligence (Weight: 12%)
Pipeline: SOMA/HORIZON | Module: SOMA

Reads from:
    - yfinance: BTC-USD price history (compute MVRV/NVT proxies)
    - yfinance: MSTR price + BTC price (NAV premium/discount)
    - web_context (optional): enriched on-chain metrics from orchestrator

Produces:
    - BTC on-chain signal (ACCUMULATION / NEUTRAL / DISTRIBUTION / CAPITULATION)
    - MSTR NAV premium/discount assessment
    - Confidence adjusted by data availability

Rationale (Grok Expert): "Directly augments macro for this book.
MSTR without on-chain is like TSLA without S-curve tracking."
Highest marginal value addition per Grok's review.
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


# ─── On-Chain Thresholds ────────────────────────────────────────────────────

# BTC 200-day MA ratio (Mayer Multiple proxy)
_MAYER_DEEP_VALUE = 0.8        # Price < 80% of 200d MA → deep value
_MAYER_VALUE = 0.95            # Price < 95% of 200d MA → value
_MAYER_OVERBOUGHT = 1.4        # Price > 140% of 200d MA → overbought
_MAYER_EXTREME = 2.0           # Price > 200% of 200d MA → extreme

# BTC realized vol regime
_BTC_VOL_LOW = 0.40            # Annualized vol < 40%
_BTC_VOL_HIGH = 0.80           # Annualized vol > 80%
_BTC_VOL_EXTREME = 1.20        # Annualized vol > 120%

# MSTR NAV premium/discount
_NAV_DEEP_DISCOUNT = -0.20     # MSTR trading >20% below BTC NAV
_NAV_DISCOUNT = -0.05          # 5-20% below NAV
_NAV_PREMIUM = 0.20            # 0-20% premium
_NAV_EXTREME_PREMIUM = 0.50    # >50% premium

# Approximate MSTR BTC holdings for NAV calc (as of early 2026)
# Updated periodically — MSTR holds ~500k+ BTC, ~15.4M diluted shares
_MSTR_BTC_HOLDINGS = 506137    # Approximate total BTC held
_MSTR_SHARES_DILUTED = 15_400_000  # Approximate diluted share count


class BtcOnchainLens:
    """Bitcoin on-chain analytical lens for HORIZON.

    Computes BTC valuation signals using price-derived proxies for on-chain
    metrics (Mayer Multiple, vol regime, momentum). Enriched with web_context
    when available from the orchestrator.

    Usage:
        with BtcOnchainLens() as lens:
            result = lens.analyze(tickers=["TSLA", "MSTR"], web_context={...})
    """

    def __init__(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    def analyze(
        self,
        tickers: list[str] | None = None,
        web_context: dict | None = None,
    ) -> LensResult:
        """Run BTC on-chain analysis.

        Args:
            tickers: Portfolio tickers (used to identify BTC-exposed holdings).
            web_context: Optional dict with enriched on-chain data from orchestrator.
                Keys: mvrv_zscore, nupl, sopr, exchange_net_flow, ltc_supply_pct,
                      mstr_btc_holdings, mstr_nav_premium, funding_rate, oi_change

        Returns:
            LensResult with BTC on-chain signal.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        tickers = [t.upper() for t in (tickers or [])]
        web_context = web_context or {}

        # 1. Fetch BTC price data
        btc_data = self._fetch_btc_data()
        if not btc_data:
            return self._empty_result(now_iso, "Failed to fetch BTC price data")

        # 2. Compute on-chain proxy indicators
        indicators = self._compute_indicators(btc_data, web_context)

        # 3. Compute BTC signal
        btc_signal, btc_confidence, drivers = self._compute_btc_signal(indicators)

        # 4. Compute MSTR NAV premium/discount
        mstr_nav = self._compute_mstr_nav(btc_data, web_context)

        # 5. Build per-holding signals
        holding_signals = []
        for ticker in tickers:
            if ticker == "MSTR":
                # MSTR is directly BTC-exposed
                mstr_signal = btc_signal * 0.7 + mstr_nav.get("nav_signal", 0) * 0.3
                mstr_signal = max(-1.0, min(1.0, mstr_signal))
                holding_signals.append(HoldingSignal(
                    ticker="MSTR",
                    signal=mstr_signal,
                    direction=self._signal_to_direction(mstr_signal),
                    confidence=btc_confidence * 0.9,
                    rationale=(
                        f"MSTR as leveraged BTC proxy. BTC signal: {btc_signal:+.2f}. "
                        f"NAV premium/discount: {mstr_nav.get('premium_pct', 0):+.1%}. "
                        f"{mstr_nav.get('rationale', '')}"
                    ),
                    data_points={**indicators, **mstr_nav},
                ))
            else:
                # Non-BTC holdings get minimal signal from this lens
                holding_signals.append(HoldingSignal(
                    ticker=ticker,
                    signal=0.0,
                    direction=Direction.NEUTRAL,
                    confidence=0.3,
                    rationale=f"{ticker}: Not directly BTC-exposed. On-chain lens N/A.",
                    data_points={"btc_exposed": False},
                ))

        # 6. Portfolio signal (weighted by BTC exposure)
        btc_exposed = [h for h in holding_signals if h.data_points.get("btc_exposed", True)]
        if btc_exposed:
            portfolio_signal = sum(h.signal for h in btc_exposed) / len(btc_exposed)
        else:
            portfolio_signal = 0.0
        portfolio_signal = max(-1.0, min(1.0, portfolio_signal))

        # If no BTC-exposed holdings, this lens contributes minimal signal
        has_btc_exposure = any(t in ("MSTR", "COIN", "BITO") for t in tickers)
        if not has_btc_exposure:
            portfolio_signal *= 0.2  # Dampen if no direct BTC exposure
            btc_confidence *= 0.5

        warnings = []
        if not web_context:
            warnings.append("No enriched on-chain data — using price-derived proxies only")

        return LensResult(
            lens_name=LensName.BTC_ONCHAIN,
            timestamp=now_iso,
            signal=portfolio_signal,
            direction=self._signal_to_direction(portfolio_signal),
            confidence=btc_confidence,
            rationale=self._build_rationale(indicators, mstr_nav, portfolio_signal),
            holding_signals=holding_signals,
            data_freshness_hours=0.0,
            key_drivers=drivers[:3],
            warnings=warnings,
            raw_data={**indicators, "mstr_nav": mstr_nav},
        )

    # ── Data fetching ────────────────────────────────────────────────

    def _fetch_btc_data(self) -> dict | None:
        """Fetch BTC price history via yfinance."""
        try:
            import yfinance as yf
            btc = yf.Ticker("BTC-USD")
            hist = btc.history(period="300d")
            if hist is None or hist.empty:
                return None
            return {
                "closes": hist["Close"].tolist(),
                "volumes": hist["Volume"].tolist() if "Volume" in hist.columns else [],
                "current": hist["Close"].iloc[-1],
            }
        except Exception as e:
            print(f"[HORIZON/BtcOnchain] Failed to fetch BTC data: {e}")
            return None

    # ── Indicator computation ────────────────────────────────────────

    def _compute_indicators(self, btc_data: dict, web_context: dict) -> dict:
        """Compute on-chain proxy indicators from BTC price data."""
        closes = btc_data["closes"]
        current = btc_data["current"]
        n = len(closes)

        # Mayer Multiple (price / 200d MA)
        ma_200 = sum(closes[-200:]) / min(200, n) if n >= 50 else current
        mayer_multiple = current / ma_200 if ma_200 > 0 else 1.0

        # 63-day momentum
        mom_63d = (closes[-1] / closes[-63] - 1) if n >= 63 else 0.0

        # BTC realized volatility (20d annualized)
        if n >= 21:
            log_returns = [
                math.log(closes[i] / closes[i - 1])
                for i in range(n - 20, n)
                if closes[i - 1] > 0
            ]
            btc_vol = (
                (sum(r ** 2 for r in log_returns) / len(log_returns)) ** 0.5
                * (365 ** 0.5)  # Crypto trades 365 days
                if log_returns else 0.0
            )
        else:
            btc_vol = 0.0

        # Vol regime
        if btc_vol > _BTC_VOL_EXTREME:
            vol_regime = "EXTREME"
        elif btc_vol > _BTC_VOL_HIGH:
            vol_regime = "HIGH"
        elif btc_vol < _BTC_VOL_LOW:
            vol_regime = "LOW"
        else:
            vol_regime = "NORMAL"

        # Drawdown from 252d high
        hwm = max(closes[-min(252, n):])
        dd_from_hwm = (current / hwm - 1) if hwm > 0 else 0.0

        result = {
            "btc_price": current,
            "btc_ma200": ma_200,
            "mayer_multiple": mayer_multiple,
            "btc_momentum_63d": mom_63d,
            "btc_vol_20d": btc_vol,
            "btc_vol_regime": vol_regime,
            "btc_dd_from_hwm": dd_from_hwm,
            "btc_exposed": True,
        }

        # Merge enriched web context if available
        for key in ("mvrv_zscore", "nupl", "sopr", "exchange_net_flow",
                     "ltc_supply_pct", "funding_rate", "oi_change"):
            if key in web_context:
                result[key] = web_context[key]

        return result

    def _compute_mstr_nav(self, btc_data: dict, web_context: dict) -> dict:
        """Compute MSTR NAV premium/discount."""
        btc_price = btc_data["current"]

        # Use web context if available, otherwise estimate
        mstr_btc = web_context.get("mstr_btc_holdings", _MSTR_BTC_HOLDINGS)
        mstr_shares = web_context.get("mstr_shares_diluted", _MSTR_SHARES_DILUTED)

        # Compute NAV per share
        btc_nav_total = mstr_btc * btc_price
        nav_per_share = btc_nav_total / mstr_shares if mstr_shares > 0 else 0

        # Get MSTR current price
        try:
            import yfinance as yf
            mstr = yf.Ticker("MSTR")
            mstr_hist = mstr.history(period="5d")
            mstr_price = mstr_hist["Close"].iloc[-1] if not mstr_hist.empty else 0
        except Exception:
            mstr_price = 0

        # Premium/discount
        if nav_per_share > 0 and mstr_price > 0:
            premium_pct = (mstr_price / nav_per_share) - 1
        else:
            premium_pct = web_context.get("mstr_nav_premium", 0)

        # NAV signal
        if premium_pct < _NAV_DEEP_DISCOUNT:
            nav_signal = 0.3   # Deep discount = buy signal
            rationale = f"MSTR at deep discount to BTC NAV ({premium_pct:+.1%})"
        elif premium_pct < _NAV_DISCOUNT:
            nav_signal = 0.15
            rationale = f"MSTR at slight discount to BTC NAV ({premium_pct:+.1%})"
        elif premium_pct > _NAV_EXTREME_PREMIUM:
            nav_signal = -0.4  # Extreme premium = sell signal
            rationale = f"MSTR at extreme premium to BTC NAV ({premium_pct:+.1%})"
        elif premium_pct > _NAV_PREMIUM:
            nav_signal = -0.2
            rationale = f"MSTR at moderate premium to BTC NAV ({premium_pct:+.1%})"
        else:
            nav_signal = 0.0
            rationale = f"MSTR near BTC NAV ({premium_pct:+.1%})"

        return {
            "mstr_price": mstr_price,
            "btc_nav_per_share": nav_per_share,
            "premium_pct": premium_pct,
            "nav_signal": nav_signal,
            "rationale": rationale,
            "mstr_btc_holdings": mstr_btc,
        }

    # ── Signal computation ───────────────────────────────────────────

    def _compute_btc_signal(self, indicators: dict) -> tuple[float, float, list[str]]:
        """Compute overall BTC on-chain signal."""
        signal = 0.0
        drivers = []

        # Mayer Multiple (±0.35)
        mayer = indicators.get("mayer_multiple", 1.0)
        if mayer < _MAYER_DEEP_VALUE:
            signal += 0.35
            drivers.append(f"Mayer Multiple deep value ({mayer:.2f})")
        elif mayer < _MAYER_VALUE:
            signal += 0.15
            drivers.append(f"Mayer Multiple value zone ({mayer:.2f})")
        elif mayer > _MAYER_EXTREME:
            signal -= 0.35
            drivers.append(f"Mayer Multiple extreme ({mayer:.2f})")
        elif mayer > _MAYER_OVERBOUGHT:
            signal -= 0.2
            drivers.append(f"Mayer Multiple overbought ({mayer:.2f})")

        # BTC momentum (±0.3)
        mom = indicators.get("btc_momentum_63d", 0)
        if mom > 0.20:
            signal += 0.3
            drivers.append(f"BTC strong momentum ({mom:+.1%})")
        elif mom > 0.05:
            signal += 0.15
            drivers.append(f"BTC positive momentum ({mom:+.1%})")
        elif mom < -0.20:
            signal -= 0.3
            drivers.append(f"BTC strong negative momentum ({mom:+.1%})")
        elif mom < -0.05:
            signal -= 0.15
            drivers.append(f"BTC negative momentum ({mom:+.1%})")

        # Drawdown (±0.2)
        dd = indicators.get("btc_dd_from_hwm", 0)
        if dd < -0.50:
            signal += 0.1   # Contrarian: extreme oversold
            drivers.append(f"BTC extreme drawdown ({dd:+.1%}) — potential capitulation")
        elif dd < -0.30:
            signal -= 0.2
            drivers.append(f"BTC severe drawdown ({dd:+.1%})")
        elif dd < -0.15:
            signal -= 0.1
            drivers.append(f"BTC moderate drawdown ({dd:+.1%})")

        # Vol regime modifier (±0.1)
        vol_regime = indicators.get("btc_vol_regime", "NORMAL")
        if vol_regime == "EXTREME":
            signal -= 0.1
            drivers.append("BTC extreme volatility")

        # Enriched on-chain data (if available)
        if "mvrv_zscore" in indicators:
            mvrv = indicators["mvrv_zscore"]
            if mvrv < 0:
                signal += 0.2
                drivers.append(f"MVRV Z-Score negative ({mvrv:.2f}) — undervalued")
            elif mvrv > 6:
                signal -= 0.2
                drivers.append(f"MVRV Z-Score extreme ({mvrv:.2f}) — overvalued")

        signal = max(-1.0, min(1.0, signal))

        # Confidence (lower without enriched data)
        confidence = 0.55
        if "mvrv_zscore" in indicators:
            confidence += 0.15
        if "sopr" in indicators:
            confidence += 0.05
        confidence = min(1.0, confidence)

        return signal, confidence, drivers

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

    def _build_rationale(self, indicators: dict, mstr_nav: dict, signal: float) -> str:
        mayer = indicators.get("mayer_multiple", 0)
        mom = indicators.get("btc_momentum_63d", 0)
        dd = indicators.get("btc_dd_from_hwm", 0)
        price = indicators.get("btc_price", 0)
        direction = self._signal_to_direction(signal)
        return (
            f"BTC ${price:,.0f} | Mayer={mayer:.2f} | Mom(63d)={mom:+.1%} | "
            f"DD={dd:+.1%} | MSTR NAV {mstr_nav.get('premium_pct', 0):+.1%}. "
            f"Signal: {signal:+.2f} ({direction.value})."
        )

    def _empty_result(self, timestamp: str, reason: str) -> LensResult:
        return LensResult(
            lens_name=LensName.BTC_ONCHAIN,
            timestamp=timestamp,
            signal=0.0,
            direction=Direction.NEUTRAL,
            confidence=0.0,
            rationale=f"BTC on-chain lens unavailable: {reason}",
            warnings=[reason],
        )
