"""Tests for quality_gates.py"""

import pytest
from pathlib import Path
import sys

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_ROOT / "shared") not in sys.path:
    sys.path.insert(0, str(_ROOT / "shared"))

from social_tools.quality_gates import darkframe_gates, drycapital_gates, linkedin_gates, format_gate_table


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _result(gates: dict, name: str) -> str:
    return gates[name]["result"]


# ---------------------------------------------------------------------------
# Darkframe — mechanical gates
# ---------------------------------------------------------------------------

class TestDarkframeMechanicalGates:

    def test_length_pass(self):
        text = "a" * 250
        assert _result(darkframe_gates(text), "length_ok") == "pass"

    def test_length_fail(self):
        text = "a" * 251
        assert _result(darkframe_gates(text), "length_ok") == "fail"

    def test_length_empty_passes(self):
        assert _result(darkframe_gates(""), "length_ok") == "pass"

    def test_no_emojis_pass(self):
        text = "bitcoin is a fixed supply asset."
        assert _result(darkframe_gates(text), "no_emojis") == "pass"

    def test_no_emojis_fail_on_fire(self):
        text = "bitcoin is going to the moon 🔥"
        assert _result(darkframe_gates(text), "no_emojis") == "fail"

    def test_no_emojis_fail_on_flag(self):
        text = "us policy 🇺🇸 matters"
        assert _result(darkframe_gates(text), "no_emojis") == "fail"

    def test_no_allcaps_pass_normal(self):
        text = "tesla reported earnings yesterday."
        assert _result(darkframe_gates(text), "no_allcaps") == "pass"

    def test_no_allcaps_fail_shouting(self):
        text = "TESLA WILL HIT 1000 NEXT YEAR"
        assert _result(darkframe_gates(text), "no_allcaps") == "fail"

    def test_no_allcaps_allows_whitelisted_acronym(self):
        # "AI" and "ETF" are whitelisted — should not trigger gate
        text = "AI inference costs are dropping. The ETF holds 200 names."
        result = darkframe_gates(text)
        assert _result(result, "no_allcaps") == "pass"

    def test_no_allcaps_allows_two_char_caps(self):
        # Two-char all-caps like "US" — below 3-char threshold
        text = "US treasury yields rose overnight."
        assert _result(darkframe_gates(text), "no_allcaps") == "pass"

    def test_no_hashtags_pass(self):
        text = "a clean post with no tags."
        assert _result(darkframe_gates(text), "no_hashtags") == "pass"

    def test_no_hashtags_fail(self):
        text = "great day for #bitcoin and #AI"
        assert _result(darkframe_gates(text), "no_hashtags") == "fail"

    def test_no_exclamation_pass(self):
        text = "the marginal cost of production is converging."
        assert _result(darkframe_gates(text), "no_exclamation") == "pass"

    def test_no_exclamation_fail(self):
        text = "amazing results!"
        assert _result(darkframe_gates(text), "no_exclamation") == "fail"

    def test_combined_bad_post_fails_multiple_gates(self):
        text = "TESLA WILL HIT 1000!!! 🚀 #investing #stocks"
        results = darkframe_gates(text)
        assert _result(results, "no_allcaps") == "fail"
        assert _result(results, "no_exclamation") == "fail"
        assert _result(results, "no_emojis") == "fail"
        assert _result(results, "no_hashtags") == "fail"


# ---------------------------------------------------------------------------
# Darkframe — subjective gates
# ---------------------------------------------------------------------------

class TestDarkframeSubjectiveGates:

    def test_subjective_gates_return_needs_human(self):
        text = "the marginal cost of inference is collapsing."
        results = darkframe_gates(text)
        for gate in ["screenshot_test", "tomorrow_test", "attribution_test",
                     "cringe_test", "longevity_test"]:
            assert _result(results, gate) == "needs_human", f"{gate} should be needs_human"

    def test_subjective_gates_have_prompts(self):
        results = darkframe_gates("any text")
        for gate in ["screenshot_test", "tomorrow_test", "attribution_test",
                     "cringe_test", "longevity_test"]:
            assert results[gate]["prompt"], f"{gate} should have a non-empty prompt"

    def test_all_gate_names_present(self):
        results = darkframe_gates("any text")
        expected = {"length_ok", "no_emojis", "no_allcaps", "no_hashtags",
                    "no_exclamation", "screenshot_test", "tomorrow_test",
                    "attribution_test", "cringe_test", "longevity_test"}
        assert set(results.keys()) == expected


# ---------------------------------------------------------------------------
# Drycapital gates
# ---------------------------------------------------------------------------

class TestDrycapitalGates:

    def test_all_five_gates_present(self):
        results = drycapital_gates("any text")
        expected = {"screenshot_test", "tomorrow_test", "attribution_test",
                    "final_line_test", "cringe_test"}
        assert set(results.keys()) == expected

    def test_all_gates_are_needs_human(self):
        results = drycapital_gates("clean text here")
        for name, data in results.items():
            assert data["result"] == "needs_human", f"{name} should be needs_human"

    def test_all_gates_have_prompts(self):
        results = drycapital_gates("any text")
        for name, data in results.items():
            assert data["prompt"], f"{name} should have a prompt"


# ---------------------------------------------------------------------------
# LinkedIn gates (placeholder)
# ---------------------------------------------------------------------------

class TestLinkedinGatesPlaceholder:

    def test_returns_empty_dict(self):
        assert linkedin_gates("any text") == {}


# ---------------------------------------------------------------------------
# Gate table formatter
# ---------------------------------------------------------------------------

class TestFormatGateTable:

    def test_returns_string(self):
        results = darkframe_gates("clean text here")
        table = format_gate_table(results)
        assert isinstance(table, str)
        assert len(table) > 0

    def test_contains_gate_names(self):
        results = darkframe_gates("clean text here")
        table = format_gate_table(results)
        assert "length_ok" in table
        assert "no_emojis" in table
