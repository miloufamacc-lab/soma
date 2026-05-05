# HORIZON Pipeline — Build Plan (V2 — Cross-AI Consensus)

**Pipeline:** HORIZON — Holistic Observation & Risk-Informed Zone of Optimal Navigation
**Module:** SOMA (PROCESS stage)
**Purpose:** Cross-signal tactical timing engine that answers "when should I act on this portfolio?"
**Reviewed by:** Claude (CFA KB synthesis) + Grok (Expert mode, 55s thought, 105 sources) + Gemini (Thinking mode, Pro)

---

## Decisions (Locked — April 2, 2026)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Pipeline name | **HORIZON** | User decision, functional and clear |
| Lens count | **7 lenses** | +Bitcoin On-Chain (Grok priority #1) + Credit/Liquidity (all 3 AIs agree) |
| Weight philosophy | **Grok Expert-mode** | MACRO domain 45% total (regime gate primary filter) |
| Synthesis method | **Hierarchical** | Regime gate → concordance → weighted (CFA + Grok + Gemini unanimous) |
| Probability engine | **Full 10k-path Monte Carlo** | Bayesian priors + regime-conditioned GBM/EGARCH paths |
| Behavioral bias | **Meta-layer** (audit output, not signal input) | Grok: lower priority for automated pipeline; CFA: monitor 12 biases |
| Data staleness | **Halflife decay** on confidence (Gemini recommendation) | 48h+ → linear confidence discount |

---

## What HORIZON Does

Takes a portfolio position question (e.g. "when to liquidate 16.8% TSLA, 6.17% MSTR, 77% money market") and synthesizes ALL available DABEIBA intelligence into a probability-weighted timing recommendation.

**Input:** A natural-language portfolio timing question
**Output:** A structured, grounded analysis with Monte Carlo probability distributions across time windows

---

## Why It Belongs in SOMA

Per Architecture V2 scaling rule: new **processing function** → SOMA pipeline.
HORIZON doesn't collect new data (that's ORACLE) or make execution decisions (that's MANTIS).
It **synthesizes** existing signals into actionable intelligence — that's SOMA's job.

---

## Architecture Overview (V2 — 7 Lenses + Hierarchical Synthesis)

```
                    ┌─────────────────────────────┐
                    │       USER QUESTION          │
                    │  "When to liquidate..."      │
                    └─────────────┬────────────────┘
                                  │
                    ┌─────────────▼────────────────┐
                    │    HORIZON ORCHESTRATOR       │
                    │  shared/soma/horizon.py       │
                    └─────────────┬────────────────┘
                                  │
                    ┌─────────────▼────────────────┐
                    │     ① REGIME GATE             │
                    │  MACRO lens runs FIRST        │
                    │  Determines validity window   │
                    │  If CRISIS → override to      │
                    │  REDUCE_NOW (skip concordance) │
                    └─────────────┬────────────────┘
                                  │
      ┌─────────┬─────────┬───────┼───────┬─────────┬─────────┐
      ▼         ▼         ▼       ▼       ▼         ▼         ▼
 ┌────────┐┌────────┐┌────────┐┌──────┐┌────────┐┌────────┐┌────────┐
 │ MACRO  ││BITCOIN ││CREDIT/ ││FUND. ││ TECH.  ││ SENT.  ││ GEO/   │
 │ 35%    ││ON-CHAIN││LIQUID. ││ 15%  ││ 12%    ││  9%    ││ EVENT  │
 │        ││ 12%    ││ 10%    ││      ││        ││        ││  7%    │
 └───┬────┘└───┬────┘└───┬────┘└──┬───┘└───┬────┘└───┬────┘└───┬────┘
     │         │         │        │        │         │         │
     │      SOMA DATA LAYER (soma.db + live fetches + web)     │
     └────┬────┴────┬────┴────┬───┴───┬────┴────┬────┴────┬────┘
          │         │         │       │         │         │
     ┌────▼─────────▼─────────▼───────▼─────────▼─────────▼────┐
     │         ② CONCORDANCE CHECK                              │
     │  Count lenses in agreement (same direction)              │
     │  Threshold: ≥4/7 must agree before action                │
     │  If <4/7 → HOLD (insufficient concordance)              │
     └──────────────────────┬──────────────────────────────────┘
                            │ (only if concordance passes)
     ┌──────────────────────▼──────────────────────────────────┐
     │         ③ WEIGHTED SYNTHESIS                             │
     │  Combine passing lens signals using weights              │
     │  Generate composite score per time window                │
     └──────────────────────┬──────────────────────────────────┘
                            │
     ┌──────────────────────▼──────────────────────────────────┐
     │         ④ MONTE CARLO PROBABILITY ENGINE                 │
     │  10,000 paths per time window                            │
     │  Bayesian priors from regime transition base rates       │
     │  GBM + EGARCH vol modeling per asset                     │
     │  Output: probability distributions + confidence bands    │
     └──────────────────────┬──────────────────────────────────┘
                            │
     ┌──────────────────────▼──────────────────────────────────┐
     │         ⑤ BEHAVIORAL BIAS AUDIT (Meta-Layer)             │
     │  Scans synthesis output for 12 CFA cognitive biases      │
     │  Flags: loss aversion, anchoring, confirmation,          │
     │         overconfidence, recency, disposition effect,      │
     │         status quo, framing, hindsight, herding,          │
     │         regret aversion, mental accounting                │
     │  Adjusts confidence if bias detected (does NOT alter      │
     │  the signal — only adds warnings + confidence discount)   │
     └──────────────────────┬──────────────────────────────────┘
                            │
     ┌──────────────────────▼──────────────────────────────────┐
     │         ⑥ STRUCTURED OUTPUT                              │
     │  Time windows + probabilities + confidence +             │
     │  bias warnings + per-holding breakdown + rationale       │
     └─────────────────────────────────────────────────────────┘
```

---

## The 7 Analytical Lenses (Grok Expert-mode Weights)

### LENS 1: MACRO (weight: 35%) — REGIME GATE
**Source:** SOMA regime_history + GLI components
**What it reads:**
- Current regime (RISK_ON / NORMAL / TURBULENCE / CRISIS)
- GLI value + 3-month momentum + direction
- Diffusion index (% of adverse signals)
- GLI components: VIX, UST 10Y, DXY, HY spread, stress index, 2Y-10Y spread
- Regime streak (how long in current regime)
- Historical regime transitions (when similar levels led to shifts)

**What it produces:**
- Macro timing signal: HOLD / REDUCE_SOON / REDUCE_NOW / ACCUMULATE
- Confidence: 0.0–1.0
- Key driver explanation
- Historical parallel (last time macro looked like this, what happened)
- **REGIME GATE decision:** Does the current regime ALLOW action? (CRISIS = force REDUCE_NOW, TURBULENCE = caution flag, NORMAL/RISK_ON = lenses proceed normally)

**Rationale for 35%:** Grok Expert: "TSLA carries EV/tech/growth beta and MSTR functions as leveraged BTC proxy; both exhibit extreme sensitivity to liquidity, volatility, and risk-on/risk-off regime shifts." Combined with Credit/Liquidity lens (10%), total macro-domain influence = 45%, matching Grok's recommendation.

### LENS 2: BITCOIN ON-CHAIN (weight: 12%) — NEW
**Source:** Web search + on-chain data APIs
**What it reads:**
- NVT Ratio (Network Value to Transactions — BTC valuation metric)
- MVRV Z-Score (Market Value vs. Realized Value — overbought/oversold)
- SOPR (Spent Output Profit Ratio — holder behavior)
- Exchange net flows (inflows = selling pressure, outflows = accumulation)
- Long-term holder supply % (conviction indicator)
- MSTR-specific: BTC NAV premium/discount, convertible debt basis risk (Gemini flag)
- Derivative open interest / funding rates / liquidation levels

**What it produces:**
- On-chain signal: BTC_ACCUMULATION / BTC_NEUTRAL / BTC_DISTRIBUTION / BTC_CAPITULATION
- MSTR-specific signal: NAV premium/discount assessment
- Whale activity summary (large wallet movements)
- Confidence: 0.0–1.0

**Rationale:** Grok's #1 priority addition: "Directly augments macro for this book. MSTR without on-chain is like TSLA without S-curve tracking."

### LENS 3: CREDIT / LIQUIDITY (weight: 10%) — NEW
**Source:** Web search + FRED data
**What it reads:**
- Investment-grade (IG) corporate bond spreads (leads equities 3-6 months per CFA KB)
- High-yield (HY) spread widening/tightening trend
- Volatility Risk Premium (VRP): realized vol vs. implied vol → VRP collapse = early warning
- TED spread or equivalent interbank stress indicator
- Fed balance sheet direction (QT pace changes)
- Money market fund flows (relates directly to the 77% MM position)

**What it produces:**
- Credit signal: LIQUIDITY_FLUSH / NEUTRAL / TIGHTENING / STRESS
- VRP status: NORMAL / COMPRESSING / COLLAPSED (early warning)
- Leading indicator score (where credit conditions point equities in 3-6 months)
- Confidence: 0.0–1.0

**Rationale:** CFA KB + all 3 AIs agree: "IG spreads lead equities 3-6 months" is one of the strongest empirical findings in cross-asset research. VRP collapse preceded every major drawdown in the last decade.

### LENS 4: FUNDAMENTAL (weight: 15%)
**Source:** SOMA valuations table + ORACLE fair values
**What it reads:**
- Per-ticker: fair_value vs. current_price → implied_upside
- Execution score (quality metric)
- Valuation trend (last 5 data points per ticker — improving or deteriorating?)
- Portfolio-weighted average upside
- CFA KB valuation methodology context
- TSLA: revenue mix shift toward Energy and AI-Robotics vs. traditional Auto (Gemini flag)
- MSTR: BTC-to-NAV tracker + convertible debt leverage/dilution risk (Gemini flag)

**What it produces:**
- Fundamental timing signal per ticker: OVERVALUED / FAIR / UNDERVALUED
- Portfolio-level signal: overall positioning attractiveness
- Which holdings are most/least attractive to hold right now
- Margin of safety assessment

### LENS 5: TECHNICAL (weight: 12%)
**Source:** Live price data (web fetch) + MANTIS momentum calculations
**What it reads:**
- 63-day momentum per ticker (CFA factor, already in v2_regime.py)
- 20-day realized volatility vs. 90-day median (vol regime from MANTIS)
- Drawdown from 252-day high-water mark per ticker
- Simple trend: price vs. 50-day and 200-day moving averages
- Volume trend (if available)
- Exhaustion signals (Gemini: look for bottom signals before deploying 77% cash)

**What it produces:**
- Technical timing signal: TRENDING_UP / NEUTRAL / BREAKING_DOWN / OVERSOLD
- Vol regime: LOW_VOL / NORMAL_VOL / HIGH_VOL / EXTREME_VOL
- Drawdown proximity to MANTIS tier thresholds
- Optimal exit/entry window based on technical setup

### LENS 6: SENTIMENT & FLOW (weight: 9%)
**Source:** Web search + MUSKONOMY SITREP (for TSLA) + raw_intelligence table
**What it reads:**
- Latest news sentiment per ticker (web search, 3-5 recent articles)
- MUSKONOMY S-curve data (TSLA specific: robotaxi progress, FSD adoption, etc.)
- Analyst consensus direction (upgrade/downgrade trend)
- Options flow / put-call ratio if available (web search)
- Insider transactions (web search)
- Retail sentiment indicators (Gemini: "for MSTR and TSLA, retail sentiment is a leading indicator")

**What it produces:**
- Sentiment signal: BULLISH / NEUTRAL / BEARISH / EXTREME_FEAR / EXTREME_GREED
- Catalyst calendar (upcoming known events: earnings, product launches, regulatory)
- Near-term risk events that could force a timing decision

### LENS 7: GEOPOLITICAL & EVENT (weight: 7%)
**Source:** Web search + SOMA raw_intelligence + SPECTRE (when built)
**What it reads:**
- Major upcoming macro events (FOMC meetings, CPI releases, tariff deadlines)
- Geopolitical risk events relevant to holdings
- Regulatory calendar (SEC deadlines, policy changes)
- Market structure events (options expiry, index rebalancing)
- Tech sovereignty / AI-nationalism risks for TSLA China operations (Gemini flag)

**What it produces:**
- Event risk calendar for the timing window
- Binary event flags (known dates that could move holdings significantly)
- Pre/post event positioning recommendation

---

## Weight Summary

| Lens | Weight | Domain |
|------|--------|--------|
| MACRO (regime + GLI) | 35% | Macro (gate) |
| Bitcoin On-Chain | 12% | Crypto-specific |
| Credit / Liquidity | 10% | Macro (leading) |
| Fundamental | 15% | Valuation |
| Technical | 12% | Price action |
| Sentiment & Flow | 9% | Behavioral |
| Geopolitical & Event | 7% | Calendar risk |
| **Total** | **100%** | |

**Macro-domain total (MACRO + Credit/Liquidity) = 45%** — matches Grok Expert-mode recommendation.

---

## Synthesis Engine (Hierarchical — Not Flat Average)

The synthesis engine follows the CFA-prescribed hierarchical approach (regime gates first, then concordance, then weighted synthesis). This reduces false-positive allocation changes by ~35-45% vs flat averaging (Grok estimate).

### Step 1: REGIME GATE (Macro Lens runs first)
- CRISIS regime → **automatic REDUCE_NOW** (skip concordance, immediate action)
- TURBULENCE regime → **caution flag** (require 5/7 concordance instead of 4/7)
- NORMAL/RISK_ON → proceed to concordance check normally

### Step 2: CONCORDANCE CHECK
- Count how many of the 7 lenses signal the same direction
- **Threshold: ≥4/7 lenses must agree** before any allocation change is recommended
- If <4/7 → output is **HOLD** with explanation of which lenses disagree and why
- CFA KB: "change allocation only when MAJORITY of signals agree in the same direction"
- In TURBULENCE: threshold raises to ≥5/7 (higher bar for action when macro is unstable)

### Step 3: WEIGHTED SYNTHESIS (only if concordance passes)
- Combine agreeing lens signals using the 7-lens weights
- Produce composite score per time window (-1.0 to +1.0)
- -1.0 = maximum urgency to liquidate now
- 0.0 = neutral / no timing edge
- +1.0 = strong reason to hold / accumulate

### Step 4: MONTE CARLO PROBABILITY ENGINE (10,000 paths)
For each time window (immediate / 1-2wk / 2-4wk / 1-3mo):

**Bayesian Priors:**
- Historical base rates from regime transitions (backtest GLI states against TSLA/MSTR returns)
- Prior probability of favorable exit per regime state
- Example: NORMAL regime → 52% base rate bullish, TURBULENCE → 38%, CRISIS → 22%

**Path Generation (10,000 paths per window):**
- GBM (Geometric Brownian Motion) for drift component
- EGARCH volatility model (captures volatility clustering + asymmetric leverage effect)
- Regime-conditioned parameters (different drift/vol per GLI state)
- Correlated draws for TSLA + BTC (MSTR tracks BTC with leverage amplification)
- Macro overlay: GLI momentum affects drift across all paths

**Bayesian Updating:**
- Use real-time signal concordance as likelihood
- Concordance strength (4/7, 5/7, 6/7, 7/7) calibrates the posterior
- Example: 40% historical base rate + 80% concordance likelihood → posterior ~53%

**Output per time window:**
- P(favorable exit) = % of paths where exiting in this window beats later windows
- P(adverse move) = % of paths with >5% loss if holding through this window
- Expected value delta vs. acting now
- 10th/25th/50th/75th/90th percentile outcomes (confidence bands)
- VaR (Value at Risk) at 95% and 99% confidence

### Step 5: BEHAVIORAL BIAS AUDIT (Meta-Layer)
Scans the synthesis output for 12 CFA-prescribed cognitive biases:

| Bias | Detection Method |
|------|-----------------|
| Loss aversion | Is the signal dominated by fear of loss vs. opportunity cost? |
| Anchoring | Is the analysis anchored to a recent price or purchase price? |
| Confirmation | Are only confirming lenses emphasized, disconfirming ones minimized? |
| Overconfidence | Is confidence >80% with <5/7 concordance? |
| Recency | Are recent events over-weighted vs. base rates? |
| Disposition effect | Is there reluctance to sell losers (TSLA/MSTR down YTD)? |
| Status quo | Is HOLD favored without strong evidence against action? |
| Framing | Does the question framing bias the output? (e.g., "liquidate" primes for selling) |
| Hindsight | Are past regime transitions presented as obvious in retrospect? |
| Herding | Is consensus sentiment driving the signal more than fundamentals? |
| Regret aversion | Is the analysis avoiding action to prevent future regret? |
| Mental accounting | Is each position analyzed in isolation vs. portfolio-level? |

**Action:** Flags detected biases in the output. Does NOT alter the signal — only adds warnings and applies a confidence discount (max -15% per bias detected, capped at -30% total).

### Step 6: DATA FRESHNESS DECAY (Gemini recommendation)
Confidence is discounted based on data staleness using a halflife decay:

```
freshness_factor = 0.5 ^ (hours_since_oracle_run / halflife_hours)
```

| Data Age | Halflife = 48h | Confidence Impact |
|----------|---------------|-------------------|
| 0-12h | 0.87-1.00 | Minimal |
| 12-24h | 0.76-0.87 | Slight discount |
| 24-48h | 0.50-0.76 | Moderate discount |
| 48-96h | 0.25-0.50 | Major discount + warning |
| >96h | <0.25 | STALE DATA WARNING — run ORACLE first |

---

## Output Structure

```
HORIZON TACTICAL TIMING ANALYSIS
═══════════════════════════════════════════════════════════
Question: "When to liquidate 16.8% TSLA, 6.17% MSTR, 77% MM?"
Analysis Date: 2026-04-02
Data Freshness: ORACLE run 2026-04-01 (23h ago) ✓ [freshness: 0.82]

─── REGIME GATE ───────────────────────────────────────────
Regime: NORMAL (since YYYY-MM-DD, X days)
GLI: XX.X (momentum: [direction])
Gate Decision: PROCEED (concordance threshold: 4/7)

─── CONCORDANCE CHECK ─────────────────────────────────────
Lenses in agreement: X/7 [PASS/FAIL]
Direction: [REDUCE / HOLD / ACCUMULATE]
Agreeing: [lens list]
Dissenting: [lens list + why]

─── COMPOSITE SIGNAL ──────────────────────────────────────
Overall Bias: [HOLD / REDUCE / LIQUIDATE / ACCUMULATE]
Composite Score: X.XX (-1.0 to +1.0)
Raw Confidence: XX%
Bias-Adjusted Confidence: XX% (biases detected: [list])
Freshness-Adjusted Confidence: XX%

─── MONTE CARLO PROBABILITY DISTRIBUTION ──────────────────
(10,000 paths per window, Bayesian regime-conditioned)

Time Window        | P(Optimal) | E[Move]  | VaR 95% | VaR 99% | Recommendation
─────────────────────────────────────────────────────────────────────────────────
Apr 2-4 (immed.)   |   XX%     | +/-X.X%  | -X.X%   | -X.X%   | [action]
Apr 7-11 (1wk)     |   XX%     | +/-X.X%  | -X.X%   | -X.X%   | [action]
Apr 14-18 (2wk)    |   XX%     | +/-X.X%  | -X.X%   | -X.X%   | [action]
Apr 21-May 2 (1mo) |   XX%     | +/-X.X%  | -X.X%   | -X.X%   | [action]

Percentile Outcomes (Portfolio-Level):
  10th: -X.X%  |  25th: -X.X%  |  50th: +X.X%  |  75th: +X.X%  |  90th: +X.X%

─── PER-HOLDING BREAKDOWN ─────────────────────────────────

TSLA (16.8% of portfolio):
  Macro:       [signal] (confidence)
  Bitcoin:     N/A (not BTC-exposed)
  Credit:      [signal] — [leading indicator status]
  Fundamental: Fair value $XXX vs. $XXX current → XX% upside
  Technical:   [trend], vol regime [X], DD from HWM: X%
  Sentiment:   [signal] — [key driver]
  Events:      [upcoming catalysts]
  → Holding-level recommendation: [action + timing]

MSTR (6.17% of portfolio):
  Macro:       [signal] (confidence)
  Bitcoin:     [on-chain signal] — BTC NAV premium/discount: X%
  Credit:      [signal] — [convertible debt basis risk]
  Fundamental: BTC NAV $XXX vs. MSTR price $XXX → XX% premium/discount
  Technical:   [trend], vol regime [X], DD from HWM: X%
  Sentiment:   [signal] — [key driver]
  Events:      [upcoming catalysts]
  → Holding-level recommendation: [action + timing]

Money Market (77%):
  → Opportunity cost: risk-free rate XX% annualized
  → Redeployment timing assessment (if applicable)
  → Tax-aware considerations (Quebec superficial loss rules)

─── BEHAVIORAL BIAS AUDIT ─────────────────────────────────
Biases Detected: [list with explanations]
Confidence Discount Applied: -X%
Recommendation: [any adjustments to consider]

─── LENS DETAIL ────────────────────────────────────────────
[Each lens's full reasoning, grounded in specific data points]

─── HISTORICAL PARALLEL ────────────────────────────────────
Last time macro/technical setup was similar: [date]
What happened: [outcome]
Relevance to current situation: [assessment]

─── KEY RISKS TO THIS ANALYSIS ─────────────────────────────
1. [Risk 1 — what could invalidate this timing]
2. [Risk 2]
3. [Risk 3]

─── SOMA GROUNDING ─────────────────────────────────────────
Regime: [current] since [date] (X days)
GLI: XX.X (momentum: [direction])
Last What Changed: [summary of last material change]
Portfolio State: [from MANTIS]
Data Sources Used: [list with freshness timestamps]

─── DISCLAIMER ─────────────────────────────────────────────
This is a personal advisory intelligence tool. NOT financial advice.
NOT client-facing. Probabilities are model estimates, not predictions.
Past regime transitions do not guarantee future outcomes.
Human judgment required for all final decisions.
```

---

## File Structure

```
shared/soma/
├── horizon.py                  ← Main orchestrator (NEW)
├── horizon_lenses/             ← One file per analytical lens (NEW)
│   ├── __init__.py
│   ├── macro_lens.py           ← Lens 1: regime gate + GLI + components (35%)
│   ├── btc_onchain_lens.py     ← Lens 2: NVT, MVRV, SOPR, exchange flows (12%)
│   ├── credit_liquidity_lens.py ← Lens 3: IG/HY spreads, VRP, TED (10%)
│   ├── fundamental_lens.py     ← Lens 4: valuations + fair value (15%)
│   ├── technical_lens.py       ← Lens 5: momentum + vol + drawdown (12%)
│   ├── sentiment_lens.py       ← Lens 6: news + flow + catalysts (9%)
│   └── event_lens.py           ← Lens 7: calendar + geopolitical (7%)
├── horizon_synthesis.py        ← Hierarchical engine: gate → concordance → weighted (NEW)
├── horizon_monte_carlo.py      ← 10k-path Bayesian MC probability engine (NEW)
├── horizon_bias_audit.py       ← Behavioral bias meta-layer (NEW)
├── horizon_output.py           ← Formatted terminal + markdown output (NEW)
└── horizon_dataclasses.py      ← LensResult, SynthesisResult, MCResult, BiasAudit (NEW)
```

---

## Data Dependencies (What Already Exists vs. What's New)

### Already Available in SOMA (no new code needed to read):
- [x] regime_history (GLI, regime, diffusion, momentum, components)
- [x] valuations (fair_value, current_price, implied_upside per ticker)
- [x] portfolio_state (positions, cash%, total value, DD from HWM)
- [x] trade_log (recent trades, regime at time of trade)
- [x] outlook_snapshots (latest CIPHER conclusions)
- [x] what_changed logs (recent material changes)
- [x] raw_intelligence (MUSKONOMY SITREPs for TSLA)
- [x] kb_rules (CFA methodology, risk framework)
- [x] v2_regime.py momentum + vol calculations (MANTIS)

### Needs Live Fetching (web search during analysis):
- [ ] Current prices (for real-time technical calculations)
- [ ] Recent news sentiment (per ticker)
- [ ] Upcoming event calendar (FOMC, CPI, earnings)
- [ ] Analyst consensus / upgrades-downgrades
- [ ] Options flow / put-call (if findable)
- [ ] Geopolitical risk headlines
- [ ] BTC on-chain metrics (NVT, MVRV, SOPR, exchange flows)
- [ ] IG/HY credit spreads (FRED or web)
- [ ] VRP data (implied vs realized vol)
- [ ] MSTR NAV premium/discount

### New SOMA Table:
- [ ] `horizon_analyses` — archive of past HORIZON runs for tracking accuracy over time

### New Python Dependencies:
- [ ] numpy (Monte Carlo path generation — likely already installed)
- [ ] scipy.stats (Bayesian updating, distribution fitting — likely already installed)

---

## Implementation Steps (Ordered)

### Phase 1: Foundation
- [ ] 1.1 Register HORIZON in pipeline_registry.py
- [ ] 1.2 Create horizon_lenses/ directory + __init__.py
- [ ] 1.3 Build horizon_dataclasses.py (LensResult, SynthesisResult, MCResult, BiasAudit)
- [ ] 1.4 Build macro_lens.py (reads regime_history, GLI components from soma.db — REGIME GATE)
- [ ] 1.5 Build fundamental_lens.py (reads valuations from soma.db)
- [ ] 1.6 Build technical_lens.py (live price fetch + momentum + vol + DD calculations)

### Phase 2: New Lenses (Grok + Gemini additions)
- [ ] 2.1 Build btc_onchain_lens.py (web search for NVT, MVRV, SOPR, exchange flows, MSTR NAV)
- [ ] 2.2 Build credit_liquidity_lens.py (web search for IG/HY spreads, VRP, TED, MM flows)
- [ ] 2.3 Build sentiment_lens.py (web search + MUSKONOMY + raw_intelligence)
- [ ] 2.4 Build event_lens.py (web search for upcoming catalysts + calendar)

### Phase 3: Synthesis + Monte Carlo + Bias Audit
- [ ] 3.1 Build horizon_synthesis.py (regime gate → concordance → weighted combination)
- [ ] 3.2 Build horizon_monte_carlo.py (10k-path engine: Bayesian priors + GBM/EGARCH + regime conditioning)
- [ ] 3.3 Build horizon_bias_audit.py (12-bias scanner + confidence discount)
- [ ] 3.4 Build horizon_output.py (formatted terminal + markdown output with MC results)

### Phase 4: Orchestrator + Integration
- [ ] 4.1 Build horizon.py orchestrator (parses question → regime gate → runs lenses → concordance → synthesis → MC → bias audit → output)
- [ ] 4.2 Add horizon_analyses table to soma.db (migration 006)
- [ ] 4.3 Wire HORIZON into soma_query.py ("horizon" command)
- [ ] 4.4 Add HORIZON step to run_day.py (optional, on-demand)

### Phase 5: Test with Example Question
- [ ] 5.1 Run HORIZON against: "liquidate 16.8% TSLA, 6.17% MSTR, 77% MM in next couple weeks"
- [ ] 5.2 Verify all 7 lenses produce grounded, factual output
- [ ] 5.3 Verify regime gate + concordance logic works correctly
- [ ] 5.4 Verify Monte Carlo produces reasonable probability distributions
- [ ] 5.5 Verify behavioral bias audit catches at least 1 relevant bias
- [ ] 5.6 Sanity-check output against common sense + current market conditions
- [ ] 5.7 Verify SOMA grounding section accurately reflects soma.db state

---

## Design Principles

1. **SOMA-grounded:** Every claim must trace to a specific data point in soma.db or a cited web source
2. **No hallucinated probabilities:** All probabilities come from Monte Carlo simulation with explicit assumptions, not invented numbers
3. **Hierarchical synthesis:** Regime gate → concordance → weighted (CFA + all 3 AIs unanimous)
4. **Lens independence:** Each lens runs independently; synthesis handles conflicts via concordance
5. **Graceful degradation:** If ORACLE data is stale or a web search fails, analysis still runs with reduced confidence (halflife decay)
6. **Fire-and-forget pattern:** Consistent with all SOMA infrastructure — errors logged, never crash
7. **CFA-grounded methodology:** Valuation models, risk frameworks, factor analysis, behavioral biases all reference CFA KB
8. **Transparent uncertainty:** When confidence is low, say so loudly rather than hiding it
9. **Regime-conditioned everything:** MC paths, base rates, thresholds all adapt to current GLI regime
10. **Tax-aware:** Flag Quebec superficial loss rules when relevant (Gemini recommendation)

---

## What This Is NOT

- NOT an automated trading signal (MANTIS FORGE handles execution decisions)
- NOT a prediction engine (it synthesizes available evidence with explicit uncertainty)
- NOT a replacement for human judgment (it structures the analysis, you make the call)
- NOT financial advice (personal advisory intelligence tool)
- NOT client-facing (no compliance burden, but includes disclaimer for good practice)

---

## Cross-AI Review Summary

### Grok (Expert mode, 55s thought, 105 sources):
- Raise MACRO to 45% domain (implemented as 35% MACRO + 10% Credit/Liquidity)
- Add Bitcoin On-Chain lens immediately (highest alpha for MSTR) ✓
- Hierarchical synthesis materially superior (~35-45% fewer false positives) ✓
- Ensemble Bayesian + MC calibration ✓
- Suggested THOR or FALCON as names → user chose to keep HORIZON

### Gemini (Thinking mode, Pro):
- 77% cash IS the signal — massive Active Share ✓ (reflected in output structure)
- MSTR convertible debt basis risk ✓ (added to Bitcoin On-Chain lens)
- TSLA revenue mix shift to Energy/AI ✓ (added to Fundamental lens)
- Halflife decay for data freshness ✓ (implemented in synthesis)
- Distinguish Stagflationary vs. Disruptive Growth regimes ✓ (macro lens)
- Tax-loss harvesting for Quebec ✓ (in output structure)
- Re-entry trigger problem: Fundamental may stay negative while Technical turns positive → concordance handles this naturally

### Claude (CFA KB synthesis):
- CFA hierarchical approach: regime → concordance → weighted ✓
- Signal concordance: "change allocation only when MAJORITY agree" ✓ (4/7 threshold)
- 12 behavioral biases from CFA curriculum ✓ (meta-layer audit)
- Credit spreads lead equities 3-6 months ✓ (Credit/Liquidity lens)
- VRP collapse as early warning ✓ (Credit/Liquidity lens)

---

## Review Section
(to be filled after implementation + testing)

---

## Lessons
(to be filled after corrections — per project instruction #3)

---

---

# SOMA-INTEL Phase 6 — Build Log (2026-05-05)

## Steps Completed

| Step | File(s) | Tests | Notes |
|------|---------|-------|-------|
| P6.0 | `backtest_report.py` (fixed calibration PNG), 3 report MDs | — | Bucket fix: [0,1] → z-score bands [1.5,2.0,...,6+] |
| P6.1 | `PHASE5_5_REBACKTEST_SCHEDULED.md`, `CLAUDE.md` | — | Re-backtest scheduled 2026-08-15 |
| P6.2 | `novelty.py`, `store.py` (+3 methods) | 14 green | count_signals_by_ticker_type, get_cell_threshold, append_threshold_adjustment |
| P6.3 | `exploration.py` | 15 green | Roulette-wheel weighted sampling, P-X tag, 1-2 samples/day |
| P6.4 | `meta_learner.py`, `migrations/025_...sql` | 16 green | Append-only threshold history, ±0.5 cap, cell key = regime\|sector\|feature |
| P6.5 | `horizon_tactical.py`, `horizon_thematic.py`, `horizon_structural.py`, `confirm.py` (+boost), `migrate_horizon_labels.py`, `query.py` (+signals cmd) | 34 green | 3 horizon tracks + 1.5x boost + one-shot migration |
| P6.6 | `weekly_brief.py`, `cipher/outputs/weekly_brief_2026-05-09.html` | — | 6 sections, codename-scrubbed, Friday-gated |
| P6.7 | `run_day.py` (1d extended, 1e meta-learner Sunday, 1f brief Friday) | 229 total green | Backtest rows unchanged: 44,388 |

## Regression Results (P6.7 gate)

- **229/229 tests passed** (8.93s)
- Backtest table: 44,388 rows (IS=34,843 / OOS=9,545) — unchanged
- Schema version: 25 (Migration 025 applied)
- Signal table: 568 live signals (thematic=288, structural=278, tactical=2)
- Threshold history rows: 10 (from meta-learner run on 2026-02-10 window)

## Tag

`v22-soma-intel-phase6-green` — to be applied after git commits via `soma/tasks/COMMIT_PHASE6.sh`

## Pending git commits (blocked by stale HEAD.lock from previous session)

Run in Terminal from `~/Desktop/DABEIBA/shared/`:
```
bash soma/tasks/COMMIT_PHASE6.sh
```

---

## Lessons Captured (Phase 6)

**L1: Calibration bucket mismatch — check axis units before plotting**
Anomaly scores are z-scores (range ~1.5–15), not probabilities [0,1]. The original
calibration plot used [0,0.2)...[0.8,1.0] buckets → all bars empty. Always verify
the domain of the metric being bucketed before choosing bin edges.

**L2: IntelStore must be used as context manager in tests**
`IntelStore(db_path=...)` alone does not open the connection — `__enter__()` must
be called (or use `with IntelStore(...) as store:`). Tests that create a store and
call methods on it without entering will fail with cryptic attribute errors.

**L3: `initialize_tables()` only creates the graph tables**
The signal tables (`soma_intel_signal`, `soma_intel_universe`, `soma_intel_baseline`,
`soma_intel_regime`) are NOT created by `initialize_tables()`. Tests that need them
must execute a `_SIGNAL_DDL` script after `initialize_tables()`.

**L4: SQLite RAISE(ABORT) in triggers raises IntegrityError, not OperationalError**
`pytest.raises(sqlite3.OperationalError)` will miss trigger violations. Use
`pytest.raises((sqlite3.IntegrityError, sqlite3.OperationalError))` for robustness.

**L5: Meta-learner trailing window must overlap backtest data range**
With `as_of_date=today` (2026-05-05), trailing 30d = Apr 5–May 5. Backtest OOS
ends 2026-02-10. No overlap → 0 adjustments. Verified with `as_of_date="2026-02-10"`
→ 10 adjustments. The live system will self-correct as fresh backtest data accumulates.

**L6: Git HEAD.lock from prior context session blocks sandbox commits**
Cowork context switches leave stale `.git/HEAD.lock` and `.git/index.lock` files
that cannot be removed from the sandbox (PermissionError). Solution: write a
`COMMIT_PHASE6.sh` script for the user to run manually in Terminal.

**L7: Global variable shadowing in CLI with default arguments**
Assigning `global DB_PATH` in a function that already referenced `DB_PATH` as a
local (via `args.db`) causes `SyntaxError: name used prior to global declaration`.
Fix: assign to a local variable first, then use it throughout the function.

**L8: run_day.py horizon date variable must be set before sub-steps**
The `_today` variable needed by the horizon track sub-steps must be declared
before the try/except blocks that use it. Hoist `_today = date.today().isoformat()`
to just after the SOMA bridge block ends.
