#!/bin/bash
# RAPTOR Phase 2 — Git commit (shared/soma repo)
# Run from: ~/Desktop/DABEIBA/shared/
# Usage: bash soma/tasks/COMMIT_RAPTOR_P2.sh

set -e
cd "$(cd "$(dirname "$0")/../.." && pwd)"   # shared/
echo "Working in: $(pwd)"

echo ""
echo "=== Commit RAPTOR P2: Compliance Layer (26/26 green, 307/307 regression) ==="
git add soma/migrations/026_raptor_touchpoints_archive.sql \
        soma/raptor_compliance.py \
        soma/raptor_templates.py \
        soma/tests/test_raptor_p2.py \
        soma/tasks/COMMIT_RAPTOR_P2.sh
git commit -m "RAPTOR P2: compliance layer + shadow table + 26 tests green

- migrations/026_raptor_touchpoints_archive.sql
  Shadow table raptor_touchpoints_archive (CIRO Rule 3804 — 7yr retention)
  INSERT/UPDATE/DELETE capture triggers on raptor_touchpoints
  Immutability guards: trg_archive_no_update/delete RAISE(ABORT, 'immutable')
  Schema version 26

- raptor_compliance.py: RaptorCompliance class
  scan_prohibited_terms(): 22 patterns, 7 categories (BLOCK/WARN)
  Categories: PERFORMANCE_GUARANTEE, RISK_MISREPRESENTATION, COMPARATIVE_CLAIM,
    MISLEADING_REGISTRATION, PROHIBITED_TITLE, FORWARD_LOOKING_CLAIM, CAUTION_TITLE
  FR patterns: sans risque, garanti(e) near placement/investissement/rendement
  validate_outreach(): consent check + prohibited terms + unsubscribe + sender ID
  generate_compliant_footer(): bilingual EN/FR with AMF#, Law25/Loi25, unsubscribe
  check_referral_compliance(): REFERRAL_AGREEMENT_UNSIGNED + DISCLOSURE_NOT_DELIVERED
  seed_compliance_rules(): idempotent RAPTOR_PROHIBITED_TERMS_V1 to kb_rules

- raptor_templates.py: bilingual template library
  EMAIL_FOOTER_EN/FR with Law 25/Loi 25 privacy block + unsubscribe mechanism
  EMAIL_INITIAL_OUTREACH, EMAIL_FOLLOWUP, EMAIL_EVENT_FOLLOWUP (EN+FR)
  LINKEDIN_OUTREACH (EN+FR)
  get_template(name, language) registry function

- Full regression: 307/307 green (229 SOMA-INTEL + 52 RAPTOR P0+P1 + 26 RAPTOR P2)"

echo ""
echo "=== Done ==="
git log --oneline -5
