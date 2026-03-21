# Claude Code Prompt E — Wire CIPHER to Read KB Rules at Runtime

## Context
SOMA is in ~/Desktop/DABEIBA/shared/soma/. The KB runtime reader is built (Prompts A+B). CIPHER is in ~/Desktop/DABEIBA/cipher/.

CIPHER's communication frameworks (ADViCE, PRACTICE, money scripts) currently have their logic embedded directly in Python classes. This prompt wires CIPHER to **read framework definitions from SOMA's KB** at runtime, so updating a framework means editing one KB file — not touching code.

## Rules CIPHER Should Read

These 3 rules have `source_module` containing "CIPHER":

| Rule ID | Source File | What It Contains |
|---------|------------|-----------------|
| `ADVICE_FRAMEWORK_V1` | communication_compliance.md | The 6 elements of ADViCE: Aware, Differentiated, Validated, Insightful, Conclusion-oriented, Easy to consume — each with requirements + validation criteria |
| `PRACTICE_FRAMEWORK_V1` | communication_compliance.md | PRACTICE meeting prep checklist: Prepare, Research, Anticipate, Customize, Time, Implement, Confirm, Evaluate — each with action items |
| `MONEY_SCRIPT_TYPES_V1` | communication_compliance.md | Klontz money scripts: vigilance, avoidance, worship, status — each with behavioral tendencies, indicators, motivators, messaging angles |

## Files to Modify

### 1. Create `cipher/cipher/kb_integration.py` (NEW FILE)

```python
"""
CIPHER ↔ SOMA KB Integration Layer

Provides clean access to KB rules for CIPHER's communication frameworks.
All methods include fallbacks — CIPHER works with or without SOMA.
"""

import logging

logger = logging.getLogger(__name__)


# ── Hardcoded fallbacks (current framework definitions) ────────────

# MUST match ADVICE_FRAMEWORK_V1 in communication_compliance.md exactly.
# The KB has 5 elements: A, D, V, C, E (no "I" — "Insightful" is not in the KB).
_FALLBACK_ADVICE = {
    "A_AWARE": {
        "description": "Consensus context — how your view differs from consensus",
        "requirement": "Specify consensus estimate and your estimate with reasoning",
    },
    "D_DIFFERENTIATED": {
        "description": "Your edge — which FaVeS element is primary differentiator",
        "requirement": "Explain WHY consensus is wrong with specific research",
    },
    "V_VALIDATED": {
        "description": "Independent sources confirming thesis",
        "requirement": "Minimum 2 independent sources for high-conviction ideas",
    },
    "C_CONCLUSION": {
        "description": "Lead with recommendation",
        "format": "FIRST sentence: Rating + price target + timeframe. THEN: 2-3 key reasons.",
    },
    "E_EASY": {
        "description": "Accessible language",
        "rules": ["no_jargon", "short_sentences_1_2_lines", "80_pct_on_first_2_pages", "one_chart_replaces_3_paragraphs"],
    },
}

# MUST match PRACTICE_FRAMEWORK_V1 in communication_compliance.md exactly.
# KB uses: P_PREPARE, R_RAPPORT, A_ASK, C_CONFORM, T_TRUSTWORTHY,
#          I_IGNORE_DISTRACTIONS, C_COMMUNICATE, E_ENSURE
_FALLBACK_PRACTICE = {
    "P_PREPARE": {
        "actions": ["research_WIIFT", "self_assess_credibility", "goal_clarity", "homework", "contingency_for_objections"],
    },
    "R_RAPPORT": {
        "actions": ["first_to_say_hello", "sincere_questions", "active_listening_95_pct", "find_common_ground", "non_judgmental"],
    },
    "A_ASK": {
        "identify": ["information_need", "emotional_need", "friendship_need"],
        "approach": "Listen for explicit and implicit needs",
    },
    "C_CONFORM": {
        "actions": ["no_judgment", "use_their_terminology", "match_pace", "match_formality", "respect_channel"],
    },
    "T_TRUSTWORTHY": {
        "actions": ["share_insights_in_advance", "be_honest", "follow_through_100_pct", "discretion", "consistency", "track_record"],
    },
    "I_IGNORE_DISTRACTIONS": {
        "actions": ["be_present", "conducive_environment", "adequate_time", "single_topic_focus", "engaged_body_language"],
    },
    "C_COMMUNICATE": {
        "tone": "comforting",
        "eye_contact_pct": 0.70,
        "persuasion_strategies": ["reciprocation", "social_proof", "authority", "scarcity", "commitment_consistency", "liking"],
    },
    "E_ENSURE": {
        "actions": ["24_48hr_response", "proactive_follow_up", "monthly_check_in", "adapt_on_feedback", "measure_action_rate"],
    },
}

# MUST match MONEY_SCRIPT_TYPES_V1 in communication_compliance.md exactly.
# KB uses UPPERCASE keys: WORSHIP, STATUS, AVOIDANCE, VIGILANCE
# KB fields: belief, behaviors, blind_spots, communication
_FALLBACK_MONEY_SCRIPTS = {
    "WORSHIP": {
        "belief": "Happiness equals wealth level",
        "behaviors": ["accumulation_focused", "status_conscious", "competitive_returns"],
        "blind_spots": ["underestimates_downside", "avoids_discussing_losses"],
        "communication": ["lead_with_growth", "emphasize_wealth_accumulation", "use_metrics"],
    },
    "STATUS": {
        "belief": "Wealth equals power and intelligence",
        "behaviors": ["wants_perceived_as_smart", "learns_details", "wants_early_access"],
        "blind_spots": ["overconfidence", "chases_performance", "conflicts_with_advisor"],
        "communication": ["position_as_exclusive", "emphasize_analytical_depth", "ask_their_opinion"],
    },
    "AVOIDANCE": {
        "belief": "Wealth brings problems",
        "behaviors": ["delegates_fully", "minimal_meetings", "wants_safety"],
        "blind_spots": ["ignores_tax_optimization", "underestimates_inflation_risk"],
        "communication": ["simplify_max_3_pages", "emphasize_safety", "quarterly_contact", "focus_downside_protection"],
    },
    "VIGILANCE": {
        "belief": "Be careful and discreet",
        "behaviors": ["questions_everything", "wants_documentation", "independent_verification"],
        "blind_spots": ["analysis_paralysis", "over_focus_on_process", "misses_opportunities"],
        "communication": ["comprehensive_documentation", "show_all_assumptions", "enable_control", "be_patient"],
    },
}


# ── Public API ─────────────────────────────────────────────────────

def _load_rule(rule_id, fallback, context=None):
    """Internal: read a KB rule with graceful fallback."""
    try:
        from soma.soma_bridge import SomaBridge
        with SomaBridge() as db:
            rule = db.get_rule(rule_id)
            db.log_rule_usage(rule_id, "CIPHER", context=context)
            return rule.get("rules", fallback)
    except Exception as e:
        logger.debug(f"KB fallback for {rule_id}: {e}")
        return fallback


def get_advice_framework():
    """Read ADViCE framework definition from KB.

    Returns dict: element_key → {label, description, requirement}
    """
    return _load_rule("ADVICE_FRAMEWORK_V1", _FALLBACK_ADVICE,
                      context={"source": "advice_framework"})


def get_practice_framework():
    """Read PRACTICE meeting prep checklist from KB.

    Returns dict: element_key → {label, actions: [...]}
    """
    return _load_rule("PRACTICE_FRAMEWORK_V1", _FALLBACK_PRACTICE,
                      context={"source": "practice_framework"})


def get_money_script_types():
    """Read Klontz money script definitions from KB.

    Returns dict: script_name → {description, behavioral_tendencies, indicators, motivators, messaging_angle}
    """
    return _load_rule("MONEY_SCRIPT_TYPES_V1", _FALLBACK_MONEY_SCRIPTS,
                      context={"source": "wiift_framework"})


def get_money_script(script_name):
    """Read a single money script by name.

    Accepts either 'WORSHIP' or 'worship' — normalizes to UPPERCASE to match KB keys.
    """
    scripts = get_money_script_types()
    return scripts.get(script_name.upper(), {})
```

### 2. Modify `cipher/cipher/frameworks/advice_framework.py`

Find the ADViCEFramework class (around lines 28-60). Add KB integration:

```python
# At the top, add:
from cipher.kb_integration import get_advice_framework

class ADViCEFramework:
    def __init__(self):
        # Load framework definition from KB (falls back to hardcoded)
        self._kb_rules = get_advice_framework()

    def get_element(self, key):
        """Get a single ADViCE element definition."""
        return self._kb_rules.get(key, {})

    def get_all_elements(self):
        """Get all ADViCE elements."""
        return self._kb_rules

    def validate_output(self, content):
        """Check that output meets ADViCE requirements."""
        # Use KB-sourced requirements for validation
        results = {}
        for key, element in self._kb_rules.items():
            req = element.get("requirement", "")
            # Validation logic here — check content meets requirement
            results[key] = {"requirement": req, "met": True}  # placeholder
        return results
```

Leave existing methods intact. Add the KB-sourced `_kb_rules` dict as a new data source that existing methods can reference. Wherever the class currently has hardcoded descriptions or requirements, replace with lookups to `self._kb_rules`.

### 3. Modify `cipher/cipher/frameworks/practice_framework.py`

Find the PRACTICEFramework class (around lines 30-80). Add KB integration:

```python
# At the top, add:
from cipher.kb_integration import get_practice_framework

class PRACTICEFramework:
    def __init__(self):
        # Load PRACTICE checklist from KB (falls back to hardcoded)
        self._kb_rules = get_practice_framework()

    def get_checklist(self):
        """Get full PRACTICE meeting prep checklist from KB."""
        return self._kb_rules

    def get_step(self, step_key):
        """Get a single PRACTICE step."""
        return self._kb_rules.get(step_key, {})
```

Wire existing checklist generation to read from `self._kb_rules` instead of hardcoded strings.

### 4. Modify `cipher/cipher/frameworks/wiift_framework.py`

Find the MONEY_SCRIPTS dict and MoneyScript enum (around lines 16-68). Add KB integration:

```python
# At the top, add:
from cipher.kb_integration import get_money_script_types, get_money_script

# Keep the MoneyScript enum as-is (WORSHIP, STATUS, AVOIDANCE, VIGILANCE)
# But replace the hardcoded MONEY_SCRIPTS dict:

class WIIFTFramework:
    def __init__(self):
        # Load money script definitions from KB (falls back to hardcoded)
        self._money_scripts = get_money_script_types()

    def get_script_profile(self, script_name):
        """Get full money script profile from KB. Keys are UPPERCASE in KB."""
        return self._money_scripts.get(script_name.upper(), {})

    def get_communication_strategies(self, script_name):
        """Get the recommended communication strategies for a money script.

        KB field is 'communication' (list), not 'messaging_angle' (string).
        """
        profile = self.get_script_profile(script_name)
        return profile.get("communication", [])

    def get_blind_spots(self, script_name):
        """Get known blind spots for a money script."""
        profile = self.get_script_profile(script_name)
        return profile.get("blind_spots", [])
```

Replace existing hardcoded lookups in `_generate_wiift_angle()` (around lines 223-245) to use `self.get_script_profile()`. Note: the KB uses `communication` (list of strategies) instead of `messaging_angle` (string), and `behaviors` instead of `behavioral_tendencies`. Adapt the framework code to read KB field names:
```python
profile = self.get_script_profile(script_name)
comm_strategies = profile.get("communication", [])  # KB field name
behaviors = profile.get("behaviors", [])  # KB field name
```

### 5. Modify `cipher/cipher/ui/pages/talking_points.py`

Find where frameworks are instantiated (around lines 55-57, 159-170). Add KB context:

```python
# Where frameworks are created, pass KB context:
from cipher.kb_integration import get_advice_framework, get_money_script_types

# In the framework selection/rendering section:
advice_rules = get_advice_framework()
# Use advice_rules to populate UI labels and descriptions dynamically

money_scripts = get_money_script_types()
# Use money_scripts to populate money script selector dynamically
```

This is lower priority — the UI can work with hardcoded labels while the backend reads from KB.

## Testing

After all modifications:

```bash
# 1. Verify CIPHER works in fallback mode (no SOMA)
cd ~/Desktop/DABEIBA/cipher
python3 -c "
from cipher.kb_integration import get_advice_framework, get_money_script_types
advice = get_advice_framework()
print('ADViCE elements:', list(advice.keys()))
scripts = get_money_script_types()
print('Money scripts:', list(scripts.keys()))
"

# 2. Verify KB reads work with SOMA
cd ~/Desktop/DABEIBA/shared/soma
python3 -c "
from soma.soma_bridge import SomaBridge
with SomaBridge() as db:
    db.initialize_db()
    kr = db.get_kb_reader()
    kr.build_index()
    for rid in ['ADVICE_FRAMEWORK_V1', 'PRACTICE_FRAMEWORK_V1', 'MONEY_SCRIPT_TYPES_V1']:
        rule = db.get_rule(rid)
        print(f'{rid}: {list(rule.get(\"rules\", {}).keys())[:4]}...')
"

# 3. Verify framework classes load KB data with correct field names
cd ~/Desktop/DABEIBA/cipher
python3 -c "
from cipher.kb_integration import get_advice_framework, get_money_script_types
advice = get_advice_framework()
for key, elem in advice.items():
    print(f'  {key}: {elem.get(\"description\", \"?\")[:60]}')
scripts = get_money_script_types()
for key, elem in scripts.items():
    print(f'  {key}: {elem.get(\"belief\", \"?\")} — comm: {elem.get(\"communication\", [])}')
"

# 4. Check audit log shows CIPHER reads
cd ~/Desktop/DABEIBA/shared/soma
python3 -c "
from soma.soma_bridge import SomaBridge
with SomaBridge() as db:
    db.initialize_db()
    kr = db.get_kb_reader()
    kr.build_index()
    # Trigger CIPHER reads
    import sys; sys.path.insert(0, '../../cipher')
    from cipher.kb_integration import get_advice_framework, get_money_script_types
    get_advice_framework()
    get_money_script_types()
    audits = kr.get_rule_audit(module='CIPHER', limit=5)
    print(f'{len(audits)} CIPHER audit entries')
"
```

## Import Path Note

`from soma.soma_bridge import SomaBridge` requires `~/Desktop/DABEIBA/shared` on `sys.path`. CIPHER's `soma_integration.py` already sets this. Follow the same pattern.

## Critical: KB Field Names vs Existing Code Field Names

The KB uses different field names than CIPHER's existing code in some cases:

| Concept | KB field name | Existing code name | Action |
|---------|--------------|-------------------|--------|
| Money script type keys | `WORSHIP` (uppercase) | `MoneyScript.WORSHIP` | Use `.upper()` or `.name` for lookups |
| Money script messaging | `communication` (list) | `messaging_angle` (string) | Adapt existing code to read list |
| Money script traits | `behaviors` (list) | `behavioral_tendencies` (list) | Same concept, different name |
| ADViCE elements | 5 elements (A,D,V,C,E) | May have 6 in code | KB is authoritative — no "I_INSIGHTFUL" |
| ADViCE field | `format` (in C_CONCLUSION) | `requirement` | Some elements use `format` not `requirement` |
| PRACTICE steps | R_RAPPORT, A_ASK, C_CONFORM, T_TRUSTWORTHY, I_IGNORE_DISTRACTIONS, C_COMMUNICATE, E_ENSURE | May differ in code | KB is authoritative |

When existing CIPHER code references fields not in KB, keep the old code path as fallback.

## Important

- Do NOT change CIPHER's existing behavior — same output, KB-sourced inputs
- The MoneyScript enum stays — it's used for type safety in routing logic
- Every KB read has try/except fallback to the exact current behavior
- Fallback dicts MUST mirror KB YAML exactly (check communication_compliance.md)
- `kb_integration.py` is the single import point — no scattered SOMA imports
- Log every rule usage for the audit trail
- Framework classes should initialize KB data in `__init__` (one read per instantiation, not per method call)
- If SOMA import fails, CIPHER runs identically to before
- Commit when done: `git add -A && git commit -m "Wire CIPHER to read KB rules at runtime: 3 rules with fallbacks + audit logging"`
