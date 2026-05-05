#!/bin/bash
# RAPTOR Phase 11 — Git commit (shared/soma repo only)
# Files: test_raptor_p11_integration.py + this script
#
# Run from: ~/Desktop/DABEIBA/shared/
# Usage: bash soma/tasks/COMMIT_RAPTOR_P11.sh

set -e
cd "$(cd "$(dirname "$0")/../.." && pwd)"   # shared/
echo "Working in: $(pwd)"

echo ""
echo "=== Commit: RAPTOR P11 — End-to-End Integration Tests ==="
git add soma/tests/test_raptor_p11_integration.py \
        soma/tasks/COMMIT_RAPTOR_P11.sh
git commit -m "RAPTOR P11: End-to-end integration tests — 19 tests green

Synthetic data, no real client data required.
All 8 RAPTOR sub-modules exercised in realistic sequence.

1. Full pipeline smoke (2 tests):
   - identified → contacted → meeting_set → proposal_sent
     → onboarding → active (all stage gates pass)
   - SOMA events published at onboarding_initiated + cipher_handoff

2. Lead scoring (2 tests):
   - score_all_prospects() scores every prospect
   - prospect with consent + touchpoint + premium band > bare prospect

3. Compliance (4 tests):
   - scan_prohibited_terms() flags PERFORMANCE_GUARANTEE ('garanti')
   - clean French message returns zero hits
   - validate_outreach() blocks without consent on file
   - raptor_touchpoints_archive trigger fires on INSERT (CIRO 7yr)

4. CRM3 (2 tests):
   - generate_crm3_report() returns markdown string with key sections
   - savings section present when current MER > proposed MER

5. Privacy (2 tests):
   - process_deletion_request() scrubs PII, preserves CIRO record
   - consent_health_report() returns all required keys + valid count

6. Analytics (3 tests):
   - CLV correct for active client with known AUM band
   - Churn = LOW for recently onboarded client with today touchpoint
   - channel_effectiveness attributes active clients to source_type

7. raptor_status (2 tests):
   - All 5 sections present (pipeline, scores, actions, coi, consent)
   - Pipeline counts match actual DB stage distribution

8. Growth model + retention ROI (2 tests):
   - Aggressive scenario > conservative at Y5 (clients + revenue)
   - Retention ROI ratio >= 1.0 with active clients

- Full regression: 435/435 green"

echo ""
echo "=== Done ==="
git log --oneline -3
