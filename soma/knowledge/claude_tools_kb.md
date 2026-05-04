---
name: Claude Tools & Capabilities Knowledge Base
description: Actionable rules extracted from X.com bookmarks (March 2026) covering Claude Code features, MCP ecosystem, prompt strategy, rate limits, workflow optimization, and Cowork usage patterns for DABEIBA operators
source: X.com bookmarks — keywords: claude, anthropic, MCP, claude code, AI tools, prompt, LLM, agent, cowork, skill, agentic
last_updated: 2026-03-29
version: 1.0
scrape_count: 27
sections:
  - claude_code_features
  - claude_mcp_ecosystem
  - claude_workflow_optimization
  - claude_prompt_strategy
  - claude_rate_limits
---

# Claude Tools & Capabilities Knowledge Base

Rules extracted from Milou's X.com bookmarks (March 2026). Each rule block is structured for runtime use by DABEIBA modules. Modules using this KB:

- **ORACLE** — MCP ecosystem, financial data connectors, browser automation
- **MANTIS** — Rate limit awareness, multi-agent orchestration patterns
- **CIPHER** — Cowork workflow, prompt minimalism, output quality control
- **SOMA** — Self-improvement patterns, cross-module capability awareness

---

## SECTION 1: CLAUDE CODE FEATURES

### 1.1 Effort Levels Per Skill

<!-- RULE_BLOCK: CLAUDE_CODE_EFFORT_LEVELS_V1 -->
```yaml
rule_id: CLAUDE_CODE_EFFORT_LEVELS_V1
source_module: [SOMA, MANTIS, CIPHER, ORACLE]
confidence: 0.92
version: 1
source_tweet: "https://x.com/RoundtableSpace/status/2038296375155454376"
source_author: "@RoundtableSpace (0xMarioNawfal)"
source_date: "2026-03-29"
feature:
  name: Claude Code Skill Effort Levels
  description: >
    Claude Code skills now support effort levels that control how long the model
    thinks before answering. Can be set per-skill and overrides the session default.
  mechanics:
    setting_scope: per_skill
    override_behavior: overrides_session_default
    tradeoff: speed_vs_quality
  decision_rule: >
    IF task is fast lookup or formatting → use LOW effort
    IF task is architectural decision or multi-step analysis → use HIGH effort
    IF task is standard code/report generation → use MEDIUM (session default)
  dabeiba_application:
    Research (ORACLE): "Low effort for ticker metadata lookups, high effort for valuation synthesis"
    Decisions (MANTIS): "Low effort for signal checks, high effort for portfolio rebalancing decisions"
    Advisory (CIPHER): "Medium effort for report drafting, high effort for compliance review"
    Synthesis (SOMA): "High effort for all KB rule distillation and cross-AI synthesis"
```
<!-- END_RULE_BLOCK -->

### 1.2 Multi-Agent Orchestration Layer

<!-- RULE_BLOCK: CLAUDE_CODE_MULTIAGENT_V1 -->
```yaml
rule_id: CLAUDE_CODE_MULTIAGENT_V1
source_module: [SOMA, MANTIS]
confidence: 0.85
version: 1
source_tweet: "https://x.com/hasantoxr/status/2037963932204445836"
source_author: "@hasantoxr (Hasan Toor)"
source_date: "2026-03-28"
feature:
  name: Multi-Agent Orchestration on Claude Code
  description: >
    An open-source orchestration layer on top of Claude Code providing 5 execution
    modes, 32 specialized agents, and 3-5x faster output. Zero learning curve —
    no new tools or subscriptions required.
  performance_claim:
    speedup: "3-5x faster output"
    agent_count: 32
    execution_modes: 5
  reference_resource: "claude-howto (github.com/luongnv89/claude-howto)"
  decision_rule: >
    IF DABEIBA run_day.py is taking >30 min → evaluate multi-agent orchestration
    IF any single module is bottlenecking the pipeline → consider agent parallelization
  dabeiba_application:
    Synthesis (SOMA): "Candidate for run_day V2 architecture — parallel module execution"
    Decisions (MANTIS): "Parallel signal computation across universe tickers"
```
<!-- END_RULE_BLOCK -->

### 1.3 Claude How-To Visual Guide

<!-- RULE_BLOCK: CLAUDE_CODE_HOWTO_RESOURCE_V1 -->
```yaml
rule_id: CLAUDE_CODE_HOWTO_RESOURCE_V1
source_module: [Synthesis (SOMA)]
confidence: 0.90
version: 1
source_tweet: "https://x.com/heynavtoor/status/2037803521719017538"
source_author: "@heynavtoor (Nav Toor)"
source_date: "2026-03-28"
resource:
  name: claude-howto
  url: "https://github.com/luongnv89/claude-howto"
  type: visual_guide
  topics_covered:
    - basic_prompts_to_agent_orchestration
    - hooks
    - skills
    - MCP_servers
    - copy_paste_tutorials
  quality_signal: "3 independent bookmarks from different accounts → high signal"
  learning_investment: weekend (verified by multiple sources)
decision_rule: >
  WHEN onboarding to new Claude Code feature → check claude-howto first
  WHEN building new DABEIBA pipeline → reference hooks and skills sections
  WHEN adding MCP → use MCP server section as quick reference
```
<!-- END_RULE_BLOCK -->

### 1.4 Agent Self-Improvement Pattern (AGENT_LEARNINGS.md)

<!-- RULE_BLOCK: CLAUDE_AGENT_SELF_IMPROVEMENT_V1 -->
```yaml
rule_id: CLAUDE_AGENT_SELF_IMPROVEMENT_V1
source_module: [Synthesis (SOMA)]
confidence: 0.93
version: 1
source_tweet: "https://x.com/vishisinghal_/status/2037907362011578543"
source_author: "@vishisinghal_ (Vishakha Singhal)"
source_date: "2026-03-28"
pattern:
  name: AGENT_LEARNINGS.md Self-Improvement Loop
  description: >
    Anthropic engineers use a file called AGENT_LEARNINGS.md that Claude agents
    update whenever they make a mistake. Contains: mistakes made + patterns to avoid.
    This is the official pattern behind DABEIBA's lessons.md.
  file_content_structure:
    - mistakes_made
    - patterns_to_avoid
    - successful_approaches (extension)
  dabeiba_status: ALREADY_IMPLEMENTED
  dabeiba_equivalent: "tasks/lessons.md — same pattern, confirmed as official Anthropic internal practice"
decision_rule: >
  After ANY correction → update tasks/lessons.md immediately (already standard)
  lessons.md IS the official AGENT_LEARNINGS.md pattern — maintain rigorously
  Consider renaming to AGENT_LEARNINGS.md for clarity and alignment with Anthropic convention
validation: "This bookmark CONFIRMS DABEIBA's self-improvement loop is architecturally correct"
```
<!-- END_RULE_BLOCK -->

---

## SECTION 2: CLAUDE MCP ECOSYSTEM

### 2.1 Financial Datasets via MCP

<!-- RULE_BLOCK: CLAUDE_MCP_FINANCIAL_DATA_V1 -->
```yaml
rule_id: CLAUDE_MCP_FINANCIAL_DATA_V1
source_module: [Research (ORACLE), Decisions (MANTIS)]
confidence: 0.88
version: 1
source_tweet: "https://x.com/RoundtableSpace/status/2031146764619669736"
source_author: "@RoundtableSpace (0xMarioNawfal)"
source_date: "2026-03-09"
feature:
  name: Financial Datasets MCP
  description: >
    MCP connector for financial datasets — income statements, balance sheets,
    cash flows, and 30 years of stock data directly inside Claude chat.
  data_available:
    - income_statements
    - balance_sheets
    - cash_flows
    - stock_data_30yr_history
  access_method: MCP_connector
decision_rule: >
  WHEN Research (ORACLE) needs fundamental data beyond GuruFocus quota → check Financial Datasets MCP
  WHEN Decisions (MANTIS) needs 30yr historical price data → Financial Datasets MCP is candidate
  IF GuruFocus hits 6000 call limit → Financial Datasets MCP as overflow source
  ACTION: Evaluate connecting Financial Datasets MCP to Research (ORACLE) TITAN pipeline
dabeiba_priority: HIGH
```
<!-- END_RULE_BLOCK -->

### 2.2 Browser Automation via Claude

<!-- RULE_BLOCK: CLAUDE_BROWSER_AUTOMATION_V1 -->
```yaml
rule_id: CLAUDE_BROWSER_AUTOMATION_V1
source_module: [Research (ORACLE)]
confidence: 0.82
version: 1
source_tweet: "https://x.com/Axel_bitblaze69/status/2038300538346045914"
source_author: "@Axel_bitblaze69 (Axel Bitblaze)"
source_date: "2026-03-29"
feature:
  name: Claude Independent Browser Automation
  description: >
    Claude can now browse the internet with its own dedicated browser (not the
    user's browser). Can login with credentials, scrape data, monitor communities,
    and generate leads — all in the background.
  capabilities:
    - independent_browser_instance
    - credential_login
    - data_scraping
    - community_monitoring
    - background_execution
  decision_rule: >
    WHEN Research (ORACLE) COBALT pipeline needs web scraping → evaluate Claude browser automation
    WHEN Research (ORACLE) needs news monitoring beyond RSS feeds → Claude browser monitoring
    CAUTION: Credential handling requires security review before deployment
  dabeiba_application:
    Research_COBALT: "Macro news and earnings data scraping candidate"
    Research_SPECTRE: "Geopolitical monitoring automation candidate"
```
<!-- END_RULE_BLOCK -->

### 2.3 DexScreener MCP for Crypto Data

<!-- RULE_BLOCK: CLAUDE_MCP_DEXSCREENER_V1 -->
```yaml
rule_id: CLAUDE_MCP_DEXSCREENER_V1
source_module: [Research (ORACLE), Decisions (MANTIS)]
confidence: 0.80
version: 1
source_tweet: "https://x.com/RoundtableSpace/status/2030354041117814854"
source_author: "@RoundtableSpace (0xMarioNawfal)"
source_date: "2026-03-07"
feature:
  name: DexScreener CLI/MCP/Skills Layer
  description: >
    Open-source MCP + CLI + skills layer on top of DexScreener. Pulls live chain
    data, sets alerts, scans hot runners — all from terminal. Agents can read
    crypto alpha directly. Free and open source.
  capabilities:
    - live_onchain_data
    - price_alerts
    - hot_runner_scanning
    - terminal_cli_access
  access: free_open_source
  decision_rule: >
    WHEN Research (ORACLE) SPECTRE needs on-chain Solana data → DexScreener MCP is primary candidate
    WHEN Decisions (MANTIS) needs Jupiter/DEX price feeds → DexScreener MCP + Jupiter API
    ACTION: Evaluate as Research (ORACLE) SPECTRE pipeline data source (on-chain signal layer)
  dabeiba_priority: HIGH
  note: "Aligns with 100% Solana execution decision — direct data source for Decisions (MANTIS) universe"
```
<!-- END_RULE_BLOCK -->

---

## SECTION 3: CLAUDE WORKFLOW OPTIMIZATION

### 3.1 Cowork Background Task Execution

<!-- RULE_BLOCK: CLAUDE_COWORK_WORKFLOW_V1 -->
```yaml
rule_id: CLAUDE_COWORK_WORKFLOW_V1
source_module: [Advisory (CIPHER), Synthesis (SOMA)]
confidence: 0.95
version: 1
source_tweet: "https://x.com/MilkRoadAI/status/2036213528365826115"
source_author: "@MilkRoadAI (Milk Road AI)"
source_date: "2026-03-23"
feature:
  name: Claude Cowork Background Execution
  description: >
    Cowork launched in early 2026 with core premise: describe the task and walk
    away. Claude continues working in the background after the user leaves.
    Computer control + file access + persistent task execution.
  core_premise: "describe task → walk away → Claude keeps working"
  capabilities:
    - background_execution
    - computer_control
    - file_access
    - persistent_tasks
  dabeiba_status: CURRENTLY_IN_USE
  decision_rule: >
    FOR any DABEIBA task >5 steps → delegate to Cowork session
    FOR run_day.py execution → Cowork is the correct interface
    FOR soma_bookmark_sync.py runs → trigger via Cowork scheduled task
    BEST_PRACTICE: Describe full task context upfront; Claude maintains state across steps
```
<!-- END_RULE_BLOCK -->

### 3.2 Rate Limit Management

<!-- RULE_BLOCK: CLAUDE_RATE_LIMIT_MANAGEMENT_V1 -->
```yaml
rule_id: CLAUDE_RATE_LIMIT_MANAGEMENT_V1
source_module: [Synthesis (SOMA), Research (ORACLE), Decisions (MANTIS), Advisory (CIPHER)]
confidence: 0.90
version: 1
source_tweet: "https://x.com/aaronjmars/status/2036230574822580675"
source_author: "@aaronjmars"
source_date: "2026-03-23"
feature:
  name: Claude Rate Limit Window Management
  description: >
    Claude Pro/Max rate limits operate on a 5-hour rolling window that resets
    after the window expires. Anthropic exposes an API endpoint using the Claude
    Code API key to check current usage.
  mechanics:
    window_duration: "5 hours"
    reset_behavior: "resets after 5h window expires"
    monitoring_endpoint: "GET /api/oauth/usage"
    auth_method: "Claude Code API key"
  decision_rule: >
    IF approaching rate limit → pause and wait for 5h window reset
    BEFORE starting heavy run_day.py → check /api/oauth/usage first
    IF run_day.py fails mid-execution → likely rate limited; check usage endpoint
    SCHEDULE heavy ORACLE/MANTIS runs at window reset to maximize throughput
  implementation_note: >
    Can build a pre-flight check in run_day.py that calls /api/oauth/usage
    and aborts with a clear message if usage is >80% of limit
  dabeiba_priority: MEDIUM
```
<!-- END_RULE_BLOCK -->

---

## SECTION 4: CLAUDE PROMPT STRATEGY

### 4.1 Prompt Minimalism — Less Context = Better Output

<!-- RULE_BLOCK: CLAUDE_PROMPT_MINIMALISM_V1 -->
```yaml
rule_id: CLAUDE_PROMPT_MINIMALISM_V1
source_module: [Synthesis (SOMA), Advisory (CIPHER), Research (ORACLE), Decisions (MANTIS)]
confidence: 0.87
version: 1
source_tweet: "https://x.com/itsolelehmann/status/2036213528365826116"
source_author: "@itsolelehmann (Ole Lehmann)"
source_date: "2026-03-23"
insight:
  name: Prompt Minimalism — Deleting Context Improves Output
  description: >
    Deleting half of a Claude setup (system prompts, context, instructions)
    improved output quality. Anthropic's team confirmed: Claude performs better
    with focused, minimal context than with over-specified setups.
  mechanism: >
    Over-specified prompts cause Claude to try to satisfy too many constraints
    simultaneously, diluting focus. Minimal, clear instructions produce sharper outputs.
  decision_rules:
    - "IF prompt > 2000 tokens → audit for removable context before sending"
    - "IF Claude output feels generic → reduce constraints, not increase them"
    - "IF Advisory (CIPHER) report quality degrades → simplify the generation prompt, not complexify"
    - "IF Research (ORACLE) analysis is vague → remove intermediate instructions, keep only goal"
  anti_patterns:
    - over_specifying_format_AND_content_AND_tone_simultaneously
    - stacking_multiple_examples_when_one_suffices
    - including_background_context_Claude_can_infer
  best_practice: >
    Structure prompts as: GOAL + CONSTRAINTS (minimal) + OUTPUT_FORMAT
    Remove anything Claude can reasonably infer from SOMA context
```
<!-- END_RULE_BLOCK -->

### 4.2 Nash Equilibrium Strategist Mode

<!-- RULE_BLOCK: CLAUDE_NASH_EQUILIBRIUM_MODE_V1 -->
```yaml
rule_id: CLAUDE_NASH_EQUILIBRIUM_MODE_V1
source_module: [Synthesis (SOMA), Decisions (MANTIS)]
confidence: 0.78
version: 1
source_tweet: "https://x.com/alex_prompter/status/2037609717845873147"
source_author: "@alex_prompter (Alex Prompter)"
source_date: "2026-03-27"
feature:
  name: Nash Equilibrium Strategist Hidden Mode
  description: >
    Claude has a mode called "Nash Equilibrium Strategist" that maps any
    negotiation, competitive situation, or multi-player decision to formal
    game theory, calculates the Nash Equilibrium, and returns the
    mathematically optimal move.
  trigger_phrase: "Nash Equilibrium Strategist"
  use_cases:
    - negotiation_strategy
    - competitive_market_decisions
    - multi_player_investment_scenarios
    - counterparty_analysis
  decision_rule: >
    WHEN facing multi-party decision with conflicting incentives → invoke Nash Equilibrium Strategist
    WHEN Decisions (MANTIS) is evaluating market-maker vs taker dynamics → apply game theory framing
    WHEN Advisory (CIPHER) is preparing for client negotiation → use this mode for positioning
  confidence_note: "Treat as prompt pattern, not a literal hidden mode — but high utility regardless"
```
<!-- END_RULE_BLOCK -->

### 4.3 Prompt Master Skill

<!-- RULE_BLOCK: CLAUDE_PROMPT_MASTER_SKILL_V1 -->
```yaml
rule_id: CLAUDE_PROMPT_MASTER_SKILL_V1
source_module: [Synthesis (SOMA), Advisory (CIPHER)]
confidence: 0.83
version: 1
source_tweet: "https://x.com/hasantoxr/status/2037533806001836359"
source_author: "@hasantoxr (Hasan Toor)"
source_date: "2026-03-27"
feature:
  name: Prompt Master Skill
  description: >
    A free Claude skill that writes the perfect prompt for any AI tool on the
    first try — no re-prompts, no wasted credits, no fourth attempt.
  type: free_claude_skill
  benefit: "First-try perfect prompts for any AI tool"
  decision_rule: >
    WHEN crafting prompts for Grok, Gemini, or ChatGPT in cross-AI workflow →
    use Prompt Master skill to pre-optimize before sending
    WHEN building ai_prompt_builder.py enhancements → incorporate Prompt Master logic
  dabeiba_application:
    Synthesis (SOMA): "Enhance ai_prompt_builder.py with Prompt Master pattern"
    Advisory (CIPHER): "Pre-optimize Advisory (CIPHER) report generation prompts"
  action: "Find and install Prompt Master skill; evaluate for ai_prompt_builder.py integration"
```
<!-- END_RULE_BLOCK -->

---

## SECTION 5: LLM ECOSYSTEM CONTEXT

### 5.1 Google TurboQuant — LLM Compression Breakthrough

<!-- RULE_BLOCK: LLM_TURBOQUANT_COMPRESSION_V1 -->
```yaml
rule_id: LLM_TURBOQUANT_COMPRESSION_V1
source_module: [Synthesis (SOMA)]
confidence: 0.92
version: 1
source_tweet: "https://x.com/GoogleResearch/status/2036533564158910740"
source_author: "@GoogleResearch"
source_date: "2026-03-24"
development:
  name: Google TurboQuant
  description: >
    New LLM compression algorithm from Google Research that reduces key-value
    cache memory by at least 6x and delivers up to 8x speedup with zero accuracy
    loss. Enables INCREDIBLE AI models on 16GB Mac Mini locally.
  metrics:
    memory_reduction: "6x minimum (KV cache)"
    speedup: "up to 8x"
    accuracy_loss: "zero"
  implications:
    - Local LLM quality dramatically improves on M1/M2 MacBook
    - phi4-mini (CIPHER INTEL local AI) may get significant speedup
    - On-device inference becomes much more viable
  decision_rule: >
    WHEN phi4-mini performance is bottlenecking Advisory (CIPHER) INTEL → check for TurboQuant-compatible builds
    MONITOR: ollama team TurboQuant integration (likely Q2 2026)
    DABEIBA local AI (Advisory (CIPHER) INTEL) is prime beneficiary
  dabeiba_relevance: HIGH
```
<!-- END_RULE_BLOCK -->

### 5.2 LLM-Ready Markdown for Agent Ingestion

<!-- RULE_BLOCK: LLM_READY_MARKDOWN_V1 -->
```yaml
rule_id: LLM_READY_MARKDOWN_V1
source_module: [Research (ORACLE), Synthesis (SOMA)]
confidence: 0.85
version: 1
source_tweet: "https://x.com/LLMJunky/status/2036677722400035067"
source_author: "@LLMJunky (am.will)"
source_date: "2026-02-15"
feature:
  name: LLM-Ready Markdown Converter
  description: >
    Tool that converts any website into clean, LLM-ready markdown for agent
    ingestion — uses 80% fewer tokens than raw HTML/text extraction.
  benefit:
    token_reduction: "80% fewer tokens"
    output_format: clean_markdown
    input: any_website
  decision_rule: >
    WHEN Research (ORACLE) COBALT scrapes financial news sites → pre-process through LLM-ready markdown
    WHEN Research (ORACLE) TITAN fetches earnings reports → use markdown converter before LLM processing
    80% token savings = ~5x more data per API call budget
  implementation_note: >
    Evaluate jina.ai/r/ prefix approach or similar — prepend URL with converter endpoint
    Example: https://r.jina.ai/https://financialsite.com/earnings
  dabeiba_priority: HIGH
  note: "Particularly valuable for Research (ORACLE) pipeline where raw web content is processed"
```
<!-- END_RULE_BLOCK -->
