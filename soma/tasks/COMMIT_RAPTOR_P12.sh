#!/bin/bash
# RAPTOR Phase 12 — Git commit (shared/soma repo only)
# Files: raptor_health.py + test_raptor_p12.py + run_day.py + this script
#
# Run from: ~/Desktop/DABEIBA/shared/
# Usage: bash soma/tasks/COMMIT_RAPTOR_P12.sh

set -e
cd "$(cd "$(dirname "$0")/../.." && pwd)"   # shared/
echo "Working in: $(pwd)"

echo ""
echo "=== Commit: RAPTOR P12 — Production Hardening ==="
git add soma/raptor_health.py \
        soma/tests/test_raptor_p12.py \
        soma/run_day.py \
        soma/tasks/COMMIT_RAPTOR_P12.sh
git commit -m "RAPTOR P12: Production hardening — health check + diagnostics

- raptor_health.py: RaptorHealth class (7 checks, diagnose() report)
  _check_tables(): validates all 9 required RAPTOR tables exist → ERROR if missing
  _check_compliance_rules(): kb_rules seeded for scanner → WARN if empty
  _check_orphaned_consent(): consent rows without matching prospect → WARN
  _check_orphaned_touchpoints(): touchpoints without matching prospect → WARN
  _check_stuck_prospects(): prospects over MAX_STAGE_DAYS per stage → WARN
    limits: identified(90d) researched(60d) contacted(45d)
            meeting_set(30d) proposal_sent(60d) onboarding(120d)
  _check_deletion_sla(): Law 25 — unexecuted deletions >30d → ERROR
  _check_expiring_consent(): CASL consents expiring <30d → WARN
  diagnose(): human-readable formatted report with status icons

- run_day.py step_5b_raptor(): health check runs at startup
  WARN/ERROR surfaces immediately before daily pulse banner
  Silent when all checks pass (no noise on green)

- test_raptor_p12.py: 19 tests, all green
  Top-level: check() keys, ok on clean DB, overall ERROR propagation
  Tables: ok when schema applied, ERROR when table missing
  Compliance: ok when seeded, WARN when empty
  Orphaned consent/touchpoints: ok/WARN pair each
  Stuck prospects: ok on fresh, WARN over limit
  Deletion SLA: ok/ERROR pair
  Expiring consent: ok/WARN pair
  diagnose(): returns string, contains all section names

- Full regression: 454/454 green"

echo ""
echo "=== Done ==="
git log --oneline -3
