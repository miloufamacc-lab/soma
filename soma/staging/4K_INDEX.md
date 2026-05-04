# Phase 4K: Prediction Ledger Index

**Execution:** 2026-04-17  
**Phase:** 4K — Extraction of forward-looking claims with testable outcomes  
**Status:** COMPLETE  

---

## Three-Part Deliverable

### 1. **Primary Output: Machine-Readable JSON**
**File:** `4k_prediction_ledger_20260417_cross_scratchpad.json`

- **31 predictions** extracted from 4 scratchpads + 2 prompt examples
- **All fields:** prediction_id, claim, test_metric, outcome_criteria, resolution_date, confidence_at_entry, speaker, impact, red_team_risk
- **Queryable by:** impact tier, confidence range, resolution year, source speaker
- **Summary stats:** avg_confidence 0.597, median 0.60, impact distribution 6-10

**Usage:** Load into database; integrate with SOMA brief_log for quarterly updates.

---

### 2. **Secondary Output: Human-Readable Summary**
**File:** `4K_PREDICTION_LEDGER_SUMMARY.md`

- **Tier analysis:** Impact 10 (2 predictions), Impact 9 (10), Impact 8 (9), Impact 7 (8), Impact 6 (2)
- **Red team targets:** 19 predictions with impact ≥8; Tier A/B/C severity ranking
- **Confidence distribution:** Peak at 0.50-0.60 (52% of ledger); only 2 predictions >0.70
- **Critical watch events:** 8 quarterly milestones 2026-2028 for validation
- **Implicit dependencies:** CUDA moat, BTC non-security status, oil price regime, AI productivity assumptions

**Usage:** Executive briefing; red-team roadmap; quarterly monitoring checklist.

---

### 3. **Meta-Analysis: Completion Report**
**File:** `PHASE_4K_COMPLETION_REPORT.md`

- **Extraction scope:** 5 speakers, 4 scratchpads, 1 prompt reference
- **Methodology notes:** Confidence calibration rules, COI adjustments, limitations/blind spots
- **Red team matrix:** Tier A (strong counter), Tier B (competitive threat), Tier C (regime/macro risk)
- **SOMA integration:** Brief to brief_log, quarterly cadence, annual resolution audit
- **Phase 4M roadmap:** Quarterly updates starting 2026-07-17

**Usage:** Methodology reference; integration planning; future phase dependencies.

---

## Quick Reference: Top 5 Predictions by Impact

| Rank | Prediction | Impact | Confidence | Resolution | Risk Tier |
|------|-----------|--------|-----------|------------|-----------|
| **#1** | 4K_024: Iran accepting BTC for Strait passage (FT) | 10 | 0.75 | 2027-12-31 | Geopolitical |
| **#2** | 4K_009: NVIDIA $3T annual revenue | 10 | 0.50 | 2030-12-31 | COI + regime |
| **#3** | 4K_026: Private credit crisis ($1.8T redemptions) | 9 | 0.85 | 2027-12-31 | **Highest conf** |
| **#4** | 4K_005: STRC triple benefit (returns+safety+tax) | 9 | 0.45 | 2028-12-31 | **STRONG counter** |
| **#5** | 4K_023: Strait closure persists (oil constrained) | 9 | 0.70 | 2027-12-31 | Geopolitical |

---

## Quick Reference: Watch Events (Next 12 Months)

| When | What | Prediction | Action |
|------|------|-----------|--------|
| Q4 2026 | Strike Yield launch | 4K_030 | Confirm ≥5% yield + BTC collateral |
| Q4 2026 | TikTok trend validation closes | 4K_004 | Audit 3+ 10% moves in 4 weeks |
| Q4 2026 | 21 Inc milestone (MNPI) | 4K_031 | Material event threshold |
| Q2 2027 | Private credit H1 data | 4K_026 | Monitor redemption gate activity |
| Q3 2027 | Iran-BTC Strait passages | 4K_024 | On-chain analysis + FT verify |
| Q4 2027 | Agentic scaling law signals | 4K_012 | Watch for first plateau |

---

## Extraction Sources (Scratchpads)

| Date | Source | Speaker | Predictions | Impact-9+ |
|------|--------|---------|-------------|-----------|
| 2026-04-18 | SCRATCHPAD_20260418_saylor-digital-credit.md | Michael Saylor | 6 | 6/6 |
| 2026-04-16 | SCRATCHPAD_2026-04-16_jensen-huang-lex-fridman-nvidia_MASTER.md | Jensen Huang | 10 | 5/10 |
| 2026-04-17 | SCRATCHPAD_20260417_camillo-moss-social-arb-v22.md | Chris Camillo | 5 | 2/5 |
| 2026-04-15 | SCRATCHPAD_20260415_jm-show-ep113-bitcoin-bigger-shovel.md | Jack Mallers | 9 | 6/9 |
| 2026-04-17 | Phase 4K prompt examples | Reference | 1 | 1/1 |

---

## Prediction Breakdown by Domain

| Domain | Count | Example Predictions | Primary Speaker |
|--------|-------|-------------------|-----------------|
| **AI/Tech Infrastructure** | 10 | NVIDIA $3T, CUDA moat, compute 100×, scaling laws, agentic agents | Jensen Huang |
| **Financial Engineering** | 6 | STRC triple benefit, 0% principal loss, 18-23% TEY, reflexive flywheel | Michael Saylor |
| **Crypto/Macro** | 9 | Iran BTC, $400-500T TAM, 200× upside, deflation trap, 1973 parallel | Jack Mallers |
| **Market/AI-Age Behavior** | 5 | Pattern recognition edge, risk aversion myth, $100 future value, wealth transfer, TikTok trends | Chris Camillo + Prompt |

---

## Confidence Distribution

**All 31 predictions:**
- **0.40-0.50:** 8 (26%) — Extreme extrapolation, regime-dependent
- **0.51-0.60:** 16 (52%) — **Modal group** — forward-looking cap applies
- **0.61-0.70:** 5 (16%) — Empirical/observable
- **0.71-0.80:** 1 (3%) — Near-certain (Iran BTC)
- **0.81-0.90:** 1 (3%) — Highest confidence (private credit)

**Note:** Forward-looking claims cap at 0.60 by default; COI adjustments apply to founder/CEO claims.

---

## Red Team Severity Ranking

### **Tier A: STRONG Counter Exists**
- 4K_008: Reflexivity (Luna/UST $40B→$0 in 5 days)
- 4K_005: STRC triple benefit (2022 -91% breach)
- 4K_007: Tax-equiv yield (FASB 2023-08 reclassification risk)

### **Tier B: Competitive Threat Credible**
- 4K_010: CUDA moat (PyTorch + ASICs)
- 4K_014: Rack-scale design (SambaNova, Cerebras)
- 4K_012: Four scaling laws (agentic plateau risk)

### **Tier C: Regime/Macro Risk**
- 4K_023: Strait closure (geopolitical duration)
- 4K_011: 100× GDP compute (US-Taiwan-TSMC regime)
- 4K_009: NVIDIA $3T (AI adoption plateau risk)

---

## Integration: SOMA Brief Log

**Suggested SOMA rule for quarterly cadence:**

```sql
INSERT INTO brief_log (subject, pipeline, output_type, source)
SELECT 
  'Prediction Ledger Update',
  'MANIFEST',
  'prediction_ledger_quarterly',
  'Phase_4K_processor'
FROM predictions
WHERE resolution_date BETWEEN now() AND now() + interval 12 months
  AND impact >= 8
ORDER BY resolution_date ASC
```

**Quarterly review dates:**
- **Phase 4M (Q2):** 2026-07-17 — Add new predictions from weekly transcripts
- **Phase 4M (Q3):** 2026-10-17 — Red-team review; impact reassessment
- **Phase 4M (Q4):** 2026-12-31 — Resolution audit; confidence recalibration

---

## FAQs

### Q: Why cap confidence at 0.60 for forward-looking claims?
**A:** By definition, forward-looking claims cannot be verified until resolution date. Human forecasters typically overconfident by 20-30%; 0.60 floor reflects epistemic humility. Only empirical/observable claims (e.g., private credit data at 0.85) score higher.

### Q: Why are founders/CEOs downgraded (COI adjustment)?
**A:** They have material conflicts. Jensen predicting NVIDIA $3T upside, Saylor promoting STRC benefits, Mallers running Strike/21 Inc. Default -0.10 to -0.15 applied automatically.

### Q: Which predictions are most actionable for portfolio positioning?
**A:** 4K_024 (Iran BTC, 0.75 conf, 2027) and 4K_026 (private credit, 0.85 conf, 2027) have highest conviction + nearest horizons. 4K_009 (NVIDIA $3T) is most market-moving if true.

### Q: Which predictions are red flags (lowest confidence)?
**A:** 4K_025 (BTC $10-20M, 0.40) and 4K_010 (CUDA moat, 0.40) are extreme extrapolations with credible competitive threats. Use for scenario analysis, not base case.

### Q: How often is the ledger updated?
**A:** Quarterly (Phase 4M cadence starting 2026-07-17). New predictions added from weekly PRISM outputs; Impact-8+ claims enter red-team queue.

---

## File Locations

```
/Users/jacobopaez/Desktop/DABEIBA/shared/soma/staging/

├── 4k_prediction_ledger_20260417_cross_scratchpad.json        # PRIMARY OUTPUT
├── 4K_PREDICTION_LEDGER_SUMMARY.md                            # SECONDARY OUTPUT
├── PHASE_4K_COMPLETION_REPORT.md                              # META-ANALYSIS
├── 4K_INDEX.md                                                # THIS FILE
│
└── [source scratchpads]
    ├── SCRATCHPAD_20260418_saylor-digital-credit.md
    ├── SCRATCHPAD_2026-04-16_jensen-huang-lex-fridman-nvidia_MASTER.md
    ├── SCRATCHPAD_20260417_camillo-moss-social-arb-v22.md
    └── SCRATCHPAD_20260415_jm-show-ep113-bitcoin-bigger-shovel.md
```

---

## Next Steps

1. **Load JSON into SOMA database** — make predictions queryable by impact/confidence/speaker
2. **Generate Phase 2.5 red-team review** — create adversarial briefs for 19 Impact-8+ predictions
3. **Schedule Q2 2026 watch events** — track Strike/21 Inc/TikTok/Iran updates
4. **Phase 4M on 2026-07-17** — monthly ingestion + quarterly calibration loop

---

**Index created:** 2026-04-17  
**Next review:** 2026-07-17 (Phase 4M, Q2 update)
