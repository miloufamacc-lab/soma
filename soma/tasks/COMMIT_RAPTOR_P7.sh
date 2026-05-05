#!/bin/bash
# RAPTOR Phase 7 — Git commit (shared/soma repo)
# Run from: ~/Desktop/DABEIBA/shared/
# Usage: bash soma/tasks/COMMIT_RAPTOR_P7.sh

set -e
cd "$(cd "$(dirname "$0")/../.." && pwd)"   # shared/
echo "Working in: $(pwd)"

echo ""
echo "=== Commit RAPTOR P7: 90-Day Onboarding Automation (20/20 green, 390/390 regression) ==="
git add soma/migrations/028_raptor_onboarding.sql \
        soma/raptor_onboarding.py \
        soma/soma_bridge.py \
        soma/run_day.py \
        soma/tests/test_raptor_p7.py \
        soma/tasks/COMMIT_RAPTOR_P7.sh
git commit -m "RAPTOR P7: 90-day onboarding automation + 20 tests green

- migrations/028_raptor_onboarding.sql
  raptor_onboarding_milestones: milestone_id, prospect_id, milestone,
  due_date, completed_date, notes, write_timestamp
  Indexes: (prospect_id, milestone), (due_date, completed_date)
  Schema version 28

- raptor_onboarding.py: RaptorOnboarding class
  initiate_onboarding(): validates proposal_sent stage, transitions to
    onboarding, creates Day 7/30/60/90 milestone rows, logs event
  get_onboarding_status(): all onboarding prospects with milestone progress
  check_milestone_due(): overdue milestones sorted by days_overdue desc
  handoff_to_cipher(): creates CIPHER client_profile, advances to active,
    logs raptor_cipher_handoff event; warns on incomplete milestones (non-blocking)
  MILESTONES dict: {day_7: 7d, day_30: 30d, day_60: 60d, day_90: 90d}

- soma_bridge.py: 3 new milestone methods
  write_onboarding_milestone(): upsert on (prospect_id, milestone)
  get_onboarding_milestones(prospect_id): prospect-scoped, ordered by due_date
  get_all_onboarding_milestones(): all prospects, ordered by due_date

- run_day.py: step_5b_raptor() updated
  Imports RaptorOnboarding, runs check_milestone_due() daily
  Banner now shows: Onboarding N in progress | M milestone(s) overdue
  Top 3 overdue milestones printed with days_overdue
  raptor_daily_pulse event payload includes overdue_milestones count
  Pipeline row includes 'onboarding' stage count

- Full regression: 390/390 green (229 SOMA-INTEL + 141 RAPTOR P0-P7 + misc)"

echo ""
echo "=== Done ==="
git log --oneline -7
