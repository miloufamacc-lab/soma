#!/bin/bash
# RAPTOR Phase 9 — Git commit (shared/soma repo only)
# Files: raptor_analytics.py + test_raptor_p9.py + this script
#
# Run from: ~/Desktop/DABEIBA/shared/
# Usage: bash soma/tasks/COMMIT_RAPTOR_P9.sh

set -e
cd "$(cd "$(dirname "$0")/../.." && pwd)"   # shared/
echo "Working in: $(pwd)"

echo ""
echo "=== Commit: RAPTOR P9 — Analytics & Economics Layer ==="
git add soma/raptor_analytics.py \
        soma/tests/test_raptor_p9.py \
        soma/tasks/COMMIT_RAPTOR_P9.sh
git commit -m "RAPTOR P9: Analytics & Economics Layer — 26 tests green

- raptor_analytics.py: RaptorAnalytics class (read-only, 7 methods)
  calculate_client_lifetime_value(): individual or portfolio CLV
    formula: aum × fee_rate × tenure_years × referral_multiplier
    portfolio: by_band breakdown, avg_clv, total_clv
  calculate_payback_period(): acquisition cost / monthly_revenue
    acquisition_cost = tp_count × hours × hourly_rate
  churn_risk_score(): 0–100 composite, 4 factors
    contact_frequency(0.40), aum_band(0.30), stage_velocity(0.20),
    referral_history(0.10) → LOW/MEDIUM/HIGH + recommended_action
  get_at_risk_clients(): active prospects with score > 60, sorted desc
  retention_vs_acquisition_roi(): avg_replacement_cost / avg_retention_cost
    industry multiplier default 4.0 (3-5× industry range)
  growth_scenario_model(): Y1/Y3/Y5 projections, 3 scenarios
    conservative(0.7× new, 1.5× churn), base, aggressive(1.5× new, 0.7× churn)
  channel_effectiveness(): per source_type conversion_rate, avg_aum, velocity

- test_raptor_p9.py: 26 tests, all green
  CLV (6): individual, custom params, unknown raises, empty portfolio,
           aggregate, excludes non-active
  Payback (4): required keys, calculation, zero touchpoints, unknown raises
  Churn (4): high risk, low risk, required keys, unknown raises
  At-risk (3): excludes non-active, sorted desc, required keys
  Retention ROI (2): no clients, ratio positive
  Growth model (3): three scenarios, snapshot months, aggressive > conservative
  Channel (4): empty, required keys, conversion rate, sorted desc

- Bug fix: raptor_analytics.py used 'assets_band' but DB column is
  'estimated_assets_band' — fixed in all 7 call sites

- Full regression: 416/416 green"

echo ""
echo "=== Done ==="
git log --oneline -3
