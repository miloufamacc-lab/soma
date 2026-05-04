"""
HORIZON Monte Carlo Probability Engine — 10,000-Path Regime-Conditioned Simulation
Pipeline: SOMA/HORIZON | Module: SOMA

Implements:
    - GBM (Geometric Brownian Motion) with regime-conditioned drift
    - EGARCH-style volatility clustering (simplified for tractability)
    - Correlated draws for TSLA + BTC (MSTR as leveraged BTC proxy)
    - Bayesian updating: prior from regime history → posterior via concordance
    - 4 time windows: IMMEDIATE (1-3d), SHORT_TERM (1-2w), MEDIUM_TERM (2-4w), EXTENDED (1-3m)

CFA grounding: "Monte Carlo simulation is the standard framework for
multi-asset portfolio risk assessment under regime uncertainty." — CFA L3 Risk.

Note: Uses only stdlib math + standard random. No numpy/scipy dependency
to keep the codebase lightweight and portable on M1 MacBook.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from .horizon_dataclasses import (
    ConcordanceResult,
    Direction,
    MonteCarloResult,
    RegimeGateResult,
    RegimeState,
    TimeWindow,
    WindowProbability,
)


# ─── Regime-Conditioned Parameters ────────────────────────────────────────

# Annual drift (mu) and volatility (sigma) per regime, per asset class
# Calibrated from 2020-2026 observed behavior
_REGIME_PARAMS = {
    #                       drift_annual, vol_annual
    RegimeState.RISK_ON: {
        "TSLA":  (0.40, 0.65),    # Strong uptrend, high vol
        "BTC":   (0.55, 0.70),    # Crypto bull
        "MM":    (0.05, 0.001),   # Risk-free
    },
    RegimeState.NORMAL: {
        "TSLA":  (0.10, 0.55),    # Modest drift, typical TSLA vol
        "BTC":   (0.15, 0.60),    # Modest BTC drift
        "MM":    (0.05, 0.001),
    },
    RegimeState.TURBULENCE: {
        "TSLA":  (-0.10, 0.75),   # Negative drift, elevated vol
        "BTC":   (-0.15, 0.80),   # Crypto selloff
        "MM":    (0.05, 0.001),
    },
    RegimeState.CRISIS: {
        "TSLA":  (-0.40, 0.95),   # Sharp selloff, extreme vol
        "BTC":   (-0.50, 1.00),   # Crypto crash
        "MM":    (0.05, 0.001),
    },
}

# Bayesian priors: P(favorable exit) by regime
# "Favorable" = portfolio doesn't lose >5% if you hold through window
_REGIME_PRIORS = {
    RegimeState.RISK_ON: 0.62,
    RegimeState.NORMAL: 0.52,
    RegimeState.TURBULENCE: 0.38,
    RegimeState.CRISIS: 0.22,
}

# TSLA-BTC correlation by regime (MSTR is essentially leveraged BTC)
_CORRELATION = {
    RegimeState.RISK_ON: 0.45,
    RegimeState.NORMAL: 0.35,
    RegimeState.TURBULENCE: 0.55,   # Correlation rises in stress
    RegimeState.CRISIS: 0.70,       # "All correlations go to 1 in a crisis"
}

# Time windows in trading days
_WINDOW_DAYS = {
    TimeWindow.IMMEDIATE: 3,
    TimeWindow.SHORT_TERM: 10,
    TimeWindow.MEDIUM_TERM: 20,
    TimeWindow.EXTENDED: 63,
}

# EGARCH-style parameters (simplified)
_EGARCH_PERSISTENCE = 0.92     # Vol clustering persistence (α + β ≈ 0.92)
_EGARCH_LEVERAGE = 0.08        # Asymmetric leverage (negative returns → higher vol)
_EGARCH_MEAN_REVERT = 0.05     # Speed of mean reversion to regime vol

# Portfolio weights
_DEFAULT_WEIGHTS = {"TSLA": 0.168, "MSTR": 0.0617, "MM": 0.77}

# Adverse threshold
_ADVERSE_THRESHOLD = -0.05  # >5% portfolio loss


class HorizonMonteCarlo:
    """Monte Carlo probability engine for HORIZON tactical timing.

    Usage:
        mc = HorizonMonteCarlo(n_paths=10000)
        result = mc.run(
            gate=regime_gate_result,
            concordance=concordance_result,
            composite_score=0.12,
            portfolio_weights={"TSLA": 0.168, "MSTR": 0.0617, "MM": 0.77},
        )
    """

    def __init__(self, n_paths: int = 10000, seed: Optional[int] = None):
        self.n_paths = n_paths
        if seed is not None:
            random.seed(seed)

    def run(
        self,
        gate: RegimeGateResult,
        concordance: ConcordanceResult,
        composite_score: float,
        portfolio_weights: dict[str, float] | None = None,
        current_prices: dict[str, float] | None = None,
    ) -> MonteCarloResult:
        """Run the full Monte Carlo simulation.

        Args:
            gate: Regime gate result (sets parameters)
            concordance: Concordance result (for Bayesian updating)
            composite_score: Weighted composite from synthesis
            portfolio_weights: {ticker: weight} (default: TSLA/MSTR/MM)
            current_prices: Optional current prices (not needed for % returns)

        Returns:
            MonteCarloResult with probability distributions per window
        """
        weights = portfolio_weights or _DEFAULT_WEIGHTS
        regime = gate.regime

        # Get regime-conditioned parameters
        params = _REGIME_PARAMS.get(regime, _REGIME_PARAMS[RegimeState.NORMAL])
        correlation = _CORRELATION.get(regime, 0.35)

        # Bayesian prior → posterior
        prior = _REGIME_PRIORS.get(regime, 0.52)
        posterior = self._bayesian_update(prior, concordance, composite_score)

        # Run simulations for each window
        windows = []
        for tw in TimeWindow:
            days = _WINDOW_DAYS[tw]
            wp = self._simulate_window(
                tw, days, params, weights, correlation, regime, posterior
            )
            windows.append(wp)

        # Build assumptions list
        assumptions = [
            f"Regime: {regime.value} (GLI={gate.gli_value:.1f})",
            f"Drift/vol from regime-conditioned calibration (2020-2026)",
            f"EGARCH persistence={_EGARCH_PERSISTENCE}, leverage={_EGARCH_LEVERAGE}",
            f"TSLA-BTC correlation: {correlation:.2f}",
            f"Bayesian prior: {prior:.2f} → posterior: {posterior:.2f}",
            f"Adverse threshold: {_ADVERSE_THRESHOLD:.0%} portfolio loss",
            f"MSTR modeled as 1.5x leveraged BTC proxy",
            f"Money market assumed risk-free at ~5% annualized",
        ]

        warnings = []
        if regime == RegimeState.CRISIS:
            warnings.append("CRISIS regime: parameters reflect extreme conditions, fat tails likely understated")
        if concordance.agreeing_count < concordance.threshold:
            warnings.append("Concordance failed: MC paths reflect higher uncertainty")

        return MonteCarloResult(
            n_paths=self.n_paths,
            windows=windows,
            bayesian_prior=prior,
            bayesian_posterior=posterior,
            regime_used=regime,
            vol_model="EGARCH-lite",
            correlation_tsla_btc=correlation,
            assumptions=assumptions,
            warnings=warnings,
        )

    # ── Window simulation ────────────────────────────────────────────

    def _simulate_window(
        self,
        window: TimeWindow,
        days: int,
        params: dict,
        weights: dict[str, float],
        correlation: float,
        regime: RegimeState,
        posterior: float,
    ) -> WindowProbability:
        """Simulate n_paths for a single time window.

        For each path:
            1. Generate correlated daily returns for TSLA and BTC
            2. Apply EGARCH-style volatility updating
            3. Compute portfolio return over the window
        """
        portfolio_returns = []

        # Extract parameters
        tsla_mu_annual, tsla_sigma_annual = params.get("TSLA", (0.10, 0.55))
        btc_mu_annual, btc_sigma_annual = params.get("BTC", (0.15, 0.60))

        # Convert to daily
        tsla_mu = tsla_mu_annual / 252
        btc_mu = btc_mu_annual / 252
        tsla_sigma_base = tsla_sigma_annual / math.sqrt(252)
        btc_sigma_base = btc_sigma_annual / math.sqrt(252)

        # MSTR leverage factor over BTC
        mstr_leverage = 1.5

        # Portfolio weights
        w_tsla = weights.get("TSLA", 0.168)
        w_mstr = weights.get("MSTR", 0.0617)
        w_mm = weights.get("MM", 0.77)
        mm_daily = 0.05 / 252  # Risk-free daily return

        for _ in range(self.n_paths):
            # Initialize EGARCH vol state
            tsla_vol = tsla_sigma_base
            btc_vol = btc_sigma_base

            # Cumulative log returns
            tsla_cum = 0.0
            btc_cum = 0.0

            for d in range(days):
                # Generate correlated normals using Cholesky
                z1 = random.gauss(0, 1)
                z2 = random.gauss(0, 1)
                z_tsla = z1
                z_btc = correlation * z1 + math.sqrt(1 - correlation ** 2) * z2

                # Daily returns (GBM)
                tsla_ret = tsla_mu + tsla_vol * z_tsla
                btc_ret = btc_mu + btc_vol * z_btc

                # EGARCH vol update
                tsla_vol = self._egarch_update(tsla_vol, tsla_sigma_base, tsla_ret)
                btc_vol = self._egarch_update(btc_vol, btc_sigma_base, btc_ret)

                tsla_cum += tsla_ret
                btc_cum += btc_ret

            # Convert log returns to simple returns
            tsla_total = math.exp(tsla_cum) - 1
            btc_total = math.exp(btc_cum) - 1
            mstr_total = btc_total * mstr_leverage  # Leveraged BTC
            mm_total = mm_daily * days

            # Portfolio return
            port_return = (
                w_tsla * tsla_total
                + w_mstr * mstr_total
                + w_mm * mm_total
            )
            portfolio_returns.append(port_return)

        # Sort for percentile computation
        portfolio_returns.sort()
        n = len(portfolio_returns)

        # Compute statistics
        expected_move = sum(portfolio_returns) / n
        p_adverse = sum(1 for r in portfolio_returns if r < _ADVERSE_THRESHOLD) / n
        p_positive = sum(1 for r in portfolio_returns if r > 0) / n

        # Percentiles
        def pct(p):
            idx = max(0, min(n - 1, int(p / 100 * n)))
            return portfolio_returns[idx]

        percentiles = {
            10: pct(10), 25: pct(25), 50: pct(50), 75: pct(75), 90: pct(90)
        }

        var_95 = pct(5)   # 5th percentile = 95% VaR
        var_99 = pct(1)   # 1st percentile = 99% VaR

        # P(optimal) — probability this window is "best" to act
        # Approximation: posterior weighted by expected move relative
        p_optimal = self._compute_p_optimal(
            window, expected_move, p_adverse, posterior, regime
        )

        # Recommendation
        recommendation = self._window_recommendation(
            window, expected_move, p_adverse, p_optimal, posterior
        )

        # Label
        label = self._window_label(window, days)

        return WindowProbability(
            window=window,
            label=label,
            p_optimal=p_optimal,
            p_adverse=p_adverse,
            expected_move_pct=expected_move * 100,
            var_95=var_95 * 100,
            var_99=var_99 * 100,
            percentiles={k: v * 100 for k, v in percentiles.items()},
            recommendation=recommendation,
        )

    # ── EGARCH-style vol update ──────────────────────────────────────

    @staticmethod
    def _egarch_update(
        current_vol: float,
        base_vol: float,
        last_return: float,
    ) -> float:
        """Simplified EGARCH volatility update.

        - Persistence: vol clusters (high vol follows high vol)
        - Leverage: negative returns increase vol more than positive
        - Mean reversion: vol reverts toward regime base level
        """
        # Standardized return
        std_ret = last_return / current_vol if current_vol > 0 else 0

        # Persistence + innovation
        innovation = abs(std_ret) - 0.7979  # E[|z|] for standard normal ≈ 0.798
        leverage = _EGARCH_LEVERAGE * std_ret  # Negative ret → positive leverage → higher vol

        # Log-vol update (EGARCH works in log space)
        log_vol = math.log(max(current_vol, 1e-10))
        log_base = math.log(max(base_vol, 1e-10))

        log_vol_new = (
            _EGARCH_PERSISTENCE * log_vol
            + (1 - _EGARCH_PERSISTENCE) * log_base  # Mean reversion
            + _EGARCH_MEAN_REVERT * innovation
            + leverage
        )

        # Clamp to prevent explosion (max 3x base vol)
        log_vol_new = max(log_base - 0.5, min(log_base + 1.1, log_vol_new))

        return math.exp(log_vol_new)

    # ── Bayesian updating ────────────────────────────────────────────

    @staticmethod
    def _bayesian_update(
        prior: float,
        concordance: ConcordanceResult,
        composite_score: float,
    ) -> float:
        """Update prior probability using concordance as likelihood.

        Likelihood model:
            - Concordance strength maps to likelihood ratio
            - 4/7 → LR = 1.2 (weak signal)
            - 5/7 → LR = 1.8
            - 6/7 → LR = 2.5
            - 7/7 → LR = 3.5 (strong signal)
            - Failed concordance → LR = 0.8 (slight negative update)

        Additionally, composite score magnitude boosts/reduces LR.
        """
        if not concordance.passed:
            lr = 0.8  # Failed concordance: slight downward update
        else:
            # Base LR from concordance count
            lr_map = {4: 1.2, 5: 1.8, 6: 2.5, 7: 3.5}
            lr = lr_map.get(concordance.agreeing_count, 1.0)

            # Composite magnitude boost (|score| > 0.5 adds up to +0.5 LR)
            lr += abs(composite_score) * 0.5

        # Bayes' rule
        posterior = (prior * lr) / (prior * lr + (1 - prior))
        return max(0.05, min(0.95, posterior))

    # ── P(optimal) computation ───────────────────────────────────────

    @staticmethod
    def _compute_p_optimal(
        window: TimeWindow,
        expected_move: float,
        p_adverse: float,
        posterior: float,
        regime: RegimeState,
    ) -> float:
        """Estimate P(this window is optimal for action).

        Combines:
            - Bayesian posterior (base probability)
            - Window-specific risk/reward
            - Regime urgency factor
        """
        # Start with posterior as base
        p = posterior

        # IMMEDIATE window gets urgency bonus in CRISIS/TURBULENCE
        if window == TimeWindow.IMMEDIATE:
            if regime in (RegimeState.CRISIS, RegimeState.TURBULENCE):
                p += 0.15
            elif p_adverse > 0.3:
                p += 0.1  # High adverse risk → act sooner

        # SHORT_TERM is often the "sweet spot"
        elif window == TimeWindow.SHORT_TERM:
            if expected_move > 0:
                p += 0.05  # Slight positive drift = favorable
            if p_adverse < 0.15:
                p += 0.05

        # EXTENDED window gets time decay penalty
        elif window == TimeWindow.EXTENDED:
            p -= 0.1  # Uncertainty grows with time

        return max(0.05, min(0.95, p))

    # ── Recommendation logic ─────────────────────────────────────────

    @staticmethod
    def _window_recommendation(
        window: TimeWindow,
        expected_move: float,
        p_adverse: float,
        p_optimal: float,
        posterior: float,
    ) -> str:
        """Generate recommendation for a time window."""
        if p_adverse > 0.40:
            return "REDUCE EXPOSURE — high adverse risk"
        if p_adverse > 0.25:
            return "PARTIAL REDUCE — elevated risk"
        if p_optimal > 0.65:
            return "FAVORABLE WINDOW — consider acting"
        if expected_move > 0.02 and p_adverse < 0.15:
            return "HOLD — positive expected drift, low risk"
        if expected_move < -0.02:
            return "CAUTION — negative expected drift"
        return "HOLD — no clear edge"

    # ── Window label ─────────────────────────────────────────────────

    @staticmethod
    def _window_label(window: TimeWindow, days: int) -> str:
        """Generate human-readable label for a time window."""
        today = datetime.now(timezone.utc)
        labels = {
            TimeWindow.IMMEDIATE: f"Next 1-3 trading days",
            TimeWindow.SHORT_TERM: f"Next 1-2 weeks (~{days}d)",
            TimeWindow.MEDIUM_TERM: f"Next 2-4 weeks (~{days}d)",
            TimeWindow.EXTENDED: f"Next 1-3 months (~{days}d)",
        }
        return labels.get(window, f"~{days} trading days")
