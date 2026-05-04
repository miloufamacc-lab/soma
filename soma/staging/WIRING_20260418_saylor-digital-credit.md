# WIRING Manifest — INTEL_20260418_01_saylor-digital-credit
Generated: 2026-04-18 | Transcript: Saylor monologue ~50 min (pasted text) | Skill: transcript-to-intel V3.0 | Mode: STANDARD

---

## PPTX Deliverable
- **File:** `intel/by-topic/digital-assets/btc/capital-structure/INTEL_20260418_01_saylor-digital-credit.pptx`
- **Slides:** 26 | **Palette:** Charcoal Minimal | **Accent:** Gold (D4AC0D)
- **PRISM primary:** crypto | **Secondary:** macro | **Tertiary:** equities
- **QA status:** PASSED — 26 slides visually verified, all fixes applied (2-build cycle)

---

## Wiki Articles
| Action | Slug | Path | Notes |
|--------|------|------|-------|
| CREATE/UPDATE | strc-preferred-stock | wiki/compiled/crypto/digital-credit/strc-preferred-stock.md | New claim: 0% principal loss through 45% BTC drawdown; programmable L3 vision |
| UPDATE | mstr | wiki/compiled/finance/companies/mstr.md | Stat: #3 most volatile S&P 500, #1 OI/mktcap; $55B BTC holdings |
| CREATE | michael-saylor | wiki/compiled/finance/speakers/michael-saylor.md | Speaker profile: T2* (downgraded from T1 — PROMOTER conflict, issuer of STRC) |
| CREATE | digital-credit-framework | wiki/compiled/crypto/frameworks/digital-credit-framework.md | New concept: stochastic duration, digital stack L1/L2/L3, signal processing analogy |
| CREATE | investment-company-act-1940-crypto | wiki/compiled/regulatory/ica-1940-crypto-moat.md | ICA 1940 as regulatory moat for Strategy — Bitcoin non-security classification |

---

## PRISM Routing
```yaml
file: shared/soma/staging/PRISM_20260418_saylor-digital-credit.yaml
primary_category: crypto
secondary_category: macro
tertiary_category: equities
routes:
  - domain: crypto
    pipeline: COBALT
    score: 9
    trigger: STRC instrument design, Bitcoin credit ecosystem
  - domain: macro
    pipeline: TITAN
    score: 7
    trigger: Duration mismatch framework, credit market TAM
  - domain: equities
    pipeline: TITAN
    score: 6
    trigger: MSTR volatility stats, S&P positioning, options OI
signal_density: HIGH (12 claims scored 7+)
speaker_conflict: PROMOTER — all product claims confidence-adjusted -0.10 to -0.15
```

---

## DOCTRINE Evidence
```yaml
file: shared/soma/staging/DOCTRINE_20260418_saylor-digital-credit.yaml
beliefs_matched:
  - id: CRYPTO_BTC_STORE_OF_VALUE
    direction: SUPPORTING
    evidence: "Saylor frames BTC as monetary base layer with ~30% expected ARR; entire STRC structure depends on BTC appreciation"
    confidence_delta: +0.05 (strong, but promoter-conflicted source)
  - id: MACRO_FISCAL_DOMINANCE
    direction: SUPPORTING
    evidence: "25x income differential vs T-bills framed as generational capital migration; duration mismatch risk (LTCM/Lehman) cited"
    confidence_delta: +0.00 (framework consistent, no new data)
  - id: CRYPTO_DEFI_SELF_CUSTODY
    direction: NEUTRAL
    evidence: "Focus on institutional credit structure; no self-custody discussion"
    confidence_delta: 0
new_belief_candidates:
  - id: CRYPTO_DIGITAL_CREDIT_DISRUPTION_CANDIDATE
    status: CANDIDATE
    description: "Bitcoin-backed preferred credit instruments (STRC-type) may disrupt traditional credit markets by offering equity-correlated returns with synthetic credit safety"
    confidence: 0.45
    red_flags: [PROMOTER_CONFLICT, LUNA_UST_STRUCTURAL_ANALOG, FORWARD_LOOKING_TAM_OVERSTATED]
    review_required: true
```

---

## SOMA Rules (Candidates)
| Rule ID | Description | Trigger Condition |
|---------|-------------|-------------------|
| CRYPTO_STOCHASTIC_DURATION_V1 | Rank capital by probabilistic time horizon (stochastic duration), not stated maturity | When evaluating capital structure for any BTC-collateralized instrument |
| CRYPTO_PREFERRED_CREDIT_SAFETY_AUDIT_V1 | Any preferred stock claiming principal protection on BTC-collateral must be stress-tested at 45%, 60%, 77% BTC drawdown scenarios | When STRC or equivalent instrument is analyzed |
| MACRO_DIGITAL_CREDIT_TAM_FLOOR_V1 | Addressable TAM for BTC-backed credit = $10-15T (corporate + sovereign debt subset), NOT $300T (total global credit incl. retail/mortgage) | When speaker cites $300T+ TAM for digital credit |

---

## HORIZON Signals
```yaml
file: shared/soma/staging/HORIZON_20260418_saylor-digital-credit.yaml
signals:
  - id: STRC_BANKING_ADOPTION
    description: OCC/Basel recognition of BTC as Tier 1 collateral would unlock bank use of STRC as institutional product
    direction: BULLISH
    horizon: months_to_quarters
    confidence: 0.55
    red_flag: false
  - id: IRS_TAX_RECLASSIFICATION_RISK
    description: IRS reclassification of STRC distributions from return-of-capital to ordinary income would destroy primary value proposition for taxable investors
    direction: BEARISH
    horizon: quarters_to_years
    confidence: 0.60
    red_flag: true
  - id: BTC_SECURITY_RECLASSIFICATION_RISK
    description: Any Congressional action to reclassify BTC as a security would invalidate the ICA 1940 moat and the STRC structure
    direction: BEARISH
    horizon: years
    confidence: 0.35
    red_flag: true
  - id: STRATEGY_L3_ECOSYSTEM
    description: Saylor claims 4+ ecosystem partners building L3 programmable money products on STRC; materialization would validate L2 credit layer thesis
    direction: BULLISH
    horizon: quarters
    confidence: 0.45
    red_flag: false
    promoter_flagged: true
```

---

## Speaker Index Updates
| Speaker | Tier | Role | Bias | Conflicts | Prior Intel |
|---------|------|------|------|-----------|-------------|
| Michael Saylor | T2* (downgraded from T1) | Executive Chairman, Strategy/MicroStrategy | EXTREME BULLISH — Bitcoin maximalist, STRC issuer | Holds MSTR equity, personal BTC, issuer of STRC — MATERIAL FINANCIAL CONFLICT on all product claims | Check SCRATCHPAD_20260417 for prior coverage |

---

## Intel Folder Registration
- **File path:** `intel/by-topic/digital-assets/btc/capital-structure/INTEL_20260418_01_saylor-digital-credit.pptx`
- **Date symlink:** `intel/by-date/2026/04-April/18/` → (run `intel_daily.py register` to create)
- **DAILY_INDEX.md entry:** `- [INTEL_20260418_01] Saylor: Digital Credit / STRC instrument design, stochastic duration framework, reflexive flywheel thesis — crypto/capital-structure`

---

## Red Flags Summary (for SOMA ingestion)
1. **PROMOTER CONFLICT** — Saylor is issuer of STRC, holder of MSTR equity and personal BTC. All product performance claims confidence-adjusted.
2. **LUNA/UST ANALOG** — Reflexive flywheel (STRONG counter). Structurally identical mechanism failed catastrophically May 7-13, 2022 ($40B → $0).
3. **TAM OVERSTATED** — $300T addressable credit market is total global credit; realistic addressable = $10-15T.
4. **TAX TREATMENT FORWARD-LOOKING** — 18-23% TEY is contingent on IRS maintaining current return-of-capital classification (FASB ASU 2023-08 creates distributable earnings risk).
5. **DRAWDOWN WINDOW CHERRY-PICKED** — 45% drawdown safety window uses 2022 low; BTC has seen -77%, -84%, -93% drawdowns in prior cycles.
