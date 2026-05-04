# SOMA AI Registry — Cross-AI Coordination Layer

---
description: AI capability profiles, task archetypes, and prompt coordination rules for DABEIBA cross-AI workflow
source: Web research (March 2026) + DABEIBA operational history + cross-AI synthesis rounds
tags:
  - ai_registry
  - cross_ai
  - prompt_engineering
  - capability_tracking
modules:
  - CROSS_AI
  - ORACLE
  - MANTIS
  - CIPHER
last_updated: "2026-03-29"
---

## 1. Purpose

This registry is the single source of truth for every AI that participates in DABEIBA's
cross-AI workflow. It stores each AI's capabilities, limitations, preferred prompt format,
and assigned specialty lens. The prompt builder reads this registry to generate tailored
prompts that exploit each AI's strengths while respecting its constraints.

**Design principles:**
- Profiles are YAML rule blocks, parsed by the same KBReader as all other SOMA rules
- Capability-check prompts are the self-updating mechanism — paste into the AI, bring
  the structured response back, update the profile
- Context budgets are enforced — the prompt builder compresses SOMA data to fit the
  target AI's context window, prioritizing the most relevant information
- Fire-and-forget — if the registry is unavailable, the prompt builder falls back
  to a generic template

---

## 2. AI Profiles

### 2.1 Claude (Anthropic)

<!-- RULE_BLOCK: AI_PROFILE_CLAUDE_V1 -->
```yaml
rule_id: AI_PROFILE_CLAUDE_V1
source_module: CROSS_AI
version: 1
rules:
  PROFILE:
    name: Claude
    provider: Anthropic
    model_family: Claude 4.6
    current_model: claude-opus-4-6
    access_method: cowork
    url: https://claude.com
    context_window: 1000000
    max_output_tokens: 128000
    training_cutoff: "2025-05"
    last_verified: "2026-03-29"
    verification_freshness_days: 30
    cost_tier: included

  CAPABILITIES:
    web_search: true
    code_execution: true
    file_upload: true
    file_creation: true
    image_generation: false
    image_understanding: true
    audio_understanding: false
    video_understanding: false
    long_context: true
    system_prompt: true
    structured_output: true
    tool_use: true
    real_time_data: false
    deep_research: false
    thinking_mode: true
    canvas_mode: false
    mcp_support: true
    local_file_access: true

  SPECIALTY:
    primary: implementation
    secondary:
      - code_architecture
      - synthesis
      - documentation
      - cross_ai_coordination
    lens: "Implementation & synthesis — builds all DABEIBA code, coordinates cross-AI findings, resolves disagreements"

  PROMPT_PREFERENCES:
    format: markdown_with_xml_tags
    likes:
      - structured_context
      - explicit_requirements
      - step_by_step_breakdown
      - xml_tag_boundaries
    dislikes:
      - ambiguous_scope
      - open_ended_without_constraints
    optimal_prompt_length: long
    include_prior_findings: true

  KNOWN_LIMITATIONS:
    - Cannot access real-time market data natively
    - Image generation not available
    - Training cutoff May 2025 — use web search for anything after
    - Audio/video understanding not available

  DABEIBA_ROLE:
    assigned_lens: implementation_and_synthesis
    review_types:
      - code_review
      - architecture_implementation
      - cross_ai_synthesis
      - documentation
    modules:
      - ORACLE
      - MANTIS
      - CIPHER
      - SOMA
    past_contributions:
      - "Built entire DABEIBA codebase"
      - "SOMA architecture and all phase builds"
      - "Cross-AI synthesis lead — resolves Grok/Gemini/ChatGPT disagreements"
      - "KB system, validation layer, prompt coordinator"
```
<!-- END_RULE_BLOCK -->

### 2.2 Grok (xAI)

<!-- RULE_BLOCK: AI_PROFILE_GROK_V1 -->
```yaml
rule_id: AI_PROFILE_GROK_V1
source_module: CROSS_AI
version: 1
rules:
  PROFILE:
    name: Grok
    provider: xAI
    model_family: Grok 3
    current_model: grok-3
    access_method: web_ui
    url: https://x.com/i/grok
    context_window: 1000000
    max_output_tokens: 100000
    training_cutoff: "2025-03"
    last_verified: "2026-03-29"
    verification_freshness_days: 30
    cost_tier: subscription
    subscription: SuperGrok

  CAPABILITIES:
    web_search: true
    code_execution: true
    file_upload: true
    file_creation: false
    image_generation: true
    image_understanding: true
    audio_understanding: false
    video_understanding: false
    long_context: true
    system_prompt: false
    structured_output: false
    tool_use: false
    real_time_data: true
    deep_research: true
    thinking_mode: true
    canvas_mode: false
    mcp_support: false
    local_file_access: false

  MODES:
    standard: "Fast responses, no extended reasoning"
    think: "Step-by-step reasoning, slower, more accurate"
    big_brain: "Full-sized model with deep reasoning — slowest, most thorough"
    deep_search: "Multi-step web research with source citations and progress tracking"

  SPECIALTY:
    primary: quantitative_analysis
    secondary:
      - statistical_rigor
      - market_data
      - social_sentiment
      - real_time_information
    lens: "Quantitative/statistical — Sharpe significance, walk-forward methodology, parameter sensitivity, statistical rigor. Has real-time X/Twitter data access."

  PROMPT_PREFERENCES:
    format: markdown
    likes:
      - explicit_numbers_and_data
      - statistical_context
      - clear_hypotheses_to_test
      - tabular_data
      - specific_questions_not_open_ended
    dislikes:
      - vague_requests
      - too_much_narrative_without_data
      - prompts_requiring_file_creation
    optimal_prompt_length: medium
    include_prior_findings: true
    recommended_mode: think

  KNOWN_LIMITATIONS:
    - No persistent memory between sessions
    - Cannot create downloadable files (no file_creation)
    - X/Twitter data bias in real-time feeds
    - No system prompt in web UI — role must be assigned inline
    - Code execution uses sandbox — cannot install arbitrary packages
    - SuperGrok subscription required for full features

  DABEIBA_ROLE:
    assigned_lens: quantitative
    review_types:
      - backtest_validation
      - statistical_significance
      - walk_forward_analysis
      - parameter_sensitivity
      - sharpe_decomposition
      - market_data_verification
    modules:
      - MANTIS
      - ORACLE
    past_contributions:
      - "Identified p>0.43 Sharpe insignificance in V2 Option C"
      - "Proposed walk-forward framework (36m IS / 12m OOS, min OOS Sharpe 0.65)"
      - "Flagged MSTR risk concentration under equal weighting (2.6x risk of NVDA)"
      - "Confirmed option hedging rejection (IV 1.3-1.6x higher than RV)"
      - "Rated xStocks regulatory risk — needs legal opinion"
```
<!-- END_RULE_BLOCK -->

### 2.3 Gemini (Google)

<!-- RULE_BLOCK: AI_PROFILE_GEMINI_V1 -->
```yaml
rule_id: AI_PROFILE_GEMINI_V1
source_module: CROSS_AI
version: 1
rules:
  PROFILE:
    name: Gemini
    provider: Google DeepMind
    model_family: Gemini 2.5
    current_model: gemini-2.5-pro
    access_method: web_ui
    url: https://gemini.google.com
    context_window: 1048576
    max_output_tokens: 65536
    training_cutoff: "2025-01"
    last_verified: "2026-03-29"
    verification_freshness_days: 30
    cost_tier: subscription
    subscription: Gemini Advanced

  CAPABILITIES:
    web_search: true
    code_execution: true
    file_upload: true
    file_creation: true
    image_generation: true
    image_understanding: true
    audio_understanding: true
    video_understanding: true
    long_context: true
    system_prompt: true
    structured_output: true
    tool_use: true
    real_time_data: false
    deep_research: true
    thinking_mode: true
    canvas_mode: true
    mcp_support: false
    local_file_access: false

  MODES:
    standard: "Fast, no extended reasoning"
    thinking: "Extended reasoning with step-by-step work"
    deep_think: "Most thorough — works with code execution and search automatically"
    deep_research: "Multi-step research with file upload and interactive output"
    canvas: "Interactive code/document creation and editing"

  SPECIALTY:
    primary: architecture_and_compliance
    secondary:
      - infrastructure_design
      - regulatory_analysis
      - tax_compliance
      - deployment_strategy
      - multimodal_analysis
    lens: "Architecture/compliance — infrastructure, tax, regulatory, deployment. Strongest multimodal capability (audio, video, images). Deep Research mode produces comprehensive reports."

  PROMPT_PREFERENCES:
    format: markdown
    likes:
      - architecture_diagrams
      - compliance_checklists
      - structured_requirements
      - clear_scope_boundaries
      - file_uploads_for_context
    dislikes:
      - prompts_assuming_prior_context
      - unstructured_data_dumps
    optimal_prompt_length: long
    include_prior_findings: true
    recommended_mode: deep_think

  KNOWN_LIMITATIONS:
    - No persistent memory between sessions
    - No real-time market data feed
    - Google ecosystem bias in search results
    - Deep Research can take several minutes
    - Canvas mode separate from chat — context doesn't always carry over
    - Training cutoff earlier than competitors

  DABEIBA_ROLE:
    assigned_lens: architecture_and_compliance
    review_types:
      - architecture_review
      - compliance_audit
      - tax_analysis
      - deployment_planning
      - infrastructure_design
      - security_review
    modules:
      - MANTIS
      - ORACLE
      - SOMA
    past_contributions:
      - "Caught volatility annualization mismatch (sqrt365 vs sqrt252) — rated FAIL"
      - "Flagged Quebec tax reclassification risk (53.31% vs 26.65%)"
      - "Recommended WAL mode, class design, package structure for SOMA"
      - "Proposed split KB, backup strategy, migration approach"
      - "Rated xStocks as career-ending regulatory risk"
      - "Proposed Docker deployment, dead-man switch, Telegram bot"
```
<!-- END_RULE_BLOCK -->

### 2.4 ChatGPT (OpenAI)

<!-- RULE_BLOCK: AI_PROFILE_CHATGPT_V1 -->
```yaml
rule_id: AI_PROFILE_CHATGPT_V1
source_module: CROSS_AI
version: 1
rules:
  PROFILE:
    name: ChatGPT
    provider: OpenAI
    model_family: GPT-5.4
    current_model: gpt-5.4-thinking
    access_method: web_ui
    url: https://chatgpt.com
    context_window: 128000
    max_output_tokens: 32000
    training_cutoff: "2025-06"
    last_verified: "2026-03-29"
    verification_freshness_days: 30
    cost_tier: subscription
    subscription: ChatGPT Plus

  CAPABILITIES:
    web_search: true
    code_execution: true
    file_upload: true
    file_creation: true
    image_generation: true
    image_understanding: true
    audio_understanding: true
    video_understanding: false
    long_context: true
    system_prompt: true
    structured_output: true
    tool_use: true
    real_time_data: false
    deep_research: true
    thinking_mode: true
    canvas_mode: true
    mcp_support: false
    local_file_access: false

  MODES:
    instant: "Fast, no extended reasoning"
    thinking: "Extended reasoning with chain-of-thought"
    deep_research: "Multi-step research with citations"
    canvas: "Interactive document/code editing"

  SPECIALTY:
    primary: product_and_ux
    secondary:
      - workflow_design
      - feature_prioritization
      - risk_framework_design
      - creative_problem_solving
    lens: "Product/UX — workflow design, feature prioritization, user experience. Strong at identifying structural gaps others miss."

  PROMPT_PREFERENCES:
    format: markdown
    likes:
      - clear_user_stories
      - prioritized_requirements
      - visual_mockup_requests
      - comparative_analysis
    dislikes:
      - overly_technical_without_business_context
      - raw_code_dumps_without_explanation
    optimal_prompt_length: medium
    include_prior_findings: true
    recommended_mode: thinking

  KNOWN_LIMITATIONS:
    - Smaller context window than competitors (128K vs 1M)
    - GPT-4o and older models retired from ChatGPT as of Feb 2026
    - No persistent memory across sessions (custom instructions only)
    - Canvas context may not carry into main chat
    - DALL-E image gen is stylistically opinionated

  DABEIBA_ROLE:
    assigned_lens: product_and_risk_architecture
    review_types:
      - ux_review
      - workflow_design
      - risk_framework
      - feature_prioritization
      - structural_gap_analysis
    modules:
      - MANTIS
      - CIPHER
      - ORACLE
    past_contributions:
      - "Identified asset-class-aware risk layer — neither Grok nor Gemini caught it"
      - "Proposed manual confirm flow for rebalances"
      - "Suggested threshold-based rebalancing to reduce turnover"
      - "Rated real worst-case DD at 65-75% (not 47%)"
      - "Proposed ORACLE-to-MANTIS regime integration"
```
<!-- END_RULE_BLOCK -->

### 2.5 Phi-4 Mini (Local — Ollama)

<!-- RULE_BLOCK: AI_PROFILE_PHI4MINI_V1 -->
```yaml
rule_id: AI_PROFILE_PHI4MINI_V1
source_module: CROSS_AI
version: 1
rules:
  PROFILE:
    name: Phi-4 Mini
    provider: Microsoft (local via Ollama)
    model_family: Phi-4
    current_model: phi4-mini
    access_method: local_ollama
    url: http://localhost:11434
    context_window: 16384
    max_output_tokens: 4096
    training_cutoff: "2025-01"
    last_verified: "2026-03-22"
    verification_freshness_days: 90
    cost_tier: free
    hardware:
      current: "M1 MacBook Air 8GB"
      model_size_gb: 2.2
      quantization: Q4_K_M
      tokens_per_second: 15

  CAPABILITIES:
    web_search: false
    code_execution: false
    file_upload: false
    file_creation: false
    image_generation: false
    image_understanding: false
    audio_understanding: false
    video_understanding: false
    long_context: false
    system_prompt: true
    structured_output: false
    tool_use: false
    real_time_data: false
    deep_research: false
    thinking_mode: false
    canvas_mode: false
    mcp_support: false
    local_file_access: false

  SPECIALTY:
    primary: lightweight_text_processing
    secondary:
      - tagging
      - summarization
      - classification
    lens: "Lightweight local processing — runs on M1 8GB for tagging, summarization, and classification tasks. No network dependency."

  PROMPT_PREFERENCES:
    format: plain_text
    likes:
      - short_focused_prompts
      - single_task_per_prompt
      - clear_output_format
    dislikes:
      - long_context_windows
      - multi_step_reasoning
      - complex_json_output
    optimal_prompt_length: short
    include_prior_findings: false
    recommended_mode: standard

  KNOWN_LIMITATIONS:
    - 3.8B parameters — limited reasoning capability
    - 16K context window — cannot process long documents
    - No web search or real-time data
    - No tool use or code execution
    - Hallucination rate higher than frontier models
    - Only suitable for CIPHER INTEL tagging tasks

  DABEIBA_ROLE:
    assigned_lens: local_processing
    review_types: []
    modules:
      - CIPHER
    current_usage: "CIPHER INTEL submodule — tags research notes, classifies YouTube transcripts"
    past_contributions:
      - "Processes CIPHER INTEL note tagging locally"
```
<!-- END_RULE_BLOCK -->

---

## 3. Task Archetypes

Task archetypes define what SOMA data, KB context, and prompt structure each review
type requires. The prompt builder reads both the AI profile and the task archetype
to generate a tailored prompt.

### 3.1 Quantitative Review

<!-- RULE_BLOCK: TASK_QUANT_REVIEW_V1 -->
```yaml
rule_id: TASK_QUANT_REVIEW_V1
source_module: CROSS_AI
version: 1
rules:
  TASK:
    name: Quantitative Review
    description: "Statistical validation of backtest results, strategy parameters, or trading logic"
    preferred_ais:
      - grok
      - claude
    fallback_ais:
      - gemini
      - chatgpt

  SOMA_CONTEXT:
    required:
      - regime_history_latest
      - portfolio_state
    optional:
      - valuation_summary
      - trade_log_recent
      - kb_violations

  KB_SECTIONS:
    required:
      - mantis_mechanics
    optional:
      - macro_regimes

  PROMPT_STRUCTURE:
    - role_and_lens
    - dabeiba_context_summary
    - soma_data_snapshot
    - specific_question
    - cross_ai_prior_findings
    - requested_output_format

  OUTPUT_FORMAT:
    structure: "numbered findings with severity (PASS/CONCERN/FAIL)"
    require_evidence: true
    require_p_values: true
    require_confidence_intervals: true

  CROSS_AI_HISTORY:
    look_in:
      - "mantis_mechanics.md sections 11-14"
      - "kb_violations where source_module = MANTIS"
    include_prior: true
```
<!-- END_RULE_BLOCK -->

### 3.2 Architecture & Infrastructure Review

<!-- RULE_BLOCK: TASK_ARCH_REVIEW_V1 -->
```yaml
rule_id: TASK_ARCH_REVIEW_V1
source_module: CROSS_AI
version: 1
rules:
  TASK:
    name: Architecture Review
    description: "System design, infrastructure, deployment, security, and database review"
    preferred_ais:
      - gemini
      - claude
    fallback_ais:
      - chatgpt

  SOMA_CONTEXT:
    required:
      - schema_version
      - db_size
      - table_counts
    optional:
      - kb_violations
      - regime_history_latest

  KB_SECTIONS:
    required: []
    optional:
      - mantis_mechanics
      - macro_regimes

  PROMPT_STRUCTURE:
    - role_and_lens
    - architecture_description
    - code_or_schema_excerpt
    - specific_question
    - cross_ai_prior_findings
    - requested_output_format

  OUTPUT_FORMAT:
    structure: "categorized findings (Architecture, Security, Performance, Scalability)"
    require_evidence: true
    require_alternatives: true

  CROSS_AI_HISTORY:
    look_in:
      - "mantis_mechanics.md sections 10, 15"
      - "changelog.md"
    include_prior: true
```
<!-- END_RULE_BLOCK -->

### 3.3 Compliance & Regulatory Review

<!-- RULE_BLOCK: TASK_COMPLIANCE_REVIEW_V1 -->
```yaml
rule_id: TASK_COMPLIANCE_REVIEW_V1
source_module: CROSS_AI
version: 1
rules:
  TASK:
    name: Compliance Review
    description: "Regulatory, tax, legal, and CFA compliance analysis"
    preferred_ais:
      - gemini
      - chatgpt
    fallback_ais:
      - grok

  SOMA_CONTEXT:
    required:
      - regime_history_latest
      - portfolio_state
    optional:
      - trade_log_recent
      - kb_violations

  KB_SECTIONS:
    required:
      - communication_compliance
      - cfa_operational_rules
    optional:
      - mantis_mechanics

  PROMPT_STRUCTURE:
    - role_and_lens
    - regulatory_context
    - jurisdiction_details
    - specific_question
    - cross_ai_prior_findings
    - requested_output_format

  OUTPUT_FORMAT:
    structure: "risk matrix (issue, severity, jurisdiction, recommended action)"
    require_evidence: true
    require_citations: true

  CROSS_AI_HISTORY:
    look_in:
      - "mantis_mechanics.md sections 17-18"
      - "communication_compliance.md"
    include_prior: true
```
<!-- END_RULE_BLOCK -->

### 3.4 Macro & Regime Analysis

<!-- RULE_BLOCK: TASK_MACRO_ANALYSIS_V1 -->
```yaml
rule_id: TASK_MACRO_ANALYSIS_V1
source_module: CROSS_AI
version: 1
rules:
  TASK:
    name: Macro Analysis
    description: "Macroeconomic regime assessment, GLI interpretation, and market outlook"
    preferred_ais:
      - grok
      - gemini
    fallback_ais:
      - chatgpt
      - claude

  SOMA_CONTEXT:
    required:
      - regime_history_full
      - gli_components
    optional:
      - valuation_summary
      - outlook_latest
      - portfolio_state

  KB_SECTIONS:
    required:
      - macro_regimes
    optional:
      - valuation_models

  PROMPT_STRUCTURE:
    - role_and_lens
    - current_regime_snapshot
    - gli_components_detail
    - regime_history_context
    - specific_question
    - cross_ai_prior_findings
    - requested_output_format

  OUTPUT_FORMAT:
    structure: "regime assessment with forward indicators and probability estimates"
    require_evidence: true
    require_data_sources: true

  CROSS_AI_HISTORY:
    look_in:
      - "macro_regimes.md"
      - "mantis_mechanics.md section 9"
    include_prior: true
```
<!-- END_RULE_BLOCK -->

### 3.5 Strategy Review (Holistic)

<!-- RULE_BLOCK: TASK_STRATEGY_REVIEW_V1 -->
```yaml
rule_id: TASK_STRATEGY_REVIEW_V1
source_module: CROSS_AI
version: 1
rules:
  TASK:
    name: Strategy Review
    description: "Cross-module holistic strategy assessment — portfolio, risk, communication alignment"
    preferred_ais:
      - chatgpt
      - gemini
    fallback_ais:
      - grok

  SOMA_CONTEXT:
    required:
      - regime_history_latest
      - valuation_summary
      - portfolio_state
      - outlook_latest
    optional:
      - trade_log_recent
      - kb_violations
      - client_profiles

  KB_SECTIONS:
    required:
      - macro_regimes
      - valuation_models
      - communication_compliance
    optional:
      - mantis_mechanics

  PROMPT_STRUCTURE:
    - role_and_lens
    - dabeiba_platform_overview
    - soma_full_snapshot
    - module_status_summary
    - specific_question
    - cross_ai_prior_findings
    - requested_output_format

  OUTPUT_FORMAT:
    structure: "strategic assessment with prioritized action items"
    require_evidence: true
    require_trade_offs: true

  CROSS_AI_HISTORY:
    look_in:
      - "all KB files"
      - "kb_violations"
    include_prior: true
```
<!-- END_RULE_BLOCK -->

### 3.6 Valuation Review

<!-- RULE_BLOCK: TASK_VALUATION_REVIEW_V1 -->
```yaml
rule_id: TASK_VALUATION_REVIEW_V1
source_module: CROSS_AI
version: 1
rules:
  TASK:
    name: Valuation Review
    description: "Company valuation methodology, DCF assumptions, and fair value assessment"
    preferred_ais:
      - grok
      - chatgpt
    fallback_ais:
      - gemini

  SOMA_CONTEXT:
    required:
      - valuation_summary
      - regime_history_latest
    optional:
      - portfolio_state
      - kb_violations

  KB_SECTIONS:
    required:
      - valuation_models
    optional:
      - macro_regimes

  PROMPT_STRUCTURE:
    - role_and_lens
    - valuation_data_snapshot
    - methodology_description
    - specific_question
    - requested_output_format

  OUTPUT_FORMAT:
    structure: "per-ticker assessment with methodology validation"
    require_evidence: true
    require_sensitivity_analysis: true

  CROSS_AI_HISTORY:
    look_in:
      - "valuation_models.md"
    include_prior: false
```
<!-- END_RULE_BLOCK -->

---

## 4. Future AI Onboarding

When hardware upgrades enable new local models or new AI services are added:

1. Generate a **capability-check prompt** via `soma_query.py "check capabilities [name]"`
2. Paste the prompt into the new AI — it will self-report its capabilities in structured YAML
3. Add a new `AI_PROFILE_[NAME]_V1` block to this file
4. Assign a specialty lens and DABEIBA role
5. The prompt builder immediately starts generating tailored prompts for it

### Candidate Local Models (Post Hardware Upgrade)

| Model | Min RAM | Params | Best For |
|-------|---------|--------|----------|
| Qwen 2.5 3B | 8GB | 3B | Fast tagging, classification |
| Llama 3.3 8B | 16GB | 8B | General chat, code assist |
| Mistral Nemo 12B | 16GB | 12B | Instruction following |
| Llama 3.3 70B | 64GB | 70B | Near-frontier reasoning |
| DeepSeek V3 | 64GB+ | 671B MoE | Code, math, reasoning |
| Qwen 2.5 72B | 64GB | 72B | Multilingual, long context |

---

## 5. Staleness Policy

- **Cloud AIs (Grok, Gemini, ChatGPT, Claude):** Re-verify every 30 days
- **Local models (Phi-4, Ollama):** Re-verify every 90 days (they don't auto-update)
- **New AI after onboarding:** Verify within 7 days of first use
- Staleness warnings surface in `soma_status.py` and when generating prompts
