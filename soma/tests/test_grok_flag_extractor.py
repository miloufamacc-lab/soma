"""
Tests for SOMA-INTEL Phase 7.I1W-G — Grok Flag Extractor

Covers all 9 required test cases:
  1. test_extracts_known_tickers_from_fixture_html
  2. test_direction_classification
  3. test_confidence_calibration
  4. test_evidence_text_truncated_at_500
  5. test_neutral_returned_for_mixed_tone
  6. test_idempotent_overwrite_refuses
  7. test_overwrite_flag_works
  8. test_missing_input_html_clean_exit
  9. test_output_schema_matches_grok_adapter_expectation
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

# ── Ensure shared/ is on sys.path ───────────────────────────────────────────────
_SHARED = Path(__file__).parent.parent.parent  # shared/
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

# ── Fixture paths ────────────────────────────────────────────────────────────────
_FIXTURES = Path(__file__).parent / "fixtures" / "muskonomy"
_EXCERPT_HTML = _FIXTURES / "sitrep_2026-05-05_excerpt.html"

# ── Module under test (import with DABEIBA_ROOT pointed at temp dir) ─────────────
# We import after setting env so _DABEIBA_ROOT resolves correctly in tests
os.environ.setdefault("DABEIBA_ROOT", str(Path(__file__).parent.parent.parent.parent))


from soma.intel.cross_ai.grok_flag_extractor import (
    _calibrate_confidence,
    _class_to_direction,
    _truncate,
    extract_grok_flags,
)
from soma.intel.cross_ai.grok_adapter import validate_grok


# ── Helper ───────────────────────────────────────────────────────────────────────

def _run_extractor(html_path: str, run_date: str, tmp_dir: Path, overwrite: bool = False) -> Path:
    """Run the extractor against an HTML file, writing JSON to tmp_dir."""
    out = tmp_dir / f"grok_flags_{run_date}.json"
    extract_grok_flags(
        sitrep_html_path=html_path,
        run_date=run_date,
        output_path=str(out),
        overwrite=overwrite,
    )
    return out


# ────────────────────────────────────────────────────────────────────────────────
# 1. Extracts known tickers from fixture HTML
# ────────────────────────────────────────────────────────────────────────────────
def test_extracts_known_tickers_from_fixture_html(tmp_path):
    out = _run_extractor(str(_EXCERPT_HTML), "2026-05-05", tmp_path)
    assert out.exists()
    d = json.loads(out.read_text())
    tickers = {f["ticker"] for f in d["flags"]}
    # Fixture has ROBOTAXI, FSD, TERAFAB, AUTO, ENERGY segments + 3 signal rows
    assert "TSLA" in tickers, "All flags should be TSLA"
    assert len(d["flags"]) >= 5, f"Expected >=5 flags, got {len(d['flags'])}"


# ────────────────────────────────────────────────────────────────────────────────
# 2. Direction classification — all badge / dot / icon variants
# ────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("classes,expected", [
    # Current format
    (["badge", "badge-bull"],     "bullish"),
    (["badge", "badge-neu"],      "neutral"),
    (["badge", "badge-bear"],     "bearish"),
    # Older SITREP variants
    (["badge", "badge-bullish"],  "bullish"),
    (["badge", "badge-neutral"],  "neutral"),
    (["badge", "badge-bearish"],  "bearish"),
    (["badge", "badge-watch"],    "neutral"),
    # Signal dot variants
    (["signal-dot", "sig-bull"],  "bullish"),
    (["signal-dot", "sig-bear"],  "bearish"),
    (["signal-dot", "sig-neu"],   "neutral"),
    (["signal-dot", "sig-neutral"], "neutral"),
    # Signal icon variants (2026-05-02 style)
    (["signal-icon", "icon-green"], "bullish"),
    (["signal-icon", "icon-red"],   "bearish"),
    (["signal-icon", "icon-blue"],  "neutral"),
    # Card-level direction (2026-04-27 style)
    (["seg-card", "bullish"],     "bullish"),
    (["seg-card", "neutral"],     "neutral"),
    # Unknown → None
    (["badge", "badge-unknown"],  None),
    ([],                          None),
])
def test_direction_classification(classes, expected):
    assert _class_to_direction(classes) == expected


# ────────────────────────────────────────────────────────────────────────────────
# 3. Confidence calibration — strong / default / speculative mapping
# ────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("direction,text,expected_min,expected_max", [
    # High conviction bullish
    ("bullish", "Fleet expansion confirmed live — record utilization", 0.75, 0.85),
    # Standard bullish
    ("bullish", "Fleet is growing steadily with consistent rides", 0.60, 0.70),
    # Speculative bullish
    ("bullish", "Revenue may grow if regulatory approval is anticipated", 0.45, 0.55),
    # Neutral
    ("neutral", "Mixed results: some metrics up, others down", 0.45, 0.55),
    # Bearish factual
    ("bearish", "Deliveries missed consensus by 3%", 0.55, 0.65),
    # Bearish speculative
    ("bearish", "Timeline at risk if regulatory approval is pending", 0.38, 0.50),
])
def test_confidence_calibration(direction, text, expected_min, expected_max):
    conf = _calibrate_confidence(direction, text)
    assert expected_min <= conf <= expected_max, (
        f"direction={direction!r}, conf={conf} not in [{expected_min}, {expected_max}]"
    )


# ────────────────────────────────────────────────────────────────────────────────
# 4. Evidence text truncated at 500 chars with ellipsis
# ────────────────────────────────────────────────────────────────────────────────
def test_evidence_text_truncated_at_500():
    long_text = "A" * 600
    result = _truncate(long_text)
    assert len(result) <= 500
    assert result.endswith("…")


def test_evidence_text_not_truncated_when_short():
    short = "Short evidence sentence."
    assert _truncate(short) == short


# ────────────────────────────────────────────────────────────────────────────────
# 5. Neutral returned for mixed tone (not a skip)
# ────────────────────────────────────────────────────────────────────────────────
def test_neutral_returned_for_mixed_tone(tmp_path):
    """A segment card with badge-neu must produce a flag with direction=neutral,
    not be skipped."""
    out = _run_extractor(str(_EXCERPT_HTML), "2026-05-05", tmp_path)
    d = json.loads(out.read_text())
    neutral_flags = [f for f in d["flags"] if f["direction"] == "neutral"]
    assert len(neutral_flags) >= 1, "Expected at least one neutral flag from fixture"


# ────────────────────────────────────────────────────────────────────────────────
# 6. Idempotent — second run without --overwrite exits with code 2
# ────────────────────────────────────────────────────────────────────────────────
def test_idempotent_overwrite_refuses(tmp_path):
    out = _run_extractor(str(_EXCERPT_HTML), "2026-05-05", tmp_path)
    assert out.exists()
    with pytest.raises(SystemExit) as exc_info:
        extract_grok_flags(
            sitrep_html_path=str(_EXCERPT_HTML),
            run_date="2026-05-05",
            output_path=str(out),
            overwrite=False,
        )
    assert exc_info.value.code == 2


# ────────────────────────────────────────────────────────────────────────────────
# 7. Overwrite flag allows second run to succeed
# ────────────────────────────────────────────────────────────────────────────────
def test_overwrite_flag_works(tmp_path):
    out = _run_extractor(str(_EXCERPT_HTML), "2026-05-05", tmp_path)
    assert out.exists()
    # Second run with overwrite=True must not raise
    result = extract_grok_flags(
        sitrep_html_path=str(_EXCERPT_HTML),
        run_date="2026-05-05",
        output_path=str(out),
        overwrite=True,
    )
    assert result["written"] == 1
    assert result["extracted"] >= 1


# ────────────────────────────────────────────────────────────────────────────────
# 8. Missing input HTML exits with informative error, not crash
# ────────────────────────────────────────────────────────────────────────────────
def test_missing_input_html_clean_exit(tmp_path):
    non_existent = str(tmp_path / "muskonomy_sitrep_9999-99-99.html")
    out = str(tmp_path / "grok_flags_9999-99-99.json")
    with pytest.raises(SystemExit) as exc_info:
        extract_grok_flags(
            sitrep_html_path=non_existent,
            run_date="9999-99-99",
            output_path=out,
        )
    # Should exit (not crash with an unhandled exception)
    # Exit code is a non-zero string message (not 2), just any SystemExit is fine
    assert exc_info.type is SystemExit


# ────────────────────────────────────────────────────────────────────────────────
# 9. Output schema passes grok_adapter.validate_grok
# ────────────────────────────────────────────────────────────────────────────────
def test_output_schema_matches_grok_adapter_expectation(tmp_path):
    out = _run_extractor(str(_EXCERPT_HTML), "2026-05-05", tmp_path)
    result = validate_grok(str(out))
    assert result["valid"], (
        f"validate_grok rejected extractor output: {result['errors']}"
    )
    assert result["flags_valid"] >= 1
    assert result["errors"] == []
