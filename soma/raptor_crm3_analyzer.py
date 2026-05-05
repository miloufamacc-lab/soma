"""
RAPTOR — CRM3 Value Proposition Engine (Phase 4)

Calculates the embedded fee drag in a prospect's current holdings and
produces a side-by-side comparison showing potential savings when moving
to a direct-equity / lower-cost model.

"CRM3" refers to the CRM2 follow-on reforms (cost disclosure requirements)
that make embedded fees visible to Canadian investors. This tool turns that
mandatory disclosure into a conversion opportunity.

Usage:
    from soma.soma_bridge import SomaBridge
    from soma.raptor_crm3_analyzer import CRM3Analyzer, seed_fund_mers

    with SomaBridge() as bridge:
        seed_fund_mers(bridge)          # idempotent — loads common MER data
        analyzer = CRM3Analyzer(bridge)

        # Prospect's current holdings
        current = [
            {"fund_name": "RBC Canadian Equity Fund", "ticker": "RBF556",
             "weight": 0.60, "mer": 2.35},
            {"fund_name": "RBC Balanced Fund", "ticker": "RBF256",
             "weight": 0.40, "mer": 2.10},
        ]

        # Proposed direct-equity / lower-cost model
        proposed = [
            {"fund_name": "iShares Core S&P/TSX Capped Composite", "ticker": "XIC",
             "weight": 0.50, "mer": 0.06},
            {"fund_name": "Advisory management fee", "ticker": None,
             "weight": 1.00, "mer": 1.00},   # 1% advisor fee
        ]

        comparison = analyzer.compare_to_raptor_model(current, proposed)
        report     = analyzer.generate_crm3_report(prospect_id, comparison, aum_estimate=1_500_000)
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from typing import Any

# ── Modelling assumptions ─────────────────────────────────────────────────────
ASSUMED_GROSS_RETURN = 0.06     # 6% annual gross return — standard planning assumption
PROJECTION_YEARS     = (10, 20, 30)
_AUM_REFERENCE       = 1_000_000.0   # $1M reference for per-unit drag calculations

_DISCLAIMER_EN = (
    "IMPORTANT DISCLOSURES: This analysis is for illustrative purposes only and does "
    "not constitute investment advice. The fee comparison assumes a {return_pct}% annual "
    "gross return before fees, applied consistently over the projection period. "
    "Actual returns will vary and past performance does not guarantee future results. "
    "MER figures shown are approximate and sourced from publicly available fund facts. "
    "All dollar amounts are estimates. This document has not been reviewed by the AMF "
    "and is intended solely for the named prospect."
)

_DISCLAIMER_FR = (
    "MISES EN GARDE IMPORTANTES : Cette analyse est fournie à titre indicatif seulement "
    "et ne constitue pas un conseil en placement. La comparaison des frais suppose un "
    "rendement brut annuel de {return_pct} % avant frais, appliqué de manière uniforme "
    "sur la période de projection. Les rendements réels varieront et les rendements "
    "passés ne garantissent pas les résultats futurs. Les ratios de frais de gestion "
    "présentés sont approximatifs. Ce document n'a pas été examiné par l'AMF et est "
    "destiné uniquement au prospect identifié."
)


# ── Core math ─────────────────────────────────────────────────────────────────

def _normalize_weights(holdings: list[dict]) -> list[dict]:
    """Ensure weights sum to 1.0. If any weight > 1.5, assume they are percentages."""
    if not holdings:
        return []
    weights = [float(h.get("weight", 0)) for h in holdings]
    # Auto-detect percentage input (e.g. 60.0 instead of 0.60)
    if any(w > 1.5 for w in weights):
        weights = [w / 100.0 for w in weights]
    total = sum(weights)
    if total <= 0:
        raise ValueError("Holdings weights sum to zero — cannot normalize.")
    scale = 1.0 / total
    normalized = []
    for h, w in zip(holdings, weights):
        normalized.append({**h, "weight": round(w * scale, 6)})
    return normalized


def _weighted_mer(holdings: list[dict]) -> float:
    """Portfolio-weighted MER (%). Holdings must already be normalized."""
    return sum(float(h["weight"]) * float(h["mer"]) for h in holdings)


def _compound_drag(aum: float, mer_pct: float, years: int,
                   gross_return: float = ASSUMED_GROSS_RETURN) -> float:
    """Dollar fee drag over N years on an AUM starting value.

    mer_pct:      MER as a percentage, e.g. 2.0 for 2%
    gross_return: annual gross return assumed (default 6%)

    formula: aum × ((1+r)^N − (1+r−f)^N)
    where f = mer_pct / 100, r = gross_return
    """
    f = mer_pct / 100.0
    r = gross_return
    return aum * ((1 + r) ** years - (1 + r - f) ** years)


# ── Analyzer ──────────────────────────────────────────────────────────────────

class CRM3Analyzer:
    """Fee drag calculator and CRM3 value proposition report generator.

    CRM3 (Cost Disclosure Reform phase 3) makes embedded fund fees visible to
    investors. This engine turns that mandatory disclosure into a structured
    comparison showing dollar savings of moving to a lower-cost model.
    """

    def __init__(self, bridge):
        self.bridge = bridge

    def ingest_prospect_holdings(self, holdings: list[dict]) -> dict:
        """Analyze a prospect's current holdings for fee drag.

        Each holding dict: {fund_name, ticker (optional), weight, mer}
          weight: fraction (0.60) or percentage (60.0) — auto-detected
          mer:    Management Expense Ratio as %, e.g. 2.35 for 2.35%

        Returns:
            holdings         — normalized list with weights summing to 1.0
            weighted_mer     — portfolio weighted average MER (%)
            drag_per_1M_10yr — dollar drag on $1M over 10 years ($)
            drag_per_1M_20yr — dollar drag on $1M over 20 years ($)
            drag_per_1M_30yr — dollar drag on $1M over 30 years ($)
            gross_return_assumption — float (0.06)
        """
        if not holdings:
            raise ValueError("Holdings list cannot be empty.")

        norm = _normalize_weights(holdings)
        w_mer = _weighted_mer(norm)

        return {
            "holdings":               norm,
            "weighted_mer":           round(w_mer, 4),
            "drag_per_1M_10yr":       round(_compound_drag(_AUM_REFERENCE, w_mer, 10), 2),
            "drag_per_1M_20yr":       round(_compound_drag(_AUM_REFERENCE, w_mer, 20), 2),
            "drag_per_1M_30yr":       round(_compound_drag(_AUM_REFERENCE, w_mer, 30), 2),
            "gross_return_assumption": ASSUMED_GROSS_RETURN,
        }

    def compare_to_raptor_model(
        self,
        prospect_holdings: list[dict],
        proposed_holdings: list[dict],
    ) -> dict:
        """Side-by-side cost comparison between current and proposed structure.

        Returns:
            current              — ingest result for prospect_holdings
            proposed             — ingest result for proposed_holdings
            fee_savings_pct      — annual MER savings (current_mer − proposed_mer), %
            dollar_savings_10yr  — savings per $1M over 10 years ($)
            dollar_savings_20yr  — savings per $1M over 20 years ($)
            dollar_savings_30yr  — savings per $1M over 30 years ($)
            gross_return_assumption — float
        """
        current  = self.ingest_prospect_holdings(prospect_holdings)
        proposed = self.ingest_prospect_holdings(proposed_holdings)

        savings_pct = current["weighted_mer"] - proposed["weighted_mer"]

        dollar_savings: dict[str, float] = {}
        for yr in PROJECTION_YEARS:
            drag_curr = _compound_drag(_AUM_REFERENCE, current["weighted_mer"],  yr)
            drag_prop = _compound_drag(_AUM_REFERENCE, proposed["weighted_mer"], yr)
            dollar_savings[f"{yr}yr"] = round(drag_curr - drag_prop, 2)

        return {
            "current":                current,
            "proposed":               proposed,
            "fee_savings_pct":        round(savings_pct, 4),
            "dollar_savings_10yr":    dollar_savings["10yr"],
            "dollar_savings_20yr":    dollar_savings["20yr"],
            "dollar_savings_30yr":    dollar_savings["30yr"],
            "gross_return_assumption": ASSUMED_GROSS_RETURN,
        }

    def generate_crm3_report(
        self,
        prospect_id: str,
        comparison: dict,
        aum_estimate: float = _AUM_REFERENCE,
        language: str = "EN",
    ) -> str:
        """Generate a markdown CRM3 value proposition report.

        The report is compliant (AMF-safe disclaimers, no performance guarantees)
        and suitable for rendering via CIPHER or printing as a client-facing document.

        aum_estimate: prospect's estimated AUM for scaling dollar figures
        language:     "EN" or "FR"
        """
        prospect = self.bridge.get_prospect(prospect_id) if prospect_id else None
        name = (
            (prospect.get("display_name") or
             f"{prospect.get('first_name', '')} {prospect.get('last_name', '')}".strip())
            if prospect else "Prospect"
        )

        cur     = comparison["current"]
        prop    = comparison["proposed"]
        savings = comparison["fee_savings_pct"]
        scale   = aum_estimate / _AUM_REFERENCE   # scale savings to actual AUM

        s10 = round(comparison["dollar_savings_10yr"] * scale, 0)
        s20 = round(comparison["dollar_savings_20yr"] * scale, 0)
        s30 = round(comparison["dollar_savings_30yr"] * scale, 0)
        ret_pct = round(ASSUMED_GROSS_RETURN * 100, 0)

        disclaimer = (_DISCLAIMER_FR if language.upper() == "FR" else _DISCLAIMER_EN)
        disclaimer = disclaimer.format(return_pct=int(ret_pct))

        aum_fmt = f"${aum_estimate:,.0f}"
        cur_mer_fmt  = f"{cur['weighted_mer']:.2f}%"
        prop_mer_fmt = f"{prop['weighted_mer']:.2f}%"
        sav_mer_fmt  = f"{savings:.2f}%"

        lines = [
            f"# CRM3 Fee Analysis — {name}",
            "",
            f"**Estimated Assets Under Management:** {aum_fmt}  ",
            f"**Analysis Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
            "",
            "---",
            "",
            "## Current Portfolio — Fee Structure",
            "",
            f"| Fund | Weight | MER |",
            f"|------|--------|-----|",
        ]
        for h in cur["holdings"]:
            lines.append(
                f"| {h['fund_name']} | {h['weight']*100:.1f}% | {h['mer']:.2f}% |"
            )
        lines += [
            "",
            f"**Weighted Average MER: {cur_mer_fmt}**",
            "",
            f"Estimated fee drag on {aum_fmt}:",
            f"- 10 years: **${_compound_drag(aum_estimate, cur['weighted_mer'], 10):,.0f}**",
            f"- 20 years: **${_compound_drag(aum_estimate, cur['weighted_mer'], 20):,.0f}**",
            f"- 30 years: **${_compound_drag(aum_estimate, cur['weighted_mer'], 30):,.0f}**",
            "",
            "---",
            "",
            "## Proposed Structure — Fee Structure",
            "",
            f"| Component | Weight | Annual Cost |",
            f"|-----------|--------|-------------|",
        ]
        for h in prop["holdings"]:
            lines.append(
                f"| {h['fund_name']} | {h['weight']*100:.1f}% | {h['mer']:.2f}% |"
            )
        lines += [
            "",
            f"**Weighted Average Cost: {prop_mer_fmt}**",
            "",
            f"Estimated fee drag on {aum_fmt}:",
            f"- 10 years: **${_compound_drag(aum_estimate, prop['weighted_mer'], 10):,.0f}**",
            f"- 20 years: **${_compound_drag(aum_estimate, prop['weighted_mer'], 20):,.0f}**",
            f"- 30 years: **${_compound_drag(aum_estimate, prop['weighted_mer'], 30):,.0f}**",
            "",
            "---",
            "",
            "## Potential Savings",
            "",
            f"**Annual fee reduction: {sav_mer_fmt} per year**",
            "",
            f"Estimated cumulative savings on {aum_fmt}:",
            "",
            "| Horizon | Estimated Savings |",
            "|---------|-------------------|",
            f"| 10 years | **${s10:,.0f}** |",
            f"| 20 years | **${s20:,.0f}** |",
            f"| 30 years | **${s30:,.0f}** |",
            "",
            "*Savings represent the difference in fee drag between the current and proposed "
            "structures, not guaranteed returns or actual portfolio outcomes.*",
            "",
            "---",
            "",
            f"*{disclaimer}*",
        ]

        return "\n".join(lines)


# ── Fund MER seed data ────────────────────────────────────────────────────────

_SEED_FUND_MERS: list[dict] = [
    # ── RBC Royal Bank (high MER mutual funds) ───────────────────
    {"ticker": "RBF556",  "fund_name": "RBC Canadian Equity Fund",              "mer": 2.35, "fund_family": "RBC",      "fund_type": "mutual_fund", "currency": "CAD"},
    {"ticker": "RBF256",  "fund_name": "RBC Balanced Fund",                     "mer": 2.10, "fund_family": "RBC",      "fund_type": "mutual_fund", "currency": "CAD"},
    {"ticker": "RBF609",  "fund_name": "RBC Canadian Bond Fund",                "mer": 1.48, "fund_family": "RBC",      "fund_type": "mutual_fund", "currency": "CAD"},
    {"ticker": "RBF266",  "fund_name": "RBC North American Growth Fund",        "mer": 2.32, "fund_family": "RBC",      "fund_type": "mutual_fund", "currency": "CAD"},
    # ── TD Bank ──────────────────────────────────────────────────
    {"ticker": "TDB900",  "fund_name": "TD Canadian Index Fund — e-Series",     "mer": 0.33, "fund_family": "TD",       "fund_type": "mutual_fund", "currency": "CAD"},
    {"ticker": "TDB902",  "fund_name": "TD US Index Fund — e-Series",           "mer": 0.35, "fund_family": "TD",       "fund_type": "mutual_fund", "currency": "CAD"},
    {"ticker": "TDB909",  "fund_name": "TD International Index Fund — e-Series","mer": 0.50, "fund_family": "TD",       "fund_type": "mutual_fund", "currency": "CAD"},
    {"ticker": "TDB966",  "fund_name": "TD Canadian Bond Index Fund — e-Series","mer": 0.51, "fund_family": "TD",       "fund_type": "mutual_fund", "currency": "CAD"},
    # ── Fidelity ─────────────────────────────────────────────────
    {"ticker": "FID220",  "fund_name": "Fidelity Canadian Asset Allocation",    "mer": 2.28, "fund_family": "Fidelity", "fund_type": "mutual_fund", "currency": "CAD"},
    {"ticker": "FID155",  "fund_name": "Fidelity Canadian Growth Company Fund", "mer": 2.41, "fund_family": "Fidelity", "fund_type": "mutual_fund", "currency": "CAD"},
    # ── iShares ETFs (BlackRock) ─────────────────────────────────
    {"ticker": "XIC",     "fund_name": "iShares Core S&P/TSX Capped Composite ETF", "mer": 0.06, "fund_family": "iShares", "fund_type": "etf", "currency": "CAD"},
    {"ticker": "XSP",     "fund_name": "iShares Core S&P 500 Index ETF (CAD-Hedged)", "mer": 0.10, "fund_family": "iShares", "fund_type": "etf", "currency": "CAD"},
    {"ticker": "XEF",     "fund_name": "iShares Core MSCI EAFE IMI Index ETF",  "mer": 0.22, "fund_family": "iShares", "fund_type": "etf", "currency": "CAD"},
    {"ticker": "XBB",     "fund_name": "iShares Core Canadian Universe Bond Index ETF", "mer": 0.10, "fund_family": "iShares", "fund_type": "etf", "currency": "CAD"},
    # ── BMO ETFs ─────────────────────────────────────────────────
    {"ticker": "ZCN",     "fund_name": "BMO S&P/TSX Capped Composite Index ETF","mer": 0.06, "fund_family": "BMO",      "fund_type": "etf", "currency": "CAD"},
    {"ticker": "ZSP",     "fund_name": "BMO S&P 500 Index ETF",                 "mer": 0.09, "fund_family": "BMO",      "fund_type": "etf", "currency": "CAD"},
    {"ticker": "ZAG",     "fund_name": "BMO Aggregate Bond Index ETF",          "mer": 0.09, "fund_family": "BMO",      "fund_type": "etf", "currency": "CAD"},
    # ── Vanguard Canada ──────────────────────────────────────────
    {"ticker": "VCN",     "fund_name": "Vanguard FTSE Canada All Cap Index ETF","mer": 0.05, "fund_family": "Vanguard", "fund_type": "etf", "currency": "CAD"},
    {"ticker": "VXC",     "fund_name": "Vanguard FTSE Global All Cap ex Canada Index ETF", "mer": 0.22, "fund_family": "Vanguard", "fund_type": "etf", "currency": "CAD"},
    # ── Segregated fund proxy ────────────────────────────────────
    {"ticker": None, "fund_name": "Typical Segregated Fund (Equity)",           "mer": 3.00, "fund_family": "Industry", "fund_type": "segregated", "currency": "CAD",
     "notes": "Approximate MER for typical Canadian equity segregated fund (includes insurance guarantee cost)"},
]


def seed_fund_mers(bridge) -> int:
    """Seed raptor_fund_mers with common Canadian fund data.

    Idempotent — uses ON CONFLICT(ticker) DO UPDATE in write_fund_mer().
    Returns the count of records written.
    """
    count = 0
    for f in _SEED_FUND_MERS:
        bridge.write_fund_mer(
            fund_name=f["fund_name"],
            mer=f["mer"],
            ticker=f.get("ticker"),
            fund_family=f.get("fund_family"),
            fund_type=f.get("fund_type", "mutual_fund"),
            currency=f.get("currency", "CAD"),
            notes=f.get("notes"),
        )
        count += 1
    return count
