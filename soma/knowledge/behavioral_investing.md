# Behavioral Investing Rules — SOMA Knowledge Layer
# Source: PRISM pipeline extractions
# Last updated: 2026-04-14

---

<!-- RULE_BLOCK: BEHAVIORAL_SOCIAL_ARB_METHODOLOGY_V1 -->
rule_id: BEHAVIORAL_SOCIAL_ARB_METHODOLOGY_V1
source_module: PRISM
domain: behavioral
rule_data:
  - "Social arbitrage: use real-time conversational data (social media comments, forums) as alpha source preceding transactional data (credit card swipes)"
  - "Signal hierarchy: conversational data > transactional data > fundamental analysis for detecting consumer/cultural shifts"
  - "Platform ranking for signal quality: TikTok comments (most transparent) > Reddit forums > Twitter/X > Instagram (most curated/biased)"
  - "Key signal words: 'obsessed' (high conviction), 'sold out everywhere' (supply constraint), same sentiment across demographics (trend durability)"
  - "Filter: Is the signal big enough to move the needle? Is it already widely known? Is it the most important thing happening at the company?"
  - "Three needles: Revenue, Cost, Perception. ANY of the three creates a trade. Perception trades work even if fundamentals don't change."
  - "Second-order perception trade: If OTHER investors will believe it moves the needle, trade it even if you don't believe it."
confidence: 0.75
<!-- END_RULE_BLOCK -->

---

<!-- RULE_BLOCK: RISK_BUCKETING_FRAMEWORK_V1 -->
rule_id: RISK_BUCKETING_FRAMEWORK_V1
source_module: PRISM
domain: risk
rule_data:
  - "Every dollar = $100 future value (100x over lifetime with aggressive leveraged investing). Reframe ALL spending decisions through this lens."
  - "Create a dedicated 'big money account' funded ONLY by savings from tradeoff decisions — money that was already 'out the window.'"
  - "NEVER use retirement, vacation, or children's education money for asymmetric bets."
  - "The big money account is for high-risk, high-reward bets where 50% chance of total loss + 50% chance of 4x = mandatory bet."
  - "Not investing = guaranteed loss to inflation. A 60/40 portfolio at 6.5% return loses purchasing power with no way to mitigate."
  - "Risk in every part of life: no risk in personal life = no friends, no partner, no career. Investing is no different."
  - "Asymmetric return math: if 5 bets at 50/50 odds with 4x upside, losing 3 of 5 still nets positive. ALWAYS take these."
confidence: 0.75
<!-- END_RULE_BLOCK -->

<!-- RULE_BLOCK: BEHAVIORAL_IATROGENIC_RISK_V1 -->
rule_id: BEHAVIORAL_IATROGENIC_RISK_V1
source_module: PRISM
domain: behavioral
rule_data:
  - Iatrogenic risk: when proposed cure introduces more damage than the original threat
  - Three archetypes: Optimist (adaptive), Pessimist (preparatory), Alarmist (dangerous)
  - Decision checklist: assess probability, proximity, cure side-effects, cost proportionality
  - Calvin Coolidge rule: 9/10 anticipated problems resolve before reaching you
  - Applied to Bitcoin quantum threat: premature post-quantum cryptography migration could introduce new attack surfaces
  - Saylor quoting Satoshi: "We can upgrade" — consensus-driven timing over panic-driven action
confidence: 0.75
<!-- END_RULE_BLOCK -->
