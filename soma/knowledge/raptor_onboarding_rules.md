# RAPTOR_ONBOARDING_V1

**Module:** RAPTOR | **Version:** 1 | **Status:** ACTIVE  
**Source:** raptor_onboarding.py — RaptorOnboarding

---

## Rule

90-day structured onboarding converts new clients from prospect to active CIPHER relationship.
Four mandatory milestones track the transition. Completion triggers CIPHER handoff.

---

## Prerequisites

- Prospect must be in `proposal_sent` stage (all compliance gates passed)
- COI referral agreement signed if applicable (already enforced by onboarding gate)
- `initiate_onboarding()` transitions to `onboarding` stage and creates milestone schedule

---

## Milestone Schedule

| Milestone | Day | Required Action |
|-----------|-----|----------------|
| `day_7` | Day 7 | Welcome package sent + ATON transfer form initiated |
| `day_30` | Day 30 | Asset transition review meeting completed |
| `day_60` | Day 60 | Tactical portfolio update delivered |
| `day_90` | Day 90 | First formal annual review → CIPHER handoff |

**Due dates** are computed as `onboarding_start_date + N calendar days`.

---

## Milestone Completion

Milestones are marked complete by advisor via:
```python
bridge.write_onboarding_milestone(prospect_id, "day_7",
    due_date="...", completed_date=date.today().isoformat())
```

Incomplete milestones past their due_date surface as overdue in:
- `RaptorOnboarding.check_milestone_due()`
- Daily pulse banner (run_day.py step 5b)

---

## Document Checklist (Day 7)

Required documents before ATON transfer:
- IPS (Investment Policy Statement) — signed
- RDI (Relationship Disclosure Information) — signed
- KYC (Know Your Client) form — completed and signed
- Privacy consent (Law 25) — signed
- Referral agreement (if COI-referred) — already on file

---

## CIPHER Handoff (Day 90)

`RaptorOnboarding.handoff_to_cipher(prospect_id)` executes:

1. Creates `client_profiles` record in SOMA (CIPHER's client layer)
   - `client_alias` = `RAPTOR_{LAST_NAME[:12]}_{PROSPECT_ID[:8]}`
   - `wealth_level` mapped from `assets_band`
   - Source note: "Onboarded via RAPTOR. Prospect ID: {id}"
2. Advances prospect stage to `active` (CIRO 7-year archive retention begins)
3. Publishes `raptor_cipher_handoff` SOMA event

**Note:** Handoff does NOT block on incomplete milestones — it warns in receipt.
Advisor must manually close any outstanding items.

---

## Assets Band → CIPHER Wealth Level

| Prospect Band | CIPHER Wealth Level |
|---------------|-------------------|
| under_250k | emerging |
| 250k_500k | mass_affluent |
| 500k_1m | affluent |
| 1m_3m | high_net_worth |
| over_3m | ultra_high_net_worth |

---

## Compliance Notes

- ATON transfer forms: regulated by CIRO Rule 2400 (account transfer)
- IPS requirement: CIRO Rule 3400 suitability
- 7-year retention: prospect record stays in `raptor_prospects` as `active` after handoff
- Privacy consent renewed at Day 7 (express consent replaces any implied consent)
