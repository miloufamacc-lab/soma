"""
HORIZON Dataclasses — Shared contracts for the tactical timing pipeline.
Pipeline: SOMA/HORIZON | Module: SOMA

These dataclasses define the exact shape of data flowing between:
    Lenses → Synthesis → Monte Carlo → Bias Audit → Output

Design: immutable-ish (frozen where possible), with explicit types and defaults.
Every field has a docstring-level comment explaining its purpose.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


# ─── Enums ──────────────────────────────────────────────────────────────────

class LensName(str, Enum):
    """The 7 HORIZON analytical lenses (Grok Expert-mode weights)."""
    MACRO = "MACRO"
    BTC_ONCHAIN = "BTC_ONCHAIN"
    CREDIT_LIQUIDITY = "CREDIT_LIQUIDITY"
    FUNDAMENTAL = "FUNDAMENTAL"
    TECHNICAL = "TECHNICAL"
    SENTIMENT = "SENTIMENT"
    GEOPOLITICAL = "GEOPOLITICAL"


class RegimeState(str, Enum):
    """SOMA GLI regime states (from ORACLE/TITAN)."""
    RISK_ON = "RISK_ON"
    NORMAL = "NORMAL"
    TURBULENCE = "TURBULENCE"
    CRISIS = "CRISIS"


class GateDecision(str, Enum):
    """Regime gate outcomes — controls synthesis flow."""
    PROCEED = "PROCEED"            # Normal/Risk_On: run concordance at 4/7
    PROCEED_CAUTIOUS = "PROCEED_CAUTIOUS"  # Turbulence: require 5/7 concordance
    OVERRIDE_REDUCE = "OVERRIDE_REDUCE"    # Crisis: skip concordance, force reduce


class Direction(str, Enum):
    """Signal direction — the core output of each lens."""
    STRONG_SELL = "STRONG_SELL"     # -1.0 to -0.6: urgent liquidation
    SELL = "SELL"                   # -0.6 to -0.2: reduce exposure
    NEUTRAL = "NEUTRAL"            # -0.2 to +0.2: hold / no edge
    BUY = "BUY"                    # +0.2 to +0.6: accumulate
    STRONG_BUY = "STRONG_BUY"      # +0.6 to +1.0: strong conviction to hold/add


class TimeWindow(str, Enum):
    """The 4 tactical timing windows."""
    IMMEDIATE = "IMMEDIATE"     # Next 1-3 trading days
    SHORT_TERM = "SHORT_TERM"   # Next 1-2 weeks
    MEDIUM_TERM = "MEDIUM_TERM" # Next 2-4 weeks
    EXTENDED = "EXTENDED"        # Next 1-3 months


# ─── Lens Weights (Grok Expert-mode, cross-AI reviewed) ─────────────────────

LENS_WEIGHTS: dict[LensName, float] = {
    LensName.MACRO: 0.35,
    LensName.BTC_ONCHAIN: 0.12,
    LensName.CREDIT_LIQUIDITY: 0.10,
    LensName.FUNDAMENTAL: 0.15,
    LensName.TECHNICAL: 0.12,
    LensName.SENTIMENT: 0.09,
    LensName.GEOPOLITICAL: 0.07,
}

# Concordance thresholds (CFA + all 3 AIs unanimous)
CONCORDANCE_THRESHOLD_NORMAL = 4     # ≥4/7 in NORMAL/RISK_ON
CONCORDANCE_THRESHOLD_CAUTIOUS = 5   # ≥5/7 in TURBULENCE
TOTAL_LENSES = 7


# ─── LensResult ─────────────────────────────────────────────────────────────

@dataclass
class HoldingSignal:
    """Per-ticker signal within a lens result."""
    ticker: str
    signal: float                    # -1.0 to +1.0
    direction: Direction
    confidence: float                # 0.0 to 1.0
    rationale: str                   # Human-readable explanation
    data_points: dict = field(default_factory=dict)  # Key metrics used


@dataclass
class LensResult:
    """Standardized output from any HORIZON analytical lens.

    Every lens MUST produce a LensResult. The synthesis engine depends on this contract.
    """
    lens_name: LensName
    timestamp: str                                 # ISO format, UTC
    signal: float                                  # Portfolio-level: -1.0 to +1.0
    direction: Direction                           # Categorical version of signal
    confidence: float                              # 0.0 to 1.0
    rationale: str                                 # Top-level explanation
    holding_signals: list[HoldingSignal] = field(default_factory=list)
    data_freshness_hours: float = 0.0              # How old is the data
    key_drivers: list[str] = field(default_factory=list)   # Top 3 drivers
    warnings: list[str] = field(default_factory=list)      # Data quality issues
    raw_data: dict = field(default_factory=dict)   # Full data for debugging

    @property
    def is_valid(self) -> bool:
        """A lens result is valid if it has a signal and confidence."""
        return -1.0 <= self.signal <= 1.0 and 0.0 <= self.confidence <= 1.0

    def direction_sign(self) -> int:
        """Returns -1 (sell), 0 (neutral), or +1 (buy) for concordance counting."""
        if self.signal < -0.2:
            return -1
        elif self.signal > 0.2:
            return 1
        return 0


# ─── Regime Gate Result ─────────────────────────────────────────────────────

@dataclass
class RegimeGateResult:
    """Output of the regime gate (Step 1 of hierarchical synthesis)."""
    regime: RegimeState
    gli_value: float
    gli_momentum: str                  # "RISING", "FLAT", "FALLING"
    regime_streak_days: int            # How many days in current regime
    gate_decision: GateDecision
    concordance_threshold: int         # 4 or 5 depending on gate decision
    rationale: str
    macro_lens_result: LensResult      # Full macro lens output (also the gate source)


# ─── Concordance Result ─────────────────────────────────────────────────────

@dataclass
class ConcordanceResult:
    """Output of the concordance check (Step 2 of hierarchical synthesis)."""
    total_lenses: int                  # How many lenses ran successfully
    agreeing_count: int                # How many agree on direction
    threshold: int                     # Required for action (4 or 5)
    passed: bool                       # agreeing_count >= threshold
    majority_direction: Direction      # Which direction the majority favors
    agreeing_lenses: list[LensName] = field(default_factory=list)
    dissenting_lenses: list[LensName] = field(default_factory=list)
    dissent_reasons: dict = field(default_factory=dict)  # {lens: reason}


# ─── Time Window Probability ────────────────────────────────────────────────

@dataclass
class WindowProbability:
    """Monte Carlo output for a single time window."""
    window: TimeWindow
    label: str                         # Human-readable, e.g. "Apr 7-11 (1wk)"
    p_optimal: float                   # Probability this window is best
    p_adverse: float                   # Probability of >5% loss if holding through
    expected_move_pct: float           # Expected portfolio move (%)
    var_95: float                      # Value at Risk, 95th percentile (%)
    var_99: float                      # Value at Risk, 99th percentile (%)
    percentiles: dict = field(default_factory=dict)  # {10: x, 25: x, 50: x, 75: x, 90: x}
    recommendation: str = ""           # e.g. "HOLD", "REDUCE 50%", "FULL EXIT"


@dataclass
class MonteCarloResult:
    """Full Monte Carlo probability engine output."""
    n_paths: int                       # Should be 10,000
    windows: list[WindowProbability] = field(default_factory=list)
    bayesian_prior: float = 0.5        # Historical base rate for favorable exit
    bayesian_posterior: float = 0.5    # Updated probability after signal concordance
    regime_used: RegimeState = RegimeState.NORMAL
    vol_model: str = "EGARCH"          # Volatility model used
    correlation_tsla_btc: float = 0.0  # Estimated TSLA-BTC correlation
    assumptions: list[str] = field(default_factory=list)  # Explicit model assumptions
    warnings: list[str] = field(default_factory=list)


# ─── Behavioral Bias Audit ──────────────────────────────────────────────────

@dataclass
class BiasDetection:
    """A single detected cognitive bias."""
    bias_name: str                     # e.g. "loss_aversion", "anchoring"
    detected: bool
    severity: str                      # "LOW", "MEDIUM", "HIGH"
    explanation: str                   # Why this bias was flagged
    confidence_discount: float         # 0.0 to 0.15 (max discount per bias)


@dataclass
class BiasAuditResult:
    """Output of the behavioral bias meta-layer (Step 5)."""
    biases_checked: int                # Should be 12 (CFA curriculum)
    biases_detected: list[BiasDetection] = field(default_factory=list)
    total_confidence_discount: float = 0.0  # Sum of discounts, capped at 0.30
    summary: str = ""                  # Human-readable summary

    @property
    def any_detected(self) -> bool:
        return len(self.biases_detected) > 0


# ─── Data Freshness ─────────────────────────────────────────────────────────

@dataclass
class FreshnessAssessment:
    """Data freshness evaluation with halflife decay (Gemini recommendation)."""
    oracle_age_hours: float            # Hours since last ORACLE run
    halflife_hours: float = 48.0       # Decay halflife
    freshness_factor: float = 1.0      # 0.5^(age/halflife), 0.0 to 1.0
    is_stale: bool = False             # True if factor < 0.25
    warning: str = ""                  # Human-readable warning if stale

    @staticmethod
    def compute(oracle_age_hours: float, halflife_hours: float = 48.0) -> "FreshnessAssessment":
        """Compute freshness factor using halflife decay."""
        factor = 0.5 ** (oracle_age_hours / halflife_hours) if halflife_hours > 0 else 0.0
        factor = max(0.0, min(1.0, factor))
        is_stale = factor < 0.25
        warning = ""
        if is_stale:
            warning = (
                f"STALE DATA WARNING: ORACLE data is {oracle_age_hours:.1f}h old "
                f"(freshness: {factor:.2f}). Run ORACLE before trusting this analysis."
            )
        elif factor < 0.50:
            warning = (
                f"Data aging: ORACLE data is {oracle_age_hours:.1f}h old "
                f"(freshness: {factor:.2f}). Consider refreshing."
            )
        return FreshnessAssessment(
            oracle_age_hours=oracle_age_hours,
            halflife_hours=halflife_hours,
            freshness_factor=factor,
            is_stale=is_stale,
            warning=warning,
        )


# ─── Full HORIZON Analysis Result ───────────────────────────────────────────

@dataclass
class HorizonAnalysis:
    """The complete output of a HORIZON tactical timing analysis.

    This is the top-level object that the orchestrator builds and
    the output formatter renders.
    """
    # Metadata
    question: str                              # The user's original question
    analysis_date: str                         # ISO date
    run_id: str                                # Unique identifier for this analysis

    # Step 1: Regime Gate
    regime_gate: Optional[RegimeGateResult] = None

    # Step 2: All lens results
    lens_results: dict = field(default_factory=dict)  # {LensName: LensResult}

    # Step 3: Concordance
    concordance: Optional[ConcordanceResult] = None

    # Step 4: Weighted synthesis
    composite_score: float = 0.0               # -1.0 to +1.0
    composite_direction: Direction = Direction.NEUTRAL

    # Step 5: Monte Carlo
    monte_carlo: Optional[MonteCarloResult] = None

    # Step 6: Bias audit
    bias_audit: Optional[BiasAuditResult] = None

    # Step 7: Freshness
    freshness: Optional[FreshnessAssessment] = None

    # Final confidence (after all adjustments)
    raw_confidence: float = 0.0                # From lens concordance
    bias_adjusted_confidence: float = 0.0      # After bias discount
    final_confidence: float = 0.0              # After freshness decay

    # Disclaimers
    disclaimers: list[str] = field(default_factory=lambda: [
        "This is a personal advisory intelligence tool. NOT financial advice.",
        "NOT client-facing. Probabilities are model estimates, not predictions.",
        "Past regime transitions do not guarantee future outcomes.",
        "Human judgment required for all final decisions.",
    ])

    def to_dict(self) -> dict:
        """Serialize to dict for JSON storage in soma.db horizon_analyses table."""
        import dataclasses
        def _convert(obj):
            if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
                return dataclasses.asdict(obj)
            if isinstance(obj, Enum):
                return obj.value
            if isinstance(obj, dict):
                return {str(k): _convert(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_convert(v) for v in obj]
            return obj
        return _convert(self)

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=2, default=str)
