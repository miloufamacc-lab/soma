---
source: "Jack Mallers Show Ep. 113 — Bitcoin and the Bigger Shovel"
date: 2026-04-15
transcript_hash: "526802c1"
skill: transcript-to-intel V2.1
deliverable_pptx: "intel/macro/regime/INTEL_20260415_01_jm-ep113-bitcoin-bigger-shovel.pptx"
---

# DABEIBA Wiring — JM Ep. 113 (2026-04-15)

Single consolidated wiring manifest replacing separate PRISM/DOCTRINE/HORIZON YAMLs + Slide 14 of the PPTX.

## PRISM Routing

| Category | Pipeline | Module | Relevance | Tags |
|---|---|---|---|---|
| macro | TITAN | ORACLE | 9 | hormuz, oil-shock, private-credit, fed-trap, dollar-debasement, gold-trade |
| crypto | COBALT | ORACLE | 9 | iran-btc, sovereign-settlement, btc-vs-gold, monetary-network, reserve-currency |
| geopolitical | SPECTRE | ORACLE | 8 | iran-us-war, ceasefire-theater, rare-earths, insider-trading, petrodollar |
| philosophy | DOCTRINE | SOMA | 6 | taxes, libertarian, el-salvador, bukele, fiat-critique |
| risk | FORGE | ORACLE | 8 | private-credit, cre-collapse, consumer-default, ai-deflation |

Primary: macro/TITAN. Transcript is cross-domain (macro + crypto + geopolitical) — fans out to 5 categories.

## DOCTRINE Evidence

All weights = 1.0 (Tier 2 speaker, Mallers).

**Supports existing beliefs (4):**
- `MACRO_ENERGY_STRUCTURAL` — Hormuz closure = 20% global oil offline; $100 vs -$40 last QE cycle
- `MACRO_FISCAL_DOMINANCE` — Fed trapped (oil inflation vs AI deflation); dollar debasement framed as only exit
- `CRYPTO_BTC_STORE_OF_VALUE` — FT: Iran sovereign BTC settlement (first hostile-state mainstream report)
- `RISK_DRAWDOWN_ASYMMETRY` — 1973 parallel: S&P took 12mo to reprice; current rally may be false confidence

**Candidate (new):**
- `GEOPOLITICAL_PETRODOLLAR_COLLAPSE_CANDIDATE` — conviction 6. Statement: "Petrodollar system is actively failing — Iran/China using gold and BTC to settle energy trade, bypassing dollar enforcement." Status: CANDIDATE (needs 1 more independent corroboration to promote).

## HORIZON Timing Signals

| Lens | Direction | Timeframe | Conf | Signal |
|---|---|---|---|---|
| MACRO | BEARISH | months | 0.55 | 1973 parallel: S&P took 12mo to digest oil shock; current rally could be bull trap |
| CREDIT_LIQUIDITY | BEARISH | weeks | 0.85 | Private credit redemptions surging (Blue Owl 22%, Carlyle 16%); Fed probing — crisis in weeks–months |
| MACRO | BULLISH | weeks | 0.70 | Hayes USD liquidity up (short-term risk-on) vs Howell global liquidity down — divergence |
| GEOPOLITICAL | BEARISH | months | 0.70 | Strait of Hormuz structurally closed; no ceasefire in sight; Trump escalating blockade |

## Wiki Articles Created

- `wiki/compiled/finance/geopolitical/strait-of-hormuz.md`
- `wiki/compiled/crypto/concepts/bitcoin-monetary-network.md`
- `wiki/compiled/finance/macro/private-credit-crisis-2026.md`
- `wiki/compiled/finance/qna/2026-04-15-jm-ep113-bitcoin-bigger-shovel.md` (QnA summary)

## Staging Files Superseded

This manifest replaces the following (kept as archive, no longer canonical):
- `PRISM_20260415_jm-ep113-bitcoin-bigger-shovel.yaml`
- `DOCTRINE_20260415_jm-ep113-bitcoin-bigger-shovel.yaml`
- `HORIZON_20260415_jm-ep113-bitcoin-bigger-shovel.yaml`

## Scratchpad

Full CoT analysis: `SCRATCHPAD_20260415_jm-show-ep113-bitcoin-bigger-shovel.md`

## Red Flags (carried forward)

- **Promoter's Dilemma (2 claims):** BTC 200x upside (conf 0.40) + sovereign BTC mining (conf 0.45) — Mallers high conviction + BTC conflict.
- **Anonymous sources:** Sanctioned states mining BTC claim sourced from unnamed insiders via conflicted speaker.
- **Conflict flag:** BTC-vs-Gold framework discounted — Mallers runs two Bitcoin companies.

## Ingest Commands

```
python3 wiki/tools/wiki_ingest.py \
  wiki/compiled/finance/geopolitical/strait-of-hormuz.md \
  wiki/compiled/crypto/concepts/bitcoin-monetary-network.md \
  wiki/compiled/finance/macro/private-credit-crisis-2026.md \
  wiki/compiled/finance/qna/2026-04-15-jm-ep113-bitcoin-bigger-shovel.md

python3 shared/soma/ingest_staging.py --manifest WIRING_20260415_jm-ep113-bitcoin-bigger-shovel.md
```
