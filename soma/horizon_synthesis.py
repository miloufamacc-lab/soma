"""
HORIZON Synthesis Engine — Hierarchical Signal Combination
Pipeline: SOMA/HORIZON | Module: SOMA

Implements the 3-step hierarchical synthesis:
    Step 1: Regime Gate (from MacroLens) → sets concordance threshold
    Step 2: Concordance Check → ≥4/7 (or 5/7 in TURBULENCE) required
    Step 3: Weighted Combination → composite score from agreeing lenses

CFA grounding: "Change allocation only when MAJORITY of signals agree
in the same direction." Hierarchical approach reduces false-positive
allocation changes by ~35-45% vs flat averaging (Grok estimate).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from .horizon_dataclasses import (
    CONCORDANCE_THRESHOLD_CAUTIOUS,
    CONCORDANCE_THRESHOLD_NORMAL,
    LENS_WEIGHTS,
    TOTAL_LENSES,
    ConcordanceResult,
    Direction,
    GateDecision,
    LensName,
    LensResult,
    RegimeGateResult,
    RegimeState,
)


class HorizonSynthesis:
    """Hierarchical synthesis engine for HORIZON.

    Usage:
        synth = HorizonSynthesis()
        concordance = synth.concordance_check(lens_results, gate)
        composite, direction = synth.weighted_combination(
            lens_results, concordance
        )
    """

    # ── Step 2: Concordance Check ────────────────────────────────────

    def concordance_check(
        self,
        lens_results: dict[LensName, LensResult],
        gate: RegimeGateResult,
    ) -> ConcordanceResult:
        """Check concordance among lens signals.

        In CRISIS regime (gate = OVERRIDE_REDUCE), concordance is
        automatically "passed" with forced SELL direction.

        Args:
            lens_results: dict mapping LensName → LensResult
            gate: RegimeGateResult from macro lens

        Returns:
            ConcordanceResult with pass/fail and details
        """
        threshold = gate.concordance_threshold

        # CRISIS override: skip concordance, force reduce
        if gate.gate_decision == GateDecision.OVERRIDE_REDUCE:
            all_lens_names = list(lens_results.keys())
            return ConcordanceResult(
                total_lenses=len(lens_results),
                agreeing_count=len(lens_results),  # All "agree" by override
                threshold=threshold,
                passed=True,
                majority_direction=Direction.STRONG_SELL,
                agreeing_lenses=all_lens_names,
                dissenting_lenses=[],
                dissent_reasons={"CRISIS_OVERRIDE": "Regime gate forced REDUCE — concordance bypassed"},
            )

        # Normal concordance: count directions
        bullish: list[LensName] = []
        bearish: list[LensName] = []
        neutral: list[LensName] = []
        dissent_reasons: dict[str, str] = {}

        for lens_name, lr in lens_results.items():
            if not lr.is_valid:
                neutral.append(lens_name)
                dissent_reasons[lens_name.value] = "Invalid result"
                continue

            sign = lr.direction_sign()
            if sign > 0:
                bullish.append(lens_name)
            elif sign < 0:
                bearish.append(lens_name)
            else:
                neutral.append(lens_name)

        # Determine majority
        if len(bullish) >= len(bearish):
            majority_dir = Direction.BUY
            agreeing = bullish
            dissenting = bearish + neutral
        else:
            majority_dir = Direction.SELL
            agreeing = bearish
            dissenting = bullish + neutral

        # Build dissent reasons from the dissenting lenses
        for lens_name in dissenting:
            if lens_name.value not in dissent_reasons:
                lr = lens_results.get(lens_name)
                if lr:
                    dissent_reasons[lens_name.value] = (
                        f"Signal: {lr.signal:+.2f} ({lr.direction.value}). "
                        f"{lr.key_drivers[0] if lr.key_drivers else lr.rationale[:80]}"
                    )

        passed = len(agreeing) >= threshold

        return ConcordanceResult(
            total_lenses=len(lens_results),
            agreeing_count=len(agreeing),
            threshold=threshold,
            passed=passed,
            majority_direction=majority_dir,
            agreeing_lenses=agreeing,
            dissenting_lenses=dissenting,
            dissent_reasons=dissent_reasons,
        )

    # ── Step 3: Weighted Combination ─────────────────────────────────

    def weighted_combination(
        self,
        lens_results: dict[LensName, LensResult],
        concordance: ConcordanceResult,
    ) -> tuple[float, Direction, float]:
        """Compute weighted composite score.

        If concordance PASSED: weight only agreeing lenses (normalized).
        If concordance FAILED: produce conservative score near zero.

        Returns: (composite_score, direction, raw_confidence)
        """
        if not concordance.passed:
            # No concordance → composite is a dampened full-weight average
            # Provides information but the output should say HOLD
            full_weighted = 0.0
            weight_sum = 0.0
            conf_sum = 0.0
            for lens_name, lr in lens_results.items():
                w = LENS_WEIGHTS.get(lens_name, 0)
                full_weighted += lr.signal * w
                conf_sum += lr.confidence * w
                weight_sum += w

            # Dampen by 70% — strong drag toward HOLD
            composite = (full_weighted / weight_sum * 0.3) if weight_sum > 0 else 0.0
            raw_confidence = (conf_sum / weight_sum * 0.5) if weight_sum > 0 else 0.0

            return (
                max(-1.0, min(1.0, composite)),
                self._signal_to_direction(composite),
                max(0.0, min(1.0, raw_confidence)),
            )

        # Concordance passed: use agreeing lenses with normalized weights
        agreeing_set = set(concordance.agreeing_lenses)
        weighted_sum = 0.0
        weight_sum = 0.0
        conf_weighted = 0.0

        for lens_name, lr in lens_results.items():
            if lens_name in agreeing_set:
                w = LENS_WEIGHTS.get(lens_name, 0)
                weighted_sum += lr.signal * w
                conf_weighted += lr.confidence * w
                weight_sum += w

        if weight_sum > 0:
            composite = weighted_sum / weight_sum  # Normalized
            raw_confidence = conf_weighted / weight_sum
        else:
            composite = 0.0
            raw_confidence = 0.0

        # Concordance strength bonus: more lenses = higher confidence
        # 4/7 = no bonus, 5/7 = +5%, 6/7 = +10%, 7/7 = +15%
        concordance_bonus = max(0, (concordance.agreeing_count - 4)) * 0.05
        raw_confidence = min(1.0, raw_confidence + concordance_bonus)

        composite = max(-1.0, min(1.0, composite))
        direction = self._signal_to_direction(composite)

        return composite, direction, max(0.0, min(1.0, raw_confidence))

    # ── Full synthesis pipeline ──────────────────────────────────────

    def synthesize(
        self,
        lens_results: dict[LensName, LensResult],
        gate: RegimeGateResult,
    ) -> tuple[ConcordanceResult, float, Direction, float]:
        """Run the full synthesis pipeline (Steps 2-3).

        Step 1 (regime gate) is already done by MacroLens.

        Returns:
            (concordance, composite_score, direction, raw_confidence)
        """
        concordance = self.concordance_check(lens_results, gate)
        composite, direction, raw_confidence = self.weighted_combination(
            lens_results, concordance
        )
        return concordance, composite, direction, raw_confidence

    # ── Helper ───────────────────────────────────────────────────────

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
