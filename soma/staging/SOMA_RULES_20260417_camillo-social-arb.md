# SOMA Rule Extractions — transcript-to-intel V3.0
# Source: Chris Camillo × Mark Moss (~78 min, pasted)
# transcript_hash: fba58360 | Date: 2026-04-17
# Route: append to ~/Desktop/DABEIBA/shared/soma/knowledge/ (equities_models.md or staging/ if no matching file)

<!-- RULE_BLOCK: EQUITIES_SOCIAL_ARB_SIGNAL_V1 -->
rule_id: EQUITIES_SOCIAL_ARB_SIGNAL_V1
source_module: PRISM
domain: equities
rule_data:
  - "Social arb signal threshold: 3,000+ consistent comments from diverse demographics using keywords 'obsessed' or 'sold out everywhere' across multiple TikTok videos on the same product"
  - "TikTok comments inside videos are more reliable than the videos themselves — video creators may be compensated, commenters are not"
  - "Signal lead time over transactional data: days-to-weeks. Wall Street's credit card swipe data arrives weeks before earnings; conversational data leads by weeks-to-months"
  - "Applicable to consumer brands and trend-driven micro-cap situations. NOT applicable to institutional/B2B companies (no visible conversational signal)"
  - "Capacity constraint: signal edge degrades as institutional NLP (Two Sigma, Citadel ~$200M/yr spend) captures the same source. Monitor for quant alpha decay."
  - "Multi-platform verification required: single-platform signal = insufficient. Ideally: TikTok + Reddit + Amazon reviews pointing in same direction"
confidence: 0.60
source_transcript: "Chris Camillo × Mark Moss podcast, 2026-04-17"
transcript_hash: "fba58360"
<!-- END_RULE_BLOCK -->

<!-- RULE_BLOCK: RISK_MULTI_SUB_DILIGENCE_V1 -->
rule_id: RISK_MULTI_SUB_DILIGENCE_V1
source_module: PRISM
domain: risk
rule_data:
  - "When holding a position in a multi-subsidiary holding company, diligence is REQUIRED on every subsidiary contributing ≥15% of total revenue — not only the trend-driver subsidiary"
  - "Failure mode: trade thesis based on 2 of 3 subsidiaries performing; 3rd subsidiary (dominant revenue contributor) has an unknown unknown → 100% options loss + maximum NAV damage when leverage is applied"
  - "Case source: Restaurant Brands International (RBI) — Popeyes + Burger King trending (thesis correct), Tim Hortons majority revenue missed (franchisee convention, publicly discoverable)"
  - "Actionable check: before executing a multi-subsidiary holding company options trade, identify all subsidiaries above 15% revenue threshold and confirm each one has 'no known negative catalyst'"
  - "Leverage multiplies this risk: the combination of levered options + multi-subsidiary blind spot is especially lethal. Consider stock position (not options) when holding company complexity is high"
confidence: 0.85
source_transcript: "Chris Camillo × Mark Moss podcast, 2026-04-17 — Tim Hortons wipeout case study"
transcript_hash: "fba58360"
<!-- END_RULE_BLOCK -->

<!-- RULE_BLOCK: BEHAVIORAL_DOLLAR_100X_FRAMEWORK_V1 -->
rule_id: BEHAVIORAL_DOLLAR_100X_FRAMEWORK_V1
source_module: PRISM
domain: behavioral
rule_data:
  - "Project every dollar at 100x future lifetime value to change consumption tradeoffs — $5 coffee = $500 in this mental model"
  - "Redirect consumption foregone into a dedicated 'Big Money Account' (BMA), funded ONLY from expenses the investor was willing to eliminate anyway. Zero opportunity cost barrier."
  - "From BMA, apply Paul Tudor Jones 5:1 minimum risk/reward rule — only take bets where potential upside is ≥5x the potential loss. This eliminates second-guessing on positive-EV asymmetric bets."
  - "Psychological isolation: BMA is mentally separate from retirement/vacation money. Decision-making from BMA uses different risk tolerance than core capital — removes fear of 50/50 bets with 4x upside"
  - "Caveat (PROMOTER flag): Camillo commercially benefits from this framework. Mental accounting risk (Thaler 1985): treating 'written-off' BMA money as license for rationalized gambling is possible. Discipline and exit criteria still required."
confidence: 0.50
source_transcript: "Chris Camillo × Mark Moss podcast, 2026-04-17"
transcript_hash: "fba58360"
<!-- END_RULE_BLOCK -->
