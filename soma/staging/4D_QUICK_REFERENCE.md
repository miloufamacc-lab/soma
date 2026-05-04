# Phase 4d Quick Reference — SOMA Rule Extraction

**Status:** COMPLETE | **Date:** 2026-04-17 | **Rules Extracted:** 4

---

## The 4 Rules (30-Second Summary)

| Rule ID | Name | Status | Confidence | Core Idea |
|---------|------|--------|-----------|-----------|
| **RULE-0401** | Bucketing Capital for Asymmetric Bets | PRODUCTION | 0.82 | Split capital into 3 tiers (Retirement, College, Speculation). Only bet 50/50 on Tier 3. |
| **RULE-0402** | Social Arbitrage = Change Detection | PRODUCTION | 0.75 | Spot real-world change first (consumer/tech/political) → find mispriced company → trade 2-4 week window before repricing. |
| **RULE-0403** | Pattern Recognition as Durable Moat | RESEARCH | 0.70 | Institutional investors are slow (committees, benchmarks, audit). Retail with pattern library beats them on information lag. |
| **RULE-0404** | Philanthropic ROI Model | RESEARCH | 0.68 | Treat charity like investment: measure impact, require 10x+ leverage, reallocate to highest ROI. |

---

## Files Created

```
/Users/jacobopaez/Desktop/DABEIBA/shared/soma/staging/
├── 4d_soma_rules_2026_04_17_capital_allocation.yaml       ← MAIN RULES FILE (YAML)
├── PHASE_4D_EXECUTION_REPORT.md                           ← FULL REPORT
├── 4d_kb_rules_integration_map.txt                        ← SQL + VALIDATOR WIRING
└── 4D_QUICK_REFERENCE.md                                  ← THIS FILE
```

---

## What Happens Next

### Automatic (staging_dispatcher.py)
1. Dispatcher scans staging/ directory
2. Reads `4d_soma_rules_2026_04_17_capital_allocation.yaml`
3. Validates YAML schema
4. Inserts 4 rows into soma.db `kb_rules` table
5. Moves file to `processed/` with timestamp

### Manual Verification
```bash
# Check integration
python3 shared/soma/soma_query.py "kb_rules" | grep RULE-040

# Should return 4 rows with rule_id, confidence, domains
```

---

## Module Integration Points

### MANTIS (Position Sizing)
- Uses RULE-0401 to enforce Tier-3 position caps
- Validator warns if single position > 20% of Tier 3

### ORACLE (Change Detection)
- Wires RULE-0402 into DELTA & SENTINEL pipelines
- Flags observation_date for each change signal

### SOMA (Synthesis)
- Synthesizes multi-domain signals per RULE-0402
- Calculates information lag for repricing window

### CIPHER (Communication)
- Reviews pattern publication risk vs. RULE-0403
- Reports impact ROI per RULE-0404

### RAPTOR (Acquisition)
- Segments clients by capital tier (RULE-0401)
- Positions as impact-optimized advisor (RULE-0404)

---

## Production Readiness

### Ready to Deploy Now
- **RULE-0401** (0.82 confidence): Camillo 18-year track record
- **RULE-0402** (0.75 confidence): Snapple, Neato, Amazon/Nvidia evidence

### Research Phase (1-2 Quarters)
- **RULE-0403** (0.70 confidence): Test moat durability post-publication
- **RULE-0404** (0.68 confidence): Validate impact ROI model with 3-5 clients

---

## Domain Coverage

All rules rooted in **BEHAVIORAL FINANCE** (4/4 rules):
- RULE-0401: Loss aversion, compartmentalization bias
- RULE-0402: Information lag, retail vs. institutional speed
- RULE-0403: Organizational constraints, pattern recognition
- RULE-0404: Charitable giving rationalization

---

## Key Insight

These 4 rules form a **coherent investment philosophy**:

1. **Capital Bucketing** (RULE-0401) enables risk-taking
2. **Change Detection** (RULE-0402) finds alpha
3. **Pattern Recognition** (RULE-0403) explains why retail wins
4. **Impact ROI** (RULE-0404) justifies wealth deployment

Together: systematic pattern recognition + behavioral advantages + asymmetric sizing = repeatable alpha

---

## Risk Assessment

| Rule | Risk Level | Mitigation |
|------|-----------|-----------|
| RULE-0401 | LOW | Live track record; backtestable |
| RULE-0402 | LOW | Multiple case studies; falsifiable |
| RULE-0403 | MEDIUM | Moat may erode if patterns published (need pre-pub study) |
| RULE-0404 | MEDIUM | Reductionism risk (unmeasurable outcomes); need sensitivity analysis |

---

## Falsifiability (All 4 Rules Testable)

1. **RULE-0401:** Does bucketed portfolio beat non-bucketed on Sharpe over 10 years?
2. **RULE-0402:** Do 70%+ of change observations yield >5% outperformance in 2-4 weeks?
3. **RULE-0403:** Does moat erode >50% if pattern published to institutional audience?
4. **RULE-0404:** Does ROI-optimized allocation beat emotional allocation >1.5x on impact/dollar?

---

## See Also

- Full rules: `4d_soma_rules_2026_04_17_capital_allocation.yaml`
- Integration guide: `4d_kb_rules_integration_map.txt`
- Execution report: `PHASE_4D_EXECUTION_REPORT.md`
- SOMA architecture: `../soma-architecture.md` (add 4 rules to kb_rules section)

---

**Next Step:** Let staging_dispatcher.py handle the rest. Rules are production-ready for SOMA integration.
