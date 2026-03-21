---
name: MANTIS Portfolio Execution Mechanics
description: Portfolio execution framework, position sizing, regime-based allocation, rebalancing logic, risk management, trade execution, drawdown controls
source: Original DABEIBA content (not derived from CFA KBs)
last_updated: 2026-03-20
sections:
  - execution_philosophy
  - regime_based_allocation
  - position_sizing
  - rebalancing_framework
  - drawdown_controls
  - trade_execution
  - portfolio_monitoring
  - cash_management
---

# MANTIS Portfolio Execution Mechanics

MANTIS is the portfolio execution engine of the DABEIBA system. It translates ORACLE's macro regime assessments and valuation signals into concrete portfolio actions: what to buy, how much, when to rebalance, and when to raise cash.

This document codifies the decision rules, position sizing logic, and risk controls that govern MANTIS behavior.

---

## 1. Execution Philosophy

### 1.1 Core Principles

- **Regime First:** Portfolio allocation is driven primarily by ORACLE's regime classification (RISK_ON, TURBULENCE, CONTRACTION, etc.). Individual security selection is secondary to getting the macro allocation right.
- **Systematic Over Discretionary:** Every trade has a quantitative basis. MANTIS does not act on "gut feel" — it acts on threshold breaches, regime signals, and valuation gaps.
- **Asymmetric Risk Management:** Protecting capital in adverse regimes takes priority over maximizing returns in favorable ones. The cost of a drawdown compounds geometrically; a 50% loss requires a 100% gain to recover.
- **Simplicity Wins:** Fewer positions held with conviction outperform diversified mediocrity. The focus list is deliberately small (15-25 names), ensuring each position is researched and monitored.

### 1.2 Decision Hierarchy

When MANTIS evaluates an action, it follows this priority order:

1. **Regime override** — If the regime signals danger (CONTRACTION, severe TURBULENCE), reduce exposure regardless of individual valuations
2. **Risk limits** — Check drawdown controls, position size limits, and concentration constraints before any new position
3. **Valuation signal** — Use ORACLE's implied upside and execution scores to rank opportunities
4. **Liquidity check** — Ensure the position can be exited within a reasonable timeframe
5. **Tax efficiency** — Where possible, prefer tax-efficient execution (hold periods, loss harvesting)

---

## 2. Regime-Based Allocation

### 2.1 Target Allocations by Regime

Each ORACLE regime maps to a target equity exposure range and cash floor:

| Regime | Equity Target | Cash Floor | Duration Stance | Risk Appetite |
|--------|--------------|------------|-----------------|---------------|
| RISK_ON (Rebound) | 80-95% | 5% | Short | Aggressive — favor cyclicals, high-beta |
| RISK_ON (Expansion) | 70-85% | 10% | Neutral | Growth — favor quality growth |
| TURBULENCE | 50-65% | 20% | Extend slightly | Defensive — favor quality, low-vol |
| CONTRACTION | 30-50% | 30-50% | Long duration | Capital preservation — treasuries, cash |

### 2.2 Regime Transition Rules

When ORACLE signals a regime change:

- **RISK_ON to TURBULENCE:** Reduce equity exposure by 15-25% over 3-5 trading days. Sell highest-beta positions first. Raise cash floor to 20%.
- **TURBULENCE to CONTRACTION:** Further reduce equity to target range. Sell remaining cyclicals. Move duration long. Cash floor 30%.
- **CONTRACTION to RISK_ON:** Begin rebuilding equity exposure gradually (5% per week). Start with highest-conviction, cheapest names from ORACLE valuations. Don't rush — early cycle transitions often have false starts.
- **TURBULENCE to RISK_ON:** Restore equity to expansion-level targets. Favor names that were oversold during turbulence (highest implied upside).

### 2.3 Transition Speed

- **Reducing exposure:** Fast (3-5 days). Capital preservation is urgent.
- **Increasing exposure:** Slow (2-4 weeks). Confirm regime stability before fully deploying.

The asymmetry is intentional: getting out of danger quickly matters more than catching every basis point of upside.

### 2.4 GLI-Based Fine-Tuning

Within a regime, the GLI level provides finer allocation guidance:

- **GLI > 60:** Maximum equity allocation within regime range
- **GLI 45-60:** Mid-range allocation
- **GLI 30-45:** Lower end of regime range, lean defensive
- **GLI < 30:** Minimum allocation regardless of regime label

The diffusion index further modulates: if diffusion < 45 (fewer than 45% of indicators positive), lean toward the conservative end even in RISK_ON.

---

## 3. Position Sizing

### 3.1 Individual Position Limits

| Category | Maximum Weight | Rationale |
|----------|---------------|-----------|
| Core holding (high conviction, liquid) | 8% | Sufficient exposure without concentration risk |
| Standard position | 5% | Default size for focus list names |
| Speculative / small-cap | 3% | Higher risk warrants smaller allocation |
| Single-name hard cap | 10% | Never exceeded regardless of conviction |

### 3.2 Sizing Formula

Position weight is determined by:

```
Weight = Base_Weight x Conviction_Score x Regime_Multiplier
```

Where:
- **Base_Weight** = 5% (default)
- **Conviction_Score** = ORACLE execution score / 10 (range 0.0-1.0)
  - Score 8+ = full conviction (1.0x)
  - Score 6-8 = moderate (0.75x)
  - Score below 6 = reduced (0.5x)
- **Regime_Multiplier** = current regime's risk appetite
  - RISK_ON: 1.0x
  - TURBULENCE: 0.7x
  - CONTRACTION: 0.4x

Example: A stock with execution score 8.5 in RISK_ON:
Weight = 5% x 1.0 x 1.0 = 5.0%

Same stock in TURBULENCE:
Weight = 5% x 1.0 x 0.7 = 3.5%

### 3.3 Implied Upside Integration

ORACLE's implied upside (fair value vs. current price) adjusts sizing:

- **Upside > 30%:** Can size up to Core limits (8%)
- **Upside 15-30%:** Standard sizing (5%)
- **Upside 5-15%:** Reduced sizing (3%)
- **Upside < 5%:** Do not initiate new position; consider trimming existing

### 3.4 Concentration Rules

- **Top 5 positions:** Cannot exceed 35% combined
- **Single sector:** Cannot exceed 30%
- **Single country (ex-US):** Cannot exceed 15%
- **Correlated pairs:** If two positions have correlation > 0.80, treat as one position for concentration limits

---

## 4. Rebalancing Framework

### 4.1 Rebalancing Triggers

MANTIS rebalances when any of these conditions are met:

1. **Regime change:** ORACLE signals a new regime (mandatory rebalance)
2. **Drift threshold:** Any position drifts more than +/-2% from target weight
3. **Calendar:** Monthly review (first trading day of each month)
4. **Material change:** WhatChanged flags a HIGH severity event

### 4.2 Rebalancing Priority

When rebalancing, process changes in this order:

1. **Risk reduction first** — Sell positions that exceed limits or belong to the wrong regime
2. **Cash deployment second** — If cash exceeds target, deploy to highest-conviction underweights
3. **Tax-loss harvesting** — Replace losers with similar (non-wash-sale) exposure if tax-advantageous
4. **Fine-tuning last** — Adjust positions by 1-2% to match targets

### 4.3 Rebalancing Bands

| Trigger | Band Width | Action |
|---------|-----------|--------|
| Individual position drift | +/-2% from target | Trim or add to restore |
| Sector drift | +/-5% from target | Rebalance across sector names |
| Cash level drift | Below floor | Sell weakest position(s) to restore |
| Total equity drift | +/-5% from regime target | Full portfolio rebalance |

---

## 5. Drawdown Controls

### 5.1 Portfolio-Level Circuit Breakers

| Drawdown Level | Action |
|---------------|--------|
| -5% from HWM | Review: reassess all positions. No new buys until review complete. |
| -10% from HWM | Reduce: cut equity exposure by 20% of current level. Raise cash. |
| -15% from HWM | Protect: move to minimum equity allocation for current regime. Override any "buy the dip" signals. |
| -20% from HWM | Lockdown: move to CONTRACTION allocation regardless of ORACLE regime. 50%+ cash. No new equity positions. |

### 5.2 Individual Position Stop-Loss

- **Hard stop:** Exit any position that declines -25% from entry price
- **Trailing stop:** For positions up >15%, set trailing stop at -10% from peak
- **Fundamental stop:** Exit if ORACLE removes from focus list or execution score drops below 5.0

### 5.3 Recovery Protocol

After a drawdown triggers a circuit breaker:

1. Wait for ORACLE to confirm regime stabilization (at least 2 consecutive readings)
2. Rebuild exposure gradually (5% per week)
3. Start with highest-conviction names (execution score > 8)
4. Do not return to pre-drawdown allocation until portfolio recovers to -5% of HWM

---

## 6. Trade Execution

### 6.1 Order Types

| Scenario | Order Type | Rationale |
|----------|-----------|-----------|
| Normal rebalancing | Limit order (at or near bid/ask) | Minimize market impact |
| Urgent risk reduction | Market order | Speed over price when protecting capital |
| New position initiation | Limit order, scale in over 2-3 days | Avoid chasing; build position gradually |
| Profit taking / trim | Limit order above current price | Patience; let the market come to you |

### 6.2 Execution Timing

- **Avoid first 15 minutes and last 15 minutes** of trading (highest volatility, widest spreads)
- **Prefer mid-morning (10:00-11:30) or early afternoon (1:00-2:30)** for optimal liquidity
- **For large orders (>1% of ADV):** Split across 2-3 days minimum

### 6.3 Trade Documentation

Every trade logged to SOMA must include:
- Date, ticker, action (BUY/SELL/REBALANCE)
- Price and target weight
- Reason (regime change, valuation signal, rebalance, stop-loss)
- Regime at time of trade
- GLI and diffusion values at time of trade

---

## 7. Portfolio Monitoring

### 7.1 Daily Checks

Run every trading day via `run_day.py`:

1. **ORACLE update** — Fresh regime, GLI, and valuation data
2. **WhatChanged** — Any material shifts requiring action?
3. **SOMA Status** — Dashboard review of portfolio state
4. **Drawdown check** — Current portfolio value vs. high water mark

### 7.2 Weekly Review

Every Monday:

1. **Position review** — Does every holding still belong in the portfolio given current regime?
2. **Concentration check** — Any position or sector approaching limits?
3. **Cash level** — At or above floor for current regime?
4. **Upcoming catalysts** — Earnings, Fed meetings, macro data releases in the coming week

### 7.3 Monthly Deep Dive

First trading day of each month:

1. **Full rebalance** — Bring all positions to target weights
2. **Performance attribution** — What drove returns? Allocation vs. selection?
3. **Regime outlook** — Is the current regime likely to persist or transition?
4. **Focus list review** — Add/remove names based on ORACLE valuations

---

## 8. Cash Management

### 8.1 Cash Allocation

Cash is not idle — it serves three functions:

1. **Regime buffer** — Floor level required by current regime (5-50%)
2. **Opportunity reserve** — 5% set aside for sharp dislocations / extreme values
3. **Operating cash** — Sufficient for 2-3 months of expected withdrawals

### 8.2 Cash Instruments

Cash positions should be held in:
- **Money market funds** — Primary vehicle for operating cash
- **Short-term treasuries (T-bills)** — For regime buffer (slight yield advantage)
- **No long-duration bonds as "cash"** — Duration risk defeats the purpose

### 8.3 Deployment Rules

Deploying cash into equities requires ALL of:
1. ORACLE regime supports equity allocation increase
2. At least one focus list name has implied upside > 15%
3. Portfolio is not in a drawdown circuit breaker state
4. Cash after deployment remains at or above regime floor
