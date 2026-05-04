#!/usr/bin/env python3
"""
HORIZON — Holistic Observation & Risk-Informed Zone of Optimal Navigation
Pipeline: SOMA/HORIZON | Module: SOMA

The main orchestrator. Runs the full 6-step tactical timing analysis:
    Step 1: Regime Gate (MacroLens)
    Step 2: All 7 lenses
    Step 3: Concordance + weighted synthesis
    Step 4: Monte Carlo probability engine (10,000 paths)
    Step 5: Behavioral bias audit (12 CFA biases)
    Step 6: Data freshness assessment + confidence chain

Usage (standalone):
    python3 ~/Desktop/DABEIBA/shared/soma/horizon.py "When to liquidate TSLA + MSTR?"

Usage (from soma_query.py):
    soma_query.py "horizon When to liquidate?"

Usage (from Python):
    from shared.soma.horizon import run_horizon
    analysis = run_horizon("When to liquidate TSLA + MSTR?")
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone
from typing import Optional

# Make shared package importable when run standalone
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from shared.soma.horizon_dataclasses import (
    Direction,
    FreshnessAssessment,
    HorizonAnalysis,
    LensName,
    LensResult,
    RegimeGateResult,
)
from shared.soma.horizon_synthesis import HorizonSynthesis
from shared.soma.horizon_monte_carlo import HorizonMonteCarlo
from shared.soma.horizon_bias_audit import HorizonBiasAudit
from shared.soma.horizon_output import HorizonOutputFormatter
from shared.soma.soma_bridge import SomaBridge

# Lenses
from shared.soma.horizon_lenses.macro_lens import MacroLens
from shared.soma.horizon_lenses.fundamental_lens import FundamentalLens
from shared.soma.horizon_lenses.technical_lens import TechnicalLens
from shared.soma.horizon_lenses.btc_onchain_lens import BtcOnchainLens
from shared.soma.horizon_lenses.credit_liquidity_lens import CreditLiquidityLens
from shared.soma.horizon_lenses.sentiment_lens import SentimentLens
from shared.soma.horizon_lenses.event_lens import EventLens


# ─── ANSI codes ───────────────────────────────────────────────────────
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RESET = "\033[0m"

# Default portfolio (from MANTIS current state)
_DEFAULT_WEIGHTS = {"TSLA": 0.168, "MSTR": 0.0617, "MM": 0.77}
_DEFAULT_TICKERS = ["TSLA", "MSTR"]
_MC_PATHS = 10000


def run_horizon(
    question: str,
    tickers: list[str] | None = None,
    portfolio_weights: dict[str, float] | None = None,
    db_path: str | None = None,
    web_context: dict | None = None,
    n_paths: int = _MC_PATHS,
    verbose: bool = True,
) -> HorizonAnalysis:
    """Run the full HORIZON tactical timing analysis.

    Args:
        question: The user's timing question.
        tickers: Portfolio tickers to analyze (default: TSLA, MSTR).
        portfolio_weights: Portfolio weights (default: TSLA 16.8%, MSTR 6.17%, MM 77%).
        db_path: Optional SOMA DB path override.
        web_context: Optional enriched data for lenses (on-chain, FRED, etc.)
        n_paths: Monte Carlo paths (default 10,000).
        verbose: Print progress to terminal.

    Returns:
        HorizonAnalysis — the complete analysis object.
    """
    tickers = [t.upper() for t in (tickers or _DEFAULT_TICKERS)]
    weights = portfolio_weights or _DEFAULT_WEIGHTS
    web_context = web_context or {}
    run_id = str(uuid.uuid4())[:8]
    analysis_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if verbose:
        print(f"\n{BOLD}{CYAN}{'=' * 60}{RESET}")
        print(f"{BOLD}  HORIZON — Timing & Signals{RESET}")
        print(f"{BOLD}{CYAN}{'=' * 60}{RESET}")
        print(f"  {DIM}Run: {run_id} | Date: {analysis_date}{RESET}")
        print(f"  {DIM}Question: {question[:60]}{RESET}\n")

    # ── Step 1: All 7 Lenses ────────────────────────────────────────
    if verbose:
        print(f"  {CYAN}[1/6]{RESET} Running 7 analytical lenses...")

    lens_results: dict[LensName, LensResult] = {}
    gate: Optional[RegimeGateResult] = None

    # 1a. Macro (also produces the regime gate)
    try:
        with MacroLens(db_path=db_path) as lens:
            lr, gate = lens.analyze(tickers=tickers)
        lens_results[LensName.MACRO] = lr
        if verbose:
            print(f"    MACRO:            {lr.signal:+.3f} ({lr.direction.value})")
    except Exception as e:
        if verbose:
            print(f"    MACRO:            {RED}ERROR{RESET} {e}")

    # 1b. Fundamental
    try:
        with FundamentalLens(db_path=db_path) as lens:
            lr = lens.analyze(tickers=tickers)
        lens_results[LensName.FUNDAMENTAL] = lr
        if verbose:
            print(f"    FUNDAMENTAL:      {lr.signal:+.3f} ({lr.direction.value})")
    except Exception as e:
        if verbose:
            print(f"    FUNDAMENTAL:      {RED}ERROR{RESET} {e}")

    # 1c. Technical
    try:
        with TechnicalLens() as lens:
            lr = lens.analyze(tickers=tickers)
        lens_results[LensName.TECHNICAL] = lr
        if verbose:
            print(f"    TECHNICAL:        {lr.signal:+.3f} ({lr.direction.value})")
    except Exception as e:
        if verbose:
            print(f"    TECHNICAL:        {RED}ERROR{RESET} {e}")

    # 1d. BTC On-Chain
    try:
        with BtcOnchainLens() as lens:
            lr = lens.analyze(tickers=tickers, web_context=web_context.get("btc_onchain"))
        lens_results[LensName.BTC_ONCHAIN] = lr
        if verbose:
            print(f"    BTC_ONCHAIN:      {lr.signal:+.3f} ({lr.direction.value})")
    except Exception as e:
        if verbose:
            print(f"    BTC_ONCHAIN:      {RED}ERROR{RESET} {e}")

    # 1e. Credit/Liquidity
    try:
        with CreditLiquidityLens() as lens:
            lr = lens.analyze(tickers=tickers, web_context=web_context.get("credit"))
        lens_results[LensName.CREDIT_LIQUIDITY] = lr
        if verbose:
            print(f"    CREDIT_LIQUIDITY: {lr.signal:+.3f} ({lr.direction.value})")
    except Exception as e:
        if verbose:
            print(f"    CREDIT_LIQUIDITY: {RED}ERROR{RESET} {e}")

    # 1f. Sentiment
    try:
        with SentimentLens(db_path=db_path) as lens:
            lr = lens.analyze(tickers=tickers, web_context=web_context.get("sentiment"))
        lens_results[LensName.SENTIMENT] = lr
        if verbose:
            print(f"    SENTIMENT:        {lr.signal:+.3f} ({lr.direction.value})")
    except Exception as e:
        if verbose:
            print(f"    SENTIMENT:        {RED}ERROR{RESET} {e}")

    # 1g. Event/Geopolitical
    try:
        with EventLens(db_path=db_path) as lens:
            lr = lens.analyze(tickers=tickers, web_context=web_context.get("events"))
        lens_results[LensName.GEOPOLITICAL] = lr
        if verbose:
            print(f"    GEOPOLITICAL:     {lr.signal:+.3f} ({lr.direction.value})")
    except Exception as e:
        if verbose:
            print(f"    GEOPOLITICAL:     {RED}ERROR{RESET} {e}")

    if verbose:
        print(f"    {GREEN}{len(lens_results)}/7 lenses operational{RESET}")

    # Bail if no gate (critical failure)
    if gate is None:
        if verbose:
            print(f"\n  {RED}FATAL: Macro lens failed — cannot proceed without regime gate.{RESET}")
        return HorizonAnalysis(
            question=question,
            analysis_date=analysis_date,
            run_id=run_id,
            lens_results=lens_results,
        )

    # ── Step 2: Synthesis ────────────────────────────────────────────
    if verbose:
        print(f"\n  {CYAN}[2/6]{RESET} Running hierarchical synthesis...")

    synth = HorizonSynthesis()
    concordance, composite, direction, raw_conf = synth.synthesize(
        lens_results, gate
    )

    if verbose:
        status = f"{GREEN}PASS{RESET}" if concordance.passed else f"{YELLOW}FAIL{RESET}"
        print(f"    Concordance: {concordance.agreeing_count}/{concordance.total_lenses} [{status}]")
        print(f"    Composite: {composite:+.3f} ({direction.value})")

    # ── Step 3: Monte Carlo ──────────────────────────────────────────
    if verbose:
        print(f"\n  {CYAN}[3/6]{RESET} Running Monte Carlo ({n_paths:,} paths)...")

    mc = HorizonMonteCarlo(n_paths=n_paths, seed=None)
    mc_result = mc.run(
        gate=gate,
        concordance=concordance,
        composite_score=composite,
        portfolio_weights=weights,
    )

    if verbose:
        print(f"    Bayesian: {mc_result.bayesian_prior:.0%} → {mc_result.bayesian_posterior:.0%}")
        for w in mc_result.windows:
            print(f"    {w.label:<30} P(opt)={w.p_optimal:.0%}  E={w.expected_move_pct:+.1f}%")

    # ── Step 4: Bias Audit ───────────────────────────────────────────
    if verbose:
        print(f"\n  {CYAN}[4/6]{RESET} Running behavioral bias audit...")

    audit = HorizonBiasAudit()
    bias_result = audit.run(
        lens_results=lens_results,
        concordance=concordance,
        composite_score=composite,
        gate=gate,
        monte_carlo=mc_result,
        question=question,
    )

    if verbose:
        if bias_result.any_detected:
            names = [b.bias_name for b in bias_result.biases_detected]
            print(f"    Detected: {', '.join(names)} (discount: -{bias_result.total_confidence_discount:.0%})")
        else:
            print(f"    {GREEN}No biases detected{RESET}")

    # ── Step 5: Freshness ────────────────────────────────────────────
    if verbose:
        print(f"\n  {CYAN}[5/6]{RESET} Assessing data freshness...")

    oracle_age = _get_oracle_age(db_path)
    freshness = FreshnessAssessment.compute(oracle_age)

    if verbose:
        color = RED if freshness.is_stale else (YELLOW if freshness.freshness_factor < 0.5 else GREEN)
        print(f"    ORACLE age: {oracle_age:.1f}h | Freshness: {color}{freshness.freshness_factor:.2f}{RESET}")

    # ── Step 6: Assemble + confidence chain ──────────────────────────
    if verbose:
        print(f"\n  {CYAN}[6/6]{RESET} Assembling final analysis...")

    bias_adj_conf = max(0.0, raw_conf - bias_result.total_confidence_discount)
    final_conf = max(0.0, bias_adj_conf * freshness.freshness_factor)

    analysis = HorizonAnalysis(
        question=question,
        analysis_date=analysis_date,
        run_id=run_id,
        regime_gate=gate,
        lens_results=lens_results,
        concordance=concordance,
        composite_score=composite,
        composite_direction=direction,
        monte_carlo=mc_result,
        bias_audit=bias_result,
        freshness=freshness,
        raw_confidence=raw_conf,
        bias_adjusted_confidence=bias_adj_conf,
        final_confidence=final_conf,
    )

    # ── Store in SOMA ────────────────────────────────────────────────
    _store_analysis(analysis, db_path, verbose)

    if verbose:
        print(f"\n  {GREEN}{BOLD}HORIZON analysis complete.{RESET}")
        print(f"  Confidence chain: {raw_conf:.0%} → {bias_adj_conf:.0%} (bias) → {final_conf:.0%} (fresh)\n")

    return analysis


# ── Helpers ──────────────────────────────────────────────────────────

def _get_oracle_age(db_path: str | None) -> float:
    """Get ORACLE data age in hours."""
    try:
        with SomaBridge(db_path=db_path) as bridge:
            _, age = bridge.is_fresh("regime_history", max_age_hours=9999)
        return age if age != float("inf") else 9999.0
    except Exception:
        return 9999.0


def _store_analysis(analysis: HorizonAnalysis, db_path: str | None, verbose: bool):
    """Store the analysis in soma.db horizon_analyses table."""
    try:
        with SomaBridge(db_path=db_path) as bridge:
            # Ensure the table exists (idempotent)
            bridge.conn.execute("""
                CREATE TABLE IF NOT EXISTS horizon_analyses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    analysis_date TEXT NOT NULL,
                    question TEXT,
                    composite_score REAL,
                    composite_direction TEXT,
                    concordance_passed INTEGER,
                    concordance_count INTEGER,
                    regime TEXT,
                    gli_value REAL,
                    raw_confidence REAL,
                    bias_adjusted_confidence REAL,
                    final_confidence REAL,
                    n_lenses INTEGER,
                    n_biases_detected INTEGER,
                    freshness_factor REAL,
                    full_json TEXT,
                    write_timestamp TEXT
                )
            """)
            bridge.conn.execute(
                """INSERT INTO horizon_analyses
                   (run_id, analysis_date, question, composite_score,
                    composite_direction, concordance_passed, concordance_count,
                    regime, gli_value, raw_confidence, bias_adjusted_confidence,
                    final_confidence, n_lenses, n_biases_detected,
                    freshness_factor, full_json, write_timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    analysis.run_id,
                    analysis.analysis_date,
                    analysis.question,
                    analysis.composite_score,
                    analysis.composite_direction.value,
                    1 if analysis.concordance and analysis.concordance.passed else 0,
                    analysis.concordance.agreeing_count if analysis.concordance else 0,
                    analysis.regime_gate.regime.value if analysis.regime_gate else None,
                    analysis.regime_gate.gli_value if analysis.regime_gate else None,
                    analysis.raw_confidence,
                    analysis.bias_adjusted_confidence,
                    analysis.final_confidence,
                    len(analysis.lens_results),
                    len(analysis.bias_audit.biases_detected) if analysis.bias_audit else 0,
                    analysis.freshness.freshness_factor if analysis.freshness else None,
                    analysis.to_json(),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            bridge.conn.commit()
            if verbose:
                print(f"  {DIM}Stored in soma.db (horizon_analyses, run={analysis.run_id}){RESET}")
    except Exception as e:
        if verbose:
            print(f"  {YELLOW}Warning: could not store analysis: {e}{RESET}")


def print_report(analysis: HorizonAnalysis):
    """Print the formatted HORIZON report."""
    formatter = HorizonOutputFormatter()
    print(formatter.render(analysis))


# ── CLI entry point ──────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print(f"\n  {BOLD}HORIZON — Timing & Signals{RESET}")
        print(f"  Usage: python3 horizon.py \"When should I liquidate TSLA + MSTR?\"")
        print(f"  Or:    soma_query.py \"horizon When to liquidate?\"")
        return

    question = " ".join(sys.argv[1:])
    analysis = run_horizon(question, verbose=True)
    print()
    print_report(analysis)


if __name__ == "__main__":
    main()
