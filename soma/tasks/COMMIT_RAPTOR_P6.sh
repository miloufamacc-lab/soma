#!/bin/bash
# RAPTOR Phase 6 — Git commit (shared/soma repo)
# Run from: ~/Desktop/DABEIBA/shared/
# Usage: bash soma/tasks/COMMIT_RAPTOR_P6.sh

set -e
cd "$(cd "$(dirname "$0")/../.." && pwd)"   # shared/
echo "Working in: $(pwd)"

echo ""
echo "=== Commit RAPTOR P6: run_day.py Integration & Daily Pulse (370/370 regression) ==="
git add soma/raptor_engine.py \
        soma/run_day.py \
        soma/tasks/COMMIT_RAPTOR_P6.sh
git commit -m "RAPTOR P6: run_day.py integration + raptor_status() daily pulse

- raptor_engine.py: RaptorEngine.raptor_status()
  One-screen terminal summary for run_day.py step 5b.
  Returns: pipeline {stage: count}, scores {hot/warm/cold},
  actions {immediate/re_consent/overdue}, coi {total/due/referrals_month},
  consent {valid/expiring_30d/deletion_pending}
  Delegates to get_action_queue(), suggest_coi_touchpoints(),
  and RaptorPrivacy.consent_health_report()

- run_day.py: step_5b_raptor()
  Positioned after CIPHER (step 5), before Wiki Sync (step 7b).
  Prints RAPTOR Daily Pulse banner with color-coded action flags:
    [!] immediate outreach (red if >0)
    [R] re-consent needed (yellow if >0)
    [O] overdue follow-ups (yellow if >0)
  Logs raptor_daily_pulse event to soma_events (source_module=RAPTOR).
  Non-fatal: ImportError skips gracefully, exceptions print FAIL + continue.
  Docstring updated to include [5b] RAPTOR step.

- Full regression: 370/370 green (no new tests — integration-only phase)"

echo ""
echo "=== Done ==="
git log --oneline -6
