# RAPTOR_CONSENT_POLICY_V1

**Module:** RAPTOR | **Version:** 1 | **Status:** ACTIVE  
**Source:** raptor_privacy.py — RaptorPrivacy, raptor_compliance.py, soma_bridge.py

---

## Governing Regulations

- **Law 25 (Quebec)** — Act respecting the protection of personal information in the private sector
- **CASL** — Canada's Anti-Spam Legislation (S.C. 2010, c. 23)
- **CIRO Rule 3804** — 7-year record retention

---

## Consent Types

| Type | Duration | Requirements |
|------|----------|-------------|
| `casl_express` | Indefinite (until revoked) | Written or oral with evidence; preferred |
| `casl_implied` | 2 years from last transaction or inquiry | Must track expiry_date |
| `law25_explicit` | Per request; indefinite until revoked | Specific to data use purpose |

---

## Consent Lifecycle

### Granting
- Consent recorded in `raptor_consent_ledger` at first contact
- `consent_date`, `consent_type`, `consent_method`, `expiry_date` all required
- `consent_text_hash` = SHA-256 of exact consent language shown to prospect

### Expiry
- CASL implied: `expiry_date = consent_date + 730 days` (2 years)
- Express consent: `expiry_date = NULL` (no expiry unless revoked)
- 30-day advance warning surfaced in `consent_health_report()` and daily pulse

### Revocation
- `revoked = 1`, `revoked_date = ISO date`
- Prospect must be immediately added to suppression list
- PII scrubbing must occur within 30 days of revocation (Law 25)

---

## Right to Be Forgotten (Law 25 — Art. 28)

**Timeline:** PII must be scrubbed within 30 days of written request.

**What is scrubbed:**
- `first_name` → "DELETED"
- `last_name` → "[HASH8]" (SHA-256[:8] of prospect_id)
- `display_name` → "DELETED_HASH8"
- `email`, `phone`, `linkedin_url`, `notes` → NULL

**What is KEPT (CIRO Rule 3804 — 7-year retention):**
- All other prospect record fields (stage history, scores, dates)
- Anonymized record structure preserved in `raptor_prospects`
- Consent ledger marked with `deletion_requested=1`, `deletion_executed_date`

**Implementation:** `RaptorPrivacy.process_deletion_request(prospect_id)`

---

## Dormant Prospect Cleanup (CASL s.10 — Implied Consent Expiry)

**Criteria (ALL must be true):**
- `pipeline_stage` in ('lost', 'dormant')
- `first_name != 'DELETED'` (not already anonymized)
- No active non-expired consent
- Last activity (max touchpoint date or created_date) < 24-month cutoff

**Schedule:** Run monthly or on demand via `RaptorPrivacy.run_dormant_cleanup()`

---

## Breach Notification (Law 25 — Art. 3.5 + CAI Regulation)

**Trigger:** `soma_event` with `event_type = 'raptor_breach_declared'`

**Required actions:**
1. Count affected prospects (non-anonymized PII)
2. Generate EN + FR notification templates
3. Report to Commission d'accès à l'information du Québec (CAI)
4. Notify affected individuals "as soon as possible"

**Implementation:** `RaptorPrivacy.run_breach_notification_check()`

---

## Consent Health Dashboard

`consent_health_report()` returns:
- `valid_consent_count` — distinct prospects with active non-expired consent
- `expiring_30d / 60d / 90d` — forward-looking expiry counts
- `revoked_not_scrubbed` — compliance gap requiring immediate action
- `deletion_pending` — deletion_requested but not yet executed

Surfaced daily in run_day.py step 5b RAPTOR banner.
