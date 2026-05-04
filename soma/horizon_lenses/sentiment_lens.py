"""
HORIZON Sentiment Lens — Behavioral & Narrative Intelligence (Weight: 9%)
Pipeline: SOMA/HORIZON | Module: SOMA

Reads from Synthesis (SOMA):
    - raw_intelligence (MUSKONOMY SITREPs, analyst notes, news tags)
    - outlook_snapshots (key_conclusions_json)

Reads from live data:
    - Options-implied sentiment via VIX term structure (yfinance)
    - Put/Call proxy from VIX vs VIX3M ratio

Optionally reads from web_context:
    - analyst_consensus, insider_activity, options_flow,
      social_sentiment, news_headlines

Produces:
    - News/narrative sentiment signal
    - Options-implied sentiment (fear vs greed proxy)
    - MUSKONOMY intelligence signal (TSLA-specific)
    - Combined portfolio sentiment

CFA grounding: "Market sentiment often diverges from fundamentals in the
short run. The behavioral investor uses sentiment as a contrarian or
confirming signal, never as a standalone driver." — CFA L3 Behavioral Finance.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from typing import Optional

from ..horizon_dataclasses import (
    Direction,
    HoldingSignal,
    LensName,
    LensResult,
)
from ..soma_bridge import SomaBridge


# ─── Sentiment Thresholds ─────────────────────────────────────────────────

# VIX term structure (VIX / VIX3M ratio — contango vs backwardation)
_VIX_RATIO_EXTREME_FEAR = 1.15    # VIX >> VIX3M = acute fear (backwardation)
_VIX_RATIO_FEAR = 1.05            # Near-term fear elevated
_VIX_RATIO_NORMAL = 0.95          # Normal contango
_VIX_RATIO_COMPLACENT = 0.85      # Deep contango = complacency

# Raw intelligence significance
_INTEL_HIGH_SIGNIFICANCE = 0.8
_INTEL_MEDIUM_SIGNIFICANCE = 0.5

# Freshness for MUSKONOMY data
_MUSKONOMY_FRESH_HOURS = 36       # MUSKONOMY runs daily at 7 AM ET


class SentimentLens:
    """Sentiment analytical lens — behavioral signals for HORIZON.

    Usage:
        with SentimentLens() as lens:
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

    def analyze(
        self,
        tickers: list[str] | None = None,
        web_context: dict | None = None,
    ) -> LensResult:
        """Run the sentiment lens analysis.

        Args:
            tickers: Portfolio tickers to analyze.
            web_context: Optional enriched data from orchestrator.
                Keys: analyst_consensus (dict per ticker),
                      insider_activity (dict per ticker),
                      options_flow (dict per ticker),
                      social_sentiment (float -1 to +1),
                      news_headlines (list of {headline, sentiment, ticker})

        Returns:
            LensResult with sentiment signal.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        tickers = [t.upper() for t in (tickers or [])]
        web_context = web_context or {}

        # 1. Read SOMA intelligence
        intel_signal, intel_data = self._analyze_raw_intelligence(tickers)

        # 2. Read outlook conclusions
        outlook_signal, outlook_data = self._analyze_outlook()

        # 3. Options-implied sentiment (VIX term structure)
        options_signal, options_data = self._analyze_options_sentiment()

        # 4. Process enriched web context
        enriched_signal, enriched_data = self._process_web_context(web_context, tickers)

        # 5. Synthesize
        signal, confidence, drivers, rationale = self._synthesize(
            intel_signal, intel_data,
            outlook_signal, outlook_data,
            options_signal, options_data,
            enriched_signal, enriched_data,
            tickers,
        )

        # 6. Build per-holding signals
        holding_signals = []
        for ticker in tickers:
            # Ticker-specific sentiment boost from MUSKONOMY/intel
            ticker_boost = self._ticker_specific_signal(ticker, intel_data, web_context)
            h_signal = max(-1.0, min(1.0, signal + ticker_boost))
            holding_signals.append(HoldingSignal(
                ticker=ticker,
                signal=h_signal,
                direction=self._signal_to_direction(h_signal),
                confidence=confidence,
                rationale=f"Sentiment for {ticker}: base={signal:+.2f}, ticker_adj={ticker_boost:+.2f}",
                data_points={
                    "base_sentiment": signal,
                    "ticker_adjustment": ticker_boost,
                    "muskonomy_available": bool(intel_data.get("muskonomy_entries")),
                },
            ))

        # 7. All data
        all_data = {**intel_data, **outlook_data, **options_data, **enriched_data}

        warnings = []
        if not intel_data.get("muskonomy_entries"):
            warnings.append("No MUSKONOMY SITREPs found — TSLA sentiment degraded")
        if not web_context:
            warnings.append("No enriched sentiment data — using SOMA + options proxy only")

        return LensResult(
            lens_name=LensName.SENTIMENT,
            timestamp=now_iso,
            signal=signal,
            direction=self._signal_to_direction(signal),
            confidence=confidence,
            rationale=rationale,
            holding_signals=holding_signals,
            data_freshness_hours=intel_data.get("intel_age_hours", 9999.0),
            key_drivers=drivers[:3],
            warnings=warnings,
            raw_data=all_data,
        )

    # ── SOMA raw intelligence ────────────────────────────────────────

    def _analyze_raw_intelligence(self, tickers: list[str]) -> tuple[float, dict]:
        """Analyze raw_intelligence table for sentiment signals.

        MUSKONOMY SITREPs contain structured JSON with segment analysis.
        """
        if not self._bridge or not self._bridge.conn:
            return 0.0, {"intel_available": False}

        try:
            # Get recent intelligence entries (last 7 days)
            rows = self._bridge.conn.execute(
                """SELECT * FROM raw_intelligence
                   WHERE timestamp > datetime('now', '-7 days')
                   ORDER BY id DESC LIMIT 20"""
            ).fetchall()
        except Exception:
            return 0.0, {"intel_available": False}

        if not rows:
            return 0.0, {"intel_available": False, "muskonomy_entries": 0}

        # Convert sqlite3.Row objects to dicts upfront
        rows = [dict(r) for r in rows]

        muskonomy_entries = []
        other_entries = []

        for entry in rows:
            if entry.get("source") == "muskonomy_sitrep":
                muskonomy_entries.append(entry)
            else:
                other_entries.append(entry)

        # Parse latest MUSKONOMY SITREP for TSLA-specific signals
        muskonomy_signal = 0.0
        muskonomy_summary = ""
        if muskonomy_entries:
            latest = muskonomy_entries[0]
            try:
                content = json.loads(latest.get("content", "{}"))
                muskonomy_signal, muskonomy_summary = self._parse_muskonomy(content)
            except (json.JSONDecodeError, TypeError):
                pass

        # Compute age of latest intel
        intel_age = 9999.0
        if rows:
            try:
                latest_ts = rows[0]["timestamp"]
                if latest_ts:
                    ts = datetime.fromisoformat(str(latest_ts))
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    intel_age = (datetime.now(timezone.utc) - ts).total_seconds() / 3600
            except Exception:
                pass

        # Average significance of recent entries
        sigs = [r["significance_score"] for r in rows if r.get("significance_score")]
        avg_sig = sum(sigs) / len(sigs) if sigs else 0.5

        # Simple signal: high significance + MUSKONOMY bullish = positive
        signal = muskonomy_signal * 0.6  # MUSKONOMY weighted at 60% of intel signal

        return signal, {
            "intel_available": True,
            "muskonomy_entries": len(muskonomy_entries),
            "other_entries": len(other_entries),
            "muskonomy_signal": muskonomy_signal,
            "muskonomy_summary": muskonomy_summary,
            "avg_significance": avg_sig,
            "intel_age_hours": intel_age,
        }

    def _parse_muskonomy(self, content: dict) -> tuple[float, str]:
        """Parse MUSKONOMY SITREP JSON for sentiment signal.

        Returns: (signal -1 to +1, summary string)
        """
        signal = 0.0
        parts = []

        # Check regime status note
        regime_status = content.get("regime_status", "")
        if "CAUTION" in str(regime_status).upper():
            signal -= 0.1
            parts.append("regime flagged as CAUTION")

        # Check for key developments in segments
        segments = content.get("segments", {})
        if isinstance(segments, dict):
            for seg_name, seg_data in segments.items():
                if isinstance(seg_data, dict):
                    # Look for positive/negative keywords in developments
                    dev = str(seg_data.get("developments", "")).lower()
                    if any(w in dev for w in ["growth", "record", "expansion", "launch", "approval"]):
                        signal += 0.05
                        parts.append(f"{seg_name}: positive development")
                    if any(w in dev for w in ["decline", "recall", "lawsuit", "ban", "loss"]):
                        signal -= 0.05
                        parts.append(f"{seg_name}: negative development")

        # Check executive actions / catalysts
        catalysts = content.get("catalysts", [])
        if catalysts:
            signal += 0.05 * min(len(catalysts), 3)
            parts.append(f"{len(catalysts)} catalysts noted")

        # Check risks
        risks = content.get("risks", [])
        if risks:
            signal -= 0.03 * min(len(risks), 3)
            parts.append(f"{len(risks)} risks noted")

        signal = max(-0.5, min(0.5, signal))
        summary = "; ".join(parts) if parts else "No actionable signals"

        return signal, summary

    # ── Outlook analysis ─────────────────────────────────────────────

    def _analyze_outlook(self) -> tuple[float, dict]:
        """Analyze the latest outlook snapshot for directional bias."""
        if not self._bridge:
            return 0.0, {"outlook_available": False}

        outlook = self._bridge.get_latest_outlook()
        if not outlook:
            return 0.0, {"outlook_available": False}

        signal = 0.0
        conclusions = []

        # Parse key_conclusions_json
        kc_json = outlook.get("key_conclusions_json", "")
        if kc_json:
            try:
                conclusions = json.loads(kc_json) if isinstance(kc_json, str) else kc_json
            except (json.JSONDecodeError, TypeError):
                pass

        # Simple keyword sentiment from conclusions
        if conclusions:
            pos_count = sum(
                1 for c in conclusions
                if any(w in str(c).lower() for w in ["upside", "bullish", "recovery", "improving", "risk_on"])
            )
            neg_count = sum(
                1 for c in conclusions
                if any(w in str(c).lower() for w in ["downside", "bearish", "deteriorating", "crisis", "weakening"])
            )
            total = pos_count + neg_count
            if total > 0:
                signal = (pos_count - neg_count) / total * 0.3

        return signal, {
            "outlook_available": True,
            "outlook_date": outlook.get("date"),
            "n_conclusions": len(conclusions),
            "outlook_signal": signal,
        }

    # ── Options-implied sentiment ────────────────────────────────────

    def _analyze_options_sentiment(self) -> tuple[float, dict]:
        """Compute options-implied sentiment from VIX term structure.

        VIX/VIX3M > 1.0 = backwardation = acute fear (bearish short-term)
        VIX/VIX3M < 0.9 = deep contango = complacency (mildly bearish — contrarian)
        """
        try:
            import yfinance as yf
        except ImportError:
            return 0.0, {"options_available": False}

        try:
            vix = yf.Ticker("^VIX").history(period="5d")
            vix3m = yf.Ticker("^VIX3M").history(period="5d")

            if vix is None or vix.empty or vix3m is None or vix3m.empty:
                return 0.0, {"options_available": False, "reason": "VIX data empty"}

            vix_val = vix["Close"].iloc[-1]
            vix3m_val = vix3m["Close"].iloc[-1]

            if vix3m_val <= 0:
                return 0.0, {"options_available": False, "reason": "VIX3M zero"}

            ratio = vix_val / vix3m_val

            # Signal mapping
            if ratio > _VIX_RATIO_EXTREME_FEAR:
                signal = -0.4  # Extreme near-term fear
                state = "EXTREME_FEAR"
            elif ratio > _VIX_RATIO_FEAR:
                signal = -0.2
                state = "FEAR"
            elif ratio < _VIX_RATIO_COMPLACENT:
                signal = -0.1  # Contrarian: too complacent
                state = "COMPLACENT"
            elif ratio < _VIX_RATIO_NORMAL:
                signal = 0.1   # Normal contango = healthy
                state = "HEALTHY"
            else:
                signal = 0.0
                state = "NEUTRAL"

            return signal, {
                "options_available": True,
                "vix": vix_val,
                "vix3m": vix3m_val,
                "vix_ratio": ratio,
                "vix_term_state": state,
            }

        except Exception as e:
            return 0.0, {"options_available": False, "reason": str(e)}

    # ── Web context processing ───────────────────────────────────────

    def _process_web_context(
        self, web_context: dict, tickers: list[str]
    ) -> tuple[float, dict]:
        """Process optional enriched sentiment data from the orchestrator."""
        if not web_context:
            return 0.0, {"enriched": False}

        signal = 0.0
        result = {"enriched": True}

        # Analyst consensus (per ticker average)
        analyst = web_context.get("analyst_consensus", {})
        if analyst:
            # Expected: {ticker: {"buy": n, "hold": n, "sell": n}}
            scores = []
            for ticker in tickers:
                if ticker in analyst:
                    a = analyst[ticker]
                    buy = a.get("buy", 0)
                    hold = a.get("hold", 0)
                    sell = a.get("sell", 0)
                    total = buy + hold + sell
                    if total > 0:
                        score = (buy - sell) / total
                        scores.append(score)
            if scores:
                analyst_signal = sum(scores) / len(scores) * 0.3
                signal += analyst_signal
                result["analyst_signal"] = analyst_signal

        # Insider activity
        insider = web_context.get("insider_activity", {})
        if insider:
            # Expected: {ticker: {"net_shares": int}} positive = buying
            for ticker in tickers:
                if ticker in insider:
                    net = insider[ticker].get("net_shares", 0)
                    if net > 0:
                        signal += 0.1
                        result["insider_buying"] = True
                    elif net < 0:
                        signal -= 0.05
                        result["insider_selling"] = True

        # Social sentiment
        social = web_context.get("social_sentiment")
        if social is not None:
            signal += social * 0.15  # Max ±0.15
            result["social_sentiment"] = social

        signal = max(-0.5, min(0.5, signal))
        result["enriched_signal"] = signal

        return signal, result

    # ── Ticker-specific adjustments ──────────────────────────────────

    def _ticker_specific_signal(
        self, ticker: str, intel_data: dict, web_context: dict
    ) -> float:
        """Compute ticker-specific sentiment adjustment.

        TSLA gets boost/penalty from MUSKONOMY data.
        MSTR inherits BTC sentiment.
        """
        boost = 0.0

        if ticker == "TSLA" and intel_data.get("muskonomy_signal"):
            boost += intel_data["muskonomy_signal"] * 0.3  # MUSKONOMY influence

        if ticker == "MSTR":
            # MSTR sentiment tracks BTC narrative — small positive bias
            # (BTC community is generally constructive on accumulation strategies)
            boost += 0.05

        return max(-0.2, min(0.2, boost))

    # ── Synthesis ────────────────────────────────────────────────────

    def _synthesize(
        self,
        intel_signal: float, intel_data: dict,
        outlook_signal: float, outlook_data: dict,
        options_signal: float, options_data: dict,
        enriched_signal: float, enriched_data: dict,
        tickers: list[str],
    ) -> tuple[float, float, list[str], str]:
        """Synthesize all sentiment components into a single signal."""
        drivers = []

        # Weight the components
        # SOMA intelligence: 30%, Options: 30%, Outlook: 15%, Enriched: 25%
        weights = {
            "intel": 0.30,
            "options": 0.30,
            "outlook": 0.15,
            "enriched": 0.25,
        }

        # If no enriched data, redistribute weight
        if not enriched_data.get("enriched"):
            weights = {"intel": 0.40, "options": 0.40, "outlook": 0.20, "enriched": 0.0}

        signal = (
            intel_signal * weights["intel"]
            + options_signal * weights["options"]
            + outlook_signal * weights["outlook"]
            + enriched_signal * weights["enriched"]
        )
        signal = max(-1.0, min(1.0, signal))

        # Drivers
        if abs(intel_signal) > 0.05:
            drivers.append(
                f"SOMA intel: {intel_signal:+.2f} "
                f"({'bullish' if intel_signal > 0 else 'bearish'})"
            )
        if abs(options_signal) > 0.05:
            vix_state = options_data.get("vix_term_state", "UNKNOWN")
            drivers.append(f"VIX term structure: {vix_state} (signal={options_signal:+.2f})")
        if abs(enriched_signal) > 0.05:
            drivers.append(f"Enriched sentiment: {enriched_signal:+.2f}")
        if abs(outlook_signal) > 0.05:
            drivers.append(f"Outlook bias: {outlook_signal:+.2f}")

        if not drivers:
            drivers.append("No strong sentiment signals detected")

        # Confidence
        confidence = 0.45  # Base — sentiment is the noisiest lens
        if intel_data.get("muskonomy_entries", 0) > 0:
            confidence += 0.1
        if options_data.get("options_available"):
            confidence += 0.1
        if enriched_data.get("enriched"):
            confidence += 0.1
        # All components agree = higher confidence
        component_signs = [
            1 if s > 0.05 else (-1 if s < -0.05 else 0)
            for s in [intel_signal, options_signal, outlook_signal, enriched_signal]
            if s != 0
        ]
        if component_signs and len(set(component_signs)) == 1:
            confidence += 0.1
        confidence = max(0.1, min(1.0, confidence))

        # Rationale
        direction = self._signal_to_direction(signal)
        rationale = (
            f"Sentiment signal: {signal:+.2f} ({direction.value}). "
            f"Components — SOMA intel: {intel_signal:+.2f}, "
            f"VIX term: {options_signal:+.2f} ({options_data.get('vix_term_state', 'N/A')}), "
            f"outlook: {outlook_signal:+.2f}, enriched: {enriched_signal:+.2f}. "
            f"MUSKONOMY entries: {intel_data.get('muskonomy_entries', 0)}."
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

    def _empty_result(self, timestamp: str, reason: str) -> LensResult:
        return LensResult(
            lens_name=LensName.SENTIMENT,
            timestamp=timestamp,
            signal=0.0,
            direction=Direction.NEUTRAL,
            confidence=0.0,
            rationale=f"Sentiment lens unavailable: {reason}",
            warnings=[reason],
        )
