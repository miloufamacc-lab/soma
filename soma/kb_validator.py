"""
SENTINEL — Systematic Enforcement of Norms, Thresholds, Investments & Logic
Pipeline: SOMA/SENTINEL | Module: SOMA | Status: BUILT

KBValidator — SOMA's active intelligence layer.

Validates every write to SOMA against the KB rule base. Violations are
logged (never blocked) so the system builds an audit trail of every
moment a module's output contradicts the CFA knowledge base.

This is what makes SOMA *alive* — it doesn't just store data, it
continuously checks that the data makes sense.

Design:
    - Fire-and-forget: a validation failure never crashes the caller
    - Each write type has a dedicated check method
    - Checks consult KB rules via KBReader (cached, fast)
    - Violations go to kb_violations table with severity + context
    - Severity levels: INFO (note), WARNING (worth reviewing), CRITICAL (contradicts KB rule)
"""

import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class KBValidator:
    """Validates SOMA writes against the Knowledge Base rules."""

    def __init__(self, bridge):
        """Initialize with a SomaBridge instance (must have open connection)."""
        self.bridge = bridge
        self._kb = None  # lazy-loaded KBReader

    def _get_kb(self):
        """Lazy-load KBReader."""
        if self._kb is None:
            try:
                self._kb = self.bridge.get_kb_reader()
            except Exception as e:
                logger.debug(f"KBValidator: could not lazy-load KBReader: {e}")
        return self._kb

    def _now(self):
        return datetime.now(timezone.utc).isoformat()

    def _log_violation(self, severity, rule_id, source_module, write_type,
                       description, context=None):
        """Write a violation to kb_violations table."""
        try:
            self.bridge.conn.execute(
                """INSERT INTO kb_violations
                   (severity, rule_id, source_module, write_type, description,
                    context_json, detected_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (severity, rule_id, source_module, write_type, description,
                 json.dumps(context or {}), self._now()),
            )
            self.bridge._maybe_commit()
        except Exception as e:
            logger.debug(f"KBValidator: could not log violation: {e}")

    # ── Write-type validators ─────────────────────────────────────────

    def validate_regime_write(self, gli_value, regime, diffusion_index,
                              momentum, module_version=None) -> None:
        """Check a regime write against REGIME_ALLOCATIONS_V1."""
        kb = self._get_kb()
        if not kb:
            return

        try:
            rule = kb.get_rule("REGIME_ALLOCATIONS_V1")
            allocations = rule.get("rules", {})
        except Exception as e:
            logger.debug(f"KBValidator: could not get REGIME_ALLOCATIONS_V1: {e}")
            return

        # Check: does the detected regime make sense given GLI value?
        if regime in ("RISK_ON", "RISK_ON_REBOUND", "RISK_ON_EXPANSION"):
            if gli_value is not None and gli_value < 40:
                self._log_violation(
                    "WARNING", "REGIME_ALLOCATIONS_V1", "ORACLE", "regime",
                    f"Regime is {regime} but GLI={gli_value:.1f} (below 40 — inconsistent with risk-on)",
                    {"gli_value": gli_value, "regime": regime},
                )
        elif regime in ("CONTRACTION", "CRISIS"):
            if gli_value is not None and gli_value > 65:
                self._log_violation(
                    "WARNING", "REGIME_ALLOCATIONS_V1", "ORACLE", "regime",
                    f"Regime is {regime} but GLI={gli_value:.1f} (above 65 — inconsistent with contraction)",
                    {"gli_value": gli_value, "regime": regime},
                )

        # Check: diffusion alignment
        if diffusion_index is not None:
            if regime in ("RISK_ON", "RISK_ON_REBOUND", "RISK_ON_EXPANSION") and diffusion_index > 0.55:
                self._log_violation(
                    "INFO", "REGIME_ALLOCATIONS_V1", "ORACLE", "regime",
                    f"Risk-on regime but diffusion={diffusion_index:.0%} adverse (>55%) — watch for transition",
                    {"diffusion_index": diffusion_index, "regime": regime},
                )

    def validate_valuation_write(self, ticker, fair_value, current_price,
                                 implied_upside, execution_score=None,
                                 module_version=None) -> None:
        """Check a valuation write against POSITION_SIZING_V1 upside thresholds."""
        kb = self._get_kb()
        if not kb:
            return

        try:
            rule = kb.get_rule("POSITION_SIZING_V1")
            sizing = rule.get("rules", {})
        except Exception as e:
            logger.debug(f"KBValidator: could not get POSITION_SIZING_V1: {e}")
            return

        upside_rules = sizing.get("UPSIDE_ADJUSTMENT", {})

        # Check: extreme upside (might indicate data error)
        if implied_upside is not None and implied_upside > 2.0:
            self._log_violation(
                "WARNING", "POSITION_SIZING_V1", "ORACLE", "valuation",
                f"{ticker}: implied upside {implied_upside:.0%} exceeds 200% — verify inputs",
                {"ticker": ticker, "implied_upside": implied_upside,
                 "fair_value": fair_value, "current_price": current_price},
            )

        # Check: negative fair value (should never happen)
        if fair_value is not None and fair_value <= 0:
            self._log_violation(
                "CRITICAL", "POSITION_SIZING_V1", "ORACLE", "valuation",
                f"{ticker}: fair value is ${fair_value:.2f} (non-positive — model error)",
                {"ticker": ticker, "fair_value": fair_value},
            )

        # Check: very low upside — KB says don't initiate new positions below 5%
        below_threshold = upside_rules.get("below_5_pct", 0.0)
        if implied_upside is not None and 0 < implied_upside < 0.05:
            self._log_violation(
                "INFO", "POSITION_SIZING_V1", "ORACLE", "valuation",
                f"{ticker}: upside {implied_upside:.1%} below 5% — KB says no new positions at this level",
                {"ticker": ticker, "implied_upside": implied_upside},
            )

    def validate_portfolio_write(self, cash_pct, total_value, dd_from_hwm,
                                 positions_json=None, module_version=None) -> None:
        """Check portfolio state against REGIME_ALLOCATIONS and DRAWDOWN_CONTROLS."""
        kb = self._get_kb()
        if not kb:
            return

        # Get current regime from SOMA for cross-reference
        current_regime = None
        try:
            latest = self.bridge.get_latest_regime()
            if latest:
                current_regime = latest.get("regime")
        except Exception as e:
            logger.debug(f"KBValidator: could not get latest regime: {e}")

        # ── Check: cash floor vs regime allocation ──
        if current_regime and cash_pct is not None:
            try:
                rule = kb.get_rule("REGIME_ALLOCATIONS_V1")
                allocations = rule.get("rules", {})
                regime_alloc = allocations.get(current_regime, {})
                cash_floor = regime_alloc.get("cash_floor")

                if cash_floor is not None and cash_pct < cash_floor:
                    self._log_violation(
                        "WARNING", "REGIME_ALLOCATIONS_V1", "MANTIS", "portfolio",
                        f"Cash {cash_pct:.1%} below {current_regime} floor of {cash_floor:.0%}",
                        {"cash_pct": cash_pct, "cash_floor": cash_floor,
                         "regime": current_regime},
                    )

                # Check equity exposure vs target range
                equity_exposure = 1.0 - cash_pct
                equity_target = regime_alloc.get("equity_target")
                if equity_target and len(equity_target) == 2:
                    if equity_exposure > equity_target[1]:
                        self._log_violation(
                            "WARNING", "REGIME_ALLOCATIONS_V1", "MANTIS", "portfolio",
                            f"Equity {equity_exposure:.0%} exceeds {current_regime} max of {equity_target[1]:.0%}",
                            {"equity_exposure": equity_exposure,
                             "equity_target_max": equity_target[1],
                             "regime": current_regime},
                        )
                    elif equity_exposure < equity_target[0]:
                        self._log_violation(
                            "INFO", "REGIME_ALLOCATIONS_V1", "MANTIS", "portfolio",
                            f"Equity {equity_exposure:.0%} below {current_regime} min of {equity_target[0]:.0%} — underweight",
                            {"equity_exposure": equity_exposure,
                             "equity_target_min": equity_target[0],
                             "regime": current_regime},
                        )
            except Exception:
                pass

        # ── Check: drawdown against circuit breaker tiers ──
        if dd_from_hwm is not None:
            try:
                rule = kb.get_rule("DRAWDOWN_CONTROLS_V1")
                dd_rules = rule.get("rules", {})
                cb = dd_rules.get("CIRCUIT_BREAKERS", {})

                # dd_from_hwm is typically negative (e.g., -0.12 = 12% DD)
                dd_abs = abs(dd_from_hwm) if dd_from_hwm < 0 else dd_from_hwm / 100

                for tier_key, tier_data in sorted(cb.items(), reverse=True):
                    # Extract threshold from key (dd_20_pct → 0.20)
                    try:
                        threshold = int(tier_key.split("_")[1]) / 100
                    except (IndexError, ValueError):
                        continue

                    if dd_abs >= threshold:
                        action = tier_data.get("action", "unknown")
                        desc = tier_data.get("description", "")
                        self._log_violation(
                            "CRITICAL" if threshold >= 0.15 else "WARNING",
                            "DRAWDOWN_CONTROLS_V1", "MANTIS", "portfolio",
                            f"DD {dd_abs:.1%} from HWM triggers {tier_key}: {action}",
                            {"dd_from_hwm": dd_from_hwm, "tier": tier_key,
                             "action": action, "required": desc},
                        )
                        break  # Only log the highest triggered tier
            except Exception:
                pass

        # ── Check: position concentration limits ──
        if positions_json:
            try:
                rule = kb.get_rule("POSITION_SIZING_V1")
                sizing = rule.get("rules", {})
                conc = sizing.get("CONCENTRATION", {})
                limits = sizing.get("POSITION_LIMITS", {})

                positions = json.loads(positions_json) if isinstance(positions_json, str) else positions_json
                hard_cap = limits.get("single_name_hard_cap", 0.10)

                if isinstance(positions, dict):
                    weights = sorted(positions.values(), reverse=True)

                    # Single-name hard cap
                    for ticker, weight in positions.items():
                        if isinstance(weight, (int, float)) and weight > hard_cap:
                            self._log_violation(
                                "CRITICAL", "POSITION_SIZING_V1", "MANTIS", "portfolio",
                                f"{ticker}: weight {weight:.1%} exceeds hard cap of {hard_cap:.0%}",
                                {"ticker": ticker, "weight": weight, "hard_cap": hard_cap},
                            )

                    # Top-5 concentration
                    top_5_limit = conc.get("top_5_max_combined", 0.35)
                    if len(weights) >= 5:
                        top_5_sum = sum(weights[:5])
                        if top_5_sum > top_5_limit:
                            self._log_violation(
                                "WARNING", "POSITION_SIZING_V1", "MANTIS", "portfolio",
                                f"Top 5 positions = {top_5_sum:.1%} (exceeds {top_5_limit:.0%} KB limit)",
                                {"top_5_sum": top_5_sum, "limit": top_5_limit},
                            )
            except Exception:
                pass

    def validate_trade_write(self, ticker, action, weight, regime_at_time=None,
                             module_version=None) -> None:
        """Check a trade against POSITION_SIZING_V1 and REGIME_ALLOCATIONS_V1."""
        kb = self._get_kb()
        if not kb:
            return

        try:
            rule = kb.get_rule("POSITION_SIZING_V1")
            sizing = rule.get("rules", {})
        except Exception as e:
            logger.debug(f"KBValidator: could not get POSITION_SIZING_V1: {e}")
            return

        limits = sizing.get("POSITION_LIMITS", {})
        hard_cap = limits.get("single_name_hard_cap", 0.10)

        # Check: trade creates position above hard cap
        if weight is not None and weight > hard_cap and action in ("BUY", "REBALANCE"):
            self._log_violation(
                "CRITICAL", "POSITION_SIZING_V1", "MANTIS", "trade",
                f"{ticker}: trade weight {weight:.1%} exceeds {hard_cap:.0%} hard cap",
                {"ticker": ticker, "action": action, "weight": weight},
            )

        # Check: buying in CONTRACTION regime (should be minimal per KB)
        if regime_at_time in ("CONTRACTION", "CRISIS") and action == "BUY":
            formula = sizing.get("SIZING_FORMULA", {})
            regime_mult = formula.get("regime_multipliers", {}).get("CONTRACTION", 0.4)
            self._log_violation(
                "INFO", "POSITION_SIZING_V1", "MANTIS", "trade",
                f"{ticker}: new buy in {regime_at_time} regime — KB multiplier is {regime_mult}x (defensive)",
                {"ticker": ticker, "regime": regime_at_time, "multiplier": regime_mult},
            )

    # ── Coordination: recommend config for new entities ───────────────

    def recommend_valuation_method(self, ticker, sector=None, has_dividends=False,
                                   is_conglomerate=False, is_distressed=False) -> list[tuple]:
        """Consult KB to recommend the right valuation method for a new ticker.

        This is what makes SOMA a *coordinator* — not just a validator.
        When ORACLE adds a new company, it asks SOMA which approach to use.
        """
        kb = self._get_kb()
        recommendations = []

        try:
            rule = kb.get_rule("VALUATION_METHOD_SELECTOR_V1")
            methods = rule.get("rules", {})
        except Exception as e:
            logger.debug(f"KBValidator: could not get VALUATION_METHOD_SELECTOR_V1: {e}")
            methods = {}

        # Apply KB criteria
        if is_distressed:
            recommendations.append(("ASSET_BASED", "Company appears distressed — KB recommends asset-based valuation"))
        if is_conglomerate:
            recommendations.append(("SOTP", "Diverse business lines — KB recommends Sum-of-the-Parts"))
        if has_dividends:
            recommendations.append(("DDM", "Stable dividends present — KB recommends Dividend Discount Model"))

        # Default: DCF for most companies
        if not recommendations:
            recommendations.append(("DCF", "Standard approach — KB default for companies with estimable cash flows"))

        # Log the consultation
        if kb:
            try:
                kb.log_rule_usage("VALUATION_METHOD_SELECTOR_V1", "ORACLE",
                                  context={"ticker": ticker, "sector": sector,
                                           "recommendation": recommendations[0][0]})
            except Exception as e:
                logger.debug(f"KBValidator: could not log rule usage: {e}")

        return recommendations

    def recommend_position_sizing(self, ticker, implied_upside=None,
                                  conviction_score=None, regime=None) -> dict:
        """Consult KB to recommend position sizing parameters for a new/existing position."""
        kb = self._get_kb()
        if not kb:
            return {"base_weight": 0.05, "reason": "KB unavailable — using default"}

        try:
            rule = kb.get_rule("POSITION_SIZING_V1")
            sizing = rule.get("rules", {})
        except Exception as e:
            logger.debug(f"KBValidator: could not get POSITION_SIZING_V1: {e}")
            return {"base_weight": 0.05, "reason": "KB rule unavailable — using default"}

        formula = sizing.get("SIZING_FORMULA", {})
        upside_adj = sizing.get("UPSIDE_ADJUSTMENT", {})

        # Base weight
        base = formula.get("base_weight", 0.05)

        # Conviction multiplier
        thresholds = formula.get("conviction_score_thresholds", {})
        multipliers = formula.get("conviction_multipliers", {})
        conv_mult = multipliers.get("reduced", 0.5)
        if conviction_score is not None:
            if conviction_score >= thresholds.get("full", 8.0):
                conv_mult = multipliers.get("full", 1.0)
            elif conviction_score >= thresholds.get("moderate", 6.0):
                conv_mult = multipliers.get("moderate", 0.75)

        # Regime multiplier
        regime_mults = formula.get("regime_multipliers", {})
        regime_mult = 1.0
        if regime:
            if "CONTRACTION" in regime:
                regime_mult = regime_mults.get("CONTRACTION", 0.4)
            elif "TURBULENCE" in regime:
                regime_mult = regime_mults.get("TURBULENCE", 0.7)
            else:
                regime_mult = regime_mults.get("RISK_ON", 1.0)

        # Upside-based max weight
        max_weight = 0.05
        if implied_upside is not None:
            if implied_upside > 0.30:
                max_weight = upside_adj.get("above_30_pct", 0.08)
            elif implied_upside > 0.15:
                max_weight = upside_adj.get("range_15_30_pct", 0.05)
            elif implied_upside > 0.05:
                max_weight = upside_adj.get("range_5_15_pct", 0.03)
            else:
                max_weight = upside_adj.get("below_5_pct", 0.0)

        recommended = min(base * conv_mult * regime_mult, max_weight)

        # Log consultation
        try:
            kb.log_rule_usage("POSITION_SIZING_V1", "MANTIS",
                              context={"ticker": ticker, "recommendation": round(recommended, 4)})
        except Exception as e:
            logger.debug(f"KBValidator: could not log rule usage: {e}")

        return {
            "recommended_weight": round(recommended, 4),
            "base_weight": base,
            "conviction_multiplier": conv_mult,
            "regime_multiplier": regime_mult,
            "max_weight_for_upside": max_weight,
            "reason": f"KB: base={base} × conviction={conv_mult} × regime={regime_mult}, capped at {max_weight:.0%} (upside tier)",
        }

    # ── Aggregate health check ────────────────────────────────────────

    def get_violation_summary(self, limit=50):
        """Return recent violations for dashboard display."""
        try:
            rows = self.bridge.conn.execute(
                """SELECT severity, rule_id, source_module, write_type,
                          description, context_json, detected_at
                   FROM kb_violations
                   ORDER BY id DESC LIMIT ?""",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def get_violation_counts(self):
        """Return violation counts by severity."""
        try:
            rows = self.bridge.conn.execute(
                """SELECT severity, COUNT(*) AS cnt
                   FROM kb_violations
                   GROUP BY severity"""
            ).fetchall()
            return {r["severity"]: r["cnt"] for r in rows}
        except Exception:
            return {}
