"""
RAPTOR — Acquisition Economics & Analytics Layer (Phase 9)

Computes client lifetime value, payback period, churn risk, retention ROI,
channel effectiveness, and growth scenario modelling.

All methods are read-only — no DB writes.

Key assumptions (configurable as kwargs):
  fee_rate              = 0.01    (1% annual AUM fee — typical Quebec independent)
  avg_tenure_years      = 10.0   (industry average for HNW advisory)
  referral_multiplier   = 1.30   (30% of clients refer ≥1 new client)
  advisor_hourly_rate   = 200.0  (CAD — fully-loaded cost)
  hours_per_touchpoint  = 1.0    (average advisor hours per touchpoint)
  churn_risk_threshold  = 60     (score above which client = at risk)

Usage:
    from soma.soma_bridge import SomaBridge
    from soma.raptor_analytics import RaptorAnalytics

    with SomaBridge() as bridge:
        analytics = RaptorAnalytics(bridge)
        clv       = analytics.calculate_client_lifetime_value()
        payback   = analytics.calculate_payback_period(prospect_id)
        churn     = analytics.churn_risk_score(prospect_id)
        at_risk   = analytics.get_at_risk_clients()
        roi       = analytics.retention_vs_acquisition_roi()
        growth    = analytics.growth_scenario_model(months=60)
        channels  = analytics.channel_effectiveness()
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

# ── Assumptions ───────────────────────────────────────────────────────────────

DEFAULT_FEE_RATE             = 0.01
DEFAULT_TENURE_YEARS         = 10.0
DEFAULT_REFERRAL_MULTIPLIER  = 1.30
DEFAULT_ADVISOR_HOURLY_RATE  = 200.0
DEFAULT_HOURS_PER_TOUCHPOINT = 1.0
CHURN_RISK_THRESHOLD         = 60

# AUM band midpoints (CAD)
_ASSETS_MID: dict[str, float] = {
    "under_250k": 125_000,
    "250k_500k":  375_000,
    "500k_1m":    750_000,
    "1m_3m":    2_000_000,
    "over_3m":  5_000_000,
}
_DEFAULT_AUM = 500_000.0  # fallback when band unknown

# Churn risk weights
_CHURN_WEIGHTS = {
    "contact_frequency": 0.40,   # days since last touchpoint
    "aum_band":          0.30,   # proxy for retention value
    "stage_velocity":    0.20,   # how long since reaching active
    "referral_history":  0.10,   # clients who refer churn less
}


def _aum_mid(assets_band: str | None) -> float:
    return _ASSETS_MID.get(assets_band or "", _DEFAULT_AUM)


class RaptorAnalytics:
    """Acquisition economics and forecasting for RAPTOR."""

    def __init__(self, bridge):
        self.bridge = bridge

    # ── Client Lifetime Value ─────────────────────────────────────────────────

    def calculate_client_lifetime_value(
        self,
        prospect_id: str | None = None,
        fee_rate: float = DEFAULT_FEE_RATE,
        avg_tenure_years: float = DEFAULT_TENURE_YEARS,
        referral_multiplier: float = DEFAULT_REFERRAL_MULTIPLIER,
    ) -> dict:
        """Compute CLV for one prospect or the entire active portfolio.

        Formula:
            CLV = aum × fee_rate × tenure_years × referral_multiplier

        If prospect_id is None: returns portfolio-wide aggregate + breakdown.
        If prospect_id is given: returns individual CLV.
        """
        def _clv(aum: float) -> float:
            return aum * fee_rate * avg_tenure_years * referral_multiplier

        if prospect_id is not None:
            p = self.bridge.get_prospect(prospect_id)
            if not p:
                raise ValueError(f"[RAPTOR Analytics] Unknown prospect_id: {prospect_id}")
            aum = _aum_mid(p.get("estimated_assets_band"))
            return {
                "prospect_id":  prospect_id,
                "assets_band":  p.get("estimated_assets_band"),
                "aum_estimate": aum,
                "clv":          round(_clv(aum), 2),
                "fee_rate":     fee_rate,
                "tenure_years": avg_tenure_years,
                "referral_multiplier": referral_multiplier,
            }

        # Portfolio-wide
        active = [p for p in self.bridge.get_all_prospects()
                  if p["pipeline_stage"] == "active"]
        if not active:
            return {
                "client_count": 0,
                "total_aum_estimate": 0.0,
                "total_clv": 0.0,
                "avg_clv": 0.0,
                "fee_rate": fee_rate,
                "tenure_years": avg_tenure_years,
            }

        aums  = [_aum_mid(p.get("estimated_assets_band")) for p in active]
        total_aum = sum(aums)
        total_clv = sum(_clv(a) for a in aums)

        # CLV by band
        band_summary: dict[str, dict] = {}
        for p in active:
            band = p.get("estimated_assets_band") or "unknown"
            aum  = _aum_mid(band)
            if band not in band_summary:
                band_summary[band] = {"count": 0, "total_clv": 0.0}
            band_summary[band]["count"] += 1
            band_summary[band]["total_clv"] = round(
                band_summary[band]["total_clv"] + _clv(aum), 2
            )

        return {
            "client_count":       len(active),
            "total_aum_estimate": round(total_aum, 2),
            "total_clv":          round(total_clv, 2),
            "avg_clv":            round(total_clv / len(active), 2),
            "by_band":            band_summary,
            "fee_rate":           fee_rate,
            "tenure_years":       avg_tenure_years,
            "referral_multiplier": referral_multiplier,
        }

    # ── Payback Period ────────────────────────────────────────────────────────

    def calculate_payback_period(
        self,
        prospect_id: str,
        advisor_hourly_rate: float = DEFAULT_ADVISOR_HOURLY_RATE,
        hours_per_touchpoint: float = DEFAULT_HOURS_PER_TOUCHPOINT,
        fee_rate: float = DEFAULT_FEE_RATE,
    ) -> dict:
        """Estimate months from first contact until cumulative fees > acquisition cost.

        Acquisition cost proxy:
            touchpoint_count × hours_per_touchpoint × advisor_hourly_rate

        Monthly revenue:
            aum_estimate × fee_rate / 12
        """
        p = self.bridge.get_prospect(prospect_id)
        if not p:
            raise ValueError(f"[RAPTOR Analytics] Unknown prospect_id: {prospect_id}")

        touchpoints = self.bridge.get_touchpoints(prospect_id)
        tp_count    = len(touchpoints)
        acq_cost    = tp_count * hours_per_touchpoint * advisor_hourly_rate

        aum            = _aum_mid(p.get("estimated_assets_band"))
        monthly_revenue = aum * fee_rate / 12.0

        payback_months = (
            round(acq_cost / monthly_revenue, 1)
            if monthly_revenue > 0
            else None
        )

        # Days from first touchpoint to active stage
        if touchpoints:
            first_tp_date = min(t["date"][:10] for t in touchpoints)
        else:
            first_tp_date = (p.get("created_date") or date.today().isoformat())[:10]

        if p["pipeline_stage"] == "active" and p.get("updated_date"):
            active_date = p["updated_date"][:10]
            actual_days = (
                date.fromisoformat(active_date) - date.fromisoformat(first_tp_date)
            ).days
        else:
            actual_days = None

        return {
            "prospect_id":       prospect_id,
            "pipeline_stage":    p["pipeline_stage"],
            "touchpoint_count":  tp_count,
            "acquisition_cost":  round(acq_cost, 2),
            "monthly_revenue":   round(monthly_revenue, 2),
            "payback_months":    payback_months,
            "days_to_active":    actual_days,
            "aum_estimate":      aum,
        }

    # ── Churn Risk Score ──────────────────────────────────────────────────────

    def churn_risk_score(
        self,
        prospect_id: str,
        contact_frequency_max_days: int = 90,
    ) -> dict:
        """Score churn risk 0–100 for an active client.

        Factors:
          contact_frequency (0.40) — days since last touchpoint (90+ days = high risk)
          aum_band         (0.30) — lower AUM = higher churn risk
          stage_velocity   (0.20) — long time in active stage without touchpoint
          referral_history (0.10) — made a referral → lower churn risk

        Returns risk_score, risk_level (LOW/MEDIUM/HIGH), recommended_action.
        """
        p = self.bridge.get_prospect(prospect_id)
        if not p:
            raise ValueError(f"[RAPTOR Analytics] Unknown prospect_id: {prospect_id}")

        today = date.today()

        # ── Contact frequency factor ──────────────────────────────────────────
        touchpoints = self.bridge.get_touchpoints(prospect_id)
        if touchpoints:
            last_tp = max(t["date"][:10] for t in touchpoints)
            days_since = (today - date.fromisoformat(last_tp)).days
        else:
            days_since = 365
        contact_score = min(days_since / contact_frequency_max_days, 1.0)

        # ── AUM band factor (lower AUM = higher churn risk) ──────────────────
        band_risk = {
            "over_3m":    0.10,
            "1m_3m":      0.20,
            "500k_1m":    0.35,
            "250k_500k":  0.55,
            "under_250k": 0.80,
        }
        aum_score = band_risk.get(p.get("estimated_assets_band") or "", 0.50)

        # ── Stage velocity factor ─────────────────────────────────────────────
        active_date = (p.get("updated_date") or p.get("created_date") or "")[:10]
        if active_date:
            days_active = max(
                (today - date.fromisoformat(active_date)).days, 0
            )
            # 0 days active = no risk; 730 days without recent contact = elevated
            velocity_score = min(days_active / 730.0, 1.0) if days_since > 60 else 0.0
        else:
            velocity_score = 0.5

        # ── Referral history factor ───────────────────────────────────────────
        refs = self.bridge.get_referrals_by_prospect(prospect_id)
        referral_score = 0.0 if refs else 0.5

        # ── Composite ────────────────────────────────────────────────────────
        raw = (
            contact_score  * _CHURN_WEIGHTS["contact_frequency"] +
            aum_score      * _CHURN_WEIGHTS["aum_band"] +
            velocity_score * _CHURN_WEIGHTS["stage_velocity"] +
            referral_score * _CHURN_WEIGHTS["referral_history"]
        )
        risk_score = round(raw * 100, 1)

        if risk_score >= 70:
            risk_level = "HIGH"
            action = "Schedule review meeting within 2 weeks"
        elif risk_score >= CHURN_RISK_THRESHOLD:
            risk_level = "MEDIUM"
            action = "Send personalised touchpoint within 30 days"
        else:
            risk_level = "LOW"
            action = "Maintain regular cadence"

        return {
            "prospect_id":      prospect_id,
            "risk_score":       risk_score,
            "risk_level":       risk_level,
            "recommended_action": action,
            "days_since_contact": days_since,
            "factors": {
                "contact_frequency": round(contact_score, 3),
                "aum_band":          round(aum_score, 3),
                "stage_velocity":    round(velocity_score, 3),
                "referral_history":  round(referral_score, 3),
            },
        }

    # ── At-Risk Clients ───────────────────────────────────────────────────────

    def get_at_risk_clients(self) -> list[dict]:
        """Return all active prospects with churn_risk_score > CHURN_RISK_THRESHOLD.

        Sorted by risk_score descending.
        """
        at_risk = []
        for p in self.bridge.get_all_prospects():
            if p["pipeline_stage"] != "active":
                continue
            result = self.churn_risk_score(p["prospect_id"])
            if result["risk_score"] > CHURN_RISK_THRESHOLD:
                at_risk.append({
                    "prospect_id":   p["prospect_id"],
                    "display_name":  (
                        p.get("display_name")
                        or f"{p.get('first_name','')} {p.get('last_name','')}".strip()
                    ),
                    "risk_score":    result["risk_score"],
                    "risk_level":    result["risk_level"],
                    "action":        result["recommended_action"],
                    "days_since_contact": result["days_since_contact"],
                })
        at_risk.sort(key=lambda x: x["risk_score"], reverse=True)
        return at_risk

    # ── Retention vs Acquisition ROI ──────────────────────────────────────────

    def retention_vs_acquisition_roi(
        self,
        fee_rate: float = DEFAULT_FEE_RATE,
        avg_tenure_years: float = DEFAULT_TENURE_YEARS,
        advisor_hourly_rate: float = DEFAULT_ADVISOR_HOURLY_RATE,
        hours_per_touchpoint: float = DEFAULT_HOURS_PER_TOUCHPOINT,
        acquisition_cost_multiplier: float = 4.0,
    ) -> dict:
        """Compare cost to retain existing clients vs. cost to replace them.

        Industry rule: replacing a client costs 3-5× the cost of retaining one.
        acquisition_cost_multiplier default = 4.0 (midpoint estimate).

        Returns per-client averages + portfolio totals.
        """
        active = [p for p in self.bridge.get_all_prospects()
                  if p["pipeline_stage"] == "active"]
        if not active:
            return {"client_count": 0, "message": "No active clients"}

        retention_costs = []
        replacement_costs = []
        clvs = []

        for p in active:
            pid = p["prospect_id"]
            # Retention cost: ongoing touchpoints (annual estimate)
            tps = self.bridge.get_touchpoints(pid)
            annual_tp  = max(len(tps) / max(1, self._months_active(p) / 12), 1)
            ret_cost   = annual_tp * hours_per_touchpoint * advisor_hourly_rate

            # Replacement cost: acquisition cost multiplier × retention cost
            rep_cost = ret_cost * acquisition_cost_multiplier

            aum = _aum_mid(p.get("estimated_assets_band"))
            clv = aum * fee_rate * avg_tenure_years * 1.30

            retention_costs.append(ret_cost)
            replacement_costs.append(rep_cost)
            clvs.append(clv)

        n = len(active)
        avg_ret  = sum(retention_costs) / n
        avg_rep  = sum(replacement_costs) / n
        avg_clv  = sum(clvs) / n

        return {
            "client_count":                  n,
            "avg_annual_retention_cost":     round(avg_ret, 2),
            "avg_replacement_cost":          round(avg_rep, 2),
            "retention_roi_ratio":           round(avg_rep / avg_ret, 1),
            "avg_clv":                       round(avg_clv, 2),
            "total_annual_retention_budget": round(sum(retention_costs), 2),
            "total_replacement_exposure":    round(sum(replacement_costs), 2),
            "recommendation": (
                "Prioritise retention investment — replacement cost is "
                f"{round(avg_rep / avg_ret, 1)}× higher than retention cost."
            ),
        }

    def _months_active(self, prospect: dict) -> float:
        """Helper: months since prospect record was created."""
        created = (prospect.get("created_date") or date.today().isoformat())[:10]
        delta   = (date.today() - date.fromisoformat(created)).days
        return max(delta / 30.0, 1.0)

    # ── Growth Scenario Model ─────────────────────────────────────────────────

    def growth_scenario_model(
        self,
        months: int = 60,
        new_per_month: float = 1.0,
        avg_aum: float = 750_000,
        churn_rate: float = 0.05,
        referral_rate: float = 0.30,
        fee_rate: float = DEFAULT_FEE_RATE,
    ) -> dict:
        """Forward projection of AUM, revenue, client count at Y1 / Y3 / Y5.

        Three scenarios:
          conservative: 0.7× new, 1.5× churn
          base:         as given
          aggressive:   1.5× new, 0.7× churn

        Monthly compound:
          clients_next = clients × (1 - churn_rate/12) + new + (clients × referral_rate/12)
          aum_next     = clients_next × avg_aum
          revenue      = aum × fee_rate
        """
        def _project(n_per_mo: float, churn: float) -> list[dict]:
            clients   = float(self.bridge.conn.execute(
                "SELECT COUNT(*) AS n FROM raptor_prospects WHERE pipeline_stage='active'"
            ).fetchone()["n"])
            snapshots = []
            for m in range(1, months + 1):
                referrals = clients * (referral_rate / 12.0)
                clients   = max(
                    clients * (1 - churn / 12.0) + n_per_mo + referrals,
                    0,
                )
                if m in (12, 36, 60):
                    total_aum = clients * avg_aum
                    snapshots.append({
                        "month":        m,
                        "year":         m // 12,
                        "clients":      round(clients, 1),
                        "total_aum":    round(total_aum, 0),
                        "annual_revenue": round(total_aum * fee_rate, 0),
                    })
            return snapshots

        return {
            "assumptions": {
                "avg_aum":       avg_aum,
                "fee_rate":      fee_rate,
                "referral_rate": referral_rate,
            },
            "conservative": _project(new_per_month * 0.7, churn_rate * 1.5),
            "base":         _project(new_per_month,       churn_rate),
            "aggressive":   _project(new_per_month * 1.5, churn_rate * 0.7),
        }

    # ── Channel Effectiveness ─────────────────────────────────────────────────

    def channel_effectiveness(self) -> dict:
        """Rank acquisition channels by conversion rate, AUM, and velocity.

        Computed from all raptor_prospects (any stage).
        Returns per-channel: total, converted, conversion_rate, avg_aum, avg_days_to_active.
        """
        prospects = self.bridge.get_all_prospects()
        channels: dict[str, dict] = {}

        for p in prospects:
            ch = p.get("source_type") or "unknown"
            if ch not in channels:
                channels[ch] = {
                    "total": 0, "converted": 0,
                    "aum_sum": 0.0, "days_sum": 0.0, "days_count": 0,
                }
            channels[ch]["total"] += 1

            if p["pipeline_stage"] == "active":
                channels[ch]["converted"] += 1
                channels[ch]["aum_sum"] += _aum_mid(p.get("estimated_assets_band"))

                # Days from created to active
                created = (p.get("created_date") or "")[:10]
                updated = (p.get("updated_date") or "")[:10]
                if created and updated:
                    try:
                        d = (date.fromisoformat(updated) -
                             date.fromisoformat(created)).days
                        channels[ch]["days_sum"]   += d
                        channels[ch]["days_count"] += 1
                    except ValueError:
                        pass

        result = {}
        for ch, data in channels.items():
            conv  = data["converted"]
            total = data["total"]
            result[ch] = {
                "total":            total,
                "converted":        conv,
                "conversion_rate":  round(conv / total, 3) if total else 0.0,
                "avg_aum":          round(data["aum_sum"] / conv, 0) if conv else 0.0,
                "avg_days_to_active": (
                    round(data["days_sum"] / data["days_count"], 1)
                    if data["days_count"] > 0 else None
                ),
            }

        # Sort by conversion_rate desc
        return dict(
            sorted(result.items(),
                   key=lambda x: x[1]["conversion_rate"], reverse=True)
        )
