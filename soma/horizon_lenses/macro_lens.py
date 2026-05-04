"""
HORIZON Macro Lens — Regime Gate + GLI Intelligence (Weight: 35%)
Pipeline: SOMA/HORIZON | Role: REGIME GATE (runs FIRST)

Reads from Synthesis (SOMA):
    - regime_history (GLI, regime state, diffusion, momentum, components)
    - regime streak (how long in current regime)
    - historical regime transitions

Produces:
    - LensResult with macro timing signal
    - RegimeGateResult (controls synthesis flow)

The macro lens is special: it determines whether other lenses proceed normally
(NORMAL/RISK_ON), with extra caution (TURBULENCE), or are bypassed entirely (CRISIS).

CFA grounding: "For concentrated positions, regime/macro factors drive the majority
of drawdown variance and tactical alpha" — CFA TAA literature.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from ..horizon_dataclasses import (
    Direction,
    GateDecision,
    HoldingSignal,
    LensName,
    LensResult,
    RegimeGateResult,
    RegimeState,
)
from ..soma_bridge import SomaBridge


# ─── Macro Signal Thresholds ────────────────────────────────────────────────
# These translate raw GLI/regime data into directional signals.
# Calibrated based on ORACLE regime model (NORMAL at GLI ~50-65, etc.)

# GLI momentum thresholds (rate of change)
_GLI_MOM_STRONG_POSITIVE = 5.0    # Strong recovery signal
_GLI_MOM_POSITIVE = 1.0           # Mild tailwind
_GLI_MOM_NEGATIVE = -1.0          # Mild headwind
_GLI_MOM_STRONG_NEGATIVE = -5.0   # Strong deterioration

# Diffusion index thresholds (% of adverse signals)
_DIFFUSION_RISK_ON = 0.30         # Few adverse signals → bullish
_DIFFUSION_NEUTRAL_HIGH = 0.55    # Mixed signals
_DIFFUSION_STRESS = 0.65          # Many adverse signals → caution
_DIFFUSION_CRISIS = 0.80          # Most signals adverse → alarm

# Spot component thresholds
_VIX_LOW = 15.0
_VIX_ELEVATED = 25.0
_VIX_HIGH = 35.0
_VIX_EXTREME = 50.0

_HY_SPREAD_TIGHT = 3.0            # Credit healthy
_HY_SPREAD_WIDE = 5.0             # Credit stress
_HY_SPREAD_BLOW = 7.0             # Credit crisis


class MacroLens:
    """Macro analytical lens — regime gate for HORIZON.

    Usage:
        with MacroLens() as lens:
            result, gate = lens.analyze(tickers=["TSLA", "MSTR"])
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

    def analyze(self, tickers: list[str] | None = None) -> tuple[LensResult, RegimeGateResult]:
        """Run the macro lens analysis.

        Returns:
            (LensResult, RegimeGateResult) — the lens signal AND the gate decision.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        tickers = tickers or []

        # 1. Read current regime data
        regime_data = self._bridge.get_latest_regime()
        if not regime_data:
            return self._empty_result(now_iso, "No regime data in SOMA")

        # 2. Read regime history for streak + transition analysis
        history = self._bridge.get_regime_history(limit=60)

        # 3. Check data freshness
        is_fresh, age_hours = self._bridge.is_fresh("regime_history", max_age_hours=96)

        # 4. Parse GLI components
        components = self._parse_components(regime_data.get("gli_components_json"))

        # 5. Compute regime streak
        streak_days = self._compute_streak(history)

        # 6. Analyze GLI momentum direction
        gli_mom = regime_data.get("momentum", 0.0) or 0.0
        gli_direction = self._classify_momentum(gli_mom)

        # 7. Compute the macro signal
        signal, confidence, drivers, rationale = self._compute_signal(
            regime_data, components, gli_direction, streak_days, age_hours
        )

        # 8. Build per-holding signals (macro affects all holdings the same way)
        holding_signals = []
        for ticker in tickers:
            holding_signals.append(HoldingSignal(
                ticker=ticker,
                signal=signal,
                direction=self._signal_to_direction(signal),
                confidence=confidence,
                rationale=f"Macro regime {regime_data['regime']} applies to all holdings",
                data_points={
                    "regime": regime_data["regime"],
                    "gli": regime_data["gli_value"],
                    "gli_momentum": gli_mom,
                },
            ))

        # 9. Build the LensResult
        lens_result = LensResult(
            lens_name=LensName.MACRO,
            timestamp=now_iso,
            signal=signal,
            direction=self._signal_to_direction(signal),
            confidence=confidence,
            rationale=rationale,
            holding_signals=holding_signals,
            data_freshness_hours=age_hours if age_hours != float("inf") else 9999.0,
            key_drivers=drivers[:3],
            warnings=self._build_warnings(regime_data, age_hours, is_fresh),
            raw_data={
                "regime": regime_data["regime"],
                "gli_value": regime_data["gli_value"],
                "gli_momentum": gli_mom,
                "diffusion_index": regime_data.get("diffusion_index"),
                "streak_days": streak_days,
                "components": components,
                "data_date": regime_data.get("date"),
            },
        )

        # 10. Build the regime gate decision
        gate = self._build_gate(regime_data, gli_direction, streak_days, lens_result)

        return lens_result, gate

    # ── Signal computation ───────────────────────────────────────────

    def _compute_signal(
        self,
        regime_data: dict,
        components: dict,
        gli_direction: str,
        streak_days: int,
        age_hours: float,
    ) -> tuple[float, float, list[str], str]:
        """Compute the macro signal from regime + GLI + components.

        Returns: (signal, confidence, drivers, rationale)
        """
        regime = regime_data.get("regime", "NORMAL")
        gli = regime_data.get("gli_value", 50.0)
        diffusion = regime_data.get("diffusion_index", 0.5)
        momentum = regime_data.get("momentum", 0.0) or 0.0

        # ── Base signal from regime state ────────────────────────────
        regime_signals = {
            "RISK_ON": 0.6,
            "NORMAL": 0.1,
            "TURBULENCE": -0.4,
            "CRISIS": -0.9,
        }
        signal = regime_signals.get(regime, 0.0)
        drivers = [f"Regime: {regime}"]

        # ── Momentum adjustment (±0.2 max) ──────────────────────────
        if momentum > _GLI_MOM_STRONG_POSITIVE:
            signal += 0.2
            drivers.append(f"GLI momentum strong positive ({momentum:+.1f})")
        elif momentum > _GLI_MOM_POSITIVE:
            signal += 0.1
            drivers.append(f"GLI momentum positive ({momentum:+.1f})")
        elif momentum < _GLI_MOM_STRONG_NEGATIVE:
            signal -= 0.2
            drivers.append(f"GLI momentum strong negative ({momentum:+.1f})")
        elif momentum < _GLI_MOM_NEGATIVE:
            signal -= 0.1
            drivers.append(f"GLI momentum negative ({momentum:+.1f})")

        # ── Diffusion adjustment (±0.15 max) ─────────────────────────
        if diffusion < _DIFFUSION_RISK_ON:
            signal += 0.1
            drivers.append(f"Low diffusion ({diffusion:.2f}) — few stress signals")
        elif diffusion > _DIFFUSION_CRISIS:
            signal -= 0.15
            drivers.append(f"High diffusion ({diffusion:.2f}) — broad stress")
        elif diffusion > _DIFFUSION_STRESS:
            signal -= 0.1
            drivers.append(f"Elevated diffusion ({diffusion:.2f}) — growing stress")

        # ── VIX adjustment (±0.1 max) ────────────────────────────────
        spot = components.get("spot", {})
        vix = spot.get("vix", 20.0)
        if vix > _VIX_EXTREME:
            signal -= 0.1
            drivers.append(f"VIX extreme ({vix:.1f})")
        elif vix > _VIX_HIGH:
            signal -= 0.05
            drivers.append(f"VIX high ({vix:.1f})")
        elif vix < _VIX_LOW:
            signal += 0.05
            drivers.append(f"VIX low ({vix:.1f})")

        # ── HY spread adjustment (±0.1 max) ──────────────────────────
        hy_spread = spot.get("hy_spread", 3.5)
        if hy_spread > _HY_SPREAD_BLOW:
            signal -= 0.1
            drivers.append(f"HY spread blowout ({hy_spread:.2f})")
        elif hy_spread > _HY_SPREAD_WIDE:
            signal -= 0.05
            drivers.append(f"HY spread wide ({hy_spread:.2f})")
        elif hy_spread < _HY_SPREAD_TIGHT:
            signal += 0.05
            drivers.append(f"HY spread tight ({hy_spread:.2f})")

        # ── Clamp to [-1.0, +1.0] ────────────────────────────────────
        signal = max(-1.0, min(1.0, signal))

        # ── Confidence ────────────────────────────────────────────────
        # Higher confidence when: regime is clear, data is fresh, streak is long
        confidence = 0.7  # Base confidence for macro lens
        if streak_days > 30:
            confidence += 0.1  # Entrenched regime = more confident
        if streak_days < 5:
            confidence -= 0.15  # Recent transition = less confident
        if age_hours > 72:
            confidence -= 0.2  # Old data = less confident
        elif age_hours > 48:
            confidence -= 0.1
        # Extreme regimes have higher confidence (clearer signal)
        if regime in ("CRISIS", "RISK_ON"):
            confidence += 0.1
        confidence = max(0.1, min(1.0, confidence))

        # ── Rationale ─────────────────────────────────────────────────
        rationale = (
            f"GLI regime is {regime} (GLI={gli:.1f}, momentum={momentum:+.1f}, "
            f"diffusion={diffusion:.2f}). "
            f"Streak: {streak_days} days in {regime}. "
            f"Direction: {gli_direction}. "
            f"Macro signal: {signal:+.2f} ({self._signal_to_direction(signal).value})."
        )

        return signal, confidence, drivers, rationale

    # ── Gate decision ────────────────────────────────────────────────

    def _build_gate(
        self,
        regime_data: dict,
        gli_direction: str,
        streak_days: int,
        macro_lens_result: LensResult,
    ) -> RegimeGateResult:
        """Build the regime gate decision that controls synthesis flow."""
        regime_str = regime_data.get("regime", "NORMAL")
        try:
            regime = RegimeState(regime_str)
        except ValueError:
            regime = RegimeState.NORMAL

        # Gate logic (per cross-AI consensus):
        # CRISIS → force REDUCE_NOW, skip concordance
        # TURBULENCE → require 5/7 concordance
        # NORMAL/RISK_ON → normal 4/7 concordance
        if regime == RegimeState.CRISIS:
            gate_decision = GateDecision.OVERRIDE_REDUCE
            concordance_threshold = 0  # Not applicable — overridden
            rationale = (
                f"CRISIS regime detected (GLI={regime_data.get('gli_value', 0):.1f}). "
                "Regime gate OVERRIDES to REDUCE_NOW — concordance check bypassed. "
                "CFA TAA: concentrated positions must de-risk immediately in CRISIS."
            )
        elif regime == RegimeState.TURBULENCE:
            gate_decision = GateDecision.PROCEED_CAUTIOUS
            concordance_threshold = 5
            rationale = (
                f"TURBULENCE regime (GLI={regime_data.get('gli_value', 0):.1f}). "
                "Elevated concordance threshold: ≥5/7 lenses must agree before action. "
                "Macro instability requires higher bar for allocation changes."
            )
        else:
            gate_decision = GateDecision.PROCEED
            concordance_threshold = 4
            rationale = (
                f"{regime.value} regime (GLI={regime_data.get('gli_value', 0):.1f}). "
                "Standard concordance threshold: ≥4/7 lenses. "
                "Lenses proceed normally."
            )

        return RegimeGateResult(
            regime=regime,
            gli_value=regime_data.get("gli_value", 0.0),
            gli_momentum=gli_direction,
            regime_streak_days=streak_days,
            gate_decision=gate_decision,
            concordance_threshold=concordance_threshold,
            rationale=rationale,
            macro_lens_result=macro_lens_result,
        )

    # ── Helper methods ───────────────────────────────────────────────

    def _parse_components(self, json_str: str | None) -> dict:
        """Parse GLI components JSON string into dict."""
        if not json_str:
            return {}
        try:
            if isinstance(json_str, str):
                return json.loads(json_str)
            return json_str
        except (json.JSONDecodeError, TypeError):
            return {}

    def _compute_streak(self, history: list[dict]) -> int:
        """Count how many consecutive days the current regime has persisted.

        Uses unique dates from regime_history (ORACLE may write multiple
        entries per day, so we deduplicate by date).
        """
        if not history:
            return 0
        current_regime = history[0].get("regime")
        if not current_regime:
            return 0

        dates_seen = set()
        for entry in history:
            if entry.get("regime") != current_regime:
                break
            date = entry.get("date", "")
            if date and date not in dates_seen:
                dates_seen.add(date)

        if not dates_seen:
            return 0

        # Approximate streak in calendar days from earliest to latest
        sorted_dates = sorted(dates_seen)
        try:
            start = datetime.strptime(sorted_dates[0], "%Y-%m-%d")
            end = datetime.strptime(sorted_dates[-1], "%Y-%m-%d")
            return max(1, (end - start).days + 1)
        except (ValueError, IndexError):
            return len(dates_seen)

    def _classify_momentum(self, momentum: float) -> str:
        """Classify GLI momentum into RISING/FLAT/FALLING."""
        if momentum > _GLI_MOM_POSITIVE:
            return "RISING"
        elif momentum < _GLI_MOM_NEGATIVE:
            return "FALLING"
        return "FLAT"

    @staticmethod
    def _signal_to_direction(signal: float) -> Direction:
        """Convert a -1.0 to +1.0 signal to a Direction enum."""
        if signal <= -0.6:
            return Direction.STRONG_SELL
        if signal <= -0.2:
            return Direction.SELL
        if signal >= 0.6:
            return Direction.STRONG_BUY
        if signal >= 0.2:
            return Direction.BUY
        return Direction.NEUTRAL

    def _build_warnings(self, regime_data: dict, age_hours: float, is_fresh: bool) -> list[str]:
        """Build data quality warnings."""
        warnings = []
        if not is_fresh:
            warnings.append(
                f"Regime data is {age_hours:.0f}h old — consider running ORACLE"
            )
        if regime_data.get("regime") == "CRISIS":
            warnings.append("CRISIS regime active — extreme caution required")
        if not regime_data.get("gli_components_json"):
            warnings.append("GLI components missing — signal based on regime only")
        return warnings

    def _empty_result(
        self, timestamp: str, reason: str
    ) -> tuple[LensResult, RegimeGateResult]:
        """Return a neutral result when no data is available."""
        lens = LensResult(
            lens_name=LensName.MACRO,
            timestamp=timestamp,
            signal=0.0,
            direction=Direction.NEUTRAL,
            confidence=0.0,
            rationale=f"Macro lens unavailable: {reason}",
            warnings=[reason],
        )
        gate = RegimeGateResult(
            regime=RegimeState.NORMAL,
            gli_value=0.0,
            gli_momentum="UNKNOWN",
            regime_streak_days=0,
            gate_decision=GateDecision.PROCEED,
            concordance_threshold=4,
            rationale=f"No regime data — defaulting to PROCEED with standard threshold",
            macro_lens_result=lens,
        )
        return lens, gate
