#!/bin/bash
# RAPTOR Phase 3 — Git commit (shared/soma repo)
# Run from: ~/Desktop/DABEIBA/shared/
# Usage: bash soma/tasks/COMMIT_RAPTOR_P3.sh

set -e
cd "$(cd "$(dirname "$0")/../.." && pwd)"   # shared/
echo "Working in: $(pwd)"

echo ""
echo "=== Commit RAPTOR P3: COI Network & Referral Intelligence (20/20 green, 327/327 regression) ==="
git add soma/raptor_engine.py \
        soma/tests/test_raptor_p3.py \
        soma/tasks/COMMIT_RAPTOR_P3.sh
git commit -m "RAPTOR P3: COI network intelligence + 20 tests green

- raptor_engine.py: 4 new RaptorEngine methods
  get_coi_leaderboard(): composite_score = referrals × conversion_rate × avg_asset_score
    Ranked by composite desc; COIs with zero referrals score 0
  get_reciprocity_report(): balance = received - given
    Status: UNDER_INVESTING / OVER_INVESTING / BALANCED
    Sorted by abs(balance) desc
  suggest_coi_touchpoints(): COIs not contacted in >=60 days
    Staleness proxy: max(referral_date) → relationship_start_date → suggest always
    Sorted by days_since_last_contact desc
  get_referral_funnel(coi_id=None): by_outcome, avg_days_to_convert,
    pending_by_stage, coi_breakdown (all-COI view only)

- seed_coi_strategy_rule(): writes RAPTOR_COI_STRATEGY_V1 to kb_rules
  Encodes: optimal network size (5-10), profession priority
  (accountant/notaire/lawyer/insurance), contact cadence, reciprocity 1:1 target
  Idempotent (INSERT OR IGNORE)

- _VERSION bump: RAPTOR-1.1 → RAPTOR-1.3
- COI_STALE_DAYS = 60 constant exported for test use

- Full regression: 327/327 green (229 SOMA-INTEL + 78 RAPTOR P0+P1+P2+P3)"

echo ""
echo "=== Done ==="
git log --oneline -5
