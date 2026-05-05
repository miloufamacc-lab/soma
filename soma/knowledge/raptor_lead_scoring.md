# RAPTOR_LEAD_SCORING_V1

**Module:** RAPTOR | **Version:** 1 | **Status:** ACTIVE  
**Source:** raptor_engine.py — RaptorEngine.calculate_lead_score()

---

## Rule

Prospects are scored 0–100 using a weighted multi-factor model with temporal decay.
A score > 80 triggers immediate outreach; 50–80 = nurture; < 50 = passive monitoring.

## Scoring Weights (default — tunable via kb_rules)

| Factor | Default Weight | Notes |
|--------|---------------|-------|
| assets_band | 0.30 | Highest weight — AUM is the primary qualifier |
| source_type | 0.20 | COI referral > event > digital |
| recency | 0.20 | Days since last activity (linear decay) |
| engagement | 0.15 | Touchpoint count (log-scaled, cap at 15) |
| geo_lang | 0.10 | Quebec French-speaking = maximum fit |
| complexity | 0.05 | High complexity (business owner, estate) = higher score |

## Assets Band → Score

| Band | Score |
|------|-------|
| over_3m | 1.0 |
| 1m_3m | 0.85 |
| 500k_1m | 0.70 |
| 250k_500k | 0.50 |
| under_250k | 0.20 |
| unknown | 0.10 |

## Source Type → Score

| Source | Score |
|--------|-------|
| coi_referral | 1.0 |
| existing_client | 0.9 |
| event | 0.6 |
| cold_outreach | 0.3 |
| digital | 0.4 |
| other / unknown | 0.2 |

## Recency Decay

- 0–30 days: 1.0
- 31–90 days: linear decay → 0.5 at 90 days
- > 90 days: further linear decay → 0.0 at 365 days

## Score Decay (CASL 2-year implied consent)

- After 180 days of inactivity: 10% decay applied to raw score
- After 365 days: 25% decay
- After 730 days (2 years): CASL implied consent expires; score floored at 0

## Thresholds

| Band | Score Range | Action |
|------|-------------|--------|
| HOT (immediate) | > 80 | Priority outreach within 48h |
| WARM (nurture) | 50–80 | Structured follow-up cadence |
| COLD (passive) | < 50 | Monitor; re-engage on life event |

## Compliance Notes

- Scores are advisory only — not disclosed to prospects (CIRO)
- Re-calculated on every touchpoint and on each run_day.py cycle
- Score history not persisted — current score only stored in raptor_prospects.lead_score
