"""
RAPTOR — 90-Day Onboarding Automation (Phase 7)

Manages the post-acquisition onboarding journey from prospect → client.
Tracks four mandatory milestones, flags overdue items in the daily pulse,
and executes the CIPHER handoff at Day 90.

Milestone schedule:
  Day  7 — Welcome package sent + ATON transfer initiated
  Day 30 — Asset transition review meeting
  Day 60 — Tactical update (first portfolio touch)
  Day 90 — First formal review → transition to CIPHER client_profiles

Compliance notes:
  - Prospect must be in 'proposal_sent' stage to initiate onboarding
  - All milestones are recommended but not blocking for handoff
  - Handoff transitions prospect to 'active' (CIRO 7-yr retention stage)

Usage:
    from soma.soma_bridge import SomaBridge
    from soma.raptor_onboarding import RaptorOnboarding

    with SomaBridge() as bridge:
        ob = RaptorOnboarding(bridge)
        receipt  = ob.initiate_onboarding(prospect_id)
        status   = ob.get_onboarding_status()
        overdue  = ob.check_milestone_due()
        handoff  = ob.handoff_to_cipher(prospect_id)
"""
from __future__ import annotations

from datetime import date, timedelta

# ── Milestone definitions ────────────────────────────────────────────────────

MILESTONES: dict[str, dict] = {
    "day_7":  {"label": "Welcome package sent + ATON transfer initiated", "days": 7},
    "day_30": {"label": "Asset transition review meeting",                "days": 30},
    "day_60": {"label": "Tactical update (first portfolio touch)",        "days": 60},
    "day_90": {"label": "First formal review → CIPHER handoff",           "days": 90},
}

_ONBOARDING_STAGE  = "onboarding"
_COMPLETE_STAGE    = "active"
_ELIGIBLE_STAGES   = {"proposal_sent"}


def _due_date(start_iso: str, days: int) -> str:
    return (date.fromisoformat(start_iso) + timedelta(days=days)).isoformat()


class RaptorOnboarding:
    """90-day onboarding automation for RAPTOR — prospect → client pipeline."""

    def __init__(self, bridge):
        self.bridge = bridge

    # ── Initiate onboarding ───────────────────────────────────────────────────

    def initiate_onboarding(self, prospect_id: str) -> dict:
        """Transition a prospect into the 90-day onboarding programme.

        Steps:
          1. Validate prospect exists and is in an eligible stage.
          2. Advance pipeline_stage to 'onboarding'.
          3. Create four milestone rows with computed due_dates.
          4. Return a receipt with the scheduled milestone dates.

        Raises ValueError if prospect is unknown or ineligible.
        """
        p = self.bridge.get_prospect(prospect_id)
        if not p:
            raise ValueError(
                f"[RAPTOR Onboarding] Unknown prospect_id: {prospect_id}"
            )
        if p["pipeline_stage"] not in _ELIGIBLE_STAGES:
            raise ValueError(
                f"[RAPTOR Onboarding] prospect_id {prospect_id} is in stage "
                f"'{p['pipeline_stage']}' — must be in {_ELIGIBLE_STAGES} to onboard."
            )

        start = date.today().isoformat()

        # Advance stage
        self.bridge.write_pipeline_transition(
            prospect_id, _ONBOARDING_STAGE,
            reason="RAPTOR 90-day onboarding initiated",
            transitioned_by="raptor_onboarding",
        )

        # Create milestone rows
        scheduled: list[dict] = []
        for key, meta in MILESTONES.items():
            dd = _due_date(start, meta["days"])
            self.bridge.write_onboarding_milestone(prospect_id, key, dd)
            scheduled.append({"milestone": key, "label": meta["label"], "due_date": dd})

        # Log event
        self.bridge.publish_event(
            "raptor_onboarding_initiated",
            {"prospect_id": prospect_id, "start_date": start, "milestones": scheduled},
            source_module="RAPTOR",
            correlation_key=prospect_id,
        )

        return {
            "prospect_id":      prospect_id,
            "onboarding_start": start,
            "milestones":       scheduled,
        }

    # ── Status overview ───────────────────────────────────────────────────────

    def get_onboarding_status(self) -> list[dict]:
        """Return onboarding progress for every prospect in 'onboarding' stage.

        Each entry includes:
          prospect_id, display_name, milestones (list of {milestone, due_date,
          completed_date, overdue}), completed_count, total_count.
        """
        today = date.today().isoformat()
        status: list[dict] = []

        for p in self.bridge.get_all_prospects():
            if p["pipeline_stage"] != _ONBOARDING_STAGE:
                continue

            pid  = p["prospect_id"]
            name = (
                p.get("display_name")
                or f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()
            )
            rows = self.bridge.get_onboarding_milestones(pid)
            milestones = []
            for r in rows:
                overdue = (
                    r["completed_date"] is None
                    and (r["due_date"] or "") < today
                )
                milestones.append({
                    "milestone":      r["milestone"],
                    "due_date":       r["due_date"],
                    "completed_date": r["completed_date"],
                    "overdue":        overdue,
                })

            completed = sum(1 for m in milestones if m["completed_date"])
            status.append({
                "prospect_id":     pid,
                "display_name":    name,
                "milestones":      milestones,
                "completed_count": completed,
                "total_count":     len(milestones),
            })

        return status

    # ── Overdue milestone check ───────────────────────────────────────────────

    def check_milestone_due(self) -> list[dict]:
        """Return all overdue milestones across every onboarding prospect.

        A milestone is overdue when due_date < today AND completed_date IS NULL.
        Sorted by days_overdue descending (most overdue first).
        """
        today_d = date.today()
        today_s = today_d.isoformat()
        overdue: list[dict] = []

        for row in self.bridge.get_all_onboarding_milestones():
            if row["completed_date"]:
                continue
            if (row["due_date"] or "") >= today_s:
                continue

            # Belongs to an onboarding prospect?
            p = self.bridge.get_prospect(row["prospect_id"])
            if not p or p["pipeline_stage"] != _ONBOARDING_STAGE:
                continue

            days_over = (today_d - date.fromisoformat(row["due_date"])).days
            label = MILESTONES.get(row["milestone"], {}).get("label", row["milestone"])
            overdue.append({
                "prospect_id":  row["prospect_id"],
                "milestone":    row["milestone"],
                "label":        label,
                "due_date":     row["due_date"],
                "days_overdue": days_over,
            })

        overdue.sort(key=lambda x: x["days_overdue"], reverse=True)
        return overdue

    # ── CIPHER handoff ────────────────────────────────────────────────────────

    def handoff_to_cipher(self, prospect_id: str) -> dict:
        """Transition a completed onboarding prospect to CIPHER client_profiles.

        Steps:
          1. Validate prospect is in 'onboarding' stage.
          2. Check milestone completion (warn if incomplete, do not block).
          3. Create CIPHER client_profile from prospect data.
          4. Advance pipeline_stage to 'active'.
          5. Log handoff event in soma_events.
          6. Return handoff receipt.

        Raises ValueError if prospect unknown or not in 'onboarding'.
        """
        p = self.bridge.get_prospect(prospect_id)
        if not p:
            raise ValueError(
                f"[RAPTOR Onboarding] Unknown prospect_id: {prospect_id}"
            )
        if p["pipeline_stage"] != _ONBOARDING_STAGE:
            raise ValueError(
                f"[RAPTOR Onboarding] prospect_id {prospect_id} is in stage "
                f"'{p['pipeline_stage']}' — must be 'onboarding' to hand off."
            )

        # Milestone completeness check (advisory only)
        milestones = self.bridge.get_onboarding_milestones(prospect_id)
        incomplete = [m["milestone"] for m in milestones if not m["completed_date"]]

        # Build client_alias — deterministic from prospect_id prefix
        suffix = prospect_id[:8].upper()
        client_alias = (
            f"RAPTOR_{p.get('last_name', suffix).upper()[:12]}_{suffix}"
        )
        display_name = (
            p.get("display_name")
            or f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()
        )

        # Map prospect assets_band → CIPHER wealth_level
        assets_map = {
            "under_250k": "emerging",
            "250k_500k":  "mass_affluent",
            "500k_1m":    "affluent",
            "1m_3m":      "high_net_worth",
            "over_3m":    "ultra_high_net_worth",
        }
        wealth = assets_map.get(p.get("assets_band", ""), None)

        # Create CIPHER client profile
        self.bridge.write_client_profile(
            client_alias,
            display_name=display_name,
            wealth_level=wealth,
            notes=f"Onboarded via RAPTOR. Prospect ID: {prospect_id}",
            module_version="RAPTOR-P7",
        )

        # Transition to active
        self.bridge.write_pipeline_transition(
            prospect_id, _COMPLETE_STAGE,
            reason="RAPTOR 90-day onboarding complete — CIPHER handoff",
            transitioned_by="raptor_onboarding",
        )

        # Log handoff event
        today = date.today().isoformat()
        self.bridge.publish_event(
            "raptor_cipher_handoff",
            {
                "prospect_id":         prospect_id,
                "client_alias":        client_alias,
                "incomplete_milestones": incomplete,
                "handoff_date":        today,
            },
            source_module="RAPTOR",
            correlation_key=prospect_id,
        )

        return {
            "prospect_id":           prospect_id,
            "client_alias":          client_alias,
            "cipher_profile_created": True,
            "incomplete_milestones": incomplete,
            "handoff_date":          today,
        }
