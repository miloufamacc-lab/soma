# RAPTOR_PIPELINE_GATES_V1

**Module:** RAPTOR | **Version:** 1 | **Status:** ACTIVE  
**Source:** soma_bridge.py — _validate_pipeline_transition()

---

## Pipeline Stages (in order)

```
identified → researched → contacted → meeting_set → proposal_sent → onboarding → active
                                                                              ↘ lost / dormant
```

Terminal stages: `active`, `lost`, `dormant`

---

## Gate Rules

### → contacted
**Gate:** Prospect must have at least one active, non-expired, non-revoked consent record.

**Check:** `get_consent_status(prospect_id).has_active_consent == True`

**Regulation:** CASL s.6 — commercial electronic messages require express or implied consent

**Error:** "no active consent on record (Law 25 / CASL requirement)"

---

### → onboarding
**Gate:** Any COI referral linked to this prospect must have a signed referral agreement.

**Check:** For each referral, `coi.referral_agreement_signed == 1`

**Regulation:** NI 31-103 s.13.7 — referral arrangements require written agreement

**Error:** "COI '{name}' has no signed referral agreement (NI 31-103)"

**Note:** Prospects with no COI referrals pass this gate automatically.

---

### → proposal_sent
**Gate (1):** At least one compliance-approved touchpoint must exist.

**Check:** `COUNT(*) FROM raptor_touchpoints WHERE compliance_approved = 1 > 0`

**Gate (2):** Caller must pass `trigger_touchpoint_id` referencing the specific
compliance-approved touchpoint used to justify the proposal.

**Check:** touchpoint exists + belongs to prospect + `compliance_approved = 1`

**Regulation:** CIRO Rule 3400 suitability documentation

**Error:** "zero compliance-approved touchpoints" / "touchpoint not found or not approved"

---

## Other Stage Notes

| Stage | No Gate | Notes |
|-------|---------|-------|
| identified → researched | None | Internal research only |
| researched → contacted | Consent gate (above) | |
| contacted → meeting_set | None | |
| meeting_set → proposal_sent | Touchpoint gate (above) | |
| onboarding → active | None (code gate) | CIPHER handoff via raptor_onboarding.py |
| Any → lost | None | Advisor discretion |
| Any → dormant | None | Advisor discretion |

---

## Stage Transition Logging

All transitions are written to `raptor_pipeline_log`:
- `from_stage`, `to_stage`, `transition_date`, `reason`, `transitioned_by`
- `trigger_touchpoint_id` (for proposal_sent gate audit trail)

Transitions are **permanent** — no stage reversal except by explicit new transition.
Full history preserved for CIRO 7-year retention.
