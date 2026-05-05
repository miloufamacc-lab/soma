#!/bin/bash
# RAPTOR Phase 1 — Git commit (shared/soma repo)
# Run from: ~/Desktop/DABEIBA/shared/
# Usage: bash soma/tasks/COMMIT_RAPTOR_P1.sh

set -e
cd "$(cd "$(dirname "$0")/../.." && pwd)"   # shared/
echo "Working in: $(pwd)"

echo ""
echo "=== Commit RAPTOR P1: Lead Scoring Engine (26/26 green) ==="
git add soma/raptor_engine.py \
        soma/tests/test_raptor_p1.py \
        soma/tasks/COMMIT_RAPTOR_P1.sh
git commit -m "RAPTOR P1: lead scoring engine + 26 tests green

- raptor_engine.py: RaptorEngine class
  6-factor weighted scoring (assets 35%, source 25%, recency 15%,
  engagement 10%, geo_lang 10%, complexity 5%)
  Decay: x0.90 per 30-day inactive period, floor at 5.0
- calculate_lead_score(): single prospect, optional write-back
- score_all_prospects(): batch, skips active/lost/dormant
- get_action_queue(): immediate (>80) / nurture (50-80) / passive (<50)
  + re_consent (expiring 30d) + overdue_followup (mid-funnel 30d+)
- get_pipeline_analytics(): stage dist, conversion rates, avg days,
  source effectiveness, COI leaderboard
- seed_scoring_rule(): writes RAPTOR_LEAD_SCORING_V1 to soma.db kb_rules
  (idempotent, weights tunable without code change)
- Full regression: 281/281 green (229 SOMA-INTEL + 52 RAPTOR P0+P1)"

echo ""
echo "=== Done ==="
git log --oneline -5
