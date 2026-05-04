<!-- RULE_BLOCK: EQ_STOCHASTIC_DURATION_LADDER_V1 -->
rule_id: EQ_STOCHASTIC_DURATION_LADDER_V1
source_module: PRISM
domain: equities
rule_data:
  - "Capital sources ranked by realistic time-of-use ('stochastic duration'):"
  - "  - Exchange leverage (50x-10x): ~1 hour (margin call risk)"
  - "  - Repo / asset-back financing: ~1 day (one margin call away)"
  - "  - Senior debt with covenants: ~1 year (covenants checked quarterly)"
  - "  - Junior / convertible debt: ~5-7 years (no covenants but large interest bill)"
  - "  - Senior preferred: longer than debt but covenanted"
  - "  - Junior / variable preferred: longest duration short of equity (no covenants, dividend can flex)"
  - "  - Common equity: ~100 years (NPV horizon)"
  - "Rule: For Bitcoin-treasury issuers, prefer variable preferred over senior debt for any capital intended to fund long-duration BTC accumulation."
  - "Anti-pattern: financing long-duration assets with short-duration money — see Lehman, LTCM, Silvergate."
confidence: 0.65
source_transcript: "Saylor — Digital Credit keynote 2026-04-25"
transcript_hash: "2e310387"
<!-- END_RULE_BLOCK -->

<!-- RULE_BLOCK: EQ_REFLEXIVE_FLYWHEEL_V1 -->
rule_id: EQ_REFLEXIVE_FLYWHEEL_V1
source_module: PRISM
domain: equities
rule_data:
  - "Bitcoin-treasury equity premium (mNAV) is sustained by a reflexive loop:"
  - "  1. Credit issuance funds Bitcoin purchases"
  - "  2. Bitcoin purchases grow Bitcoin-per-share"
  - "  3. Bitcoin-per-share growth expands the equity premium"
  - "  4. Equity premium attracts new investor pools"
  - "  5. New capital fuels more credit issuance"
  - "Loop is symmetric — reverses violently if mNAV touches 1.0x or below (precedents: MSTR Nov 2022, MSTR Aug 2024, GBTC -49% Dec 2022)"
  - "Operational rule: monitor mNAV; if mNAV < 1.10x, halt ATM equity issuance (becomes dilutive)"
  - "Operational rule: monitor BTC ARR; loop requires sustained 25%+ to compound BTC-per-share faster than dilution"
confidence: 0.50
source_transcript: "Saylor — Digital Credit keynote 2026-04-25"
transcript_hash: "2e310387"
notes: "Borrowed from Soros reflexivity (uncredited by Saylor). Steelman STRONG — symmetric reversal is the dominant risk."
<!-- END_RULE_BLOCK -->

<!-- RULE_BLOCK: EQ_VARIABLE_RATE_PAR_DEFENSE_V1 -->
rule_id: EQ_VARIABLE_RATE_PAR_DEFENSE_V1
source_module: PRISM
domain: equities
rule_data:
  - "Variable-rate perpetual preferred can defend par via dividend reset, BUT:"
  - "  - Mechanism unstressed below ~3x collateral coverage ratio"
  - "  - 6-month STRC track record (45% BTC drawdown) ran with ~5x coverage — par defense was easy"
  - "  - Auction-rate securities (2008, $330B) had similar par mechanism that broke when forced rate-hike spiral kicked in"
  - "Operational rule: if BTC/preferred coverage falls below 3x, re-underwrite STRC NAV scenarios for tail-event price action"
  - "Operational rule: STRC at par + paying yield through a 50%+ BTC drawdown is the real test"
confidence: 0.60
source_transcript: "Saylor — Digital Credit keynote 2026-04-25"
transcript_hash: "2e310387"
<!-- END_RULE_BLOCK -->

<!-- RULE_BLOCK: EQ_ROC_TAX_CLASSIFICATION_RISK_V1 -->
rule_id: EQ_ROC_TAX_CLASSIFICATION_RISK_V1
source_module: PRISM
domain: equities
rule_data:
  - "STRC return-of-capital tax classification depends on issuer having no current or accumulated E&P"
  - "FASB ASU 2023-08 (effective fiscal years after Dec 15 2024) requires MSTR to mark Bitcoin to fair value through income statement"
  - "If FV gains generate positive E&P, IRS may reclassify STRC distributions as ordinary dividends"
  - "Operational rule: tax-equivalent yield of 14-23% only holds if ROC classification survives FASB-driven E&P math"
  - "Operational rule: monitor MSTR 10-Q E&P disclosures; reduce STRC TEY assumption to ordinary-dividend treatment if positive E&P emerges"
confidence: 0.65
source_transcript: "Saylor — Digital Credit keynote 2026-04-25 (counter-evidence from FASB)"
transcript_hash: "2e310387"
<!-- END_RULE_BLOCK -->
