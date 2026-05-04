"""
HORIZON Output Formatter — Structured Analysis Report
Pipeline: SOMA/HORIZON | Module: SOMA

Renders a complete HorizonAnalysis into the military-grade SITREP format
specified in the HORIZON architecture document.

Sections:
    1. Header (question, date, freshness)
    2. Regime Gate
    3. Concordance Check
    4. Composite Signal
    5. Monte Carlo Probability Distribution
    6. Per-Holding Breakdown
    7. Behavioral Bias Audit
    8. Key Risks
    9. SOMA Grounding
    10. Disclaimers
"""

from __future__ import annotations

from .horizon_dataclasses import (
    Direction,
    GateDecision,
    HorizonAnalysis,
    LensName,
    LENS_WEIGHTS,
    RegimeState,
    TimeWindow,
)


class HorizonOutputFormatter:
    """Formats a HorizonAnalysis into a readable text report.

    Usage:
        formatter = HorizonOutputFormatter()
        text = formatter.render(analysis)
    """

    def render(self, a: HorizonAnalysis) -> str:
        """Render the full analysis report."""
        sections = [
            self._header(a),
            self._regime_gate(a),
            self._concordance(a),
            self._composite_signal(a),
            self._monte_carlo(a),
            self._per_holding(a),
            self._bias_audit(a),
            self._key_risks(a),
            self._soma_grounding(a),
            self._disclaimers(a),
        ]
        return "\n".join(s for s in sections if s)

    # ── Section renderers ────────────────────────────────────────────

    def _header(self, a: HorizonAnalysis) -> str:
        lines = [
            "HORIZON TACTICAL TIMING ANALYSIS",
            "=" * 60,
            f'Question: "{a.question}"',
            f"Analysis Date: {a.analysis_date}",
            f"Run ID: {a.run_id}",
        ]

        if a.freshness:
            f = a.freshness
            status = "STALE" if f.is_stale else ("OK" if f.freshness_factor > 0.5 else "AGING")
            lines.append(
                f"Data Freshness: ORACLE {f.oracle_age_hours:.0f}h ago "
                f"[freshness: {f.freshness_factor:.2f}] {status}"
            )

        lines.append("")
        return "\n".join(lines)

    def _regime_gate(self, a: HorizonAnalysis) -> str:
        if not a.regime_gate:
            return ""

        g = a.regime_gate
        lines = [
            "-" * 3 + " REGIME GATE " + "-" * 44,
            f"Regime: {g.regime.value} (streak: {g.regime_streak_days}d)",
            f"GLI: {g.gli_value:.2f} (momentum: {g.gli_momentum})",
            f"Gate Decision: {g.gate_decision.value} "
            f"(concordance threshold: {g.concordance_threshold}/7)",
        ]

        if g.gate_decision == GateDecision.OVERRIDE_REDUCE:
            lines.append("*** CRISIS OVERRIDE: Skip concordance, force REDUCE ***")

        lines.append("")
        return "\n".join(lines)

    def _concordance(self, a: HorizonAnalysis) -> str:
        if not a.concordance:
            return ""

        c = a.concordance
        status = "PASS" if c.passed else "FAIL"
        lines = [
            "-" * 3 + " CONCORDANCE CHECK " + "-" * 38,
            f"Lenses in agreement: {c.agreeing_count}/{c.total_lenses} [{status}]",
            f"Direction: {c.majority_direction.value}",
        ]

        if c.agreeing_lenses:
            names = [n.value for n in c.agreeing_lenses]
            lines.append(f"Agreeing: {', '.join(names)}")

        if c.dissenting_lenses:
            names = [n.value for n in c.dissenting_lenses]
            lines.append(f"Dissenting: {', '.join(names)}")

            for lens_name in c.dissenting_lenses:
                reason = c.dissent_reasons.get(lens_name.value, "")
                if reason:
                    lines.append(f"  {lens_name.value}: {reason}")

        if not c.passed:
            lines.append(
                f">> Concordance FAILED ({c.agreeing_count}/{c.threshold} needed) "
                f"-> default to HOLD"
            )

        lines.append("")
        return "\n".join(lines)

    def _composite_signal(self, a: HorizonAnalysis) -> str:
        # Map composite to action label
        d = a.composite_direction
        label_map = {
            Direction.STRONG_SELL: "LIQUIDATE",
            Direction.SELL: "REDUCE",
            Direction.NEUTRAL: "HOLD",
            Direction.BUY: "ACCUMULATE",
            Direction.STRONG_BUY: "STRONG HOLD / ACCUMULATE",
        }
        label = label_map.get(d, d.value)

        lines = [
            "-" * 3 + " COMPOSITE SIGNAL " + "-" * 39,
            f"Overall Bias: {label}",
            f"Composite Score: {a.composite_score:+.3f} (-1.0 to +1.0)",
            f"Raw Confidence: {a.raw_confidence:.0%}",
            f"Bias-Adjusted Confidence: {a.bias_adjusted_confidence:.0%}",
            f"Freshness-Adjusted Confidence: {a.final_confidence:.0%}",
        ]

        if a.bias_audit and a.bias_audit.any_detected:
            names = [b.bias_name for b in a.bias_audit.biases_detected]
            lines.append(f"Biases detected: {', '.join(names)}")

        lines.append("")
        return "\n".join(lines)

    def _monte_carlo(self, a: HorizonAnalysis) -> str:
        if not a.monte_carlo:
            return ""

        mc = a.monte_carlo
        lines = [
            "-" * 3 + " MONTE CARLO PROBABILITY DISTRIBUTION " + "-" * 19,
            f"({mc.n_paths:,} paths, {mc.vol_model}, "
            f"regime={mc.regime_used.value}, "
            f"Bayesian {mc.bayesian_prior:.0%} -> {mc.bayesian_posterior:.0%})",
            "",
        ]

        # Table header
        lines.append(
            f"{'Window':<28} | {'P(Opt)':>7} | {'E[Move]':>8} | "
            f"{'VaR 95%':>8} | {'VaR 99%':>8} | Recommendation"
        )
        lines.append("-" * 100)

        for w in mc.windows:
            lines.append(
                f"{w.label:<28} | {w.p_optimal:>6.0%} | "
                f"{w.expected_move_pct:>+7.1f}% | "
                f"{w.var_95:>+7.1f}% | {w.var_99:>+7.1f}% | "
                f"{w.recommendation}"
            )

        # Percentiles from the SHORT_TERM window (most actionable)
        short = next((w for w in mc.windows if w.window == TimeWindow.SHORT_TERM), None)
        if short and short.percentiles:
            p = short.percentiles
            lines.append("")
            lines.append(f"Percentile Outcomes (1-2 week, portfolio-level):")
            lines.append(
                f"  10th: {p.get(10, 0):+.1f}%  |  "
                f"25th: {p.get(25, 0):+.1f}%  |  "
                f"50th: {p.get(50, 0):+.1f}%  |  "
                f"75th: {p.get(75, 0):+.1f}%  |  "
                f"90th: {p.get(90, 0):+.1f}%"
            )

        if mc.assumptions:
            lines.append("")
            lines.append("Assumptions:")
            for assumption in mc.assumptions:
                lines.append(f"  - {assumption}")

        lines.append("")
        return "\n".join(lines)

    def _per_holding(self, a: HorizonAnalysis) -> str:
        lines = ["-" * 3 + " PER-HOLDING BREAKDOWN " + "-" * 34]

        # Collect per-ticker signals from each lens
        tickers = set()
        for lr in a.lens_results.values():
            for hs in lr.holding_signals:
                tickers.add(hs.ticker)

        for ticker in sorted(tickers):
            weight_pct = {"TSLA": "16.8%", "MSTR": "6.17%"}.get(ticker, "?%")
            lines.append(f"\n{ticker} ({weight_pct} of portfolio):")

            for lens_name in LensName:
                lr = a.lens_results.get(lens_name)
                if not lr:
                    lines.append(f"  {lens_name.value:<20} N/A")
                    continue

                # Find this ticker's holding signal
                hs = next((h for h in lr.holding_signals if h.ticker == ticker), None)
                if hs:
                    lines.append(
                        f"  {lens_name.value:<20} {hs.signal:+.2f} "
                        f"({hs.direction.value}) conf={hs.confidence:.0%}"
                    )
                    # Add key data points
                    for k, v in list(hs.data_points.items())[:3]:
                        if isinstance(v, float):
                            lines.append(f"    {k}: {v:+.3f}")
                        elif isinstance(v, bool):
                            lines.append(f"    {k}: {'Yes' if v else 'No'}")
                        else:
                            lines.append(f"    {k}: {v}")
                else:
                    lines.append(
                        f"  {lens_name.value:<20} {lr.signal:+.2f} "
                        f"({lr.direction.value}) [portfolio-level]"
                    )

        # Money Market section
        lines.append(f"\nMoney Market (77.0% of portfolio):")
        lines.append(f"  Risk-free rate: ~5.0% annualized")
        lines.append(f"  Opportunity cost: holding cash while equity exposure limited")
        lines.append(f"  Quebec superficial loss rules: 30-day wash sale equivalent")

        lines.append("")
        return "\n".join(lines)

    def _bias_audit(self, a: HorizonAnalysis) -> str:
        if not a.bias_audit:
            return ""

        ba = a.bias_audit
        lines = ["-" * 3 + " BEHAVIORAL BIAS AUDIT " + "-" * 34]

        if not ba.any_detected:
            lines.append("No cognitive biases detected. Confidence maintained.")
        else:
            lines.append(f"Biases Detected ({len(ba.biases_detected)}/12 checked):")
            for b in ba.biases_detected:
                name = b.bias_name.replace("_", " ").title()
                lines.append(f"  [{b.severity}] {name}: {b.explanation}")

            lines.append(
                f"\nTotal Confidence Discount: -{ba.total_confidence_discount:.0%}"
            )

        lines.append("")
        return "\n".join(lines)

    def _key_risks(self, a: HorizonAnalysis) -> str:
        lines = ["-" * 3 + " KEY RISKS TO THIS ANALYSIS " + "-" * 29]

        risks = []

        # Freshness risk
        if a.freshness and a.freshness.is_stale:
            risks.append(
                f"STALE DATA: ORACLE data is {a.freshness.oracle_age_hours:.0f}h old. "
                f"Run ORACLE before acting on this analysis."
            )

        # Concordance risk
        if a.concordance and not a.concordance.passed:
            risks.append(
                f"LOW CONCORDANCE: Only {a.concordance.agreeing_count}/7 lenses agree. "
                f"No clear edge detected — timing is uncertain."
            )

        # Monte Carlo risk
        if a.monte_carlo:
            worst_var = min(w.var_99 for w in a.monte_carlo.windows)
            if worst_var < -5:
                risks.append(
                    f"TAIL RISK: VaR 99% = {worst_var:+.1f}% in worst window. "
                    f"Concentrated portfolio amplifies fat-tail risk."
                )

        # Regime transition risk
        if a.regime_gate and a.regime_gate.regime == RegimeState.NORMAL:
            risks.append(
                "REGIME TRANSITION: Current NORMAL regime could shift to "
                "TURBULENCE on macro shock (tariff escalation, credit event)."
            )

        # Correlation risk
        if a.monte_carlo and a.monte_carlo.correlation_tsla_btc > 0.5:
            risks.append(
                f"CORRELATION RISK: TSLA-BTC correlation elevated ({a.monte_carlo.correlation_tsla_btc:.2f}). "
                f"TSLA and MSTR may sell off together."
            )

        if not risks:
            risks.append("No material risks identified beyond standard model uncertainty.")

        for i, r in enumerate(risks, 1):
            lines.append(f"{i}. {r}")

        lines.append("")
        return "\n".join(lines)

    def _soma_grounding(self, a: HorizonAnalysis) -> str:
        lines = ["-" * 3 + " SOMA GROUNDING " + "-" * 41]

        if a.regime_gate:
            g = a.regime_gate
            lines.append(
                f"Regime: {g.regime.value} (streak: {g.regime_streak_days}d)"
            )
            lines.append(f"GLI: {g.gli_value:.2f} (momentum: {g.gli_momentum})")

        if a.freshness:
            lines.append(
                f"ORACLE age: {a.freshness.oracle_age_hours:.1f}h "
                f"(freshness: {a.freshness.freshness_factor:.2f})"
            )

        lines.append(f"Lenses operational: {len(a.lens_results)}/7")
        lines.append(f"Pipeline: SOMA/HORIZON | Run: {a.run_id}")

        lines.append("")
        return "\n".join(lines)

    def _disclaimers(self, a: HorizonAnalysis) -> str:
        lines = ["-" * 3 + " DISCLAIMERS " + "-" * 44]
        for d in a.disclaimers:
            lines.append(f"- {d}")
        lines.append("=" * 60)
        return "\n".join(lines)
