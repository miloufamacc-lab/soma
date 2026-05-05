#!/bin/bash
# RAPTOR Phase 5 — Git commit (shared/soma repo)
# Run from: ~/Desktop/DABEIBA/shared/
# Usage: bash soma/tasks/COMMIT_RAPTOR_P5.sh

set -e
cd "$(cd "$(dirname "$0")/../.." && pwd)"   # shared/
echo "Working in: $(pwd)"

echo ""
echo "=== Commit RAPTOR P5: Privacy & Data Sanitization Engine (19/19 green, 370/370 regression) ==="
git add soma/raptor_privacy.py \
        soma/soma_bridge.py \
        soma/tests/test_raptor_p5.py \
        soma/tasks/COMMIT_RAPTOR_P5.sh
git commit -m "RAPTOR P5: Privacy & data sanitization engine + 19 tests green

- raptor_privacy.py: RaptorPrivacy class
  process_deletion_request(): scrubs PII fields (first_name->DELETED,
    last_name->[HASH8], email/phone/linkedin_url/notes->None), calls
    execute_data_deletion(), returns Law 25 compliance receipt with
    ciro_archive_preserved=True (record kept for CIRO Rule 3804 7yr retention)
  run_dormant_cleanup(inactive_months=24): anonymizes lost/dormant prospects
    inactive > N months; skips active consent, already-anonymized, recent activity
  consent_health_report(): valid_consent_count, expiring_30/60/90d,
    revoked_not_scrubbed, deletion_pending — full CASL/Law 25 snapshot
  run_breach_notification_check(): reads soma_events for raptor_breach_declared,
    generates EN/FR CAI notification templates, logs notification event,
    returns {breach_detected, affected_count, templates}
  Helper: _pii_suffix() — SHA-256[:8] deterministic anonymization suffix

- soma_bridge.py: execute_data_deletion()
  UPDATE raptor_consent_ledger SET deletion_requested=1,
    deletion_executed_date=? WHERE prospect_id=?
  Returns rowcount (number of consent records marked)

- Full regression: 370/370 green (229 SOMA-INTEL + 122 RAPTOR P0-P5 + misc)"

echo ""
echo "=== Done ==="
git log --oneline -5
