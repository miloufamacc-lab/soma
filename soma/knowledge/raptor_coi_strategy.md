# RAPTOR_COI_STRATEGY_V1

**Module:** RAPTOR | **Version:** 1 | **Status:** ACTIVE  
**Source:** raptor_engine.py — seed_coi_strategy_rule(), get_coi_leaderboard(), suggest_coi_touchpoints()

---

## Rule

Centre of Influence (COI) network is the primary referral channel for net new asset acquisition.
Strategy targets a focused, reciprocal network of 5–10 high-quality COIs.

## Network Composition

**Optimal network size:** 5–10 active COIs (COI_OPTIMAL_MIN / COI_OPTIMAL_MAX constants)

**Priority professions (ranked):**
1. Accountant / CPA — highest referral quality (tax-driven wealth events)
2. Notaire / Notary — estate planning transitions
3. Lawyer / Avocat — business sale, divorce, inheritance
4. Insurance advisor — existing wealth + risk awareness
5. Other financial professionals

**Avoid:** COIs who also manage investments (conflict of interest, NI 31-103)

## Contact Cadence

- **Active COIs:** Minimum 1 meaningful touchpoint every 60 days (COI_STALE_DAYS = 60)
- **Touch types:** Lunch, coffee, referral update call, industry event, joint client event
- **Quality over quantity:** Substantive touchpoints only — no mass emails

## Reciprocity Framework

- **Target:** 1:1 reciprocity (referrals given = referrals received over rolling 12 months)
- **balance = received − given**
  - Positive (> 0): UNDER_INVESTING — increase outbound referrals to this COI
  - Negative (< 0): OVER_INVESTING — reduce investment; COI not reciprocating
  - Zero: BALANCED — maintain cadence
- Reciprocity tracked via `raptor_coi_network.reciprocity_given / reciprocity_received`

## Referral Agreement Requirements

- Written referral agreement required before any compensation arrangement (NI 31-103 s.13.7)
- Agreement must be signed BEFORE prospect enters 'onboarding' stage (gate enforced in code)
- Agreement stored at `raptor_coi_network.referral_agreement_path`

## Leaderboard Formula

```
composite_score = total_referrals × conversion_rate × avg_asset_score
```

Where `avg_asset_score` = mean of `_ASSET_SCORES` values for referred prospects.
COIs with zero referrals score 0 and appear at bottom of leaderboard.

## Staleness Detection

A COI is flagged as "due for contact" when:
- `max(referral_date)` OR `relationship_start_date` is ≥ 60 days ago
- COI appears in `suggest_coi_touchpoints()` output

## Compliance

- No compensation arrangement without written agreement (NI 31-103)
- Referral fees must be disclosed to referred prospects (NI 31-103 s.13.7)
- COI list treated as confidential — not disclosed in marketing
