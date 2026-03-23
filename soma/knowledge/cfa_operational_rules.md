---
name: CFA Operational Rules for SOMA Runtime
description: Actionable decision rules extracted from CFA Knowledge Base V14.0 for DABEIBA module integration — ethics, risk frameworks, behavioral bias detection, GIPS compliance, and equity factor selection
source: CFA Knowledge Base V14.0 (Sections 4, 5, 13, 16, and supporting materials)
last_updated: 2026-03-22
version: 1.0
sections:
  - ethics_standards
  - risk_framework
  - behavioral_biases
  - gips_compliance
  - equity_factors
---

# CFA Operational Rules for SOMA Runtime

This knowledge base extracts actionable decision rules from the CFA Knowledge Base (V14.0) and structures them as executable YAML rule blocks for runtime use by DABEIBA modules. Each rule block is designed for code-level consumption: decision trees, quantitative thresholds, classification rules, and trigger conditions that modules can act on immediately.

**Modules using this KB:**
- **CIPHER** — Ethics, behavioral bias detection, communication adaptation, GIPS compliance
- **ORACLE** — Risk measurement thresholds, framework classification
- **MANTIS** — Risk limits, equity factor rotation signals

---

## SECTION 1: ETHICS & STANDARDS (CFA Code V14.0)

### 1.1 Overview
The CFA Standards of Professional Conduct provide the ethical framework governing client communication, research integrity, and reporting in CIPHER. These rules focus on decision-points in client reporting and research dissemination.

<!-- RULE_BLOCK: ETHICS_STANDARDS_V1 -->
```yaml
rule_id: ETHICS_STANDARDS_V1
source_module: [CIPHER]
confidence: 0.90
standards:
  STANDARD_I_PROFESSIONALISM:
    name: Professionalism
    sub_standards:
      I_A_KNOWLEDGE_OF_LAW:
        description: Comply with the stricter of local law or CFA Standards
        decision_rule: "IF local_law_permits AND cfa_standards_prohibit THEN follow_cfa_standards ELSE follow_local_law"
        action_trigger: regulatory_review_before_communication
      I_B_INDEPENDENCE_AND_OBJECTIVITY:
        description: Maintain independence from gifts, favors, relationships
        threshold_token_gift_value: 150  # USD, typically local norm
        action_if_lavish_gift: dissociate_from_recommendation
        action_if_research_pressure: document_dissent_and_comply_with_policy
      I_C_MISREPRESENTATION:
        description: No false statements on qualifications, services, performance
        prohibited_actions: [plagiarism, cherry_picking_performance, omitting_material_facts]
        required_actions: [attribute_others_work, full_transparency, citation_on_research]
      I_D_MISCONDUCT:
        description: No dishonesty, fraud, or deceit affecting professional reputation
        scope: [professional_conduct, personal_conduct_reflecting_on_profession]
      I_E_COMPETENCE:
        description: Maintain competence for professional responsibilities (NEW 2023)
        required_actions: [stay_current_with_tools, stay_current_with_methods, stay_current_with_regulations]
        not_requirement: formal_continuing_education_hours

  STANDARD_II_INTEGRITY_OF_CAPITAL_MARKETS:
    name: Integrity of Capital Markets
    sub_standards:
      II_A_MATERIAL_NONPUBLIC_INFORMATION:
        description: Cannot trade or recommend based on material nonpublic information
        decision_tree:
          step_1: "Is information MATERIAL? (reasonable investor would consider important)"
          step_2: "Is information NONPUBLIC? (not broadly disseminated)"
          action_if_both_yes: "DO_NOT_TRADE, DO_NOT_CAUSE_OTHERS_TO_TRADE"
          exception: mosaic_theory_permitted
        mosaic_theory_rule: "CAN combine nonmaterial nonpublic info WITH public info → PERMISSIBLE"
        required_controls: [firewall_procedures, compliance_preclearance, trading_records]
      II_B_MARKET_MANIPULATION:
        description: No actions designed to deceive or artificially influence prices
        prohibited_actions: [pump_and_dump, layering, spoofing, false_rumors, model_input_manipulation]

  STANDARD_III_DUTIES_TO_CLIENTS:
    name: Duties to Clients
    sub_standards:
      III_A_LOYALTY_PRUDENCE_CARE:
        description: Act in clients' best interests (fiduciary duty)
        key_rules:
          identify_actual_client: "In pension/trust context, beneficiaries are actual client, NOT plan sponsor"
          soft_dollar_arrangements: "Must directly benefit clients, not just the firm"
          directed_brokerage: "Acceptable IF client requests AND disadvantages disclosed"
      III_B_FAIR_DEALING:
        description: Treat all clients fairly (not identically)
        rules:
          simultaneous_dissemination: "Recommendations disseminated simultaneously to similar clients"
          ipo_allocation: "Pro-rata or other fair method, NOT favoring certain clients"
          service_levels: "Different service tiers ACCEPTABLE IF disclosed (e.g., premium gets earlier access)"
      III_C_SUITABILITY:
        description: Ensure investments suitable given client IPS
        rules:
          portfolio_context: "Must evaluate in ENTIRE portfolio context, not individual position alone"
          unsolicited_trades: "Still require portfolio context evaluation"
          ips_review: "Must review and update regularly (recommend annually)"
      III_D_PERFORMANCE_PRESENTATION:
        description: Fair, accurate, complete presentation of performance
        required_compliance: GIPS  # Strong recommendation
        prohibited_actions: [cherry_picking_periods, cherry_picking_accounts]
        required_actions: [disclose_methodology_changes, disclose_timing_promptly]
      III_E_PRESERVATION_OF_CONFIDENTIALITY:
        description: Keep client information confidential
        exceptions_permit_disclosure: [illegal_activity_detected, required_by_law, client_permits]

  STANDARD_IV_DUTIES_TO_EMPLOYERS:
    name: Duties to Employers
    sub_standards:
      IV_A_LOYALTY:
        description: Act in employer's interest, protect confidential information
        permitted: [prepare_to_leave, update_resume, conduct_interviews]
        prohibited: [take_client_lists, take_proprietary_models, solicit_clients]
      IV_B_ADDITIONAL_COMPENSATION:
        description: Disclose outside compensation that could create conflict
      IV_C_SUPERVISORY_RESPONSIBILITIES:
        description: Prevent and detect violations by subordinates
        key_rule: "Cannot delegate compliance responsibility → personally liable for inadequate supervision"

  STANDARD_V_INVESTMENT_ANALYSIS:
    name: Investment Analysis, Recommendations, Actions
    sub_standards:
      V_A_DILIGENCE_AND_REASONABLE_BASIS:
        description: Adequate basis for all recommendations
        rules:
          third_party_research: "CAN rely IF due diligence performed on provider"
          quantitative_models: "Must understand assumptions AND limitations"
          group_research: "Dissenting views should be documented"
      V_B_COMMUNICATION_WITH_CLIENTS:
        description: Disclose services, costs, process, limitations (REVISED 2023)
        required_disclosures: [investment_process, cost_structure, material_changes_to_process, limitations]
        facts_vs_opinions: "Clearly distinguish facts from opinions → label estimates and projections"

  STANDARD_VI_CONFLICTS_OF_INTEREST:
    name: Conflicts of Interest
    key_rules:
      disclosure_required: true
      priority_of_transactions: "Employer and client transactions ahead of personal"
      referral_fees: "Must disclose"

  STANDARD_VII_RESPONSIBILITIES_AS_MEMBER:
    name: Responsibilities as CFA Member
    key_rules:
      conduct_standard: "Professional conduct reflects on profession"
      reference_to_cfa: "Cannot misrepresent CFA designation or claim unearned credential"
```
<!-- END_RULE_BLOCK -->

---

## SECTION 2: RISK FRAMEWORK (CFA Knowledge Base Section 5)

### 2.1 Overview
Risk measurement and management frameworks provide the quantitative language for assessing portfolio risk across multiple dimensions. This section structures risk taxonomy, measurement methods, and decision thresholds for ORACLE (macro regime classification) and MANTIS (portfolio risk controls).

<!-- RULE_BLOCK: RISK_FRAMEWORK_V1 -->
```yaml
rule_id: RISK_FRAMEWORK_V1
source_module: [ORACLE, MANTIS]
confidence: 0.85
risk_taxonomy:
  MARKET_RISK:
    equity_risk:
      measures: [beta, sector_concentration, factor_exposures]
      decision_use: portfolio_volatility, drawdown_simulation, scenario_analysis
    interest_rate_risk:
      measures: [duration, convexity, key_rate_durations]
      threshold_duration_sensitivity: 1_percent_parallel_shift
    currency_risk:
      types: [translation_exposure, transaction_exposure, economic_exposure]
    commodity_risk:
      direct_holdings: relevant
      input_cost_sensitivity: relevant
    volatility_risk:
      measures: [vega_exposure, variance_swap_positions]

  CREDIT_RISK:
    default_risk:
      measure: probability_of_default_PD
      data_source: credit_rating_agency, CDS_spreads, fundamental_analysis
    recovery_risk:
      measure: loss_given_default_LGD
      range_typical: [0.3, 0.7]  # 30-70% depending on seniority
    spread_risk:
      measure: credit_spread_duration
    migration_risk:
      measure: downgrade_probability
      monitoring: quarterly_rating_reviews
    concentration_risk:
      types: [single_name, sector, geography]
      decision_rule: "Limit concentration to max_portfolio_weight_per_name"

  LIQUIDITY_RISK:
    market_liquidity:
      measures: [bid_ask_spread, market_depth, price_impact]
      threshold_bid_ask_tightness: less_than_0_05_percent_normal
    funding_liquidity:
      measure: ability_to_meet_cash_needs_without_forced_sales
      scenario: stress_scenario_requires_2_week_liquidation_plan
    redemption_risk:
      measure: fund_level_liquidity_mismatch
      rule: "Ensure fund redemption terms exceed underlying asset illiquidity"
    illiquidity_premium:
      description: Additional return required for accepting illiquid positions
      typical_range: [0.01, 0.05]  # 1-5% depending on redemption constraints

  OPERATIONAL_RISK:
    model_risk:
      description: Incorrect assumptions, coding errors, outdated models
      control: model_validation, independent_review, assumption_testing
    counterparty_risk:
      measure: exposure_to_counterparty_default
      scenario: track_counterparty_credit_quality, establish_exposure_limits
    settlement_risk:
      measure: failure_to_receive_assets_or_funds
      control: DVP_settlement, fail_safe_procedures
    legal_regulatory_risk:
      types: [changing_rules, compliance_failures, litigation]
      control: compliance_monitoring, regulatory_review
    cybersecurity_risk:
      control: data_encryption, access_controls, incident_response_plan

  TAIL_RISK:
    definition: Events beyond normal distribution assumptions
    characteristics:
      fat_tails: leptokurtosis → standard_models_underestimate
      correlation_breakdown: crisis_correlations_approach_1_0
      contagion: cross_market_cross_asset_spillover
    measurement_method: historical_scenario_analysis, monte_carlo_stress_tests
    decision_rule: "Scenario weight extreme events higher than normal distribution would suggest"

risk_measurement_methods:
  STANDARD_DEVIATION:
    definition: Total risk including systematic and specific
    assumption: normal_distribution
    use_case: absolute_risk_attribution
    limitation: fat_tails_not_captured

  TRACKING_ERROR:
    definition: Std dev of excess returns vs benchmark
    formula: "σ(R_portfolio - R_benchmark)"
    use_case: relative_risk_attribution
    ratio: Information_Ratio = Alpha / Tracking_Error

  VALUE_AT_RISK_VAR:
    definition: Maximum expected loss at given confidence level over specified period
    methods:
      parametric: "Assumes normal distribution, uses mean/variance (simplest, fastest)"
      historical: "Uses actual historical return distribution (empirical)"
      monte_carlo: "Simulates thousands of scenarios (most flexible)"
    confidence_levels: [0.90, 0.95, 0.99]  # Common thresholds
    horizon: [1_day, 1_week, 1_month]  # Common periods
    limitation: says_nothing_about_losses_beyond_VaR_threshold

  CONDITIONAL_VAR_EXPECTED_SHORTFALL:
    definition: Average loss in tail beyond VaR threshold
    formula: "CVaR = E(Loss | Loss > VaR)"
    advantage_over_var: captures_magnitude_of_extreme_losses
    preferred_by: [regulators, sophisticated_risk_managers]

  BETA:
    definition: Systematic risk relative to market
    formula: "β = Cov(R_i, R_m) / Var(R_m)"
    use_case: [CAPM_analysis, hedging_decisions]

  SHARPE_RATIO:
    definition: Excess return per unit of total risk
    formula: "Sharpe = (R_p - R_f) / σ_p"
    interpretation: higher_is_better
    benchmark: "Risk-free rate + acceptable excess return per unit volatility"

  TREYNOR_RATIO:
    definition: Excess return per unit of systematic risk
    formula: "Treynor = (R_p - R_f) / β_p"
    use_case: comparing_managers_with_different_systematic_risk

  INFORMATION_RATIO:
    definition: Value added per unit of active risk
    formula: "IR = α / Tracking_Error"
    threshold_good_manager: IR > 0.5

  SORTINO_RATIO:
    definition: Excess return per unit of downside risk only
    formula: "Sortino = (R_p - Target) / σ_downside"
    advantage: penalizes_only_downside_deviation

  CAPTURE_RATIOS:
    definition: Upside capture / downside capture asymmetry
    upside_capture: "Return when benchmark up / benchmark return"
    downside_capture: "Return when benchmark down / benchmark return"
    positive_asymmetry: "UC > DC → capture more upside than downside"

risk_management_techniques:
  DERIVATIVES_HEDGING:
    protective_put:
      description: Limits downside, preserves upside
      cost: premium_paid
      max_loss: strike_price_minus_current_price_plus_premium
    covered_call:
      description: Generates income, limits upside, modest downside cushion
      income: premium_received
      trade_off: capped_upside
    collar_zero_cost:
      description: Protective put + covered call, bounded outcomes
      cost: zero_or_minimal
      payoff_range: bounded
    bull_bear_spreads:
      description: Limited risk/reward directional bets
      use_case: high_conviction_directional_view
    forward_futures:
      description: Lock in price/rate, symmetric payoff
      use_case: hedge_specific_exposure
    swaps:
      description: Exchange risk exposures (rates, currency, total return)
      use_case: customize_risk_profile

  PORTFOLIO_LEVEL_RISK_MANAGEMENT:
    diversification:
      dimensions: [assets, geographies, strategies, time]
      target_correlation: aim_for_uncorrelated_or_negative
    rebalancing:
      methods: [calendar_based, threshold_based]
      frequency_recommendation: quarterly_or_when_allocation_drift_exceeds_5_percent
    stress_testing:
      method: scenario_analysis_for_extreme_events
      scenarios: [historical_crisis, constructed_scenario, reverse_stress_test]
    position_sizing:
      methods: [Kelly_criterion, risk_budgeting]
      principle: size_larger_for_higher_conviction_lower_risk
    stop_losses:
      description: Systematic exit rules
      caveat: beware_whipsaw_in_volatile_markets
      alternative: volatility_triggered_rebalance

decision_thresholds_for_risk_action:
  VAR_99_PERCENT_1DAY:
    threshold_alert: 2_percent_of_portfolio
    threshold_action: reduce_exposure_or_hedge
  DRAWDOWN_CURRENT:
    threshold_warning: 10_percent_from_peak
    threshold_action: 15_percent_from_peak
  DAILY_VOLATILITY:
    threshold_alert: 2_standard_deviations_above_normal
    threshold_action: 3_standard_deviations_above_normal
  CREDIT_SPREAD_WIDENING:
    threshold_alert: 50_basis_points_above_normal
    threshold_action: 100_basis_points_above_normal
  CORRELATION_BREAKDOWN:
    threshold_alert: equity_bond_correlation_above_0_5
    threshold_action: review_diversification_thesis
```
<!-- END_RULE_BLOCK -->

---

## SECTION 3: BEHAVIORAL BIASES & COMMUNICATION ADAPTATION (CFA Knowledge Base Section 4)

### 3.1 Overview
Behavioral biases affect how clients perceive risk, interpret market signals, and make decisions. CIPHER uses these rules to detect client biases and adapt communication to mitigate their impact.

<!-- RULE_BLOCK: BEHAVIORAL_BIASES_V1 -->
```yaml
rule_id: BEHAVIORAL_BIASES_V1
source_module: [CIPHER]
confidence: 0.85
cognitive_biases:
  ANCHORING:
    definition: Fixating on initial data point when making subsequent estimates
    detection_signals:
      - client_repeatedly_references_purchase_price
      - client_cites_historical_return_as_target
      - client_uses_outdated_benchmark_or_reference
    debiasing_communication:
      - present_multiple_reference_points
      - focus_on_forward_looking_fundamentals
      - explicitly_update_assumptions_based_on_new_data
    portfolio_impact: failure_to_adjust_to_new_information, holding_losers_at_anchor_price
    detection_rule: "IF client_says 'I_bought_at' OR 'target_was' OR 'historical_average_was' THEN flag_anchoring"

  CONFIRMATION_BIAS:
    definition: Seeking information confirming existing beliefs, ignoring contradictory evidence
    detection_signals:
      - client_dismisses_negative_research
      - client_seeks_only_bullish_or_bearish_sources_matching_view
      - client_ignores_disconfirming_evidence
    debiasing_communication:
      - actively_seek_disconfirming_evidence
      - devil_advocate_analysis
      - pre_mortem_exercises
    portfolio_impact: concentrated_positions, failure_to_cut_losses, missed_opportunities
    detection_rule: "IF client_dismisses_contrary_view OR selection_only_bullish_sources THEN flag_confirmation_bias"

  AVAILABILITY_BIAS:
    definition: Overweighting easily recalled events (recent, dramatic, personally experienced)
    detection_signals:
      - client_focuses_on_recent_market_crash
      - client_cites_celebrity_stock_pick
      - client_uses_personal_anecdote_as_evidence
    debiasing_communication:
      - use_base_rates_and_statistical_evidence
      - systematic_analysis_over_anecdote
      - provide_historical_frequency_comparison
    portfolio_impact: overreaction_to_recent_events, under_diversification, panic_selling
    detection_rule: "IF client_recent_event_focus OR anecdotal_reasoning THEN flag_availability_bias"

  REPRESENTATIVENESS:
    definition: Judging probability based on how closely something matches a prototype
    detection_signals:
      - client_says_this_company_reminds_me_of_apple_in_2005
      - client_pattern_matches_to_2008_crisis
      - client_generalizes_from_small_sample
    debiasing_communication:
      - emphasize_base_rates_over_pattern_matching
      - statistical_reasoning_with_confidence_intervals
      - highlight_sample_size_limitations
    portfolio_impact: extrapolating_small_samples, gamblers_fallacy, hot_hand_fallacy
    detection_rule: "IF client_pattern_matches OR small_sample_generalization THEN flag_representativeness"

  OVERCONFIDENCE:
    definition: Overestimating accuracy of own forecasts and ability
    detection_signals:
      - narrow_confidence_intervals_on_forecasts
      - excessive_trading_activity
      - concentrated_portfolio_with_few_convictions
    debiasing_communication:
      - track_forecast_accuracy_and_share_results
      - maintain_decision_journal
      - provide_calibration_feedback
    portfolio_impact: under_diversification, excessive_trading_costs, unintended_risk
    detection_rule: "IF narrow_confidence_intervals OR high_portfolio_turnover OR concentrated_positions THEN flag_overconfidence"

  STATUS_QUO_BIAS:
    definition: Preference for current state, resistance to change even when beneficial
    detection_signals:
      - client_says_ive_always_done_it_this_way
      - reluctance_to_rebalance
      - ignoring_new_information_or_strategy
    debiasing_communication:
      - frame_inaction_as_active_choice
      - regular_scheduled_review_process
      - explicitly_document_decision_to_maintain_status_quo
    portfolio_impact: failure_to_rebalance, holding_legacy_positions, tax_inefficient_portfolios
    detection_rule: "IF client_resistance_to_change THEN flag_status_quo_bias_and_schedule_formal_review"

  CONSERVATISM:
    definition: Slow to update beliefs in response to new evidence
    detection_signals:
      - maintaining_forecasts_despite_clear_data_shifts
      - slow_recognition_of_regime_changes
      - underweighting_recent_data
    debiasing_communication:
      - Bayesian_updating_frameworks
      - explicit_probability_revision_process
      - quantified_regime_change_signals
    portfolio_impact: slow_reaction_to_market_regime_changes, missed_opportunities
    detection_rule: "IF client_maintains_outdated_forecast OR slow_regime_recognition THEN flag_conservatism"

  MENTAL_ACCOUNTING:
    definition: Treating money differently based on source, intended use, or account
    detection_signals:
      - client_keeps_play_money_separate
      - different_risk_tolerance_for_different_accounts
      - treating_inherited_assets_differently
    debiasing_communication:
      - consolidate_portfolio_view
      - focus_on_total_wealth
      - demonstrate_aggregate_risk_profile
    portfolio_impact: sub_optimal_aggregate_portfolio, duplicated_risk_exposures
    detection_rule: "IF client_separates_accounts_by_psychology OR different_risk_preferences THEN flag_mental_accounting"

emotional_biases:
  LOSS_AVERSION:
    definition: Pain of losses exceeds pleasure from equivalent gains (ratio ~2-2.5x)
    detection_signals:
      - holding_losers_too_long
      - selling_winners_too_quickly
      - disposition_effect_visible_in_trades
    debiasing_communication:
      - cannot_fully_eliminate
      - accommodate_with_downside_protection_strategies
      - frame_portfolio_in_terms_of_wealth_preservation
    portfolio_impact: disposition_effect, excessive_risk_aversion_after_losses
    decision_rule: "Offer_protective_structures (e.g. stops, collars, diversification)"

  ENDOWMENT_EFFECT:
    definition: Overvaluing assets already owned
    detection_signals:
      - unwillingness_to_sell_inherited_stock
      - assigning_sentimental_value_to_holdings
      - excessive_concentration_in_single_position
    debiasing_communication:
      - would_you_buy_at_current_price_framework
      - periodic_portfolio_reset_analysis
      - discuss_opportunity_cost
    portfolio_impact: concentrated_positions, especially_inherited_assets
    decision_rule: "Regular_suitability_review_with_fresh_eyes"

  REGRET_AVERSION:
    definition: Avoiding actions that might produce regret, even if expected value positive
    detection_signals:
      - herding_behavior
      - preference_for_conventional_investments
      - paralysis_and_inaction
    debiasing_communication:
      - systematic_rebalancing_rules
      - pre_commitment_strategies
      - emphasize_process_over_outcome
    portfolio_impact: under_allocation_to_contrarian_positions, missed_rebalancing
    decision_rule: "Establish_pre_commitment_rules_agreed_in_calm_markets"

  SELF_CONTROL:
    definition: Inability to act in long-term interest due to short-term temptation
    detection_signals:
      - spending_investment_capital
      - inability_to_save
      - impulsive_trading
    debiasing_communication:
      - automatic_savings_plans
      - lock_up_structures
      - separate_accounts
    portfolio_impact: inadequate_savings, early_withdrawals, short_term_focused_investing
    decision_rule: "Implement_structural_controls (automatic_transfers, restricted_accounts)"

  HERDING:
    definition: Following the crowd regardless of own analysis
    detection_signals:
      - buying_what_is_popular
      - selling_during_panics
      - FOMO_driven_investing
    debiasing_communication:
      - systematic_investment_process
      - contrarian_indicators
      - documented_decision_rules
    portfolio_impact: whipsaw_losses, pro_cyclical_trading, poor_market_timing
    detection_rule: "IF client_FOMO_or_panic THEN remind_of_documented_investment_policy"

communication_adaptation_rules:
  IF_ANCHORING_DETECTED:
    action: show_forward_DCF_valuation, update_target_price, provide_multiple_scenarios
  IF_CONFIRMATION_BIAS_DETECTED:
    action: present_bull_AND_bear_case, force_structured_devils_advocate, document_risks
  IF_AVAILABILITY_BIAS_DETECTED:
    action: provide_historical_frequency_chart, compare_current_to_historical_base_rates
  IF_OVERCONFIDENCE_DETECTED:
    action: show_forecast_accuracy_history, widen_confidence_intervals, emphasize_uncertainty
  IF_LOSS_AVERSION_DETECTED:
    action: offer_downside_protection, frame_as_wealth_preservation, show_asymmetric_payoffs
  IF_HERDING_DETECTED:
    action: remind_of_documented_IPS, show_contrarian_valuation_signals, emphasize_long_term_plan
```
<!-- END_RULE_BLOCK -->

---

## SECTION 4: GIPS COMPLIANCE FRAMEWORK (CFA Knowledge Base Section 7.10-7.11)

### 4.1 Overview
GIPS (Global Investment Performance Standards) provides the standardized framework for fair, complete, and accurate performance presentation. CIPHER uses these rules to ensure compliance and validate performance reporting before client distribution.

<!-- RULE_BLOCK: GIPS_COMPLIANCE_V1 -->
```yaml
rule_id: GIPS_COMPLIANCE_V1
source_module: [CIPHER]
confidence: 0.90
gips_framework:
  purpose: Standardize_performance_presentation_for_investment_managers
  authority: CFA_Institute, GIPS_Steering_Committee
  adoption_status: recommended_by_CFA_Standards

gips_eight_sections:
  1_FUNDAMENTALS_OF_COMPLIANCE:
    description: Composite definition, verification scope, methodology governance
    key_rules:
      - must_define_composites_by_objective_and_strategy
      - verification_must_be_by_independent_third_party
      - maintain_documentation_of_policies_and_procedures
      - track_composite_changes_over_time

  2_INPUT_DATA:
    description: Source data integrity, currency, timing
    key_rules:
      - use_trade_date_accounting_or_settlement_date_accounting_consistently
      - include_all_cash_positions_and_accrued_income
      - convert_non_base_currency_data_at_market_rates
      - document_data_quality_procedures
    decision_rule: "IF data_quality_issues THEN disclose_in_notes AND correct_retroactively"

  3_CALCULATION_METHODOLOGY:
    description: Return calculation methods, timing, adjustments
    key_methods:
      time_weighted_return:
        definition: TWR removes impact of cash flows, preferred for manager evaluation
        use_case: manager_performance_attribution, comparing_manager_skill
        formula: "TWR = [(1+R1) × (1+R2) × ... × (1+Rn)] - 1"
        required_for_GIPS: true
      money_weighted_return:
        definition: MWR is internal rate of return, reflects investor experience
        use_case: client_return_analysis, showing_investor_realized_return
        formula: "Solve for rate such that NPV of cash flows = 0"
      modified_dietz:
        definition: Approximation of TWR using weighted average of cash flows
        use_case: GIPS_compliant_monthly_reporting
        formula: "MWR ≈ (Ending Value - Beginning Value - Net Cash Flows) / (BV + Σ(CF_i × Weight_i))"
    decision_rule: "Use_TWR_for_GIPS_manager_presentation; Use_MWR_for_client_return_analysis"
    frequency: daily_or_monthly_as_defined_in_composite

  4_COMPOSITE_CONSTRUCTION:
    description: How accounts grouped, inclusion/exclusion criteria
    key_rules:
      - include_all_discretionary_accounts_in_composite
      - exclude_non_discretionary_accounts
      - exclude_accounts_with_significant_restrictions
      - define_composite_clearly_by_strategy_and_objective
      - separate_composites_for_different_strategies
      - inception_date_is_earliest_account_date_in_composite
    decision_rule: "IF account_added_mid_period THEN include_from_inception OR from_addition_date_with_clear_disclosure"

  5_DISCLOSURE:
    description: Required and recommended disclosures
    required_disclosures:
      - composite_definition
      - investment_strategy_and_objective
      - composite_creation_date_and_inception_date
      - benchmarks_used_and_description
      - fee_schedule
      - valuation_methodology
      - methodology_changes
    recommended_disclosures:
      - composite_assets_as_percent_of_firm_assets
      - non_GIPS_compliant_periods
      - reconciliation_to_firm_assets
      - significant_events_or_external_constraints
    decision_rule: "Disclose_all_required; Strongly_recommend_all_recommended"

  6_PRESENTATION_AND_REPORTING:
    description: How performance presented to clients
    minimum_presentation_period: 5_years_of_performance
    GIPS_composites_table_must_include:
      - composite_return
      - benchmark_return
      - composite_std_dev
      - benchmark_std_dev
      - number_of_accounts_in_composite
      - composite_assets_at_end_of_period
      - firm_assets_at_end_of_period
      - percentage_of_firm_assets
      - dispersion_of_composite_returns
    decision_rule: "IF period < 5_years THEN show_available_history AND note_partial_period"

  7_REAL_ESTATE_PROVISIONS:
    description: Special rules for real estate composites
    key_rules:
      - use_GIPS_real_estate_specific_return_calculation
      - disclose_valuation_methodology
      - mark_to_market_quarterly_or_annually
      - exclude_very_new_properties_first_year

  8_PRIVATE_EQUITY_PROVISIONS:
    description: Special rules for private equity composites
    key_rules:
      - inception_date_is_first_capital_call_or_fund_launch
      - use_modified_dietz_or_money_weighted_return
      - disclose_vintage_year_grouping
      - mark_to_market_consistent_with_valuation_policies

performance_presentation_rules:
  FAIR_AND_ACCURATE:
    rules:
      - cannot_cherry_pick_periods
      - cannot_cherry_pick_accounts
      - must_present_balanced_performance_picture
      - include_both_strong_and_weak_periods_in_history
    violation_scenario: "IF only_showing_best_3_years_of_5_year_history THEN violation"

  COMPLETE_PRESENTATION:
    rules:
      - show_minimum_5_years
      - show_benchmark_alongside_composite
      - show_dispersion_across_accounts
      - disclose_all_material_changes
    decision_rule: "More_information_better_than_less"

  METHODOLOGY_CHANGES:
    rules:
      - must_be_disclosed_promptly
      - must_provide_reconciliation_to_old_methodology
      - must_show_impact_on_reported_returns
    example_change: "Switching_from_Modified_Dietz_to_full_TWR_calculation"

  SUPPLEMENTAL_INFORMATION:
    permitted:
      - custom_benchmarks_if_justified
      - additional_years_of_history
      - alternative_return_metrics_with_methodology_disclosure
      - risk_adjusted_metrics
    required: clear_disclaimer_that_non_GIPS_measures

verification_and_audit:
  third_party_verification:
    required: "Strongly_recommended_after_3_years_of_GIPS_compliance"
    verifier_must:
      - be_independent_of_firm
      - test_compliance_with_GIPS_standards
      - confirm_calculation_accuracy
      - verify_composite_construction
  verification_statement:
    include:
      - period_covered
      - verification_findings
      - areas_of_non_compliance_if_any
      - statement_of_independence

client_communication_rules:
  PERFORMANCE_MARKETING:
    allowed:
      - truthful_historical_returns
      - composite_returns_with_benchmark
      - risk_metrics_with_context
    prohibited:
      - cherry_picked_periods
      - selected_accounts_only
      - performance_without_benchmark_comparison
      - misleading_risk_presentation

  FORECAST_PRESENTATIONS:
    allowed:
      - prospective_returns_if_clearly_labeled_estimates
      - scenario_analysis
      - forward_projections_with_assumptions_disclosed
    required:
      - label_as_estimate_not_guarantee
      - disclose_assumptions_driving_estimate
      - show_sensitivity_to_assumption_changes

decision_framework_for_reporting:
  BEFORE_PERFORMANCE_REPORT_DISTRIBUTION:
    step_1_verify_data: "Check_all_account_values_and_cash_flows_reconcile"
    step_2_check_methodology: "Confirm_calculation_method_matches_policy_and_GIPS_standards"
    step_3_validate_composites: "Verify_all_accounts_properly_classified_and_weighted"
    step_4_check_disclosures: "Ensure_all_required_and_recommended_disclosures_present"
    step_5_review_presentation: "Confirm_table_includes_all_required_fields_and_context"
    step_6_benchmark_comparison: "Verify_benchmark_properly_calculated_and_comparable"
    IF_all_checks_pass: "APPROVE_for_distribution"
    IF_any_check_fails: "REMEDIATE_and_retest_before_distribution"
```
<!-- END_RULE_BLOCK -->

---

## SECTION 5: EQUITY FACTOR SELECTION & ROTATION (CFA Knowledge Base Section 13.9)

### 5.1 Overview
Equity factor exposures drive portfolio returns across market cycles. MANTIS uses these rules to identify which factors are positioned to outperform in different macro regimes and to detect unintended factor exposures that may create risk.

<!-- RULE_BLOCK: EQUITY_FACTORS_V1 -->
```yaml
rule_id: EQUITY_FACTORS_V1
source_module: [MANTIS]
confidence: 0.80
equity_factor_definitions:
  VALUE:
    definition: Low price-to-book, low P/E, high dividend yield
    historical_premium: 3_to_5_percent_annual
    characteristics:
      - P/B_low: less_than_1_2x
      - P/E_low: less_than_market_median
      - dividend_yield_high: above_market_average
    measurement_method:
      - Fama_French_value_factor
      - specific_multiples_screening
    best_environment: recovery_phase, early_expansion
    worst_environment: growth_bubbles, deflation
    signal_strength: strong_in_recovery, weak_in_low_rate_regime

  SIZE:
    definition: Small-cap outperformance relative to large-cap
    historical_premium: 2_to_3_percent_annual
    measurement_method:
      - market_cap_quintile_analysis
      - log_size_regression
      - equal_weight_vs_cap_weight_performance
    best_environment: recovery_phase, reflation_period
    worst_environment: flight_to_quality, recession
    signal_strength: strong_in_credit_easing, weak_in_risk_off

  MOMENTUM:
    definition: Recent winners continue winning in trending markets
    historical_premium: 4_to_8_percent_annual
    characteristics:
      - 12_month_past_return_positive
      - positive_recent_price_trend
      - positive_earnings_revision_momentum
    measurement_method:
      - relative_strength_12_month
      - price_momentum_factor
      - earnings_revision_momentum
    best_environment: trending_markets, low_volatility_regimes
    worst_environment: regime_reversals, sharp_drawdowns
    fragility: most_susceptible_to_crowding_driven_crashes
    crowding_example: "Aug_2007_momentum_crash, Mar_2009_reversal"
    caution: momentum_premium_was_absent_2010_2020_value_period

  QUALITY:
    definition: High ROE, low debt, stable earnings, operational excellence
    historical_premium: 2_to_4_percent_annual
    characteristics:
      - ROE_high: greater_than_median
      - debt_to_equity_low: conservative_leverage
      - earnings_stability: low_earnings_surprise_frequency
      - cash_flow_generation: strong_free_cash_flow
    measurement_method:
      - profitability_score
      - financial_health_metrics
      - earnings_quality_analysis
    best_environment: late_cycle, recession, uncertainty
    worst_environment: speculative_rallies, risk_on_bubbles
    signal_strength: strong_when_recession_risk_rising

  LOW_VOLATILITY:
    definition: Low beta stocks, low volatility, defensive characteristics
    historical_premium: 1_to_2_percent_annual_risk_adjusted
    characteristics:
      - beta_less_than_0_8
      - realized_volatility_below_median
      - downside_capture_ratio_less_than_upside_capture
    measurement_method:
      - historical_volatility_calculation
      - beta_estimation
      - downside_deviation
    best_environment: bear_markets, high_uncertainty
    worst_environment: bull_markets, risk_on_phases
    signal_strength: strong_defensive_hedge

factor_rotation_framework:
  RECESSION_PHASE:
    dominant_factors: [quality, low_volatility]
    rationale: Flight_to_safety, earnings_stability_valued, beta_risk_penalized
    positioning: Overweight_quality, overweight_low_vol, underweight_momentum
    portfolio_construction: High_quality, low_leverage, stable_cash_flows

  EARLY_RECOVERY:
    dominant_factors: [value, size]
    rationale: Beaten_down_stocks_recover_most, small_firms_benefit_from_credit_easing
    positioning: Overweight_value, overweight_size, neutral_to_positive_momentum
    portfolio_construction: Cyclical_exposure, emerging_franchises, credit_sensitives

  MID_EXPANSION:
    dominant_factors: [momentum]
    rationale: Trends_established, growth_visible, earnings_acceleration
    positioning: Overweight_momentum, maintain_quality_core, reduce_value_exposure
    portfolio_construction: Trending_stocks, earnings_growers, momentum_accelerators

  LATE_CYCLE:
    dominant_factors: [quality]
    rationale: Earnings_compression_favors_profitable_companies, momentum_crashes
    positioning: Overweight_quality, neutral_momentum, reduce_cyclical_exposure
    portfolio_construction: Defensive_quality, low_leverage, inflation_hedges

  BEAR_MARKET:
    dominant_factors: [low_volatility, quality]
    rationale: Defensive_characteristics, downside_protection_valued
    positioning: Overweight_defensive, overweight_quality, minimize_beta
    portfolio_construction: High_quality_defensive, minimal_cyclical, cash_raised

factor_crowding_risk:
  definition: When too many investors chase same factor → premium arbitraged → factor becomes fragile
  detection: Rising_dispersion_in_factor_returns, increasing_correlation_among_factor_followers
  worst_offender: momentum_factor_most_susceptible
  historical_examples:
    - August_2007_momentum_crash
    - March_2009_momentum_reversal
    - January_2020_value_reversal
  response_if_detected: Reduce_momentum_overweight, increase_quality_overweight, diversify_factor_sources

portfolio_factor_exposure_diagnostic:
  step_1_regression:
    action: Regress_portfolio_returns_on_factor_returns
    output: Identify_actual_exposures_to_each_factor
  step_2_benchmark_comparison:
    action: Compare_exposures_to_benchmark
    output: Identify_active_factor_bets
  step_3_intentionality_assessment:
    action: Determine_if_bets_are_intentional_alpha_or_unintentional_risk
    output: "Classify_as_ALPHA_SOURCE (intentional) OR UNINTENDED_RISK (risk)"
  step_4_remediation:
    IF_unintentional: "Hedge_or_neutralize_the_exposure"
    IF_intentional: "Ensure_sizing_appropriate_for_conviction_level"
  decision_rule: "No_unintended_factor_bets; All_bets_must_be_documented_with_conviction_and_time_horizon"

factor_selection_rules_by_macro_regime:
  ORACLE_REBOUND:
    primary_factors: [value, size, momentum]
    rationale: Recovery_from_trough_favors_beaten_down_cyclicals
    mantis_action: Increase_small_cap_exposure, tilt_value, emphasize_turnarounds

  ORACLE_EXPANSION:
    primary_factors: [momentum, growth_variant_of_quality]
    rationale: Earnings_acceleration, profitable_growth
    mantis_action: Momentum_overweight, quality_growth, sector_rotation_into_drivers

  ORACLE_SPECULATION:
    primary_factors: [quality, low_volatility_hedges]
    rationale: Late_cycle_excess, earnings_compression, policy_uncertainty
    mantis_action: Reduce_momentum, increase_quality, add_defensive_hedges

  ORACLE_CONTRACTION:
    primary_factors: [quality, low_volatility, defensive_value]
    rationale: Recession_protection, earnings_stability, capital_preservation
    mantis_action: Defensive_positioning, low_beta, quality_overweight, raise_cash

universe_selection_for_mantis:
  solana_ecosystem:
    relevant_factor_exposures: [growth, momentum, innovation_factor]
    caution: High_beta, momentum_factor_heavy, crowding_risk_elevated
    monitoring: Daily_momentum_metrics, trend_persistence, correlation_breakdown

decision_tree_for_factor_allocation:
  IF_regime_is_recovery:
    THEN: "Overweight_value_and_size, underweight_growth"
  ELIF_regime_is_expansion:
    THEN: "Overweight_momentum, maintain_quality_core"
  ELIF_regime_is_late_cycle:
    THEN: "Overweight_quality, underweight_momentum"
  ELIF_regime_is_contraction:
    THEN: "Overweight_low_volatility_and_quality, raise_cash"
  ELSE: "Maintain_balanced_exposure_across_factors"

factor_crowding_remediation:
  IF_momentum_crowding_detected:
    action: Reduce_momentum_exposure_by_25_percent
    alternative: Substitute_with_quality_momentum_combination
  IF_factor_correlation_too_high:
    action: Reduce_largest_factor_bet
    alternative: Increase_diversification_across_factors
  IF_factor_premium_inverted:
    action: Review_systematic_thesis
    alternative: Consider_counter_positioning_if_supported_by_valuation
```
<!-- END_RULE_BLOCK -->

---

## Usage & Integration

These rule blocks are designed for programmatic consumption via `soma_kb_reader.py` and related SOMA infrastructure. Each block can be:
- **Parsed** into SQLite tables for runtime queries
- **Referenced** in decision trees and condition checks within CIPHER, ORACLE, and MANTIS
- **Audited** for consistency with CFA guidance and regulatory expectations
- **Updated** as new CFA curriculum materials are incorporated or macro regimes evolve

**Cross-module flows:**
- **CIPHER** → Ethics + Behavioral rules to shape client communication
- **ORACLE** → Risk framework for regime classification and VaR thresholds
- **MANTIS** → Risk limits + equity factor rotation for position sizing and universe selection

---

**Derived from:** CFA Knowledge Base V14.0 (Sections 4, 5, 13, 16)
**Last verified:** March 22, 2026
**Confidence levels:** 0.80-0.90 across all rule blocks
