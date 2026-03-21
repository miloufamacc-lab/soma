---
name: Macro Regimes & Liquidity Framework
description: GLI framework, regime definitions, liquidity cycles, macro inference chains, FRED indicators, diffusion index logic, central bank analysis
source: ORACLE CFA Knowledge Base (Sections 1,2,4,5,6,8,15,D,G)
last_updated: 2026-03-20
sections:
  - macro_to_market_map
  - asset_allocation_framework
  - behavioral_finance
  - risk_framework
  - geopolitical_analysis
  - forward_guidance
  - global_economics
  - risk_premiums
  - market_efficiency
---

## SECTION 1: MACRO-TO-MARKET RELATIONSHIP MAP

### Purpose
These are the inference chains the platform uses to connect economic signals to market outcomes. Each chain shows how a change at one level cascades through the system. The system should trace these chains when analyzing any macro development.

### 1.1 Central Bank Policy Chains

**Monetary Easing Chain:**
Central bank cuts rates → short-term rates fall → money supply expands → liquidity increases → borrowing costs decrease → consumer spending rises → business investment rises → corporate earnings improve → equity valuations rise → credit spreads tighten → bond prices rise (short-duration first) → currency weakens (capital seeks higher yield elsewhere) → exports become competitive → current account improves

**Monetary Tightening Chain:**
Central bank raises rates → short-term rates rise → money supply contracts → liquidity decreases → borrowing costs increase → consumer spending slows → business investment declines → corporate earnings compress → equity valuations fall → credit spreads widen → bond prices fall (short-duration first) → currency strengthens → imports cheapen → current account deteriorates

**Quantitative Easing Chain:**
CB buys government bonds → bond prices rise / yields fall → term premium compressed → investors forced into riskier assets (search for yield) → credit spreads tighten → equity multiples expand → wealth effect boosts consumption → asset price inflation may decouple from real economy → currency weakens → EM capital flows increase

**Taylor Rule Decision Chain:**
Real target rate = policy-neutral real rate + 0.5(expected GDP growth - trend growth) + 0.5(expected inflation - target inflation) → If current rate > target → policy too tight → expect easing → bullish bonds/equities → If current rate < target → policy too loose → expect tightening → bearish bonds, mixed equities

**Yield Curve Shape Signals:**
- Steep upward slope → fiscal AND monetary policy expansive → economy should improve → bullish equities, cyclicals
- Flat/inverted → policy restrictive OR slowdown expected → economy should contract → defensive positioning, long-duration bonds
- Bear steepening (LT rates rise faster) → inflation expectations rising → real assets, TIPS, commodities
- Bull flattening (ST rates fall faster) → rate cuts beginning → early cycle positioning

<!-- RULE_BLOCK: YIELD_CURVE_SIGNALS_V1 -->
```yaml
rule_id: YIELD_CURVE_SIGNALS_V1
source_module: [ORACLE]
confidence: 0.85
rules:
  STEEP_UPWARD:
    signal: expansive_policy
    positioning: bullish_equities
    sectors: cyclicals
  FLAT_INVERTED:
    signal: restrictive_or_slowdown
    positioning: defensive
    duration: long_duration_bonds
  BEAR_STEEPENING:
    signal: inflation_expectations_rising
    positioning: real_assets
    instruments: [TIPS, commodities]
  BULL_FLATTENING:
    signal: rate_cuts_beginning
    positioning: early_cycle
```
<!-- END_RULE_BLOCK -->

### 1.2 Inflation Transmission Chains

**Inflation Within Expectations:**
Cash → earns real rate of interest (neutral)
Bonds → ST yields rise/fall more than LT yields (neutral to slightly negative)
Equity → no impact given predictable economic growth (neutral)
Real estate → neutral with typical returns

**Inflation Above Expectations:**
Cash → does well with increasing yield
Bonds → prices decline (nominal bonds hurt most)
Equity → generally poor, except companies able to pass through costs
Real estate → does well as asset values increase
Commodities → strong positive (inflation hedge)

**Deflation:**
Cash → low nominal return but rising real purchasing power
Bonds → attractive as future cash flows gain purchasing power (if no default)
Equity → poor with declining economic activity and asset values
Real estate → poor with declining property values

**Cost-Push Inflation Chain:**
Supply shock (energy, commodities) → input costs rise → producer margins compress → firms raise prices → wages lag → real consumer spending falls → stagflation risk → CB faces dilemma (fight inflation OR support growth) → policy uncertainty → volatility rises → defensive assets outperform

**Demand-Pull Inflation Chain:**
Excess stimulus → aggregate demand exceeds supply → labor market tightens → wages rise → spending accelerates → prices rise broadly → CB tightens → rates rise → growth moderates → eventually inflation subsides BUT asset prices may decline first

<!-- RULE_BLOCK: INFLATION_ASSET_MAP_V1 -->
```yaml
rule_id: INFLATION_ASSET_MAP_V1
source_module: [ORACLE]
confidence: 0.90
rules:
  WITHIN_EXPECTATIONS:
    cash: neutral
    bonds: neutral_to_slightly_negative
    equity: neutral
    real_estate: neutral
  ABOVE_EXPECTATIONS:
    cash: positive
    bonds: negative
    equity: negative
    real_estate: positive
    commodities: positive
  DEFLATION:
    cash: positive_real
    bonds: positive
    equity: negative
    real_estate: negative
```
<!-- END_RULE_BLOCK -->

### 1.3 Credit Cycle Chains

**Credit Expansion Chain:**
Low rates → lending standards loosen → credit growth accelerates → asset prices rise (collateral values increase) → more lending possible → leverage builds → risk premiums compress → spreads tighten → corporate bond issuance rises → M&A activity increases → private equity activity peaks → WARNING: late-cycle excess

**Credit Contraction Chain:**
Rates rise / defaults spike → lending standards tighten → credit growth slows → asset prices fall (collateral values decline) → margin calls / forced selling → leverage unwinds → risk premiums expand → spreads widen → refinancing risk rises → corporate distress → employment falls → further demand destruction → BOTTOM: when spreads peak and policy responds

**Credit Spread Signal Chain:**
Investment grade spreads widening → market pricing higher default risk → leading indicator of economic slowdown → typically leads equity decline by 3-6 months → high yield spreads follow with amplification → when spreads exceed 500bps HY → distressed opportunity approaching → watch for stabilization as contrarian entry signal

<!-- RULE_BLOCK: CREDIT_SPREAD_THRESHOLDS_V1 -->
```yaml
rule_id: CREDIT_SPREAD_THRESHOLDS_V1
source_module: [ORACLE]
confidence: 0.85
rules:
  HY_DISTRESSED:
    spread_bps_threshold: 500
    signal: distressed_opportunity_approaching
    action: watch_for_stabilization_contrarian_entry
  IG_WIDENING:
    signal: leading_indicator_slowdown
    equity_lead_months: [3, 6]
    description: "IG widening typically leads equity decline by 3-6 months"
  CREDIT_EXPANSION_WARNING:
    signal: late_cycle_excess
    indicators: ["spreads_tighten", "bond_issuance_rises", "M&A_peaks", "PE_activity_peaks"]
```
<!-- END_RULE_BLOCK -->

### 1.4 Currency & Trade Chains

**Currency Depreciation Chain:**
Currency weakens → exports become cheaper (competitive advantage) → import prices rise → imported inflation → current account improves → BUT foreign-denominated debt becomes more expensive → capital flight risk for EM → central bank may defend with rate hikes → self-correcting if fundamentals sound

**Currency Appreciation Chain:**
Currency strengthens → exports become expensive → import prices fall → disinflationary → current account deteriorates → foreign earnings translate to less domestic currency → multinational corporate earnings compressed → BUT foreign asset purchases become cheaper → capital attracted by strong currency

**Interest Rate/Currency Peg Linkage:**
Pegging country must follow anchor country's monetary policy → pegging country rates typically exceed anchor rates → interest rate differential fluctuates with confidence in peg → overvalued pegged currency → higher rates needed to compensate for expected decline → twin deficit + peg = high vulnerability → speculative attack risk

**Current Account Identity:**
(X - M) = (S - I) + (T - G) → Tax cut → Investment rises → Current account deficit widens AND capital account surplus grows → Growth in other countries rises as tax-cut country imports more → Spillover effects through trade linkages

### 1.5 Business Cycle to Asset Class Mapping

**INITIAL RECOVERY (maps to ORACLE GLI: REBOUND)**
- Government policy stimulative
- Business confidence rising, inflation decelerating
- Short-term rates low, long-term rates bottoming
- Stocks may rise briskly anticipating recovery
- Cyclical and riskier assets do well
- ACTION: Overweight equities (especially cyclicals, small caps), underweight bonds (except high yield), overweight EM

**EARLY EXPANSION (maps to ORACLE GLI: EXPANSION)**
- Unemployment falling, output gap shrinking
- Business confidence increasing, profits rising rapidly
- Monetary policy becoming less stimulative
- ST rates increasing, LT stable/slightly rising, yield curve flattening
- Stocks do well
- ACTION: Maintain equity overweight, begin reducing duration, favor credit over govts

**LATE EXPANSION (maps to ORACLE GLI: SPECULATION)**
- Output gap closed, capacity pressures boost investment
- Boom mentality, inflation rising
- Monetary policy turning restrictive
- ST and LT rates increasing, yield curve continues to flatten
- Stocks rise but volatile, cyclical assets may underperform
- ACTION: Reduce equity beta, favor quality/value over growth, inflation protection (TIPS, commodities, real assets)

**SLOWDOWN (maps to transitional)**
- Rising rates, fewer viable investments, accumulated debt
- Business confidence wavers, inflation still increasing
- Government policy turning neutral
- ST and LT rates peaking then declining, yield curve may invert
- Credit spreads widen (especially weaker credits)
- Stocks declining
- ACTION: Increase cash, begin adding duration, reduce credit exposure, defensive sectors

**CONTRACTION (maps to ORACLE GLI: CONTRACTION)**
- Business confidence weak, investment spending drops, corporate failures
- Government policy easing, profits drop sharply
- Credit spreads widen until signs of turn
- ST and LT rates declining, yield curve steepens substantially
- Stocks decrease but increase in later stages anticipating turn
- ACTION: Overweight govts/duration, underweight equities (until late), maximize quality, watch for cycle turn signals

### 1.6 Emerging Market Risk Chain

**EM Warning Signs (quantitative thresholds):**
1. Fiscal policy: Government deficit/GDP ratio > 4%
2. Debt: Government debt/GDP ratio > 70%
3. Growth: Real economic growth < 4%
4. External balance: Current account deficit > 4% of GDP
5. Foreign debt: Foreign debt/GDP ratio > 50%, Debt/current account receipts > 200%
6. Liquidity: Foreign exchange reserves to short-term foreign currency debt ratio < 100%
7. Political/legal: Weak property rights, corruption, capital controls, nationalization risk

**EM Crisis Cascade:**
Multiple warning signs triggered → capital flight begins → currency depreciates sharply → foreign-denominated debt burden increases → central bank raises rates to defend currency → domestic economy contracts → corporate defaults rise → banking system stressed → sovereign credit downgrade → further capital flight → contagion to similar EM economies

### 1.7 Energy & Commodity Chains

**Oil Price Shock Chain:**
Geopolitical disruption → oil supply reduced → energy prices spike → transportation and manufacturing costs rise → consumer discretionary spending falls → corporate margins compress (energy-intensive sectors hardest hit) → inflation expectations rise → central bank forced to tighten despite growth weakness → stagflation → energy exporters benefit, importers suffer → current account shifts → currency realignment

**Commodity Super-Cycle Chain:**
EM industrialization → infrastructure demand → base metals demand rises → mining investment lags (5-10yr development) → supply deficit → prices rise → resource-exporting nations benefit → terms of trade shift → DM manufacturing costs rise → substitution and efficiency gains eventually moderate demand → supply response arrives → prices normalize

---

## SECTION 2: ASSET ALLOCATION DECISION FRAMEWORK

### 2.1 Strategic Asset Allocation (SAA) Process

**IPS → Capital Market Expectations → SAA → TAA → Portfolio Construction → Monitoring**

The Investment Policy Statement drives everything. It captures:
- Return objectives (required return vs desired return)
- Risk tolerance (ability AND willingness - use the LOWER)
- Time horizon
- Liquidity needs
- Tax considerations
- Legal/regulatory constraints
- Unique circumstances

### 2.2 Capital Market Expectations Formation

**Forecasting Approaches:**

Econometrics → complex regression models, structural and reduced form, risk of estimation error and regime changes

Economic indicators → leading (PMI, yield curve, building permits), coincident (GDP, employment), lagging (CPI, unemployment duration) → focus on identifying turning points → diffusion index measures proportion pointing up/down

Checklist approach → simple, subjective synthesis of multiple indicators

**Forecasting Challenges (9 pitfalls):**
1. Limitations of economic data (lags, revisions, methodological changes)
2. Data measurement errors (transcription, survivorship bias, smoothed/appraised data)
3. Historical estimate limitations (how long a dataset? regime change problem)
4. Ex post risk underestimates ex ante risk
5. Biased methods (data mining, time period bias)
6. Failing to condition on business cycle phase
7. Misinterpretation of correlations
8. Psychological biases (anchoring, status quo, confirmation, overconfidence, prudence, availability)
9. Model/parameter/input uncertainty

### 2.3 Asset Class Return Forecasting Methods

**Fixed Income Returns:**
- DCF Method: Initial YTM is best estimate for expected bond return
- Building block (risk premium) approach: Real risk-free rate + term premium + credit premium + liquidity premium
- Key rule: If holding period = Macaulay duration → immunized (total return little affected by yield changes). Shorter H → price risk dominates. Longer H → reinvestment risk dominates.

**Equity Returns (Grinold-Kroner Model):**
E(R) = (D/P - %delta_S) + (%delta_E) + %delta(P/E)
- Component 1: Expected income = dividend yield minus share repurchase rate
- Component 2: Nominal earnings growth = real earnings growth + inflation
- Component 3: Repricing = change in P/E multiple
- If net shares are repurchased, delta_S is negative, so minus negative = positive cash flow

**Equilibrium Approach (Singer-Terhaar):**
- Fully integrated market: RP_i = rho_i,GM * sigma_i * (RP_GM / sigma_GM) [= beta_i * RP_GM]
- Fully segmented market: RP_i = sigma_i * (RP_i / sigma_i) [own Sharpe ratio]
- Weighted average based on degree of market integration
- Add illiquidity premium for non-systematic risks

**Real Estate Returns:**
- Cap rate approach: income yield + NOI growth rate
- Economic factors: GDP growth, population growth, interest rates, supply pipeline
- Competitive factors: vacancy rates, absorption rates, new construction

**Exchange Rate Forecasting:**
- Purchasing power parity (long-term)
- Interest rate parity (covered and uncovered)
- Current account / capital account flows
- Relative economic strength

### 2.4 Asset Allocation by Macro Regime (ORACLE GLI Integration)

**REBOUND Phase (GLI Rising from Trough):**
| Asset Class | Position | Rationale |
|---|---|---|
| Equities | Strong OW | Earnings recovery, multiple expansion |
| Small Caps | Strong OW | Maximum beta to recovery |
| Cyclicals | Strong OW | Operating leverage to revenue recovery |
| HY Credit | Strong OW | Spreads compress from peak |
| IG Credit | OW | Carry attractive, spread tightening |
| Govts/Duration | UW | Rates bottomed, curve steepening |
| Commodities | OW | Demand recovery, restocking |
| Cash | Strong UW | Opportunity cost highest |
| EM | OW | Risk appetite returning |

**EXPANSION Phase (GLI Solidly Positive):**
| Asset Class | Position | Rationale |
|---|---|---|
| Equities | OW | Earnings growth strong but slowing momentum |
| Quality/Growth | Tilt | Prefer sustainable earners |
| HY Credit | Neutral→UW | Spreads already tight, less upside |
| IG Credit | OW | Carry still attractive |
| Govts/Duration | UW | Rates rising with growth |
| Real Estate | OW | Rent growth, cap rate compression |
| Commodities | Neutral | Supply responses emerging |

**SPECULATION Phase (GLI Extended/Overheating):**
| Asset Class | Position | Rationale |
|---|---|---|
| Equities | UW→Neutral | Valuations stretched, policy tightening |
| Value/Defensive | Tilt | Quality premium rises |
| TIPS/Real Assets | OW | Inflation protection |
| Commodities | OW | Late-cycle inflation beneficiary |
| HY Credit | UW | Spreads too tight for risk |
| Govts/Duration | Neutral | Curve flattening, begin adding |
| Cash | OW | Optionality value rising |

**CONTRACTION Phase (GLI Falling/Negative):**
| Asset Class | Position | Rationale |
|---|---|---|
| Govts/Duration | Strong OW | Flight to quality, rates falling |
| Cash | OW | Capital preservation |
| Equities | UW (early) → Neutral (late) | Watch for turn signals |
| Defensive | Strong Tilt | Utilities, healthcare, staples |
| Gold | OW | Safe haven, monetary debasement hedge |
| HY Credit | UW→OW (late) | Distressed opportunities emerge |
| EM | UW | Risk-off, capital flight |

**CRISIS Regime (ORACLE-specific):**
| Asset Class | Position | Rationale |
|---|---|---|
| Treasuries | Maximum OW | Ultimate safe haven |
| Cash | Strong OW | Liquidity premium spikes |
| Gold | Strong OW | Store of value |
| All Risk Assets | Maximum UW | Correlations go to 1 in crisis |
| Options/Hedges | Active | Tail risk protection critical |

### 2.5 Asset Allocation Approaches

**Mean-Variance Optimization (MVO):**
- Inputs: Expected returns, standard deviations, correlations
- Output: Efficient frontier of optimal portfolios
- Issues: Highly sensitive to inputs (especially expected returns), concentrated portfolios, ignores liabilities, single-period
- Improvements: Resampled MVO (Monte Carlo), reverse optimization (Black-Litterman), constrained optimization

**Black-Litterman Model:**
- Starts with market-implied equilibrium returns (from market cap weights)
- Overlays manager views with confidence levels
- Produces more diversified, intuitive portfolios
- Process: Market equilibrium → + Manager views (with confidence) → Revised expected returns → Optimize

**Risk Parity:**
- Weight assets so each contributes equally to portfolio risk
- Typically results in high bond allocation (since bonds less volatile)
- Requires leverage to achieve target returns
- Performs well in diverse macro environments

**Goals-Based Asset Allocation:**
- Most relevant for private wealth (CFA L3 focus)
- Separate portfolios for separate goals (needs vs wants vs dreams)
- Each sub-portfolio with own risk/return profile
- Essential goals → low-risk portfolio (high probability of success)
- Aspirational goals → higher-risk portfolio (can tolerate failure)

### 2.6 Real-World Constraints on Asset Allocation

- Asset size (too large → market impact, too small → limited access to alternatives)
- Liquidity needs (emergency reserves, known outflows)
- Time horizon (short → more conservative, long → can accept illiquidity premium)
- Tax considerations (tax-loss harvesting, asset location, after-tax rebalancing)
- Regulatory (pension funding requirements, insurance capital charges)
- Governance (investment committee skill, decision-making speed)
- ESG/SRI constraints
- Currency exposure (hedge or not, cost of hedging)

---

## SECTION 4: BEHAVIORAL FINANCE FRAMEWORK

### 4.1 Cognitive Biases (Information Processing Errors)

**Anchoring:**
- Definition: Fixating on initial data point when making subsequent estimates
- Detection: Client repeatedly references purchase price, initial target, or historical return
- Debiasing: Present multiple reference points, focus on forward-looking fundamentals
- Portfolio Impact: Failure to adjust to new information, holding losers at "anchor" price

**Confirmation Bias:**
- Definition: Seeking information that confirms existing beliefs, ignoring contradictory evidence
- Detection: Client dismisses negative research, seeks only bullish/bearish sources matching their view
- Debiasing: Actively seek disconfirming evidence, devil's advocate analysis, pre-mortem exercises
- Portfolio Impact: Concentrated positions, failure to cut losses, missed opportunities

**Availability Bias:**
- Definition: Overweighting easily recalled events (recent, dramatic, personally experienced)
- Detection: Client focuses on recent market crash, celebrity stock pick, personal anecdote
- Debiasing: Use base rates and statistical evidence, systematic analysis over anecdote
- Portfolio Impact: Overreaction to recent events, under-diversification, panic selling

**Representativeness:**
- Definition: Judging probability based on how closely something matches a prototype
- Detection: "This company reminds me of Apple in 2005" or "This pattern looks like 2008"
- Debiasing: Emphasize base rates over pattern-matching, statistical reasoning
- Portfolio Impact: Extrapolating small samples, gambler's fallacy, hot hand fallacy

**Overconfidence:**
- Definition: Overestimating accuracy of own forecasts and ability
- Detection: Narrow confidence intervals, excessive trading, concentrated portfolios
- Debiasing: Track forecast accuracy, maintain decision journal, seek calibration feedback
- Portfolio Impact: Under-diversification, excessive trading costs, higher risk than intended

**Status Quo Bias:**
- Definition: Preference for current state, resistance to change even when change is beneficial
- Detection: "I've always done it this way," reluctance to rebalance, ignoring new information
- Debiasing: Frame inaction as an active choice, regular scheduled review process
- Portfolio Impact: Failure to rebalance, holding legacy positions, tax-inefficient portfolios

**Conservatism:**
- Definition: Slow to update beliefs in response to new evidence
- Detection: Maintaining forecasts despite clear data shifts, slow to recognize regime changes
- Debiasing: Bayesian updating frameworks, explicit probability revision process
- Portfolio Impact: Slow reaction to market regime changes, missed opportunities

**Mental Accounting:**
- Definition: Treating money differently based on its source, intended use, or account
- Detection: Keeping "play money" separate, different risk tolerance for different accounts
- Debiasing: Consolidate portfolio view, focus on total wealth
- Portfolio Impact: Sub-optimal aggregate portfolio, duplicated risk exposures

### 4.2 Emotional Biases (Harder to Correct)

**Loss Aversion:**
- Definition: Pain of losses exceeds pleasure from equivalent gains (roughly 2-2.5x)
- Detection: Holding losers too long, selling winners too quickly (disposition effect)
- Debiasing: Cannot fully eliminate, accommodate with downside protection strategies
- Portfolio Impact: Disposition effect, excessive risk aversion after losses

**Endowment Effect:**
- Definition: Overvaluing assets already owned
- Detection: Unwillingness to sell inherited stock, assigning sentimental value to holdings
- Debiasing: "Would you buy this at current price?" framework
- Portfolio Impact: Concentrated positions, especially inherited assets

**Regret Aversion:**
- Definition: Avoiding actions that might produce regret, even if expected value is positive
- Detection: Herding behavior, preference for conventional investments, paralysis
- Debiasing: Systematic rebalancing rules, pre-commitment strategies
- Portfolio Impact: Under-allocation to contrarian positions, missed rebalancing opportunities

**Self-Control:**
- Definition: Inability to act in long-term interest due to short-term temptation
- Detection: Spending investment capital, inability to save, impulsive trading
- Debiasing: Automatic savings plans, lock-up structures, separate accounts
- Portfolio Impact: Inadequate savings, early withdrawals, short-term focused investing

**Herding:**
- Definition: Following the crowd regardless of own analysis
- Detection: Buying what's popular, selling during panics, FOMO-driven investing
- Debiasing: Systematic investment process, contrarian indicators, decision rules
- Portfolio Impact: Buying high/selling low, trend-chasing, momentum crashes

### 4.3 Behavioral Investor Types (BITs)

**Passive Preserver:**
- Primary biases: Loss aversion, endowment, status quo
- Risk tolerance: Low
- Investment approach: Conservative, capital preservation focused
- Advisor approach: Accommodate emotional biases, educate slowly, focus on downside protection

**Friendly Follower:**
- Primary biases: Regret aversion, herding, availability
- Risk tolerance: Low to medium
- Investment approach: Follows trends, influenced by media and peers
- Advisor approach: Education-focused, provide structured decision framework, limit information overload

**Independent Individualist:**
- Primary biases: Overconfidence, confirmation, self-attribution
- Risk tolerance: Medium to high
- Investment approach: Active, research-driven, contrarian tendencies
- Advisor approach: Challenge assumptions with data, leverage their engagement, guide without dictating

**Active Accumulator:**
- Primary biases: Overconfidence, self-control, illusion of control
- Risk tolerance: High (may be higher than appropriate)
- Investment approach: Concentrated, frequent trading, entrepreneurial
- Advisor approach: Establish firm risk limits, demonstrate cost of overtrading, channel energy productively

### 4.4 Debiasing for the Platform

**Systematic Debiasing Approach:**
1. Identify: Which biases are present in the client/market narrative?
2. Classify: Cognitive (can correct through education) vs Emotional (must accommodate)
3. Quantify: How much is the bias likely distorting the analysis?
4. Correct/Accommodate: Adjust analysis for cognitive biases, design around emotional biases
5. Monitor: Track whether debiasing is working over time

---

## SECTION 5: RISK FRAMEWORK

### 5.1 Risk Taxonomy

**Market Risk:**
- Equity risk: beta, sector concentration, factor exposures
- Interest rate risk: duration, convexity, key rate durations
- Currency risk: translation, transaction, economic exposure
- Commodity risk: direct holdings, input cost sensitivity
- Volatility risk: vega exposure, variance swap positions

**Credit Risk:**
- Default risk: probability of default (PD)
- Recovery risk: loss given default (LGD)
- Spread risk: credit spread duration
- Migration risk: downgrade probability
- Concentration risk: single-name, sector, geography

**Liquidity Risk:**
- Market liquidity: bid-ask spreads, market depth, price impact
- Funding liquidity: ability to meet cash needs without forced sales
- Redemption risk: fund-level liquidity mismatch
- Illiquidity premium: compensation for accepting illiquid positions

**Operational Risk:**
- Model risk: incorrect assumptions, coding errors
- Counterparty risk: derivative counterparty default
- Settlement risk: failed trade settlement
- Legal/regulatory risk: changing rules, compliance failures
- Cybersecurity risk

**Tail Risk:**
- Events beyond normal distribution assumptions
- Fat tails (leptokurtosis) → standard models underestimate
- Correlation breakdown: correlations approach 1 in crisis
- Contagion: cross-market, cross-asset spillover

### 5.2 Risk Measurement Methods

**Standard Deviation:**
- Total risk measure, includes systematic and specific risk
- Assumes normal distribution (limitation)
- Used for absolute risk attribution

**Tracking Error (Active Risk):**
- Standard deviation of excess returns vs benchmark
- Measures consistency of active management
- Used for relative risk attribution
- Information Ratio = Alpha / Tracking Error

**Value at Risk (VaR):**
- Maximum expected loss at given confidence level over specified period
- Parametric: assumes normal distribution, uses mean/variance
- Historical: uses actual historical return distribution
- Monte Carlo: simulates thousands of scenarios
- Limitation: says nothing about magnitude of losses beyond VaR threshold

**Conditional VaR (CVaR / Expected Shortfall):**
- Average loss in the tail beyond VaR threshold
- Better captures tail risk than VaR alone
- Preferred by regulators and sophisticated risk managers

**Beta:**
- Systematic risk relative to market
- Beta = Cov(Ri, Rm) / Var(Rm)
- Used for CAPM-based analysis and hedging

**Key Performance/Risk Ratios:**
- Sharpe = (Rp - Rf) / sigma_p → excess return per unit of total risk
- Treynor = (Rp - Rf) / beta_p → excess return per unit of systematic risk
- Information Ratio = alpha / tracking error → value added per unit of active risk
- Sortino = (Rp - target) / sigma_downside → penalizes only downside deviation
- Appraisal Ratio = alpha / sigma_epsilon → alpha per unit of unsystematic risk
- Capture Ratios: UC/DC → upside capture / downside capture; CR = UC/DC; CR > 1 = positive asymmetry (convex)

### 5.3 Risk Management Techniques

**Derivatives-Based Hedging:**
- Protective put: limits downside, preserves upside, costs premium
- Covered call: generates income, limits upside, provides modest downside cushion
- Collar (zero-cost): protective put + covered call, bounded outcomes
- Bull/bear spreads: limited risk/reward directional bets
- Forward/futures: lock in price/rate, symmetric payoff
- Swaps: exchange risk exposures (interest rate, currency, total return)

**Portfolio-Level Risk Management:**
- Diversification: across assets, geographies, strategies, time
- Rebalancing: calendar-based or threshold-based
- Stress testing: scenario analysis for extreme events
- Position sizing: Kelly criterion, risk budgeting
- Stop-losses: systematic exit rules (but beware whipsaw)

### 5.4 Options Strategy Decision Framework

**Market View → Strategy:**
| View | Strategy | Max Gain | Max Loss |
|---|---|---|---|
| Bullish, limited risk appetite | Bull call spread | X_H - X_L - net premium | Net premium paid |
| Bullish, want protection | Protective put | Unlimited | S - X_put + premium |
| Mildly bullish, want income | Covered call | X_call - S + premium | S - premium received |
| Neutral, want protection | Collar | X_call - S - net premium | S - X_put + net premium |
| Expecting volatility increase | Long straddle | Unlimited | Total premium paid |
| Expecting volatility decrease | Short straddle | Total premium received | Unlimited |
| Bullish, want leverage | Synthetic long forward | Unlimited | X + c - p (to zero) |

**Synthetic Relationships (Put-Call Parity):**
c - p = S - PV(X) or equivalently S + p = c + PV(X)
- Synthetic long forward = long call + short put (same X, T)
- Synthetic short forward = short call + long put (same X, T)
- Protective put = synthetic long call
- Covered call = synthetic short put

---

## SECTION 6: GEOPOLITICAL ANALYSIS FRAMEWORK

### 6.1 Geopolitical Event Assessment Process

**Step 1: Classify the Event**
- Military/security (armed conflict, territorial dispute, nuclear threat)
- Economic/trade (sanctions, tariffs, trade agreements, currency manipulation)
- Political (election, regime change, policy shift, institutional breakdown)
- Resource/energy (supply disruption, pipeline politics, resource nationalism)
- Technology (cyber attack, tech decoupling, standards wars)

**Step 2: Assess Direct Impact**
- Which countries directly involved?
- Which sectors/commodities directly affected?
- What is the probability of escalation vs de-escalation?
- What is the time horizon (acute vs structural)?

**Step 3: Map Second-Order Effects**
- Trade route disruptions → shipping costs → input prices → margins
- Sanctions → energy supply → prices → inflation → central bank response
- Political instability → capital flight → currency → debt sustainability
- Alliance shifts → defense spending → fiscal impact → bond markets

**Step 4: Identify Third-Order Effects**
- Supply chain restructuring (friend-shoring, near-shoring)
- Technology access changes (chip restrictions, data localization)
- Reserve currency dynamics (de-dollarization, BRICS alternatives)
- Long-term capital allocation shifts (ESG, defense, energy security)

### 6.2 Energy Security Analysis

**Energy Dependency Chain:**
Energy import dependency → vulnerability to supply disruption → strategic reserves adequacy → alternative supplier availability → substitution capability → price transmission speed → inflation impact → economic growth impact → political stability impact

**Key Nodes:**
- Strait of Hormuz: ~20% of global oil passes through
- Strait of Malacca: critical for Asian energy imports
- Suez Canal: Europe-Asia trade route
- Russian gas pipelines: European energy security
- OPEC+ decisions: supply management, geopolitical tool

### 6.3 Sanctions & Currency Weaponization

**Sanctions Impact Chain:**
Sanctions imposed → targeted country's trade restricted → currency weakens → inflation rises → foreign reserves depleted → debt service costs rise → economic contraction → political pressure → either compliance or alliance seeking (Russia-China-Iran axis formation)

**Currency Weaponization Chain:**
Dollar used as weapon (SWIFT exclusion, sanctions) → targeted countries seek alternatives → bilateral trade in local currencies → BRICS payment systems develop → gradual reduction in dollar demand → long-term: marginal pressure on dollar reserve status → short-term: minimal impact (no viable alternative at scale)

### 6.4 Geopolitical Risk Integration with Portfolio

**Framework: How to translate geopolitical risk into portfolio action:**

1. Identify the geopolitical scenario with highest probability of market impact
2. Map the transmission channels (energy, trade, currency, confidence)
3. Estimate magnitude and timing of market impact
4. Identify which assets benefit vs suffer
5. Assess current portfolio exposure to those assets
6. Determine if the risk is priced in or represents an opportunity
7. Size the hedge/position proportional to confidence and potential impact
8. Monitor trigger points for escalation/de-escalation

---

## SECTION 8: FORWARD GUIDANCE LOGIC

### 8.1 Leading vs Lagging Indicators

**Leading Indicators (signal what's coming):**
- Yield curve slope (inverted → recession in 12-18 months)
- PMI / ISM Manufacturing (below 50 → contraction ahead)
- Building permits / housing starts
- Initial jobless claims (rising → labor market weakening)
- Stock market (3-6 months forward looking)
- Consumer confidence / University of Michigan sentiment
- Credit conditions surveys (tightening → slowdown)
- High yield spreads (widening → stress building)
- Money supply growth (slowing → tightening ahead)

**Coincident Indicators (confirm current state):**
- GDP growth
- Industrial production
- Employment / payroll data
- Personal income
- Retail sales

**Lagging Indicators (confirm what happened):**
- Unemployment rate (lags turning points by months)
- Core CPI (inflation is lagging)
- Corporate profits (reported with delay)
- Bank lending rates (adjust after policy changes)
- Duration of unemployment

### 8.2 Signal Confirmation Patterns

**Recession Signal Confirmation:**
Yield curve inverts → credit spreads begin widening → leading indicators turn down → PMI crosses below 50 → initial claims trend higher → CONFIRMATION: recession likely within 6-12 months

**Recovery Signal Confirmation:**
Yield curve steepens → credit spreads narrow from peak → leading indicators bottom → PMI crosses above 50 → initial claims trend lower → CONFIRMATION: recovery underway

**Inflation Regime Change:**
Commodity prices surge → PPI accelerates → CPI follows with lag → inflation expectations rise (breakevens, surveys) → wage growth accelerates → Fed rhetoric shifts hawkish → CONFIRMATION: inflation regime established

### 8.3 From "What Is" to "What's Likely Next"

**Current State Assessment:**
1. Where are we in the business cycle? (Use leading indicators, output gap, credit conditions)
2. What is monetary policy stance vs Taylor Rule? (Too tight, neutral, too loose)
3. What are credit conditions doing? (Tightening or loosening? Senior Loan Officer Survey)
4. What does the yield curve say? (Shape, slope changes, term premium)
5. What are cross-asset signals saying? (Equities, credit, commodities, volatility pointing same direction?)

**Forward Projection:**
1. Given current cycle phase, what typically comes next?
2. What would change the trajectory? (Policy surprise, external shock, geopolitical event)
3. What are the non-consensus risks? (What would catch the market off guard)
4. What is the market pricing in vs what we expect? (Where is the gap = opportunity)
5. What is the time horizon for the projection to play out?

### 8.4 Cross-Asset Confirmation Matrix

**When signals agree → high conviction:**
- Equities falling + credit spreads widening + yield curve flattening + VIX rising → RISK OFF confirmed
- Equities rising + credit spreads tightening + curve steepening + VIX falling → RISK ON confirmed

**When signals diverge → investigate:**
- Equities rising but credit spreads widening → fragile rally, likely to resolve with equity decline
- Yield curve steepening but equities falling → market pricing recession but recovery potential
- VIX falling but credit spreads widening → complacency signal, risk of sudden correction
- Dollar strengthening + gold rising → fear-driven flows, unusual and worth investigating

---

## SECTION 15: GLOBAL ECONOMICS & CAPITAL FLOWS

*Expanded from V2 placeholder. Source: CFA L3 curriculum economics content, L1-L2 macro foundations, practitioner knowledge*

### 15.1 Conditional vs Unconditional Capital Market Assumptions

**Unconditional inputs:** 10+ year averages, ignore current conditions → strategic long-term allocation
**Conditional inputs:** explicitly incorporate current valuation, business cycle, interest rates → tactical/dynamic allocation

**When to Use Conditional Inputs:**
IF market valuations are extreme (CAPE significantly above/below long-term average) → conditional inputs capture mean-reversion tendency → can improve allocation decisions
IF entering a known regime shift (rising rate environment, recession entry) → conditional inputs capture changing risk/return dynamics
IF normal market conditions → unconditional inputs may be adequate

→ ORACLE GLI Integration: When GLI signals regime change → switch from unconditional to conditional CMAs → adjust allocation per Section 2.4 regime tables
Links to: Section 8.3 (forward guidance logic)

### 15.2 Business Cycle Framework

**Four Phases with Investment Implications:**

**Phase 1 — Early Recovery (Trough to Initial Expansion):**
Characteristics: GDP turns positive, unemployment still high, excess capacity, low inflation, aggressive monetary easing
→ Central bank: rates at floor, QE likely → bond yields low
→ Best performers: Small-cap value, Financials, Consumer discretionary, HY credit
→ Worst: Defensives underperform (utilities, staples, healthcare)
→ Fixed income: flattening yield curve as short rates anchored, long rates begin to rise
→ Currency: mixed — currency of recovering economy may strengthen on growth expectations but CB holds rates low
→ PM action: increase equity allocation, extend credit duration, shift from quality to cyclicals

**Phase 2 — Mid-Expansion:**
Characteristics: GDP above trend, unemployment falling, moderate inflation, CB begins tightening
→ Central bank: rate hikes begin → yield curve flattening
→ Best performers: IT, Industrials, Materials (capex beneficiaries), Momentum factor
→ Corporate earnings: strong growth, operating leverage kicking in, margins expanding
→ Credit: spreads tight and tightening further → HY outperforms IG
→ PM action: maintain equity overweight but begin rotating toward quality; reduce duration

**Phase 3 — Late Expansion:**
Characteristics: GDP decelerating, full employment, inflation rising, CB restrictive
→ Central bank: rates above neutral → inverted yield curve signals recession risk (lead time 12-24 months)
→ Best performers: Energy, Materials (inflation beneficiaries), Quality factor, Short-duration
→ Worst: Long-duration bonds, Growth stocks (discount rate rising)
→ Credit: spreads bottomed, beginning to widen → HY underperforms → reduce credit exposure
→ PM action: reduce equity to neutral/underweight, shorten duration, increase cash, add quality/defensive

**Phase 4 — Recession (Contraction):**
Characteristics: GDP negative, unemployment rising, inflation falling, aggressive monetary easing
→ Central bank: emergency cuts → yield curve steepens (short rates collapse)
→ Best performers: Government bonds (flight to quality), Cash, Gold, Defensive sectors (healthcare, utilities, staples), Quality + Low Vol factors
→ Worst: Small-cap, Cyclicals, HY (defaults spike), EM assets, PE/alternatives (liquidity crisis)
→ Credit: spreads spike → distressed opportunities emerge → but timing is critical
→ PM action: maximum defensive positioning; begin accumulating risk assets in late recession (contrarian)

### 15.3 Leading & Lagging Indicator Framework

**Leading Indicators (signal direction 6-12 months ahead):**
- Yield curve slope (10Y-2Y spread): <0 = recession signal, historically 12-24 month lead
- PMI (Manufacturing & Services): <50 = contraction signal
- Initial jobless claims: rising trend = labor market weakening
- Building permits: housing leads broader economy by 12-18 months
- Consumer confidence/expectations: forward-looking spending intentions
- Credit conditions (Senior Loan Officer Survey): tightening = growth headwind
- M2 money supply growth: monetary conditions lead real economy by 9-18 months
- Stock market: S&P 500 is itself a leading indicator (embedded in Conference Board LEI)

**Coincident Indicators (confirm current state):**
- Industrial production, Retail sales, Non-farm payrolls, Personal income

**Lagging Indicators (confirm past direction):**
- Unemployment rate (peaks AFTER recession ends), CPI (inflation peaks late), Corporate profits (reported with lag), Bank lending standards (tighten after damage done)

**Indicator Conflict Resolution:**
IF leading indicators diverge (some positive, some negative) → weight financial conditions indicators (yield curve, credit) more heavily than survey-based
IF leading AND coincident indicators disagree → trust leading indicators for forward positioning
→ PM heuristic: no single indicator is reliable alone → use composite of 5+ indicators → change allocation only when MAJORITY signal same direction
Caveat: Post-GFC, traditional indicators have been distorted by QE, zero rates, and fiscal stimulus → relationships may be weaker than historical norms

### 15.4 Monetary Transmission Mechanism

**Rate Channel:**
CB lowers policy rate → short-term rates fall → bank funding costs decrease → banks lower lending rates → borrowing increases → investment + consumption rise → GDP growth → employment
→ Time lag: 6-18 months from rate change to real economy impact
→ Limitation: "pushing on a string" — rate cuts can't force lending if banks are impaired or borrowers unwilling

**Asset Price Channel:**
CB easing → bond prices rise → equity prices rise (lower discount rate) → wealth effect → consumer spending increases → real economy improves
→ This is the primary QE transmission mechanism
→ Limitation: wealth effect is concentrated among asset owners → increases inequality → may not reach real economy broadly

**Exchange Rate Channel:**
CB easing → domestic rates fall relative to foreign → currency depreciates → exports more competitive → net exports improve → GDP growth
→ Limitation: "beggar thy neighbor" — if all CBs ease simultaneously, no currency benefit → competitive devaluation risk

**Credit Channel:**
CB easing → bank reserves increase → banks' lending capacity expands → credit availability improves → borrowers invest → GDP growth
→ Limitation: bank capital constraints, regulatory requirements can block this channel even with abundant reserves

**Expectations Channel:**
CB forward guidance → shapes expectations of future rates → influences long-term rates TODAY → affects investment decisions immediately
→ This is the most POWERFUL channel when rates are already near zero → "the commitment to be irresponsible" (Krugman)

### 15.5 Currency Dynamics & Capital Flows

**Purchasing Power Parity (PPP):**
Long-run equilibrium: exchange rate adjusts so that identical goods cost the same in different currencies
→ Holds over 5-10+ year horizons, unreliable for short-term trading
→ Currencies >20% above PPP → overvalued → tend to depreciate over subsequent 3-5 years

**Interest Rate Parity (IRP):**
Forward rate = Spot × (1 + r_domestic) / (1 + r_foreign)
→ Higher interest rate currencies trade at a FORWARD DISCOUNT
→ Covered interest parity: holds by arbitrage (no-arbitrage condition)
→ Uncovered interest parity: DOES NOT hold empirically → forward rate bias → carry trade profits

**Carry Trade Mechanics:**
Borrow in low-yield currency → invest in high-yield currency → earn interest differential
→ Works in calm markets: low-yield currencies depreciate LESS than IRP predicts → carry is positive
→ FAILS in crisis: flight to safety → safe haven currencies (JPY, CHF, USD) appreciate sharply → carry trade unwinds violently → "goes up by the stairs, comes down in the elevator"
→ PM heuristic: carry trade = selling insurance against global risk events → positive expected return but negatively skewed (small gains, occasional large losses)

**Capital Flow Framework:**
Current account deficit → requires capital account surplus (foreign investment) → sustainable IF capital inflows are FDI (productive) → UNSUSTAINABLE if funded by hot money (portfolio flows)
→ Sudden stop risk: capital inflows reverse → currency crisis → forced adjustment (EM crisis pattern: Mexico 1994, Asia 1997, Turkey 2018)
→ Twin deficit problem: fiscal deficit + current account deficit → both require foreign financing → increases vulnerability

**Currency Hedging Decision:**
IF currency is >15% above PPP AND interest rate differential is small → hedge (overvaluation likely to correct)
IF currency is near PPP AND large positive carry → leave unhedged (earn carry)
IF portfolio has natural hedges (companies with foreign revenue offset currency exposure) → less hedging needed
→ Hedging cost = forward discount ≈ interest rate differential → for USD-based investor hedging JPY exposure: cost ≈ US rate − Japan rate
Links to: Section 12.3 (currency component of FI returns), Section 1.1 (currency chains)

### 15.6 Fiscal Policy & Multipliers

**Fiscal Multiplier Hierarchy:**
- Government spending (direct): multiplier 0.8-1.5 (highest — direct demand injection)
- Transfer payments to low-income: multiplier 0.8-1.2 (high — high marginal propensity to consume)
- Tax cuts for middle class: multiplier 0.5-0.9 (moderate)
- Tax cuts for high income: multiplier 0.2-0.5 (lowest — much is saved, not spent)
- Corporate tax cuts: multiplier 0.2-0.4 (benefits flow to shareholders, often saved)

**Fiscal-Monetary Interaction:**
Fiscal expansion + Monetary easing = maximum stimulus → asset prices surge, GDP accelerates (2020-2021 pattern)
Fiscal expansion + Monetary tightening = mixed → fiscal spending partially offset by higher rates → crowding out → uncertain outcome
Fiscal austerity + Monetary easing = moderate stimulus → CB does heavy lifting → "pushing on a string" risk
Fiscal austerity + Monetary tightening = maximum contraction → deleveraging → deflationary spiral risk
Links to: Section 1.1 (policy chains), Section 6.1 (sovereign risk)

---

## APPENDIX D: RISK PREMIUMS DEEP DIVE

### D.1 Risk Premium Taxonomy & Regime Signals

**Five Major Risk Premiums:**

**1. Equity Risk Premium (ERP):**
Definition: expected excess return of equities over risk-free rate
→ Historical (ex-post): ~4-6% geometric over T-bills (DM average, 120 years, Dimson-Marsh-Staunton)
→ Current estimation methods: Grinold-Kroner (D/P + earnings growth − dilution + repricing), Survey-based (typically 3-5%), Implied from earnings yield minus real rate
→ Regime signal: when ERP is HIGH (CAPE low, spreads wide) → future returns historically ABOVE average → buy signal
→ When ERP is LOW (CAPE >30, compressed spreads) → future returns historically BELOW average → reduce equity
→ CAPE (Shiller P/E) >30: subsequent 10yr real returns averaged ~0-3%; CAPE <15: subsequent 10yr averaged 8-12%
Caveat: ERP estimation has wide uncertainty bands (±2-3%) → no single method is reliable

**2. Credit Risk Premium:**
Definition: excess return on credit bonds over duration-matched government bonds
→ Components: expected default loss + credit migration loss + LIQUIDITY premium + TRUE credit risk premium
→ Historical: IG spread premium ≈ 50-80bps over defaults/downgrades → pure compensation for RISK
→ HY: spread premium larger but more volatile → actual credit loss eats ~200-300bps of HY spread
→ Regime signal: IG spreads >200bps → recession/crisis pricing → historically excellent entry point
→ IG spreads <80bps → complacency → poor risk/reward → reduce credit
→ HY spreads >600bps → distressed cycle → opportunities for patient capital
→ HY spreads <300bps → late-cycle froth → exit

**3. Liquidity Premium:**
Definition: additional return for holding less-liquid assets
→ On-the-run to off-the-run Treasury: ~3-5bps → smallest, most reliable
→ Small-cap vs. large-cap equity: part of size premium (~1-2% annual)
→ Private vs. public assets: ~150-400bps depending on market conditions
→ Regime signal: in crisis, liquidity premium SPIKES → forced sellers create distressed prices → liquidity providers earn outsized returns
→ In calm markets, liquidity premium COMPRESSES → less compensation for lock-up
→ PM heuristic: BUILD liquidity reserves in calm markets → DEPLOY into illiquid opportunities during crises

**4. Term Premium:**
Definition: additional return for holding longer-duration bonds over rolling short-term bonds
→ Historical: ~100-150bps (positive yield curve)
→ When term premium is NEGATIVE (inverted curve): market pricing recession → strong recession predictor
→ When term premium is extremely HIGH (steep curve): recovery phase → positive for banks, financials
→ QE has compressed term premium toward zero or negative → distorting normal signal
→ As QT reverses QE → term premium normalizes higher → headwind for long-duration bonds

**5. Volatility Risk Premium (VRP):**
Definition: difference between implied volatility and subsequent realized volatility
→ Historical: implied vol > realized vol ~80% of the time → VRP is positive → options tend to be "expensive"
→ Strategies: systematic short volatility (put writing, variance swaps) → earn VRP in most periods
→ Regime signal: when VRP is very HIGH (implied >> realized) → calm markets, complacency → selling vol is profitable but tail risk accumulating
→ When VRP COLLAPSES or goes NEGATIVE → crisis mode → vol sellers get crushed → February 2018 "volmageddon" pattern
Caveat: VRP harvesting is "picking up pennies in front of a steamroller" → positive expected value but extreme negative skew → must size positions for survivability

### D.2 Risk Premium Interactions

**ERP × Credit Premium:** both widen in recession → highly correlated in stress → diversification between equity and credit is ILLUSORY in crisis
**ERP × Term Premium:** both driven by growth/inflation expectations → rising inflation compresses ERP (higher discount rates) AND flattens term premium
**Liquidity × Credit:** liquidity premium amplifies credit moves → in crisis, credit spreads widen AND liquidity evaporates simultaneously → double punishment
**VRP × All Others:** VRP collapse signals regime shift → when implied vol spikes → ALL other premiums are repriced → VRP is the CANARY in the coal mine

→ ORACLE integration: monitor all five premiums simultaneously → when 3+ premiums are in "complacency" zone → increase defensive positioning → when 3+ are in "crisis" zone → increase risk allocation
Links to: Section 1.1 (all monetary/credit chains), Section 5.1 (risk framework), Section 15.2 (business cycle)

---

## APPENDIX G: MARKET EFFICIENCY & EQUITY CONCEPTS

*Source: CFA L1 Kaplan Study Notes — Equity (Market Efficiency). Provides foundational framework referenced by L3 active management sections.*

### G.1 Efficient Market Hypothesis (Fama, 1970)

**Definition:** A market is informationally efficient if security prices quickly and fully reflect available information in a statistical sense. If a market is efficient with respect to a particular information set, investors CANNOT use that information to earn positive abnormal (risk-adjusted) returns on average — they cannot consistently "beat the market."

**Three Forms of Market Efficiency:**

| Form | Prices Reflect | How to Beat the Market | Implication |
|------|---------------|----------------------|-------------|
| Weak form | Past market data (prices, volumes, trading data) | Cannot beat with technical analysis; only fundamental analysis or inside information | Evidence: developed markets are generally weak-form efficient |
| Semi-strong form | All publicly available information (financials, news, analyst reports) | Cannot beat with fundamental analysis; only inside information | Evidence: developed markets may be semi-strong efficient |
| Strong form | ALL information including private/inside information | No one can beat the market, even insiders | Evidence: markets are NOT strong-form efficient (insider trading generates excess returns) |

**Intrinsic Value vs. Market Value:**
- Intrinsic value = the value rational investors would place on an asset with full knowledge of its characteristics
- Active investors seek assets where intrinsic value ≠ market value to earn excess returns
- Passive investors accept market prices as approximately correct and earn a fair risk-adjusted return
- Evidence: on average, active funds underperform passive funds after fees

**Pricing Anomalies (challenges to EMH):**
- Time-series anomalies: calendar effects (January effect, day-of-week effect), momentum (recent winners continue winning), overreaction (past losers outperform past winners long-term)
- Cross-sectional anomalies: size effect (small-cap outperformance), value effect (low P/B outperforms high P/B)
- Other anomalies: closed-end fund discounts, IPO underpricing/long-run underperformance, post-earnings announcement drift

**Behavioral Finance Challenges to EMH:**
- Loss aversion (rather than rational risk aversion) → investors hold losers too long, sell winners too soon
- Herding → asset prices can deviate from fundamentals as investors follow each other
- Overconfidence → excessive trading, concentrated portfolios
- Information cascades → investors ignore private information and follow observed actions of others
→ If markets are not fully rational, mispricings may persist long enough for skilled active managers to exploit

**Key Exam Point:** The degree of market efficiency determines the value of active management. In highly efficient markets, passive strategies are preferred (low cost, market return). In less efficient markets (small-cap, EM, distressed), active management has greater potential to add value.

Links to: Section 13.3 (active vs. passive spectrum), Section 21.2 (Type I/II errors in manager selection), Section 3.1 (valuation — requires belief that prices can deviate from intrinsic value)
