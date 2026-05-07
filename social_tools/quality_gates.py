"""
quality_gates.py
Quality gate functions for all three social pipelines.

Each function returns a dict of the form:
    {
        "<gate_name>": {
            "result":  "pass" | "fail" | "needs_human",
            "reason":  str,           # explanation or empty string
            "prompt":  str | None,    # question to ask operator (needs_human only)
        }
    }

Mechanical gates run automatically (no human required).
Subjective gates return "needs_human" with a prompt for the operator to answer.
"""

from __future__ import annotations
import re
import unicodedata

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_EMOJI_RE = re.compile(
    "["
    "\U0001F600-\U0001F64F"   # emoticons
    "\U0001F300-\U0001F5FF"   # symbols & pictographs
    "\U0001F680-\U0001F6FF"   # transport & map
    "\U0001F1E0-\U0001F1FF"   # flags (iOS)
    "\U00002702-\U000027B0"   # dingbats
    "\U000024C2-\U0001F251"   # enclosed characters
    "\U0001F926-\U0001F937"   # supplemental symbols
    "☀-⭕"           # misc symbols
    "‍"                  # zero-width joiner
    "️"                  # variation selector-16
    "]+",
    flags=re.UNICODE,
)

_HASHTAG_RE = re.compile(r"#\w+")
_ALLCAPS_WORD_RE = re.compile(r"\b[A-Z]{3,}\b")  # words of 3+ uppercase letters


def _gate(result: str, reason: str, prompt: str | None = None) -> dict:
    return {"result": result, "reason": reason, "prompt": prompt}


# ---------------------------------------------------------------------------
# Darkframe gates
# ---------------------------------------------------------------------------

DARKFRAME_GATE_NAMES = [
    "length_ok",
    "no_emojis",
    "no_allcaps",
    "no_hashtags",
    "no_exclamation",
    "screenshot_test",
    "tomorrow_test",
    "attribution_test",
    "cringe_test",
    "longevity_test",
]


def darkframe_gates(post_text: str) -> dict[str, dict]:
    """
    Run all quality gates for the darkframe pipeline.

    Mechanical (auto):
        length_ok        — post is ≤ 250 characters
        no_emojis        — no emoji characters
        no_allcaps       — no ALL-CAPS words (3+ chars)
        no_hashtags      — no #hashtag tokens
        no_exclamation   — no exclamation marks

    Subjective (needs_human — operator must answer):
        screenshot_test  — would you screenshot this and send to a peer?
        tomorrow_test    — would this still be worth saying tomorrow?
        attribution_test — is every factual claim sourced or observable?
        cringe_test      — any line that sounds performative or tribal?
        longevity_test   — proud of this in two years?
    """
    results = {}

    # --- Mechanical gates ---

    char_count = len(post_text)
    if char_count <= 250:
        results["length_ok"] = _gate("pass", f"{char_count} chars")
    else:
        results["length_ok"] = _gate("fail", f"{char_count} chars — exceeds 250 limit")

    emoji_hits = _EMOJI_RE.findall(post_text)
    if not emoji_hits:
        results["no_emojis"] = _gate("pass", "no emoji found")
    else:
        results["no_emojis"] = _gate("fail", f"emoji found: {emoji_hits}")

    caps_hits = _ALLCAPS_WORD_RE.findall(post_text)
    # Whitelist common acceptable acronyms
    _CAPS_WHITELIST = {"AI", "US", "UK", "EU", "FSD", "ETF", "GDP", "CPI",
                       "CEO", "IPO", "IMF", "API", "BTC", "ETH", "SOL",
                       "USD", "CAD", "HNW", "RBC", "SEC", "FED", "FOMC"}
    flagged_caps = [w for w in caps_hits if w not in _CAPS_WHITELIST]
    if not flagged_caps:
        results["no_allcaps"] = _gate("pass", "no shouting detected")
    else:
        results["no_allcaps"] = _gate("fail", f"all-caps words: {flagged_caps}")

    hashtag_hits = _HASHTAG_RE.findall(post_text)
    if not hashtag_hits:
        results["no_hashtags"] = _gate("pass", "no hashtags")
    else:
        results["no_hashtags"] = _gate("fail", f"hashtags found: {hashtag_hits}")

    if "!" not in post_text:
        results["no_exclamation"] = _gate("pass", "no exclamation marks")
    else:
        results["no_exclamation"] = _gate(
            "fail", f"exclamation marks found: {post_text.count('!')} instance(s)"
        )

    # --- Subjective gates (operator must answer) ---

    results["screenshot_test"] = _gate(
        "needs_human",
        "",
        prompt="Screenshot test: would you screenshot this post and send it to a thoughtful peer — "
               "someone who would call out hype or vagueness? (yes / no / edit needed)",
    )

    results["tomorrow_test"] = _gate(
        "needs_human",
        "",
        prompt="Tomorrow test: if the news cycle moved on overnight, "
               "would this post still be worth saying? (yes / no / edit needed)",
    )

    results["attribution_test"] = _gate(
        "needs_human",
        "",
        prompt="Attribution test: is every factual claim in this post either "
               "directly observable (chart, filing, transcript) or linked to a named source? "
               "(yes / no — list the unsupported claims)",
    )

    results["cringe_test"] = _gate(
        "needs_human",
        "",
        prompt="Cringe test: read each line out loud. Does any line sound performative, "
               "tribal, breathless, or like it's fishing for engagement? (none / yes — quote the line)",
    )

    results["longevity_test"] = _gate(
        "needs_human",
        "",
        prompt="Longevity test: in two years, when the prediction resolves or the "
               "narrative shifts, would you still be proud of this post? (yes / no / unsure)",
    )

    return results


# ---------------------------------------------------------------------------
# Drycapital gates
# ---------------------------------------------------------------------------

DRYCAPITAL_GATE_NAMES = [
    "screenshot_test",
    "tomorrow_test",
    "attribution_test",
    "final_line_test",
    "cringe_test",
]


def drycapital_gates(post_text: str) -> dict[str, dict]:
    """
    Run all quality gates for the drycapital pipeline.

    All five gates are subjective (needs_human).
    The drycapital voice spec emphasizes restraint and precision —
    the gates enforce that before any draft is approved.

        screenshot_test   — forward-worthy to a sophisticated reader?
        tomorrow_test     — still worth saying after the news cycle moves?
        attribution_test  — every claim sourced or directly observable?
        final_line_test   — does the closing line land without needing applause?
        cringe_test       — any word or phrase that would embarrass you?
    """
    results = {}

    results["screenshot_test"] = _gate(
        "needs_human",
        "",
        prompt="Screenshot test: would you forward this to a sophisticated, "
               "skeptical reader who would immediately spot fluff? (yes / no / edit needed)",
    )

    results["tomorrow_test"] = _gate(
        "needs_human",
        "",
        prompt="Tomorrow test: if this angle is everywhere by morning, "
               "does this post still add something? (yes / no / edit needed)",
    )

    results["attribution_test"] = _gate(
        "needs_human",
        "",
        prompt="Attribution test: can you source every factual claim — "
               "filing, transcript, chart, named report? "
               "List any claim you cannot source. (all sourced / unsourced claims: ...)",
    )

    results["final_line_test"] = _gate(
        "needs_human",
        "",
        prompt="Final line test: read only the last sentence. "
               "Does it land cleanly on its own — no rhetorical questions, "
               "no call-to-action, no implicit applause request? (yes / no / edit needed)",
    )

    results["cringe_test"] = _gate(
        "needs_human",
        "",
        prompt="Cringe test: any word, phrase, or framing you would be embarrassed "
               "to defend in a one-on-one conversation with a senior investor? "
               "(none / yes — quote the phrase)",
    )

    return results


# ---------------------------------------------------------------------------
# LinkedIn gates (placeholder — filled in Phase 4)
# ---------------------------------------------------------------------------

def linkedin_gates(post_text: str) -> dict[str, dict]:
    """
    Quality gates for the LinkedIn pipeline.
    Placeholder — full implementation in Phase 4.
    """
    return {}


# ---------------------------------------------------------------------------
# Utility: summarize gate results for display
# ---------------------------------------------------------------------------

def format_gate_table(gate_results: dict[str, dict]) -> str:
    """
    Return a compact text table of gate results.
    Useful for displaying in draft_session.py output.
    """
    lines = [f"{'Gate':<22} {'Result':<14} {'Detail'}"]
    lines.append("-" * 70)
    for name, data in gate_results.items():
        result = data.get("result", "?")
        reason = data.get("reason", "") or data.get("prompt", "")[:50]
        lines.append(f"{name:<22} {result:<14} {reason}")
    return "\n".join(lines)
