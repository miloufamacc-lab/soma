# WIRING MANIFEST — Saylor Bitcoin Thesis
**Date:** 2026-04-22  
**Transcript slug:** saylor-bitcoin-thesis  
**Transcript hash:** 7c22a545  
**PPTX:** `intel/by-topic/crypto/btc/macro-thesis/INTEL_20260422_01_saylor-bitcoin-thesis.pptx`

---

## 4a — WIKI CROSS-REFERENCE

Existing wiki articles checked for prior coverage:
- `michael-saylor` → NOT FOUND (new speaker profile to create)
- `bitcoin-treasury-business-model` → NOT FOUND (new concept to create)
- `financial-repression` → NOT FOUND
- `bitcoin-digital-gold` → NOT FOUND

Action: Create 2 new wiki articles (speaker profile + concept).

---

## 4b — WIKI ARTICLES TO CREATE

### Article 1: michael-saylor.md (Speaker Profile)
```
---
title: Michael Saylor
slug: michael-saylor
domain: people
entity_type: speaker
credibility_tier: 2
conflict_of_interest: extreme — personal BTC holdings ~$2B+, Strategy holds 538,200+ BTC
bias: EXTREME BULL / PROMOTER
appearances: [saylor-bitcoin-thesis-20260422]
tags: [bitcoin, strategy, treasury, digital-energy, credit]
last_updated: 2026-04-22
---

Executive Chairman of Strategy (formerly MicroStrategy). Primary architect of the Bitcoin treasury company business model. First public company to adopt Bitcoin as primary treasury reserve asset (August 2020). Personal holdings estimated at ~$2B+ BTC; company holds 538,200+ BTC (~$45B at April 2026 prices).

**Credibility tier:** T2 — domain expert with extreme financial conflict on all BTC-bullish claims.  
**PROMOTER flag:** Applied to ALL forward-looking BTC price/adoption claims.  
**Rhetoric profile:** ABSOLUTE/VISIONARY — hedge ratio ~8%. Very low qualification language.  
**Hard cap:** 0.60 on all forward-looking predictions regardless of domain expertise.

**Core thesis (April 2026):** Bitcoin as digital energy → corporate treasury asset → foundation for 21st century digital credit market. Endgame: $1T BTC collateral, $100B/yr digital credit issuance.

**Prior stances:** BULLISH Bitcoin continuously since August 2020. No stance drift detected.
```

### Article 2: bitcoin-treasury-business-model.md (Concept)
```
---
title: Bitcoin Treasury Business Model
slug: bitcoin-treasury-business-model
domain: crypto
entity_type: concept
tags: [bitcoin, treasury, strategy, digital-credit, preferred-shares]
last_updated: 2026-04-22
sources: [saylor-bitcoin-thesis-20260422]
---

Business model in which a public company accumulates Bitcoin as its primary balance sheet asset, then issues digital credit instruments (convertible bonds, preferred equity) collateralized by that BTC position.

**Three company categories (Saylor taxonomy, April 2026):**
1. Pure play (100-1000x): 100% BTC focus — Strategy, MetaPlanet, Strive
2. Strong BTC player (10-20x): BTC as primary treasury + operating business
3. BTC + operations (2-4x): BTC as balance sheet hedge

**Key products:** Convertible bonds, perpetual preferred shares (STRC, STRK, STRD, STKE), BTC-backed money market instruments.

**TAM framing (Saylor):** Not competing against other BTC treasury companies — competing against $100T+ 20th-century credit market.

**Duration rule:** Long-duration debt + appreciating BTC collateral = structurally safe. Short-duration debt + volatile collateral = liquidation risk (2022 miners' failure mode).
```

---

## 4c — DOCTRINE EVIDENCE

**Target doctrine:** `CRYPTO_BTC_STORE_OF_VALUE`

```yaml
doctrine_id: CRYPTO_BTC_STORE_OF_VALUE
evidence_type: SUPPORTING
source: saylor-bitcoin-thesis-20260422
date: 2026-04-22
speaker: michael-saylor
tier: 2
promoter_flag: true
claims:
  - id: C5
    summary: "Bitcoin succeeds where gold failed — custody is the decisive variable"
    confidence: 0.80
    impact: 8
  - id: C13
    summary: "Protocol war: Bitcoin treasury companies as economic defense layer"
    confidence: 0.55
    impact: 8
  - id: C2
    summary: "180+ public companies now hold BTC — exponential corporate adoption"
    confidence: 0.75
    impact: 8
notes: >
  All evidence from PROMOTER speaker (Saylor). Custody advantage claim (C5) is the strongest
  at 0.80 confidence — grounded in verifiable historical facts (Germany gold story).
  Protocol war claim (C13) is speculative. Weight accordingly.
```

---

## 4d — SOMA RULES

### Rule 1: Financial Repression BTC Treasury Arbitrage

```yaml
rule_id: SOMA_RULE_FINREP_BTC_ARB_001
module: SOMA
domain: crypto + macro
trigger: "any BTC treasury company analysis in markets with sub-100bps risk-free rates"
condition: "local_risk_free_rate < 100bps AND btc_expected_cagr > 20%"
action: >
  Flag financial repression arbitrage opportunity. Calculate spread: BTC expected return
  minus local risk-free rate. If spread > 2000bps, route to COBRA priority analysis.
  Reference: Saylor framework April 2026 — Japan (50bps) and Switzerland (negative)
  as archetypes. MetaPlanet (Japan) as live implementation.
confidence: 0.60
source: saylor-bitcoin-thesis-20260422
created: 2026-04-22
```

### Rule 2: BTC Treasury Company Duration Safety Check

```yaml
rule_id: SOMA_RULE_BTC_DURATION_SAFETY_001
module: SOMA
domain: crypto + risk
trigger: "any BTC treasury company debt structure analysis"
condition: "debt_duration < 24_months OR collateral_depreciation_rate > 10pct_per_year"
action: >
  Flag duration mismatch risk. Long-duration instruments (4+ year convertibles, perpetual
  preferred) + appreciating BTC collateral = safe structure. Short-duration + volatile/
  depreciating collateral = 2022 miner failure pattern. Escalate to MANTIS risk review.
confidence: 0.75
source: saylor-bitcoin-thesis-20260422
created: 2026-04-22
```

---

## 4e — PRISM ROUTING YAML

```yaml
prism_routing:
  transcript_slug: saylor-bitcoin-thesis
  date: 2026-04-22
  hash: 7c22a545
  primary: crypto
  pipeline: COBALT
  secondary: macro
  pipeline_secondary: TITAN
  tertiary: philosophy
  pipeline_tertiary: DOCTRINE
  language: en
  speaker_count: 1
  duration_min: 89
  mode: STANDARD
  total_claims: 16
  implicit_claims: 3
  high_impact_claims: 13
  promoter_flag: true
  red_team_completed: true
  wiki_articles_created: 2
  soma_rules_added: 2
```

---

## 4f — HORIZON SIGNALS

```yaml
horizon_signals:
  - signal_id: HORIZON_BTC_CORP_ADOPTION_INFLECTION
    category: crypto
    direction: BULLISH
    horizon: 18_months
    trigger: "BTC treasury company count crosses 500 (currently 180+)"
    implication: >
      If 500+ public companies hold BTC, institutional ownership becomes normalized
      for equity index inclusion criteria. Structural demand floor established.
    confidence: 0.60
    source: saylor-bitcoin-thesis-20260422
    date: 2026-04-22

  - signal_id: HORIZON_STRC_YIELD_SPREAD_WATCH
    category: crypto + macro
    direction: NEUTRAL
    horizon: 12_months
    trigger: "Federal Reserve rate cuts compress fiat money market below 3.0%"
    implication: >
      STRC/BTC-backed yield spread widens further. Retail demand inflection point
      if spread exceeds 800bps while fiat deposits fall below 3%. Watch for STRC
      product capacity constraints.
    confidence: 0.65
    source: saylor-bitcoin-thesis-20260422
    date: 2026-04-22

  - signal_id: HORIZON_FINANCIAL_REPRESSION_BTC_ARB
    category: macro + crypto
    direction: BULLISH
    horizon: 24_months
    trigger: "Japan / Switzerland BTC treasury company launches with >$1B AUM"
    implication: >
      Validates financial repression arbitrage thesis. Watch MetaPlanet AUM growth
      as leading indicator. If spread capture math holds, capital flows from
      Eurozone pension funds seeking yield above local negative rates.
    confidence: 0.60
    source: saylor-bitcoin-thesis-20260422
    date: 2026-04-22
```

---

## 4j — SPEAKER INDEX UPDATE

```yaml
speaker_index_update:
  name: Michael Saylor
  slug: michael-saylor
  org: Strategy (formerly MicroStrategy)
  role: Executive Chairman
  tier: 2
  promoter_flag: true
  first_appearance: saylor-bitcoin-thesis-20260422
  appearance_count: 1
  topics: [bitcoin, treasury, digital-credit, financial-repression, protocol-war, tokenization]
  wiki_article: wiki/articles/michael-saylor.md
```

---

## 4k — PREDICTION LEDGER ENTRIES

```yaml
predictions:
  - id: PRED_SAYLOR_BTC_21M_20260422
    claim: "Bitcoin reaches $21 million per coin"
    speaker: michael-saylor
    date: 2026-04-22
    horizon: 21_years
    direction: BULLISH
    metric: BTC_USD_PRICE
    target: 21000000
    current: ~115000
    confidence: 0.30
    status: OPEN
    resolution_date: 2047

  - id: PRED_SAYLOR_BTC_29PCT_ARR_20260422
    claim: "Bitcoin appreciates 29% annually for next 21 years"
    speaker: michael-saylor
    date: 2026-04-22
    horizon: 21_years
    direction: BULLISH
    metric: BTC_USD_CAGR
    target: 0.29
    confidence: 0.30
    status: OPEN
    resolution_date: 2047

  - id: PRED_SAYLOR_CORP_ADOPTION_500_20260422
    claim: "1,000+ public companies hold BTC by late 2027"
    speaker: michael-saylor
    date: 2026-04-22
    horizon: 18_months
    direction: BULLISH
    metric: PUBLIC_CO_BTC_COUNT
    target: 1000
    current: 180
    confidence: 0.55
    status: OPEN
    resolution_date: 2027-12-31

  - id: PRED_SAYLOR_TOKENIZATION_CLARITY_20260422
    claim: "Tokenization regulatory clarity codified before 2028"
    speaker: michael-saylor
    date: 2026-04-22
    horizon: "< 2028"
    direction: NEUTRAL
    metric: US_TOKENIZATION_LAW_STATUS
    confidence: 0.55
    status: OPEN
    resolution_date: 2028-01-01
```

---

## STATUS

- [x] 4a: Wiki cross-reference — 0 existing, 2 new to create
- [x] 4b: Wiki articles drafted (michael-saylor, bitcoin-treasury-business-model)
- [x] 4c: DOCTRINE evidence YAML (CRYPTO_BTC_STORE_OF_VALUE)
- [x] 4d: 2 SOMA rules added
- [x] 4e: PRISM routing YAML
- [x] 4f: 3 HORIZON signals
- [x] 4g: VAULT check — skipped (BTC not covered; MSTR not in VAULT)
- [x] 4j: Speaker index entry
- [x] 4k: 4 prediction ledger entries
