"""
SOMA-INTEL Phase 7 §D.3 — Bayesian Update (pure functions, no I/O)

Implements the locked Bayesian math from the D.3.A brief:

  log_posterior = log_prior + Σ LLR_i
  posterior     = sigmoid(log_posterior) = scipy.special.expit(log_posterior)

LLR_COEFFICIENTS are locked starting points. D.3.B backtest will tune them.

All functions are pure (no DB, no network). Deterministic for given inputs.
"""

from __future__ import annotations

import math
from typing import Optional

# ── Locked LLR coefficients (D.3.B may tune; do not change here) ─────────────
# Format: (coefficient, cap_magnitude)
# cap_magnitude: absolute z-score is clipped to this before applying coefficient.

LLR_COEFFICIENTS: dict[str, tuple[float, float]] = {
    "macro":      (0.6, 3.0),   # max(|yield_curve_z|, |vix_term_z|)
    "sentiment":  (0.4, 2.5),   # AAII bull-minus-bear z-score
    "cross_asset":(0.5, 2.5),   # correlation breakdown z-score
    "transcript": (0.3, 2.0),   # PRISM topic drift z-score
}

# Locked daily prior probability of a regime shift (§D.3)
PRIOR: float = 0.024  # ~6 regime shifts/year ≈ 0.024/day

# Trigger thresholds (§D.3 spec, locked)
WATCH_THRESHOLD: float = 0.40
IMMINENT_THRESHOLD: float = 0.60


def _llr_for_input(input_name: str, z: Optional[float]) -> float:
    """
    Compute log-likelihood-ratio for one input.

    If z is None (missing data), returns 0.0 (neutral — no evidence update).
    The cap is applied before the coefficient, so extreme z values don't dominate.

    Args:
        input_name: One of 'macro', 'sentiment', 'cross_asset', 'transcript'.
        z: z-score for this input, or None if unavailable.

    Returns:
        LLR value (float). Always finite.
    """
    if z is None:
        return 0.0

    coef, cap = LLR_COEFFICIENTS[input_name]
    z_clipped = max(-cap, min(cap, abs(z)))   # use magnitude; sign handled by coef
    return coef * z_clipped


def compute_log_likelihood_ratios(
    macro_z: Optional[float],
    sentiment_z: Optional[float],
    cross_asset_z: Optional[float],
    transcript_drift_z: Optional[float],
) -> dict:
    """
    Compute per-input log-likelihood-ratios and collect missing input names.

    All inputs use magnitude (|z|) — higher deviation from normal in either
    direction raises the probability of a regime shift.

    Returns:
        {
          "llr_macro":       float,
          "llr_sentiment":   float,
          "llr_cross_asset": float,
          "llr_transcript":  float,
          "missing_inputs":  list[str],  # names of inputs that were None
        }
    """
    missing: list[str] = []

    if macro_z is None:
        missing.append("macro")
    if sentiment_z is None:
        missing.append("sentiment")
    if cross_asset_z is None:
        missing.append("cross_asset")
    if transcript_drift_z is None:
        missing.append("transcript")

    return {
        "llr_macro":       _llr_for_input("macro",       macro_z),
        "llr_sentiment":   _llr_for_input("sentiment",   sentiment_z),
        "llr_cross_asset": _llr_for_input("cross_asset", cross_asset_z),
        "llr_transcript":  _llr_for_input("transcript",  transcript_drift_z),
        "missing_inputs":  missing,
    }


def compute_posterior(prior: float, llrs: dict) -> tuple[float, float]:
    """
    Compute log-posterior and posterior probability using naive-Bayes update.

    Naive-Bayes assumption: inputs are conditionally independent given the
    shift/no-shift state. Documented as a v1 simplification; revisit if
    D.3.B backtest reveals significant correlation issues.

    Args:
        prior: Daily base rate of regime shift (0.024).
        llrs:  Dict returned by compute_log_likelihood_ratios.

    Returns:
        (log_posterior, posterior)
        - log_posterior: log-odds form (can be any real number).
        - posterior: sigmoid(log_posterior) in (0.0, 1.0).
    """
    log_prior = math.log(prior / (1.0 - prior))  # log-odds form

    sum_llr = (
        llrs["llr_macro"]
        + llrs["llr_sentiment"]
        + llrs["llr_cross_asset"]
        + llrs["llr_transcript"]
    )

    log_posterior = log_prior + sum_llr

    # sigmoid via scipy for numerical stability; fall back to manual if unavailable
    try:
        from scipy.special import expit
        posterior = float(expit(log_posterior))
    except ImportError:
        # Manual sigmoid — numerically stable for large negatives
        if log_posterior >= 0:
            posterior = 1.0 / (1.0 + math.exp(-log_posterior))
        else:
            e = math.exp(log_posterior)
            posterior = e / (1.0 + e)

    return log_posterior, posterior


def classify_trigger(posterior: float) -> str:
    """
    Classify the trigger state based on posterior probability.

    Thresholds are locked (§D.3 spec). D.3.C wires these to live alerts.
    D.3.A stores the state but fires no external triggers.

    Returns:
        'imminent' if posterior > 0.60
        'watch'    if posterior > 0.40
        'none'     otherwise
    """
    if posterior > IMMINENT_THRESHOLD:
        return "imminent"
    if posterior > WATCH_THRESHOLD:
        return "watch"
    return "none"
