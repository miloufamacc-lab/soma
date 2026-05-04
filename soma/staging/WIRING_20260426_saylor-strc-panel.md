# WIRING MANIFEST — Saylor / Phong Le / Lavish Panel (STRC + Digital Credit)

**Source:** Bitcoin conference panel | ~55 min | 2026-04-26
**transcript_hash:** `a33f474c`
**skill_version:** transcript-to-intel V3.0
**Subject slug:** `saylor-strc-panel`
**Primary domain:** equities (MSTR) | secondary: macro / crypto / geopolitical / philosophy

---

## 1. PRISM Routing (5 records)

| # | Category | Pipeline | Score | Tags |
|---|----------|----------|-------|------|
| 1 | equities | TITAN | 9 | mstr, strc, strategy-inc, preferred-shares, btc-treasury, ai-finance |
| 2 | macro | TITAN | 9 | credit-market, spreads, tam, banking-adoption, basel, yield-compression |
| 3 | crypto | COBALT | 7 | bitcoin, lightning, layer-2, layer-3, ossification, duration-stack |
| 4 | geopolitical | SPECTRE | 8 | us-regulators, stablecoin-guidance, occ, sec, cftc, mica-divergence |
| 5 | philosophy | DOCTRINE | 6 | future-of-work, ai-deflation, digital-capital, org-structure |

YAML: `staging/PRISM_20260426_saylor-strc-panel.yaml`

## 2. DOCTRINE Evidence (4 supports + 2 CANDIDATE)

| Belief ID | Action | Weight | Note |
|-----------|--------|--------|------|
| MACRO_FISCAL_DOMINANCE | supports | 1.0 | AI-deflation → forced money-printing thesis |
| CRYPTO_BTC_STORE_OF_VALUE | supports | 1.5 | L1 ossification reinforced; $50B+ MSTR lobbying weight |
| EQ_AI_SECULAR_THEME | supports | 1.5 | Concrete corporate use case: Strategy designs all 5 securities w/ AI |
| BEH_THESIS_DISCIPLINE | supports | 0.5 | Caveat — panel uniformity = single coordinated source |
| EQ_DIGITAL_CREDIT_DISPLACES_HY_CANDIDATE | CANDIDATE | — | Capital-charge regime is the binding constraint; review before promoting |
| EQ_BTC_PER_SHARE_KPI_CANDIDATE | CANDIDATE | — | History verified across 3 prior appearances; ready for promotion |

YAML: `staging/DOCTRINE_20260426_saylor-strc-panel.yaml`

## 3. HORIZON Signals (6 entries)

| # | Lens | Direction | Timeframe | Confidence |
|---|------|-----------|-----------|------------|
| 1 | CREDIT_LIQUIDITY | BEARISH | 5y (HY) | 0.50 |
| 2 | CREDIT_LIQUIDITY | BEARISH | 10y (IG) | 0.45 |
| 3 | CREDIT_LIQUIDITY | BEARISH | 20y (Mortgage) | 0.40 |
| 4 | FUNDAMENTAL | BULLISH | 12mo (banking adoption) | 0.60 |
| 5 | FUNDAMENTAL | BULLISH | 7y (BTC/share doubling) | 0.55 |
| 6 | GEOPOLITICAL | BULLISH | 4y (US reg tailwind) | 0.70 |

YAML: `staging/HORIZON_20260426_saylor-strc-panel.yaml`

## 4. SOMA Rule Extractions (4 rules)

| Rule ID | Domain | Confidence |
|---------|--------|------------|
| EQUITIES_DURATION_STACK_FRAMEWORK_V1 | equities | 0.65 |
| EQUITIES_BTC_PER_SHARE_KPI_V1 | equities | 0.85 |
| MACRO_CREDIT_SQUEEZE_SEQUENCE_V1 | macro | 0.50 |
| BEHAVIORAL_PANEL_UNIFORMITY_FLAG_V1 | behavioral | 0.70 |

File: `staging/SOMA_RULES_20260426_saylor-strc-panel.md`

## 5. Wiki Articles

| Slug | Action | Path |
|------|--------|------|
| michael-saylor | UPDATE — append 2026-04-26 panel section | `compiled/finance/speakers/michael-saylor.md` |
| james-lavish | UPDATE — append 2026-04-26 panel section | `compiled/finance/speakers/james-lavish.md` |
| phong-le | CREATE — first appearance in DABEIBA wiki | `compiled/finance/speakers/phong-le.md` |
| strc-variable-rate-preferred | UPDATE — new yield/AUM evidence | `compiled/crypto/digital-credit/strc-variable-rate-preferred.md` |
| 20260426-saylor-strc-panel | CREATE (QnA) | `compiled/finance/qna/20260426-saylor-strc-panel.md` |

QnA file: `staging/QNA_20260426_saylor-strc-panel.md` (move into wiki on ingest)

## 6. Cross-Transcript Speaker Index (CLI commands to run)

```bash
python3 ~/Desktop/DABEIBA/shared/tools/transcript_index.py update "Michael Saylor" \
  --transcript "saylor-strc-panel-20260426" \
  --date "2026-04-26" \
  --claims '["$300T credit market is non-performing","All 5 US fin regulators back digital assets","Squeeze sequence HY 5y -> IG 10y -> mortgage 20y","STRC wouldn'"'"'t exist without AI","Lightning is one of multiple L2 protocols"]' \
  --stances '{"bitcoin": "BULLISH", "strc": "BULLISH", "digital_credit": "BULLISH", "legacy_credit": "BEARISH", "us_regulators": "BULLISH", "private_credit": "BEARISH"}' \
  --tier "T1" \
  --role "Founder & Exec Chair, Strategy Inc."

python3 ~/Desktop/DABEIBA/shared/tools/transcript_index.py update "Phong Le" \
  --transcript "saylor-strc-panel-20260426" \
  --date "2026-04-26" \
  --claims '["STRC at $3B today, path to $300B at 11%","Three-layer duration stack L1/L2/L3","Banking adoption arrives 2026","Tokenization disrupts private credit in 10y","BTC yield is the only relevant KPI for MSTR"]' \
  --stances '{"bitcoin": "BULLISH", "strc": "BULLISH", "digital_credit": "BULLISH", "private_credit": "BEARISH", "banking_adoption": "BULLISH"}' \
  --tier "T1" \
  --role "President & CEO, Strategy Inc."

python3 ~/Desktop/DABEIBA/shared/tools/transcript_index.py update "James Lavish" \
  --transcript "saylor-strc-panel-20260426" \
  --date "2026-04-26" \
  --claims '["AI scaling toward AGI within years","AI-driven productivity is massively deflationary","Govt forced to monetize debt in response","STRC is the digital credit bridge"]' \
  --stances '{"ai_deflation": "BULLISH", "bitcoin": "BULLISH", "digital_credit": "BULLISH"}' \
  --tier "T2" \
  --role "Co-managing Partner, Bitcoin Opportunity Fund"
```

## 7. Prediction Ledger (testable forward claims)

```bash
python3 ~/Desktop/DABEIBA/shared/tools/prediction_log.py add "Bitcoin banking adoption arrives in 2026" \
  --speaker "Phong Le" --tier "T1" \
  --horizon "2026-12-31" --direction "BULLISH" \
  --metric "Banks holding BTC/MSTR/STRC on balance sheet" --target "Multiple top-20 US banks announce" \
  --confidence 0.60 --source "saylor-strc-panel-20260426" --source-date "2026-04-26"

python3 ~/Desktop/DABEIBA/shared/tools/prediction_log.py add "STRC scales to $30-300B AUM" \
  --speaker "Phong Le" --tier "T1" \
  --horizon "2030-12-31" --direction "BULLISH" \
  --metric "STRC notional outstanding" --target "$30B-$300B" \
  --confidence 0.55 --source "saylor-strc-panel-20260426" --source-date "2026-04-26"

python3 ~/Desktop/DABEIBA/shared/tools/prediction_log.py add "MSTR doubles BTC-per-share over 7 years" \
  --speaker "Michael Saylor" --tier "T1" \
  --horizon "2033-04-26" --direction "BULLISH" \
  --metric "MSTR Bitcoin Per Share" --target "+100% from 2026-04-26 baseline" \
  --confidence 0.55 --source "saylor-strc-panel-20260426" --source-date "2026-04-26"

python3 ~/Desktop/DABEIBA/shared/tools/prediction_log.py add "Digital credit displaces high-yield corporate over 5 years" \
  --speaker "Michael Saylor" --tier "T1" \
  --horizon "2031-04-26" --direction "BEARISH" \
  --metric "HY Index AUM (HYG + JNK + similar)" --target "Material outflows / spread widening" \
  --confidence 0.50 --source "saylor-strc-panel-20260426" --source-date "2026-04-26"

python3 ~/Desktop/DABEIBA/shared/tools/prediction_log.py add "20% of global capital becomes digital by 2060" \
  --speaker "Michael Saylor" --tier "T1" \
  --horizon "2060-04-26" --direction "BULLISH" \
  --metric "Digital share of global capital stack" --target "20% (vs 0.1% today)" \
  --confidence 0.45 --source "saylor-strc-panel-20260426" --source-date "2026-04-26"
```

## 8. Red Flags Surfaced

- **Authority Overreach** — Saylor's "$300T credit market broken" combines high conviction with structural-opinion framing on quantitative claim.
- **Promoter framing (3 instances)** — "75% of capital → BTC via digital credit" / "$300-400T TAM" / "Compete private not sovereign". All three speakers have material financial interest in audience accepting these claims.
- **Panel uniformity** — Zero contested topics across 3 speakers; audience challenges deflected. Treat as ONE source for confidence aggregation, not three.
- **Stale (corrected)** — STRC AUM cited as "$3 billion"; actual ~$3.84B notional as of Apr 2026 (28% higher; growth +28% in last quarter).

## 9. Adversarial Review Outcome (Phase 2.5)

5 highest-impact claims subjected to steelman counter-arguments via independent web research. Result: **5 STRONG / 0 MODERATE / 0 WEAK / 0 NONE**. All 5 confidence scores adjusted -0.05.

Most impactful counter: claim 2 ($300T "broken") = category error — credit serves liability-matching, not return-maximization. ERISA + NAIC capital-charge regimes make wholesale displacement structurally improbable regardless of yield. Single counter-argument collapses claims 5, 6, 14 simultaneously.

## 10. Files Produced

| File | Type | Path (in working folder) |
|------|------|--------------------------|
| Deck (clean briefing) | .pptx | `INTEL_20260426_01_saylor-strc-digital-credit.pptx` (30 slides) |
| Scratchpad | .md | `SCRATCHPAD_20260426_saylor-strc-panel.md` |
| PRISM YAML | .yaml | `PRISM_20260426_saylor-strc-panel.yaml` |
| DOCTRINE YAML | .yaml | `DOCTRINE_20260426_saylor-strc-panel.yaml` |
| HORIZON YAML | .yaml | `HORIZON_20260426_saylor-strc-panel.yaml` |
| SOMA rules | .md | `SOMA_RULES_20260426_saylor-strc-panel.md` |
| Wiki QnA | .md | `QNA_20260426_saylor-strc-panel.md` |
| Red-team JSON | .json | `REDTEAM_20260426_saylor-strc-panel.json` |
| Wiring manifest (this file) | .md | `WIRING_20260426_saylor-strc-panel.md` |

---

**Skill version:** V3.0  |  **Generated:** 2026-04-26  |  **Hash:** a33f474c
