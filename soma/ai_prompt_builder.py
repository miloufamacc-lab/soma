#!/usr/bin/env python3
"""
SOMA AI Prompt Builder — generates tailored cross-AI prompts from registry + SOMA data.

Usage:
    python3 ~/Desktop/DABEIBA/shared/soma/ai_prompt_builder.py grok "quant review" "Is the walk-forward efficiency realistic?"
    python3 ~/Desktop/DABEIBA/shared/soma/ai_prompt_builder.py gemini "arch review" "Review SOMA schema v5 design"
    python3 ~/Desktop/DABEIBA/shared/soma/ai_prompt_builder.py --list-ais
    python3 ~/Desktop/DABEIBA/shared/soma/ai_prompt_builder.py --check grok
    python3 ~/Desktop/DABEIBA/shared/soma/ai_prompt_builder.py --recommend "review MANTIS backtest"

How it works:
    1. Reads the target AI's profile from ai_registry.md (via KBReader)
    2. Reads the task archetype to know what SOMA data + KB context to include
    3. Gathers live SOMA data (regime, valuations, portfolio, etc.)
    4. Compresses context to fit the AI's context window
    5. Formats the prompt using the AI's preferred style
    6. Saves to shared/soma/prompts/ and prints to terminal
"""

import os
import sys
import json
import datetime

# Make shared package importable
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.join(_THIS_DIR, "..", "..")
sys.path.insert(0, _PROJECT_ROOT)
sys.path.insert(0, _THIS_DIR)

try:
    from shared.soma.soma_bridge import SomaBridge
except ImportError:
    from soma_bridge import SomaBridge

# ── ANSI ─────────────────────────────────────────────────────────────────
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
WHITE = "\033[97m"
RESET = "\033[0m"
W = 62


# ── Helpers ──────────────────────────────────────────────────────────────

def _estimate_tokens(text):
    """Rough token estimate: ~4 characters per token."""
    return len(text) // 4


def _compress_text(text, max_tokens):
    """Truncate text to fit within token budget."""
    max_chars = max_tokens * 4
    if len(text) <= max_chars:
        return text
    return text[:max_chars - 50] + "\n\n[... truncated to fit context window ...]"


def _today():
    return datetime.date.today().strftime("%Y-%m-%d")


# ── AI Name Resolution ───────────────────────────────────────────────────

_AI_ALIASES = {
    "grok": "AI_PROFILE_GROK_V1",
    "xai": "AI_PROFILE_GROK_V1",
    "gemini": "AI_PROFILE_GEMINI_V1",
    "google": "AI_PROFILE_GEMINI_V1",
    "chatgpt": "AI_PROFILE_CHATGPT_V1",
    "openai": "AI_PROFILE_CHATGPT_V1",
    "gpt": "AI_PROFILE_CHATGPT_V1",
    "claude": "AI_PROFILE_CLAUDE_V1",
    "anthropic": "AI_PROFILE_CLAUDE_V1",
    "phi4": "AI_PROFILE_PHI4MINI_V1",
    "phi": "AI_PROFILE_PHI4MINI_V1",
    "local": "AI_PROFILE_PHI4MINI_V1",
}

_TASK_ALIASES = {
    "quant": "TASK_QUANT_REVIEW_V1",
    "quant review": "TASK_QUANT_REVIEW_V1",
    "quantitative": "TASK_QUANT_REVIEW_V1",
    "backtest": "TASK_QUANT_REVIEW_V1",
    "stats": "TASK_QUANT_REVIEW_V1",
    "arch": "TASK_ARCH_REVIEW_V1",
    "arch review": "TASK_ARCH_REVIEW_V1",
    "architecture": "TASK_ARCH_REVIEW_V1",
    "infra": "TASK_ARCH_REVIEW_V1",
    "compliance": "TASK_COMPLIANCE_REVIEW_V1",
    "compliance review": "TASK_COMPLIANCE_REVIEW_V1",
    "regulatory": "TASK_COMPLIANCE_REVIEW_V1",
    "tax": "TASK_COMPLIANCE_REVIEW_V1",
    "legal": "TASK_COMPLIANCE_REVIEW_V1",
    "macro": "TASK_MACRO_ANALYSIS_V1",
    "macro analysis": "TASK_MACRO_ANALYSIS_V1",
    "regime": "TASK_MACRO_ANALYSIS_V1",
    "gli": "TASK_MACRO_ANALYSIS_V1",
    "strategy": "TASK_STRATEGY_REVIEW_V1",
    "strategy review": "TASK_STRATEGY_REVIEW_V1",
    "holistic": "TASK_STRATEGY_REVIEW_V1",
    "valuation": "TASK_VALUATION_REVIEW_V1",
    "valuation review": "TASK_VALUATION_REVIEW_V1",
    "dcf": "TASK_VALUATION_REVIEW_V1",
}


# ── Core Engine ──────────────────────────────────────────────────────────

class AIPromptBuilder:
    """Generates cross-AI prompts tailored to each AI's capabilities."""

    def __init__(self, db_path=None):
        self.db_path = db_path or os.path.join(_THIS_DIR, "data", "soma.db")
        self._bridge = None
        self._kb = None

    def _get_bridge(self):
        if self._bridge is None:
            self._bridge = SomaBridge(self.db_path)
            self._bridge.__enter__()
            self._bridge.initialize_db()
        return self._bridge

    def _get_kb(self):
        if self._kb is None:
            bridge = self._get_bridge()
            self._kb = bridge.get_kb_reader()
        return self._kb

    def close(self):
        if self._bridge:
            self._bridge.__exit__(None, None, None)
            self._bridge = None
            self._kb = None

    # ── Profile Access ───────────────────────────────────────────────

    def get_ai_profile(self, ai_name):
        """Load an AI profile from the registry."""
        rule_id = _AI_ALIASES.get(ai_name.lower())
        if not rule_id:
            # Try direct rule_id
            rule_id = f"AI_PROFILE_{ai_name.upper()}_V1"
        try:
            rule = self._get_kb().get_rule(rule_id)
            return rule.get("rules", {}) if rule else None
        except Exception:
            return None

    def get_task_archetype(self, task_type):
        """Load a task archetype from the registry."""
        rule_id = _TASK_ALIASES.get(task_type.lower())
        if not rule_id:
            rule_id = f"TASK_{task_type.upper()}_V1"
        try:
            rule = self._get_kb().get_rule(rule_id)
            return rule.get("rules", {}) if rule else None
        except Exception:
            return None

    def get_all_profiles(self):
        """Return all registered AI profiles."""
        profiles = {}
        for alias, rule_id in _AI_ALIASES.items():
            if rule_id not in [v for v in profiles.values()]:
                try:
                    rule = self._get_kb().get_rule(rule_id)
                    if rule:
                        profiles[rule_id] = rule.get("rules", {})
                except Exception:
                    pass
        return profiles

    # ── Freshness Check ──────────────────────────────────────────────

    def check_freshness(self, ai_name=None):
        """Check if AI profile(s) are stale."""
        results = []
        profiles = {}
        if ai_name:
            p = self.get_ai_profile(ai_name)
            if p:
                profiles[ai_name] = p
        else:
            profiles = self.get_all_profiles()

        today = datetime.date.today()
        for name, profile in profiles.items():
            info = profile.get("PROFILE", {})
            last_verified = info.get("last_verified", "2020-01-01")
            freshness_days = info.get("verification_freshness_days", 30)
            try:
                last_date = datetime.date.fromisoformat(last_verified)
                days_ago = (today - last_date).days
                is_stale = days_ago > freshness_days
            except (ValueError, TypeError):
                days_ago = 999
                is_stale = True

            results.append({
                "name": info.get("name", name),
                "model": info.get("current_model", "?"),
                "last_verified": last_verified,
                "days_ago": days_ago,
                "freshness_days": freshness_days,
                "is_stale": is_stale,
            })
        return results

    # ── SOMA Data Gathering ──────────────────────────────────────────

    def _gather_soma_context(self, archetype):
        """Gather SOMA data based on task archetype requirements."""
        bridge = self._get_bridge()
        context = {}

        required = archetype.get("SOMA_CONTEXT", {}).get("required", [])
        optional = archetype.get("SOMA_CONTEXT", {}).get("optional", [])
        all_keys = required + optional

        if "regime_history_latest" in all_keys:
            regime = bridge.get_latest_regime()
            if regime:
                context["regime"] = {
                    "date": regime.get("date"),
                    "regime": regime.get("regime"),
                    "gli_value": regime.get("gli_value"),
                    "momentum": regime.get("momentum"),
                    "diffusion_index": regime.get("diffusion_index"),
                }

        if "regime_history_full" in all_keys:
            history = bridge.get_regime_history(limit=10)
            if history:
                context["regime_history"] = [
                    {"date": h.get("date"), "regime": h.get("regime"),
                     "gli_value": h.get("gli_value")}
                    for h in history
                ]

        if "gli_components" in all_keys:
            regime = bridge.get_latest_regime()
            if regime and regime.get("gli_components_json"):
                try:
                    context["gli_components"] = json.loads(regime["gli_components_json"])
                except Exception:
                    pass

        if "valuation_summary" in all_keys:
            vals = bridge.get_latest_valuations()
            if vals:
                context["valuations"] = [
                    {"ticker": v.get("ticker"), "fair_value": v.get("fair_value"),
                     "current_price": v.get("current_price"),
                     "implied_upside": v.get("implied_upside")}
                    for v in vals[:20]
                ]

        if "portfolio_state" in all_keys:
            port = bridge.get_latest_portfolio_state()
            if port:
                context["portfolio"] = {
                    "cash_pct": port.get("cash_pct"),
                    "total_value": port.get("total_value"),
                    "dd_from_hwm": port.get("dd_from_hwm"),
                }

        if "outlook_latest" in all_keys:
            outlook = bridge.get_latest_outlook()
            if outlook:
                context["outlook"] = {
                    "date": outlook.get("date"),
                    "version": outlook.get("version"),
                }
                if outlook.get("key_conclusions_json"):
                    try:
                        context["outlook"]["conclusions"] = json.loads(
                            outlook["key_conclusions_json"])[:5]
                    except Exception:
                        pass

        if "trade_log_recent" in all_keys:
            trades = bridge.get_trade_log(limit=10)
            if trades:
                context["recent_trades"] = [
                    {"date": t.get("date"), "action": t.get("action"),
                     "ticker": t.get("ticker")}
                    for t in trades[:5]
                ]

        if "kb_violations" in all_keys:
            try:
                rows = bridge.conn.execute(
                    """SELECT severity, rule_id, source_module, description
                       FROM kb_violations ORDER BY id DESC LIMIT 10"""
                ).fetchall()
                if rows:
                    context["violations"] = [
                        {"severity": r["severity"], "rule": r["rule_id"],
                         "module": r["source_module"], "desc": r["description"]}
                        for r in rows
                    ]
            except Exception:
                pass

        if "schema_version" in all_keys:
            context["schema_version"] = bridge.get_schema_version()

        if "db_size" in all_keys:
            if os.path.exists(self.db_path):
                context["db_size_bytes"] = os.path.getsize(self.db_path)

        return context

    # ── Prompt Building ──────────────────────────────────────────────

    def build_prompt(self, ai_name, task_type, question=None, include_cross_ai=True):
        """Build a complete, tailored prompt for the target AI.

        Returns: (prompt_text, metadata_dict)
        """
        profile = self.get_ai_profile(ai_name)
        archetype = self.get_task_archetype(task_type)

        if not profile:
            return None, {"error": f"AI profile '{ai_name}' not found in registry"}
        if not archetype:
            return None, {"error": f"Task archetype '{task_type}' not found in registry"}

        pro = profile.get("PROFILE", {})
        spec = profile.get("SPECIALTY", {})
        prefs = profile.get("PROMPT_PREFERENCES", {})
        caps = profile.get("CAPABILITIES", {})
        role = profile.get("DABEIBA_ROLE", {})
        limits = profile.get("KNOWN_LIMITATIONS", [])
        task = archetype.get("TASK", {})
        output_fmt = archetype.get("OUTPUT_FORMAT", {})

        # Context window budget: use 40% for prompt, leave 60% for response
        context_budget = int(pro.get("context_window", 128000) * 0.40)

        # Gather SOMA data
        soma_context = self._gather_soma_context(archetype)

        # Build sections
        sections = []

        # 1. Role Assignment
        ai_display = pro.get("name", ai_name)
        lens_desc = spec.get("lens", "general analysis")
        task_name = task.get("name", task_type)
        sections.append(
            f"# DABEIBA Cross-AI Review Request\n\n"
            f"**To:** {ai_display} ({pro.get('current_model', '?')})\n"
            f"**Task:** {task_name}\n"
            f"**Date:** {_today()}\n"
            f"**Your assigned lens:** {lens_desc}\n\n"
            f"You are reviewing part of DABEIBA, a personal advisory intelligence platform "
            f"built by an independent investor in Quebec, Canada. DABEIBA has three modules:\n"
            f"- **ORACLE** — Equity analysis + macro signals (76-ticker CFA-compliant valuation engine)\n"
            f"- **MANTIS** — Algorithmic trading (concentrated crypto/equity portfolio on Solana)\n"
            f"- **CIPHER** — Research workflow + client communications\n"
            f"- **SOMA** — Central intelligence layer connecting all modules (SQLite, KB rules, validation)\n\n"
            f"Your role is to apply your **{spec.get('primary', 'general')}** expertise. "
            f"Be direct — use PASS/CONCERN/FAIL ratings where appropriate. "
            f"Disagreement with prior AI reviews is encouraged if you have evidence."
        )

        # 2. SOMA Data Snapshot
        if soma_context:
            soma_text = "## Current SOMA Data\n\n"
            soma_text += "```json\n" + json.dumps(soma_context, indent=2, default=str) + "\n```"
            soma_text = _compress_text(soma_text, context_budget // 3)
            sections.append(soma_text)

        # 3. Cross-AI History
        if include_cross_ai and role.get("past_contributions"):
            # Gather contributions from OTHER AIs (not the target)
            cross_ai_text = "## What Other AIs Found (Prior Reviews)\n\n"
            all_profiles = self.get_all_profiles()
            for rid, p in all_profiles.items():
                other_name = p.get("PROFILE", {}).get("name", "?")
                if other_name.lower() == ai_display.lower():
                    continue
                contribs = p.get("DABEIBA_ROLE", {}).get("past_contributions", [])
                if contribs:
                    cross_ai_text += f"**{other_name}:**\n"
                    for c in contribs[:5]:
                        cross_ai_text += f"- {c}\n"
                    cross_ai_text += "\n"
            cross_ai_text += (
                "You may agree or disagree with any of the above. "
                "If you disagree, explain why with evidence.\n"
            )
            cross_ai_text = _compress_text(cross_ai_text, context_budget // 4)
            sections.append(cross_ai_text)

        # 4. Specific Question
        if question:
            sections.append(
                f"## Your Specific Assignment\n\n{question}"
            )
        else:
            sections.append(
                f"## Your Assignment\n\n"
                f"Perform a **{task_name.lower()}** on the data and context above. "
                f"Apply your {spec.get('primary', 'general')} lens."
            )

        # 5. Output Format
        out_structure = output_fmt.get("structure", "structured findings")
        out_sections = []
        out_sections.append(f"## Requested Output Format\n")
        out_sections.append(f"Structure your response as: **{out_structure}**\n")
        if output_fmt.get("require_evidence"):
            out_sections.append("- Every finding must include supporting evidence or data")
        if output_fmt.get("require_p_values"):
            out_sections.append("- Include p-values and confidence intervals where applicable")
        if output_fmt.get("require_citations"):
            out_sections.append("- Cite specific regulations, standards, or precedents")
        if output_fmt.get("require_alternatives"):
            out_sections.append("- For each concern, suggest at least one alternative approach")
        if output_fmt.get("require_sensitivity_analysis"):
            out_sections.append("- Include sensitivity analysis for key assumptions")
        if output_fmt.get("require_trade_offs"):
            out_sections.append("- Explicitly name trade-offs for each recommendation")

        out_sections.append(
            f"\nEnd with a **Summary Score** (1-10) and your top 3 priority recommendations."
        )
        sections.append("\n".join(out_sections))

        # 6. Mode recommendation
        rec_mode = prefs.get("recommended_mode")
        if rec_mode and rec_mode != "standard":
            modes = profile.get("MODES", {})
            mode_desc = modes.get(rec_mode, "")
            sections.append(
                f"---\n*Recommended mode: **{rec_mode}** "
                f"{'— ' + mode_desc if mode_desc else ''}*"
            )

        # Assemble
        prompt = "\n\n".join(sections)
        prompt_tokens = _estimate_tokens(prompt)

        # Freshness warning
        freshness = self.check_freshness(ai_name)
        stale_warning = None
        if freshness and freshness[0].get("is_stale"):
            stale_warning = (
                f"WARNING: {ai_display} profile last verified {freshness[0]['days_ago']} days ago "
                f"(threshold: {freshness[0]['freshness_days']} days). "
                f"Run: python3 ai_prompt_builder.py --check {ai_name}"
            )

        metadata = {
            "target_ai": ai_display,
            "task": task_name,
            "model": pro.get("current_model"),
            "context_window": pro.get("context_window"),
            "prompt_tokens": prompt_tokens,
            "context_usage_pct": round(prompt_tokens / pro.get("context_window", 128000) * 100, 1),
            "recommended_mode": rec_mode,
            "stale_warning": stale_warning,
            "soma_data_keys": list(soma_context.keys()),
        }

        return prompt, metadata

    # ── AI Recommendation ────────────────────────────────────────────

    def recommend_ai(self, task_description):
        """Given a natural language task, recommend the best AI."""
        task_lower = task_description.lower()
        scores = {}

        # Keyword → task type mapping
        keyword_map = {
            "quant": "quant", "backtest": "quant", "sharpe": "quant",
            "walk-forward": "quant", "statistical": "quant", "p-value": "quant",
            "architecture": "arch", "infrastructure": "arch", "schema": "arch",
            "deployment": "arch", "security": "arch", "database": "arch",
            "compliance": "compliance", "regulatory": "compliance", "tax": "compliance",
            "legal": "compliance", "cfa": "compliance", "gips": "compliance",
            "macro": "macro", "regime": "macro", "gli": "macro", "fed": "macro",
            "strategy": "strategy", "holistic": "strategy", "roadmap": "strategy",
            "valuation": "valuation", "dcf": "valuation", "fair value": "valuation",
            "ux": "strategy", "workflow": "strategy", "product": "strategy",
        }

        # Find the best task match
        best_task = None
        for keyword, task_type in keyword_map.items():
            if keyword in task_lower:
                best_task = task_type
                break

        if not best_task:
            best_task = "strategy"  # default to holistic

        archetype = self.get_task_archetype(best_task)
        if archetype:
            preferred = archetype.get("TASK", {}).get("preferred_ais", [])
            return {
                "task_type": best_task,
                "preferred_ais": preferred,
                "reason": f"Based on keywords in your request, this is a {best_task} task. "
                          f"Preferred AIs: {', '.join(preferred)}.",
            }
        return {"task_type": best_task, "preferred_ais": ["claude"], "reason": "Default recommendation."}

    # ── Capability Check Generator ───────────────────────────────────

    def build_capability_check(self, ai_name):
        """Generate a prompt to ask an AI about its own capabilities.

        Paste this into the AI. The AI's response can be used to update the registry.
        """
        profile = self.get_ai_profile(ai_name)
        ai_display = ai_name
        if profile:
            ai_display = profile.get("PROFILE", {}).get("name", ai_name)

        prompt = f"""# Capability Self-Report Request

I'm updating my AI capability registry. Please answer each question accurately and concisely.

## Identity
1. What is your exact model name and version? (e.g., "Grok 3", "GPT-5.4 Thinking", "Gemini 2.5 Pro")
2. Who is your provider/company?
3. What is your training data cutoff date?

## Context & Output
4. What is your maximum context window in tokens?
5. What is your maximum output length in tokens?

## Tools & Capabilities
Answer YES or NO for each:
6. Web search (can you search the internet in real-time)?
7. Code execution (can you run code in a sandbox)?
8. File upload (can users upload files for you to analyze)?
9. File creation (can you create downloadable files)?
10. Image generation (can you create images)?
11. Image understanding (can you analyze uploaded images)?
12. Audio understanding (can you process audio files)?
13. Video understanding (can you process video files)?
14. Deep research mode (multi-step research with citations)?
15. Thinking/reasoning mode (extended chain-of-thought)?
16. Canvas/artifact mode (interactive document editing)?
17. Real-time data access (live market data, social feeds, etc.)?

## Modes
18. List all available modes/settings you support (e.g., "Think", "Deep Search", "Canvas")
    with a one-line description of each.

## Limitations
19. List your top 5 most important limitations that a user should know about.

## Output Format
Please structure your response as a YAML block I can paste directly into my registry:

```yaml
name: {ai_display}
provider: [your answer]
current_model: [your answer]
context_window: [number]
max_output_tokens: [number]
training_cutoff: "[YYYY-MM]"
capabilities:
  web_search: [true/false]
  code_execution: [true/false]
  file_upload: [true/false]
  file_creation: [true/false]
  image_generation: [true/false]
  image_understanding: [true/false]
  audio_understanding: [true/false]
  video_understanding: [true/false]
  deep_research: [true/false]
  thinking_mode: [true/false]
  canvas_mode: [true/false]
  real_time_data: [true/false]
modes:
  [mode_name]: "[description]"
limitations:
  - "[limitation 1]"
  - "[limitation 2]"
```

Be precise. Do not speculate — if you're unsure about a capability, say so."""

        return prompt

    # ── New AI Onboarding ────────────────────────────────────────────

    def build_onboarding_prompt(self, ai_name):
        """Generate a prompt to onboard a completely new AI into DABEIBA.

        This is the capability check + DABEIBA context + specialty assignment.
        """
        cap_check = self.build_capability_check(ai_name)

        onboarding = f"""{cap_check}

---

# Additional DABEIBA Context

After answering the capability questions above, I'd also like to understand
how you'd fit into our cross-AI workflow.

DABEIBA is a personal advisory intelligence platform with these modules:
- Research (ORACLE): 76-ticker equity valuation engine (CFA-compliant, macro-aware)
- Decisions (MANTIS): Algorithmic crypto/equity trading on Solana (concentrated, volatility-weighted)
- Advisory (CIPHER): Research workflow + client communications
- Synthesis (SOMA): Central intelligence layer (SQLite, KB rules, validation, cross-AI coordination)

Our current AI team:
- Claude (Anthropic): Implementation lead, builds all code, synthesis coordinator
- Grok (xAI): Quantitative lens — statistical validation, Sharpe testing, walk-forward
- Gemini (Google): Architecture/compliance — infrastructure, tax, regulatory
- ChatGPT (OpenAI): Product/UX — workflow design, risk frameworks, gap analysis

## Questions for you:
20. Based on your capabilities, what unique value could you add to this workflow?
21. What type of review would you be best suited for?
22. What are your blind spots that other AIs should compensate for?
23. Suggest a one-word specialty lens for yourself (e.g., "quantitative", "architecture")
"""
        return onboarding


# ── CLI Interface ────────────────────────────────────────────────────────

def _print_header(text):
    print(f"\n{BOLD}{CYAN}{'=' * W}{RESET}")
    print(f"{BOLD}  {text}{RESET}")
    print(f"{BOLD}{CYAN}{'=' * W}{RESET}")


def _save_prompt(prompt, ai_name, task_type):
    """Save prompt to shared/soma/prompts/ directory."""
    prompts_dir = os.path.join(_THIS_DIR, "prompts")
    os.makedirs(prompts_dir, exist_ok=True)
    filename = f"{ai_name.lower()}_{task_type.lower().replace(' ', '_')}_{_today()}.md"
    filepath = os.path.join(prompts_dir, filename)
    with open(filepath, "w") as f:
        f.write(prompt)
    return filepath


def cmd_list_ais(builder):
    """List all registered AIs with freshness status."""
    _print_header("SOMA AI Registry")
    freshness = builder.check_freshness()
    if not freshness:
        print(f"\n  {YELLOW}No AI profiles found. Is ai_registry.md indexed?{RESET}\n")
        return

    print(f"\n  {'Name':<12} {'Model':<22} {'Verified':<14} {'Status':<12}")
    print(f"  {'─' * 56}")
    for f in freshness:
        if f["is_stale"]:
            status = f"{RED}STALE ({f['days_ago']}d){RESET}"
        else:
            status = f"{GREEN}FRESH ({f['days_ago']}d){RESET}"
        print(f"  {f['name']:<12} {f['model']:<22} {f['last_verified']:<14} {status}")
    print()


def cmd_ai_detail(builder, ai_name):
    """Show full profile for one AI."""
    profile = builder.get_ai_profile(ai_name)
    if not profile:
        print(f"\n  {RED}AI '{ai_name}' not found in registry.{RESET}\n")
        return

    pro = profile.get("PROFILE", {})
    caps = profile.get("CAPABILITIES", {})
    spec = profile.get("SPECIALTY", {})
    role = profile.get("DABEIBA_ROLE", {})
    limits = profile.get("KNOWN_LIMITATIONS", [])
    modes = profile.get("MODES", {})

    _print_header(f"{pro.get('name', ai_name)} — Profile")

    print(f"\n  {BOLD}Identity{RESET}")
    print(f"  Provider:        {pro.get('provider', '?')}")
    print(f"  Model:           {pro.get('current_model', '?')}")
    print(f"  Context Window:  {pro.get('context_window', '?'):,} tokens")
    print(f"  Max Output:      {pro.get('max_output_tokens', '?'):,} tokens")
    print(f"  Training Cutoff: {pro.get('training_cutoff', '?')}")
    print(f"  Access:          {pro.get('access_method', '?')}")
    print(f"  Cost:            {pro.get('cost_tier', '?')}")
    print(f"  Last Verified:   {pro.get('last_verified', '?')}")

    print(f"\n  {BOLD}Capabilities{RESET}")
    has = [k for k, v in caps.items() if v is True]
    missing = [k for k, v in caps.items() if v is False]
    print(f"  {GREEN}Has:{RESET}     {', '.join(has[:8])}")
    if len(has) > 8:
        print(f"           {', '.join(has[8:])}")
    print(f"  {RED}Missing:{RESET} {', '.join(missing[:6])}")
    if len(missing) > 6:
        print(f"           {', '.join(missing[6:])}")

    if modes:
        print(f"\n  {BOLD}Modes{RESET}")
        for mode, desc in modes.items():
            print(f"  {CYAN}{mode:<14}{RESET} {desc[:55]}")

    print(f"\n  {BOLD}DABEIBA Role{RESET}")
    print(f"  Lens:    {spec.get('primary', '?')}")
    print(f"  Reviews: {', '.join(role.get('review_types', []))}")
    print(f"  Modules: {', '.join(role.get('modules', []))}")

    contribs = role.get("past_contributions", [])
    if contribs:
        print(f"\n  {BOLD}Past Contributions{RESET}")
        for c in contribs[:5]:
            print(f"  - {c[:70]}")

    if limits:
        print(f"\n  {BOLD}Known Limitations{RESET}")
        for lim in limits[:5]:
            print(f"  {YELLOW}- {lim[:70]}{RESET}")
    print()


def cmd_build_prompt(builder, ai_name, task_type, question=None):
    """Build and save a tailored prompt."""
    prompt, meta = builder.build_prompt(ai_name, task_type, question)
    if not prompt:
        print(f"\n  {RED}{meta.get('error', 'Unknown error')}{RESET}\n")
        return

    # Save to file
    filepath = _save_prompt(prompt, ai_name, task_type)

    # Print metadata
    _print_header(f"Prompt for {meta['target_ai']} — {meta['task']}")
    print(f"\n  Model:          {meta['model']}")
    print(f"  Context Window:  {meta['context_window']:,} tokens")
    print(f"  Prompt Size:     ~{meta['prompt_tokens']:,} tokens ({meta['context_usage_pct']}% of window)")
    print(f"  SOMA Data:       {', '.join(meta['soma_data_keys']) if meta['soma_data_keys'] else 'none available'}")
    if meta.get("recommended_mode"):
        print(f"  Recommended Mode: {CYAN}{meta['recommended_mode']}{RESET}")
    if meta.get("stale_warning"):
        print(f"\n  {YELLOW}{meta['stale_warning']}{RESET}")

    print(f"\n  {GREEN}Saved to:{RESET} {filepath}")
    print(f"\n{BOLD}{'─' * W}{RESET}")

    # Print the actual prompt
    print(f"\n{prompt}\n")
    print(f"{BOLD}{'─' * W}{RESET}")
    print(f"  {DIM}Copy the above prompt and paste into {meta['target_ai']}.{RESET}\n")


def cmd_check_capabilities(builder, ai_name):
    """Generate a capability-check prompt for an AI."""
    prompt = builder.build_capability_check(ai_name)
    filepath = _save_prompt(prompt, ai_name, "capability_check")
    _print_header(f"Capability Check — {ai_name}")
    print(f"\n  {GREEN}Saved to:{RESET} {filepath}")
    print(f"\n{prompt}\n")
    print(f"  {DIM}Paste the above into {ai_name}. Bring the YAML response back to update the registry.{RESET}\n")


def cmd_onboard(builder, ai_name):
    """Generate an onboarding prompt for a new AI."""
    prompt = builder.build_onboarding_prompt(ai_name)
    filepath = _save_prompt(prompt, ai_name, "onboarding")
    _print_header(f"Onboarding — {ai_name}")
    print(f"\n  {GREEN}Saved to:{RESET} {filepath}")
    print(f"\n{prompt}\n")
    print(f"  {DIM}Paste the above into {ai_name}. Use the response to create an AI_PROFILE block.{RESET}\n")


def cmd_recommend(builder, description):
    """Recommend the best AI for a task."""
    result = builder.recommend_ai(description)
    _print_header("AI Recommendation")
    print(f"\n  Task type: {CYAN}{result['task_type']}{RESET}")
    print(f"  Best AIs:  {GREEN}{', '.join(result['preferred_ais'])}{RESET}")
    print(f"  Reason:    {result['reason']}")
    print()


def print_usage():
    _print_header("SOMA AI Prompt Builder")
    cmds = [
        ("--list-ais", "Show all registered AIs with freshness"),
        ("--ai grok", "Full profile for one AI"),
        ("grok 'quant review' 'question'", "Build a tailored prompt"),
        ("--check grok", "Generate capability-check prompt"),
        ("--onboard newai", "Generate onboarding prompt for new AI"),
        ("--recommend 'review MANTIS'", "Suggest best AI for a task"),
    ]
    print()
    for cmd, desc in cmds:
        print(f"  {WHITE}{cmd:<36}{RESET} {DIM}{desc}{RESET}")
    print()


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print_usage()
        return

    builder = AIPromptBuilder()
    try:
        arg1 = sys.argv[1]

        if arg1 == "--list-ais":
            cmd_list_ais(builder)
        elif arg1 == "--ai" and len(sys.argv) >= 3:
            cmd_ai_detail(builder, sys.argv[2])
        elif arg1 == "--check" and len(sys.argv) >= 3:
            cmd_check_capabilities(builder, sys.argv[2])
        elif arg1 == "--onboard" and len(sys.argv) >= 3:
            cmd_onboard(builder, sys.argv[2])
        elif arg1 == "--recommend" and len(sys.argv) >= 3:
            cmd_recommend(builder, " ".join(sys.argv[2:]))
        elif arg1.startswith("--"):
            print_usage()
        else:
            # Build prompt: ai_name task_type [question]
            ai_name = arg1
            task_type = sys.argv[2] if len(sys.argv) >= 3 else "strategy"
            question = " ".join(sys.argv[3:]) if len(sys.argv) >= 4 else None
            cmd_build_prompt(builder, ai_name, task_type, question)
    finally:
        builder.close()


if __name__ == "__main__":
    main()
