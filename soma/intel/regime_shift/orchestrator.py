"""
SOMA-INTEL Phase 7 §D.3 — Daily Regime-Shift Bayesian Orchestrator

Ties ingestors → Bayesian update → DB persistence into one idempotent call.

Entry point:
    run_daily(date, store, dry_run=False, force=False) -> dict

Capability gate:
    If 'regime_shift_bayesian' is disabled, logs and returns early.
    No DB writes occur while the capability is disabled.

Idempotency:
    Skips re-computation if a posterior row already exists for the target date.
    Pass force=True to overwrite (used in smoke tests and D.3.B calibration).
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from .bayesian import PRIOR, compute_log_likelihood_ratios, compute_posterior, classify_trigger
from .ingestors import (
    ingest_macro_z,
    ingest_sentiment_z,
    ingest_cross_asset_z,
    ingest_transcript_drift_z,
)

log = logging.getLogger(__name__)


def run_daily(
    target_date: str,
    store,
    dry_run: bool = False,
    force: bool = False,
) -> dict:
    """
    Compute and persist the regime-shift Bayesian posterior for target_date.

    Args:
        target_date: ISO 8601 date string, e.g. '2024-08-15'.
        store:       IntelStore instance (must be inside a `with` block).
        dry_run:     If True, compute but do not write to DB.
        force:       If True, overwrite an existing posterior for this date.

    Returns:
        {
          "ts":            str,   # target_date
          "prior":         float,
          "posterior":     float,
          "log_posterior": float,
          "trigger_state": str,
          "missing_inputs": list[str],
          "llr_macro":     float,
          "llr_sentiment": float,
          "llr_cross_asset": float,
          "llr_transcript": float,
          "written":       bool,   # False if dry_run or skipped
          "skipped":       bool,   # True if idempotent skip
          "disabled":      bool,   # True if capability was off
        }
    """
    # ── Capability gate ─────────────────────────────────────────────────────────
    if not store.is_capability_enabled("regime_shift_bayesian"):
        log.info("regime_shift_bayesian capability disabled — skipping %s", target_date)
        return {
            "ts": target_date, "prior": PRIOR, "posterior": None,
            "log_posterior": None, "trigger_state": None,
            "missing_inputs": [], "llr_macro": 0.0, "llr_sentiment": 0.0,
            "llr_cross_asset": 0.0, "llr_transcript": 0.0,
            "written": False, "skipped": False, "disabled": True,
        }

    # ── Idempotency check ───────────────────────────────────────────────────────
    if not force and store.has_regime_shift_posterior(target_date):
        log.info(
            "regime_shift_bayesian: posterior already exists for %s — skipping (use force=True to reingest)",
            target_date,
        )
        existing = store.get_regime_shift_posterior(target_date)
        return {**existing, "written": False, "skipped": True, "disabled": False}

    # ── Ingest likelihood inputs ─────────────────────────────────────────────────
    macro_z           = ingest_macro_z(target_date, store)
    sentiment_z       = ingest_sentiment_z(target_date, store)
    cross_asset_z     = ingest_cross_asset_z(target_date, store)
    transcript_drift_z = ingest_transcript_drift_z(target_date, store)

    for name, val in [
        ("macro", macro_z),
        ("sentiment", sentiment_z),
        ("cross_asset", cross_asset_z),
        ("transcript", transcript_drift_z),
    ]:
        if val is None:
            log.warning(
                "regime_shift_bayesian(%s): %s input unavailable — neutralized (LLR=0)",
                target_date, name,
            )

    # ── Bayesian update ─────────────────────────────────────────────────────────
    llrs = compute_log_likelihood_ratios(
        macro_z, sentiment_z, cross_asset_z, transcript_drift_z
    )
    log_posterior, posterior = compute_posterior(PRIOR, llrs)
    trigger_state = classify_trigger(posterior)

    source_notes = json.dumps({
        "macro":       "soma_intel_regime.features (y2y10_spread, vix_delta_5d)",
        "sentiment":   "D.3.A.2 follow-on — AAII not yet wired",
        "cross_asset": "cache-first (oracle/cache/cross_asset_prices.csv), Yahoo Finance fallback on miss (SPY, TLT, GLD, DX-Y.NYB)",
        "transcript":  "D.3.A.2 follow-on — PRISM drift not yet wired",
    })

    log.info(
        "regime_shift_bayesian(%s): posterior=%.4f  trigger=%s  missing=%s",
        target_date, posterior, trigger_state, llrs["missing_inputs"],
    )

    result = {
        "ts":              target_date,
        "prior":           PRIOR,
        "posterior":       posterior,
        "log_posterior":   log_posterior,
        "trigger_state":   trigger_state,
        "missing_inputs":  llrs["missing_inputs"],
        "llr_macro":       llrs["llr_macro"],
        "llr_sentiment":   llrs["llr_sentiment"],
        "llr_cross_asset": llrs["llr_cross_asset"],
        "llr_transcript":  llrs["llr_transcript"],
        "written":         False,
        "skipped":         False,
        "disabled":        False,
    }

    # ── Persist ─────────────────────────────────────────────────────────────────
    if not dry_run:
        store.insert_regime_shift_likelihood(
            ts=target_date,
            macro_z=macro_z,
            sentiment_z=sentiment_z,
            cross_asset_z=cross_asset_z,
            transcript_drift_z=transcript_drift_z,
            source_notes=source_notes,
        )
        store.insert_regime_shift_posterior(
            ts=target_date,
            prior=PRIOR,
            log_posterior=log_posterior,
            posterior=posterior,
            llr_macro=llrs["llr_macro"],
            llr_sentiment=llrs["llr_sentiment"],
            llr_cross_asset=llrs["llr_cross_asset"],
            llr_transcript=llrs["llr_transcript"],
            trigger_state=trigger_state,
            missing_inputs=llrs["missing_inputs"],
        )
        result["written"] = True
        log.info("regime_shift_bayesian(%s): persisted to DB.", target_date)
    else:
        log.info("regime_shift_bayesian(%s): dry_run — not persisted.", target_date)

    return result
