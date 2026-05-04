"""
HORIZON Behavioral Bias Audit — 12 CFA Cognitive Biases Meta-Layer
Pipeline: SOMA/HORIZON | Module: SOMA

This is NOT a signal lens — it's a meta-layer that scans the synthesis
output for evidence of 12 CFA-prescribed cognitive biases.

Action: flags detected biases, does NOT alter the signal direction.
Only applies a confidence discount (max -15% per bias, capped at -30% total).

CFA grounding: CFA Level III Behavioral Finance curriculum —
"The best portfolio decisions account for the investor's own
cognitive and emotional biases."

The 12 biases:
    1. Loss aversion          7. Status quo
    2. Anchoring              8. Framing
    3. Confirmation           9. Hindsight
    4. Overconfidence        10. Herding
    5. Recency               11. Regret aversion
    6. Disposition effect    12. Mental accounting
"""

from __future__ import annotations

from .horizon_dataclasses import (
    BiasAuditResult,
    BiasDetection,
    ConcordanceResult,
    Direction,
    LensName,
    LensResult,
    MonteCarloResult,
    RegimeGateResult,
)


# Max confidence discount per bias and total cap
_MAX_DISCOUNT_PER_BIAS = 0.15
_MAX_TOTAL_DISCOUNT = 0.30


class HorizonBiasAudit:
    """Behavioral bias audit meta-layer for HORIZON.

    Usage:
        audit = HorizonBiasAudit()
        result = audit.run(
            lens_results=...,
            concordance=...,
            composite_score=...,
            gate=...,
            monte_carlo=...,
            question="When should I liquidate...",
        )
    """

    def run(
        self,
        lens_results: dict[LensName, LensResult],
        concordance: ConcordanceResult,
        composite_score: float,
        gate: RegimeGateResult,
        monte_carlo: MonteCarloResult | None = None,
        question: str = "",
    ) -> BiasAuditResult:
        """Run all 12 bias checks and produce audit result."""
        detections: list[BiasDetection] = []

        # Run all 12 checks
        checks = [
            self._check_loss_aversion(lens_results, composite_score, gate),
            self._check_anchoring(lens_results, question),
            self._check_confirmation(lens_results, concordance),
            self._check_overconfidence(concordance, composite_score),
            self._check_recency(lens_results),
            self._check_disposition(lens_results, composite_score),
            self._check_status_quo(concordance, composite_score),
            self._check_framing(question, composite_score),
            self._check_hindsight(gate),
            self._check_herding(lens_results, concordance),
            self._check_regret_aversion(concordance, composite_score),
            self._check_mental_accounting(lens_results),
        ]

        detected = [c for c in checks if c.detected]
        total_discount = min(
            _MAX_TOTAL_DISCOUNT,
            sum(c.confidence_discount for c in detected),
        )

        summary = self._build_summary(detected, total_discount)

        return BiasAuditResult(
            biases_checked=12,
            biases_detected=detected,
            total_confidence_discount=total_discount,
            summary=summary,
        )

    # ── Individual bias checks ───────────────────────────────────────

    def _check_loss_aversion(
        self,
        lens_results: dict[LensName, LensResult],
        composite_score: float,
        gate: RegimeGateResult,
    ) -> BiasDetection:
        """Bias 1: Loss Aversion — is the signal dominated by fear of loss
        rather than balanced risk/reward analysis?

        Detection: bearish signal driven primarily by loss-framed lenses
        (technical drawdown, VaR) while opportunity lenses (fundamental
        upside) are being underweighted in the user's perception.
        """
        tech = lens_results.get(LensName.TECHNICAL)
        fund = lens_results.get(LensName.FUNDAMENTAL)

        detected = False
        severity = "LOW"
        explanation = "No loss aversion detected."
        discount = 0.0

        if tech and fund:
            # Big fundamental upside being overshadowed by technical drawdown
            if (fund.signal > 0.4 and tech.signal < -0.4
                    and composite_score < 0):
                detected = True
                severity = "MEDIUM"
                explanation = (
                    f"Fundamental upside ({fund.signal:+.2f}) is large, but "
                    f"technical drawdown ({tech.signal:+.2f}) may be triggering "
                    f"loss aversion. Verify you're not overweighting the fear of "
                    f"further losses vs. the opportunity cost of missing the rebound."
                )
                discount = 0.05

        return BiasDetection(
            bias_name="loss_aversion",
            detected=detected,
            severity=severity,
            explanation=explanation,
            confidence_discount=discount,
        )

    def _check_anchoring(
        self,
        lens_results: dict[LensName, LensResult],
        question: str,
    ) -> BiasDetection:
        """Bias 2: Anchoring — is the analysis anchored to a specific
        price, date, or recent event?

        Detection: question mentions a specific price or the analysis
        relies heavily on a single data point.
        """
        detected = False
        severity = "LOW"
        explanation = "No anchoring detected."
        discount = 0.0

        # Check if question mentions specific prices
        q_lower = question.lower()
        price_anchors = any(
            w in q_lower for w in ["$", "bought at", "cost basis", "entry price", "paid"]
        )

        if price_anchors:
            detected = True
            severity = "MEDIUM"
            explanation = (
                "Question references specific prices or cost basis. "
                "HORIZON analyzes forward-looking probabilities — "
                "entry price is irrelevant to optimal timing."
            )
            discount = 0.05

        return BiasDetection(
            bias_name="anchoring",
            detected=detected,
            severity=severity,
            explanation=explanation,
            confidence_discount=discount,
        )

    def _check_confirmation(
        self,
        lens_results: dict[LensName, LensResult],
        concordance: ConcordanceResult,
    ) -> BiasDetection:
        """Bias 3: Confirmation — are only confirming lenses emphasized
        while disconfirming ones minimized?

        Detection: large spread between confirming and disconfirming
        lens signals — if dissenting lenses have high confidence.
        """
        detected = False
        severity = "LOW"
        explanation = "No confirmation bias detected."
        discount = 0.0

        # Check if dissenting lenses have high confidence
        high_conf_dissent = []
        for lens_name in concordance.dissenting_lenses:
            lr = lens_results.get(lens_name)
            if lr and lr.confidence > 0.65:
                high_conf_dissent.append((lens_name.value, lr.confidence))

        if high_conf_dissent and concordance.passed:
            detected = True
            severity = "MEDIUM"
            names = [f"{n} (conf={c:.0%})" for n, c in high_conf_dissent]
            explanation = (
                f"Concordance passed, but high-confidence dissenting lenses exist: "
                f"{', '.join(names)}. Ensure these aren't being dismissed — "
                f"the strongest disconfirming signal may be the most important."
            )
            discount = 0.05

        return BiasDetection(
            bias_name="confirmation",
            detected=detected,
            severity=severity,
            explanation=explanation,
            confidence_discount=discount,
        )

    def _check_overconfidence(
        self,
        concordance: ConcordanceResult,
        composite_score: float,
    ) -> BiasDetection:
        """Bias 4: Overconfidence — high confidence with weak concordance.

        Detection: composite confidence > 70% but only 4/7 concordance,
        or extreme signal (|score| > 0.7) with thin support.
        """
        detected = False
        severity = "LOW"
        explanation = "No overconfidence detected."
        discount = 0.0

        if concordance.passed and concordance.agreeing_count <= 4:
            if abs(composite_score) > 0.5:
                detected = True
                severity = "HIGH"
                explanation = (
                    f"Strong composite score ({composite_score:+.2f}) with bare "
                    f"minimum concordance ({concordance.agreeing_count}/7). "
                    f"The conviction level may exceed what the evidence supports. "
                    f"Consider: would you act with this level of agreement?"
                )
                discount = 0.10
            elif abs(composite_score) > 0.3:
                detected = True
                severity = "MEDIUM"
                explanation = (
                    f"Moderate signal ({composite_score:+.2f}) with just "
                    f"{concordance.agreeing_count}/7 concordance. "
                    f"The evidence is thin — size positions conservatively."
                )
                discount = 0.05

        return BiasDetection(
            bias_name="overconfidence",
            detected=detected,
            severity=severity,
            explanation=explanation,
            confidence_discount=discount,
        )

    def _check_recency(
        self,
        lens_results: dict[LensName, LensResult],
    ) -> BiasDetection:
        """Bias 5: Recency — are recent events over-weighted vs. base rates?

        Detection: sentiment and technical lenses dominating while
        macro and fundamental (longer-term) are being overshadowed.
        """
        detected = False
        severity = "LOW"
        explanation = "No recency bias detected."
        discount = 0.0

        sent = lens_results.get(LensName.SENTIMENT)
        tech = lens_results.get(LensName.TECHNICAL)
        macro = lens_results.get(LensName.MACRO)
        fund = lens_results.get(LensName.FUNDAMENTAL)

        if sent and tech and macro and fund:
            # Short-term lenses (sent + tech) vs long-term (macro + fund)
            short_term_avg = (abs(sent.signal) + abs(tech.signal)) / 2
            long_term_avg = (abs(macro.signal) + abs(fund.signal)) / 2

            # Check if direction conflicts — short-term opposing long-term
            short_sign = (1 if sent.signal + tech.signal > 0 else -1)
            long_sign = (1 if macro.signal + fund.signal > 0 else -1)

            if short_sign != long_sign and short_term_avg > long_term_avg * 1.3:
                detected = True
                severity = "MEDIUM"
                explanation = (
                    "Short-term signals (sentiment + technical) are stronger "
                    "than and oppose long-term signals (macro + fundamental). "
                    "Recent price action may be dominating the base rate view."
                )
                discount = 0.05

        return BiasDetection(
            bias_name="recency",
            detected=detected,
            severity=severity,
            explanation=explanation,
            confidence_discount=discount,
        )

    def _check_disposition(
        self,
        lens_results: dict[LensName, LensResult],
        composite_score: float,
    ) -> BiasDetection:
        """Bias 6: Disposition Effect — reluctance to realize losses.

        Detection: holdings are in drawdown (technical lens), fundamentals
        are weak, but composite is still near neutral (reluctance to sell).
        """
        detected = False
        severity = "LOW"
        explanation = "No disposition effect detected."
        discount = 0.0

        tech = lens_results.get(LensName.TECHNICAL)
        fund = lens_results.get(LensName.FUNDAMENTAL)

        if tech and tech.holding_signals:
            # Check if holdings are in significant drawdown
            in_dd = [
                h for h in tech.holding_signals
                if h.data_points.get("dd_from_hwm", 0) < -0.20
            ]

            if in_dd and -0.15 < composite_score < 0.15:
                detected = True
                severity = "MEDIUM"
                tickers = [h.ticker for h in in_dd]
                explanation = (
                    f"Holdings in significant drawdown ({', '.join(tickers)}) "
                    f"but composite score is neutral ({composite_score:+.2f}). "
                    f"Verify you're not avoiding action due to loss realization aversion."
                )
                discount = 0.05

        return BiasDetection(
            bias_name="disposition_effect",
            detected=detected,
            severity=severity,
            explanation=explanation,
            confidence_discount=discount,
        )

    def _check_status_quo(
        self,
        concordance: ConcordanceResult,
        composite_score: float,
    ) -> BiasDetection:
        """Bias 7: Status Quo — is HOLD favored without evidence?

        Detection: concordance fails and output defaults to HOLD, but
        there IS a directional lean in the data being ignored.
        """
        detected = False
        severity = "LOW"
        explanation = "No status quo bias detected."
        discount = 0.0

        if not concordance.passed:
            # Most lenses lean one way but not enough for concordance
            if concordance.agreeing_count >= 3 and abs(composite_score) > 0.1:
                lean = "bullish" if composite_score > 0 else "bearish"
                detected = True
                severity = "LOW"
                explanation = (
                    f"Concordance failed ({concordance.agreeing_count}/7) → defaulting to HOLD. "
                    f"But {concordance.agreeing_count} lenses lean {lean} "
                    f"(score={composite_score:+.2f}). Consider partial action "
                    f"rather than pure status quo."
                )
                discount = 0.03

        return BiasDetection(
            bias_name="status_quo",
            detected=detected,
            severity=severity,
            explanation=explanation,
            confidence_discount=discount,
        )

    def _check_framing(
        self,
        question: str,
        composite_score: float,
    ) -> BiasDetection:
        """Bias 8: Framing — does the question framing bias the output?

        Detection: question uses directional language that could prime
        the analysis toward sell/buy regardless of data.
        """
        detected = False
        severity = "LOW"
        explanation = "No framing bias detected."
        discount = 0.0

        q_lower = question.lower()

        sell_framing = any(
            w in q_lower
            for w in ["liquidate", "sell", "exit", "dump", "get out", "reduce"]
        )
        buy_framing = any(
            w in q_lower
            for w in ["accumulate", "buy more", "add to", "double down", "load up"]
        )

        if sell_framing and composite_score < -0.1:
            detected = True
            severity = "LOW"
            explanation = (
                "Question uses sell-oriented framing ('liquidate', 'exit', etc.) "
                "and the analysis leans bearish. This may be coincidental, but "
                "verify the data supports the direction independent of the framing."
            )
            discount = 0.03
        elif buy_framing and composite_score > 0.1:
            detected = True
            severity = "LOW"
            explanation = (
                "Question uses buy-oriented framing ('accumulate', 'add', etc.) "
                "and the analysis leans bullish. Verify independently."
            )
            discount = 0.03

        return BiasDetection(
            bias_name="framing",
            detected=detected,
            severity=severity,
            explanation=explanation,
            confidence_discount=discount,
        )

    def _check_hindsight(
        self,
        gate: RegimeGateResult,
    ) -> BiasDetection:
        """Bias 9: Hindsight — presenting past transitions as obvious.

        Detection: regime has been stable for a long time, which can
        create the illusion that it "was always going to be this way."
        """
        detected = False
        severity = "LOW"
        explanation = "No hindsight bias detected."
        discount = 0.0

        if gate.regime_streak_days > 60:
            detected = True
            severity = "LOW"
            explanation = (
                f"Regime has been {gate.regime.value} for {gate.regime_streak_days} days. "
                f"Extended stability can create false confidence that the current "
                f"regime will persist. Regime transitions are inherently "
                f"unpredictable — don't mistake a long streak for inevitability."
            )
            discount = 0.03

        return BiasDetection(
            bias_name="hindsight",
            detected=detected,
            severity=severity,
            explanation=explanation,
            confidence_discount=discount,
        )

    def _check_herding(
        self,
        lens_results: dict[LensName, LensResult],
        concordance: ConcordanceResult,
    ) -> BiasDetection:
        """Bias 10: Herding — is consensus sentiment the primary driver?

        Detection: sentiment lens has outsized influence on the direction.
        """
        detected = False
        severity = "LOW"
        explanation = "No herding bias detected."
        discount = 0.0

        sent = lens_results.get(LensName.SENTIMENT)
        if sent and abs(sent.signal) > 0.3:
            # Sentiment is strong — check if it's the swing vote
            if concordance.passed and LensName.SENTIMENT in concordance.agreeing_lenses:
                if concordance.agreeing_count == concordance.threshold:
                    detected = True
                    severity = "MEDIUM"
                    explanation = (
                        f"Sentiment lens ({sent.signal:+.2f}) is the swing vote "
                        f"for concordance. Without it, concordance would fail. "
                        f"Sentiment-driven consensus can reverse quickly — "
                        f"verify fundamental and macro support independently."
                    )
                    discount = 0.05

        return BiasDetection(
            bias_name="herding",
            detected=detected,
            severity=severity,
            explanation=explanation,
            confidence_discount=discount,
        )

    def _check_regret_aversion(
        self,
        concordance: ConcordanceResult,
        composite_score: float,
    ) -> BiasDetection:
        """Bias 11: Regret Aversion — avoiding action to prevent regret.

        Detection: evidence supports action but the analysis gravitates
        toward inaction to avoid the possibility of regret.
        """
        detected = False
        severity = "LOW"
        explanation = "No regret aversion detected."
        discount = 0.0

        # Strong concordance + strong signal but somehow ending up neutral
        if concordance.passed and concordance.agreeing_count >= 5:
            if abs(composite_score) < 0.15:
                detected = True
                severity = "MEDIUM"
                explanation = (
                    f"Strong concordance ({concordance.agreeing_count}/7) "
                    f"but weak composite ({composite_score:+.2f}). "
                    f"The lenses agree on direction but the synthesis is "
                    f"timid. This could indicate aversion to taking action "
                    f"that might later be regretted."
                )
                discount = 0.05

        return BiasDetection(
            bias_name="regret_aversion",
            detected=detected,
            severity=severity,
            explanation=explanation,
            confidence_discount=discount,
        )

    def _check_mental_accounting(
        self,
        lens_results: dict[LensName, LensResult],
    ) -> BiasDetection:
        """Bias 12: Mental Accounting — analyzing positions in isolation.

        Detection: holding-level signals diverge widely, suggesting the
        analysis treats each position as a separate "mental account"
        rather than a portfolio.
        """
        detected = False
        severity = "LOW"
        explanation = "No mental accounting bias detected."
        discount = 0.0

        # Collect all holding signals across lenses
        ticker_signals: dict[str, list[float]] = {}
        for lr in lens_results.values():
            for hs in lr.holding_signals:
                ticker_signals.setdefault(hs.ticker, []).append(hs.signal)

        if len(ticker_signals) >= 2:
            # Check if holdings have wildly different average signals
            averages = {
                t: sum(s) / len(s) for t, s in ticker_signals.items() if s
            }
            if averages:
                vals = list(averages.values())
                spread = max(vals) - min(vals)
                if spread > 0.8:
                    detected = True
                    severity = "LOW"
                    breakdown = ", ".join(f"{t}={v:+.2f}" for t, v in averages.items())
                    explanation = (
                        f"Wide signal spread across holdings ({breakdown}). "
                        f"Each position is assessed at the portfolio level — "
                        f"avoid treating each holding as an independent decision."
                    )
                    discount = 0.03

        return BiasDetection(
            bias_name="mental_accounting",
            detected=detected,
            severity=severity,
            explanation=explanation,
            confidence_discount=discount,
        )

    # ── Summary builder ──────────────────────────────────────────────

    @staticmethod
    def _build_summary(detected: list[BiasDetection], total_discount: float) -> str:
        if not detected:
            return "No cognitive biases detected. Confidence maintained."

        names = [d.bias_name.replace("_", " ").title() for d in detected]
        high = [d for d in detected if d.severity == "HIGH"]
        med = [d for d in detected if d.severity == "MEDIUM"]

        parts = [f"{len(detected)} bias(es) detected: {', '.join(names)}."]
        if high:
            parts.append(f"HIGH severity: {', '.join(d.bias_name for d in high)}.")
        if med:
            parts.append(f"MEDIUM severity: {', '.join(d.bias_name for d in med)}.")
        parts.append(f"Total confidence discount: -{total_discount:.0%}.")

        return " ".join(parts)
