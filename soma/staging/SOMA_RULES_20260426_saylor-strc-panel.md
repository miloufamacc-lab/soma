# SOMA Rule Extractions — Saylor/Le Panel 2026-04-26

<!-- RULE_BLOCK: EQUITIES_DURATION_STACK_FRAMEWORK_V1 -->
rule_id: EQUITIES_DURATION_STACK_FRAMEWORK_V1
source_module: PRISM
domain: equities
rule_data:
  - "Phong Le's three-layer duration framework for digital balance-sheet products:"
  - "Layer 1 (BTC, capital): >4-year horizon — wealth storage, no yield, max volatility"
  - "Layer 2 (STRC, credit): 3-month to 4-year horizon — 11.5% target yield, ~22% volatility"
  - "Layer 3 (digital money, settlement): <3-month horizon — ~zero volatility, near-stable price"
  - "Same investor holds all three; durations not mutually exclusive; STRC competes with HY/private credit, L3 competes with money-market funds"
confidence: 0.65
source_transcript: "Saylor + Phong Le + Lavish panel, 2026-04-26 (a33f474c)"
transcript_hash: "a33f474c"
<!-- END_RULE_BLOCK -->

<!-- RULE_BLOCK: EQUITIES_BTC_PER_SHARE_KPI_V1 -->
rule_id: EQUITIES_BTC_PER_SHARE_KPI_V1
source_module: PRISM
domain: equities
rule_data:
  - "MSTR's primary valuation KPI is Bitcoin-per-share (BPS), not GAAP EPS"
  - "BTC Yield = period-over-period change in BPS"
  - "BTC Gain = BTC held at period start × BTC Yield"
  - "Disclosed history: 2024=74%, 2025=22.8%"
  - "Long-term target: double BPS over 7 years (~10.4% CAGR)"
  - "An equity transaction is 'accretive' iff it increases near-term OR long-term BPS"
  - "1-in-20 to 1-in-50 transactions may be short-term dilutive but credit-positive (acceptable trade-off)"
confidence: 0.85
source_transcript: "Saylor + Phong Le + Lavish panel, 2026-04-26 (a33f474c)"
transcript_hash: "a33f474c"
<!-- END_RULE_BLOCK -->

<!-- RULE_BLOCK: MACRO_CREDIT_SQUEEZE_SEQUENCE_V1 -->
rule_id: MACRO_CREDIT_SQUEEZE_SEQUENCE_V1
source_module: PRISM
domain: macro
rule_data:
  - "Saylor's time-staged credit displacement thesis (digital credit replacing physical):"
  - "Phase 1 (years 1-5): High-yield / junk corporate compressed first"
  - "Phase 2 (years 6-10): Investment-grade corporate credit pressured"
  - "Phase 3 (years 11-20): Mortgage-backed and remaining IG categories squeezed"
  - "Sovereign credit explicitly NOT in scope (claim: governments will not feel threatened)"
  - "Investable framing: short HYG/JNK on 5y horizon; mortgage REITs face 20y compression"
  - "Red-team caveat: NAIC/ERISA capital-charge regime is the binding constraint, not yield differential"
confidence: 0.50
source_transcript: "Saylor at Bitcoin conference panel, 2026-04-26 (a33f474c)"
transcript_hash: "a33f474c"
<!-- END_RULE_BLOCK -->

<!-- RULE_BLOCK: BEHAVIORAL_PANEL_UNIFORMITY_FLAG_V1 -->
rule_id: BEHAVIORAL_PANEL_UNIFORMITY_FLAG_V1
source_module: PRISM
domain: behavioral
rule_data:
  - "When a multi-speaker panel exhibits zero contested topics and uniform conviction, treat as ONE source not N independent sources"
  - "Indicators: hedge_ratio < 0.05 across all speakers, no 'disagree' interactions, audience challenges deflected"
  - "Saylor + Phong Le + Lavish panel exhibits all three indicators on 2026-04-26"
  - "Adjustment: do NOT boost confidence by +0.10 for 'multi-source agreement' when sources are coordinated"
confidence: 0.70
source_transcript: "Saylor + Phong Le + Lavish panel, 2026-04-26 (a33f474c)"
transcript_hash: "a33f474c"
<!-- END_RULE_BLOCK -->
