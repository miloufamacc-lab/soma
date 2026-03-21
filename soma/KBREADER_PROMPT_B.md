# Claude Code Prompt B — Add YAML Rule Blocks to KB Files

## Context
SOMA is in ~/Desktop/DABEIBA/shared/soma/. The kb_reader.py is now built (from Prompt A). It parses YAML rule blocks embedded in KB markdown files between `<!-- RULE_BLOCK: ID -->` and `<!-- END_RULE_BLOCK -->` markers.

Now we need to add the actual rule blocks to the 4 KB files. These are the machine-readable versions of rules that are already expressed in prose. The prose stays unchanged — we're adding structured data alongside it.

## Format

Insert rule blocks immediately AFTER the relevant prose section. Keep all existing content unchanged.

```markdown
### 2.1 Target Allocations by Regime

(existing prose and tables stay exactly as-is)

<!-- RULE_BLOCK: REGIME_ALLOCATIONS_V1 -->
```yaml
rule_id: REGIME_ALLOCATIONS_V1
source_module: [ORACLE, MANTIS]
confidence: 0.95
rules:
  ...
```
<!-- END_RULE_BLOCK -->
```

## Rules to Extract

### From `mantis_mechanics.md`:

1. **REGIME_ALLOCATIONS_V1** (Section 2.1) — the target allocation table:
   - RISK_ON_REBOUND: equity 80-95%, cash 5%, aggressive
   - RISK_ON_EXPANSION: equity 70-85%, cash 10%, growth
   - TURBULENCE: equity 50-65%, cash 20%, defensive
   - CONTRACTION: equity 30-50%, cash 30-50%, preservation

2. **REGIME_TRANSITION_RULES_V1** (Section 2.2) — regime transition actions:
   - RISK_ON→TURBULENCE: reduce equity 15-25%, sell highest-beta, 3-5 days
   - TURBULENCE→CONTRACTION: further reduce, sell cyclicals, cash floor 30%
   - CONTRACTION→RISK_ON: rebuild 5%/week, cheapest names first
   - TURBULENCE→RISK_ON: restore to expansion, favor oversold names

3. **TRANSITION_SPEED_V1** (Section 2.3):
   - reducing_exposure_days: [3, 5]
   - increasing_exposure_weeks: [2, 4]

4. **POSITION_SIZING_V1** (Section 3 — position sizing rules):
   - Read the existing section and extract: max position weight, concentration limits, inverse-vol sizing formula, vol threshold

5. **DRAWDOWN_CONTROLS_V1** (Section 5 — drawdown tiers and circuit breakers):
   - DD tiers: which DD% triggers which action
   - Circuit breaker: max daily loss threshold

### From `macro_regimes.md`:

6. **INFLATION_ASSET_MAP_V1** (Section 1.2) — the asset impact table:
   - within_expectations: cash neutral, bonds neutral, equity neutral, real_estate neutral
   - above_expectations: cash positive, bonds negative, equity negative, real_estate positive, commodities positive
   - deflation: cash positive_real, bonds positive, equity negative, real_estate negative

7. **YIELD_CURVE_SIGNALS_V1** (Section 1.1) — yield curve shape → positioning:
   - steep_upward: bullish equities, cyclicals
   - flat_inverted: defensive, long-duration bonds
   - bear_steepening: real assets, TIPS, commodities
   - bull_flattening: early cycle positioning

8. **CREDIT_SPREAD_THRESHOLDS_V1** (Section 1.3) — if it has specific thresholds:
   - HY spreads > 500bps → distressed opportunity approaching

### From `valuation_models.md`:

9. **VALUATION_METHOD_SELECTOR_V1** (Section 3.1) — when to use each approach:
   - DCF: predictable cash flows, mature companies
   - DDM: stable dividends, sustainable payout
   - Relative: sufficient comparables, standard multiples
   - SOTP: conglomerates, diverse business lines
   - Real Options: significant optionality, high uncertainty

### From `communication_compliance.md`:

10. **ADVICE_FRAMEWORK_V1** — the 6 elements of ADViCE:
    - A: Aware (of change in thinking)
    - D: Differentiated (from consensus)
    - V: Validated (by evidence)
    - I: (find the actual I)
    - C: Conclusion-oriented
    - E: Easy to consume

11. **PRACTICE_FRAMEWORK_V1** — PRACTICE meeting prep elements

12. **MONEY_SCRIPT_TYPES_V1** — Klontz money scripts:
    - vigilance, avoidance, worship, status — each with behavioral tendencies

## Instructions

1. Read each KB file completely before modifying
2. Find the exact section referenced above
3. Insert the RULE_BLOCK immediately after that section's content
4. Do NOT change any existing prose, tables, or formatting
5. Validate: each rule block must have `rule_id` and `source_module` fields
6. After adding all blocks, run: `python3 -c "from soma.soma_bridge import SomaBridge; from soma.kb_reader import KBReader; db=SomaBridge(); db.__enter__(); db.initialize_db(); kr=KBReader(db); kr.build_index(); rules=kr.get_all_rules(); print(f'{len(rules)} rules indexed'); [print(f'  {rid}') for rid in sorted(rules)]"`
7. Should print 10-12 rules indexed
8. Commit: `git add -A && git commit -m "Add YAML rule blocks to KB files: 12 machine-readable rules for runtime KB reader"`
