"""Tests for saturation_check.py and research_extract.py"""

import pytest
from pathlib import Path
import sys

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_ROOT / "shared") not in sys.path:
    sys.path.insert(0, str(_ROOT / "shared"))

from social_tools.saturation_check import build_grok_saturation_prompt
from social_tools.research_extract import build_gemini_extract_prompt


# ---------------------------------------------------------------------------
# Saturation check tests
# ---------------------------------------------------------------------------

class TestBuildGrokSaturationPrompt:

    def test_returns_string(self):
        result = build_grok_saturation_prompt(
            angle="test angle",
            key_terms=["term1", "term2"],
        )
        assert isinstance(result, str)
        assert len(result) > 100

    def test_contains_angle(self):
        result = build_grok_saturation_prompt(
            angle="optimus inference economics",
            key_terms=["optimus"],
        )
        assert "optimus inference economics" in result

    def test_contains_key_terms(self):
        result = build_grok_saturation_prompt(
            angle="any angle",
            key_terms=["bitcoin", "supply shock"],
        )
        assert '"bitcoin"' in result
        assert '"supply shock"' in result

    def test_default_days_back_is_3(self):
        result = build_grok_saturation_prompt(
            angle="any angle",
            key_terms=["term"],
        )
        assert "3" in result

    def test_custom_days_back(self):
        result = build_grok_saturation_prompt(
            angle="any angle",
            key_terms=["term"],
            days_back=7,
        )
        assert "7" in result

    def test_contains_saturation_level_question(self):
        result = build_grok_saturation_prompt(
            angle="any angle",
            key_terms=["term"],
        )
        # Should ask for LOW/MEDIUM/HIGH saturation
        assert "LOW" in result
        assert "MEDIUM" in result
        assert "HIGH" in result

    def test_contains_paste_placeholder(self):
        result = build_grok_saturation_prompt(
            angle="any angle",
            key_terms=["term"],
        )
        assert "PASTE" in result.upper()

    def test_no_internal_codenames_in_output(self):
        """Verify no DABEIBA internal names leak into prompts."""
        result = build_grok_saturation_prompt(
            angle="any angle",
            key_terms=["term"],
        )
        forbidden = ["DABEIBA", "ORACLE", "MANTIS", "CIPHER", "SOMA",
                     "RAPTOR", "TITAN", "COBALT", "PRISM", "MUSKONOMY"]
        for name in forbidden:
            assert name not in result, f"Codename '{name}' leaked into saturation prompt"

    def test_empty_key_terms(self):
        result = build_grok_saturation_prompt(angle="some angle", key_terms=[])
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Research extract tests
# ---------------------------------------------------------------------------

class TestBuildGeminiExtractPrompt:

    def test_returns_string(self):
        result = build_gemini_extract_prompt(
            source_url="https://example.com",
            extraction_targets=["production rate", "cost per unit"],
        )
        assert isinstance(result, str)
        assert len(result) > 100

    def test_contains_source_url(self):
        url = "https://example.com/article-123"
        result = build_gemini_extract_prompt(
            source_url=url,
            extraction_targets=["target 1"],
        )
        assert url in result

    def test_contains_all_extraction_targets(self):
        targets = ["production rate", "target cost", "deployment timeline"]
        result = build_gemini_extract_prompt(
            source_url="https://example.com",
            extraction_targets=targets,
        )
        for t in targets:
            assert t in result

    def test_targets_are_numbered(self):
        result = build_gemini_extract_prompt(
            source_url="https://example.com",
            extraction_targets=["first", "second", "third"],
        )
        assert "1." in result
        assert "2." in result
        assert "3." in result

    def test_contains_confidence_levels(self):
        result = build_gemini_extract_prompt(
            source_url="https://example.com",
            extraction_targets=["any target"],
        )
        assert "HIGH" in result
        assert "MEDIUM" in result
        assert "LOW" in result

    def test_contains_paste_placeholder(self):
        result = build_gemini_extract_prompt(
            source_url="https://example.com",
            extraction_targets=["target"],
        )
        assert "PASTE" in result.upper()

    def test_no_internal_codenames_in_output(self):
        result = build_gemini_extract_prompt(
            source_url="https://example.com",
            extraction_targets=["target"],
        )
        forbidden = ["DABEIBA", "ORACLE", "MANTIS", "CIPHER", "SOMA",
                     "RAPTOR", "TITAN", "COBALT", "PRISM", "MUSKONOMY"]
        for name in forbidden:
            assert name not in result, f"Codename '{name}' leaked into extract prompt"

    def test_empty_extraction_targets(self):
        result = build_gemini_extract_prompt(
            source_url="https://example.com",
            extraction_targets=[],
        )
        assert isinstance(result, str)
