"""
test_design_helpers.py — Unit tests for design/dabeiba_html.py
One test per helper function. All tests are self-contained, no DB, no I/O.
"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
for _p in [str(_ROOT), str(_ROOT / "shared")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest
from design.dabeiba_html import (
    _scrub,
    _html_escape,
    _strip_css_comments,
    _expand_acronyms_once,
    _format_currency,
    _format_percent,
    _format_date_display,
    _render_section_header,
    _render_stat_block,
    _render_evidence_card,
    _render_data_table,
    _render_inline_tag,
    _render_callout,
    _render_stage_funnel,
    _codename_scan,
    _emoji_scan,
    _opaque_id,
)


# ── _scrub ────────────────────────────────────────────────────────────────────

def test_scrub_replaces_codename():
    assert _scrub("RAPTOR is active") == "[internal] is active"

def test_scrub_case_insensitive():
    assert _scrub("raptor scoring") == "[internal] scoring"

def test_scrub_word_boundary():
    """'INTEL' should not corrupt 'intelligence'."""
    result = _scrub("intelligence platform")
    assert "intelligence" in result
    assert "[internal]" not in result

def test_scrub_leaves_clean_text():
    assert _scrub("No issues here") == "No issues here"


# ── _html_escape ──────────────────────────────────────────────────────────────

def test_html_escape_tags():
    assert _html_escape("<script>alert(1)</script>") == "&lt;script&gt;alert(1)&lt;/script&gt;"

def test_html_escape_scrubs_codename():
    result = _html_escape("RAPTOR <b>")
    assert "[internal]" in result
    assert "<b>" not in result
    assert "&lt;b&gt;" in result


# ── _strip_css_comments ───────────────────────────────────────────────────────

def test_strip_css_comments_removes_block():
    css = "body { color: red; } /* this is a comment */ p { margin: 0; }"
    result = _strip_css_comments(css)
    assert "this is a comment" not in result
    assert "color: red" in result

def test_strip_css_comments_multiline():
    css = "a {\n/* multi\nline\ncomment */\ncolor: blue;\n}"
    result = _strip_css_comments(css)
    assert "multi" not in result
    assert "color: blue" in result


# ── _expand_acronyms_once ─────────────────────────────────────────────────────

def test_expand_acronyms_once_expands_first():
    html = "The FOMC decision matters. FOMC again."
    result = _expand_acronyms_once(html)
    assert "Federal Open Market Committee (FOMC)" in result

def test_expand_acronyms_once_only_first():
    html = "The FOMC decision. FOMC again."
    result = _expand_acronyms_once(html)
    assert result.count("Federal Open Market Committee") == 1

def test_expand_acronyms_once_multiple():
    html = "CPI and GDP data released."
    result = _expand_acronyms_once(html)
    assert "Consumer Price Index (CPI)" in result
    assert "gross domestic product (GDP)" in result


# ── _format_currency ──────────────────────────────────────────────────────────

def test_format_currency_millions():
    assert _format_currency(2_350_000) == "$2.35M CAD"

def test_format_currency_thousands():
    assert _format_currency(850_000, "USD") == "$850K USD"

def test_format_currency_small():
    assert _format_currency(500, "USD") == "$500 USD"

def test_format_currency_billions():
    result = _format_currency(1_500_000_000)
    assert "1.50B" in result

def test_format_currency_negative():
    result = _format_currency(-500_000)
    assert "-" in result and "500" in result


# ── _format_percent ───────────────────────────────────────────────────────────

def test_format_percent_decimal():
    assert _format_percent(0.684) == "68.4%"

def test_format_percent_whole():
    assert _format_percent(68.4) == "68.4%"

def test_format_percent_negative():
    assert _format_percent(-0.05) == "-5.0%"

def test_format_percent_zero():
    assert _format_percent(0.0) == "0.0%"


# ── _format_date_display ──────────────────────────────────────────────────────

def test_format_date_display_known():
    assert _format_date_display("2026-05-06") == "May 6, 2026"

def test_format_date_display_fallback():
    assert _format_date_display("not-a-date") == "not-a-date"


# ── _render_section_header ────────────────────────────────────────────────────

def test_render_section_header_structure():
    html = _render_section_header("LEAD OVERVIEW", "Sophie Tremblay", "QC · Montréal")
    assert "section-header" in html
    assert "LEAD OVERVIEW" in html
    assert "Sophie Tremblay" in html
    assert "QC" in html

def test_render_section_header_no_codename():
    html = _render_section_header("LEAD OVERVIEW", "Test User")
    assert _codename_scan(html) == []

def test_render_section_header_no_subtitle():
    html = _render_section_header("LEAD OVERVIEW", "Test User")
    assert "subtitle" not in html


# ── _render_stat_block ────────────────────────────────────────────────────────

def test_render_stat_block_contains_value():
    html = _render_stat_block("74.5", "Overall score")
    assert "74.5" in html
    assert "Overall score" in html

def test_render_stat_block_caption():
    html = _render_stat_block("74.5", "Score", caption="Fit 50% · Intent 25%")
    assert "stat-caption" in html
    assert "Fit 50%" in html

def test_render_stat_block_mono_class():
    html = _render_stat_block("74.5", "Score", mono=True)
    assert "stat-value--mono" in html

def test_render_stat_block_no_codename():
    html = _render_stat_block("74.5", "Overall score", caption="Fit 50%")
    assert _codename_scan(html) == []


# ── _render_evidence_card ─────────────────────────────────────────────────────

def test_render_evidence_card_structure():
    html = _render_evidence_card("Fit", "2026-05-06", "Assets match ideal profile.", "raptor.db")
    assert "evidence-card" in html
    assert "Fit" in html
    assert "May 6, 2026" in html
    assert "Assets match" in html

def test_render_evidence_card_no_source():
    html = _render_evidence_card("Fit", "2026-05-06", "Body text")
    assert "evidence-source" not in html

def test_render_evidence_card_no_codename():
    html = _render_evidence_card("Profile Fit", "2026-05-06", "Good prospect.")
    assert _codename_scan(html) == []


# ── _render_data_table ────────────────────────────────────────────────────────

def test_render_data_table_headers():
    html = _render_data_table(["Name", "Background", "Last Touchpoint"], [["Sophie", "Notes", "2026-04-25"]])
    assert "<table" in html
    assert "Name" in html
    assert "Background" in html

def test_render_data_table_row_data():
    html = _render_data_table(["Col A", "Col B"], [["val1", "val2"], ["val3", "val4"]])
    assert "val1" in html
    assert "val3" in html

def test_render_data_table_numeric_col_class():
    html = _render_data_table(["Name", "Score"], [["Sophie", "74.5"]], numeric_cols=[1])
    assert 'class="mono"' in html

def test_render_data_table_escapes_html():
    html = _render_data_table(["Name"], [["<script>bad</script>"]])
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


# ── _render_inline_tag ────────────────────────────────────────────────────────

def test_render_inline_tag_p1():
    html = _render_inline_tag("P1", "p1")
    assert "tag-p1" in html

def test_render_inline_tag_warning():
    html = _render_inline_tag("Expiring", "warn")
    assert "tag-warn" in html

def test_render_inline_tag_default():
    html = _render_inline_tag("Custom", "default")
    assert 'class="tag"' in html


# ── _render_callout ───────────────────────────────────────────────────────────

def test_render_callout_warning():
    html = _render_callout("warning", "Consent expiring", "Expires soon")
    assert "callout--warning" in html
    assert "Consent expiring" in html

def test_render_callout_success():
    html = _render_callout("success", "All clear", "No flags")
    assert "callout--success" in html

def test_render_callout_danger():
    html = _render_callout("danger", "Action required", "Immediate")
    assert "callout--danger" in html


# ── _codename_scan ────────────────────────────────────────────────────────────

def test_codename_scan_detects_raptor():
    violations = _codename_scan("RAPTOR is active")
    assert "RAPTOR" in violations

def test_codename_scan_clean():
    assert _codename_scan("No issues here") == []

def test_codename_scan_word_boundary():
    """'intelligence' should not trigger 'INTEL'."""
    violations = _codename_scan("artificial intelligence platform")
    assert "INTEL" not in violations and "intel" not in violations

def test_codename_scan_multiple():
    violations = _codename_scan("RAPTOR and ORACLE both mentioned")
    assert "RAPTOR" in violations
    assert "ORACLE" in violations


# ── _emoji_scan ───────────────────────────────────────────────────────────────

def test_emoji_scan_detects_rocket():
    assert _emoji_scan("Great progress 🚀") is True

def test_emoji_scan_detects_check():
    assert _emoji_scan("Done ✅") is True

def test_emoji_scan_clean():
    assert _emoji_scan("Clean text only") is False

def test_emoji_scan_punctuation_safe():
    assert _emoji_scan("Result: +15.2% vs. prior — excellent!") is False


# ── _opaque_id ────────────────────────────────────────────────────────────────

def test_opaque_id_length():
    assert len(_opaque_id("some-uuid-123")) == 8

def test_opaque_id_uppercase():
    result = _opaque_id("some-uuid-123")
    assert result == result.upper()

def test_opaque_id_different_inputs():
    a = _opaque_id("uuid-aaa")
    b = _opaque_id("uuid-bbb")
    assert a != b

def test_opaque_id_does_not_expose_raw():
    raw = "a3f7b2c1-4d5e-6f78-9a0b-cdef01234567"
    result = _opaque_id(raw)
    assert raw.replace("-", "").upper()[:8] != result  # not a direct slice


# ── _render_stage_funnel ──────────────────────────────────────────────────────

_SAMPLE_STAGES = [
    ("Identified", 12),
    ("Researched", 8),
    ("Contacted", 5),
    ("Meeting Scheduled", 3),
    ("Proposal Sent", 1),
]


def test_render_stage_funnel_returns_html():
    html = _render_stage_funnel(_SAMPLE_STAGES)
    assert "<div" in html
    assert "funnel" in html


def test_render_stage_funnel_all_labels_present():
    html = _render_stage_funnel(_SAMPLE_STAGES)
    for label, _ in _SAMPLE_STAGES:
        assert label in html


def test_render_stage_funnel_max_bar_is_100_percent():
    """The stage with the highest count must render a 100.0% width bar."""
    html = _render_stage_funnel(_SAMPLE_STAGES)
    assert "width:100.0%" in html


def test_render_stage_funnel_proportional_widths():
    """Stage with half the max count should render near 50% width."""
    stages = [("A", 10), ("B", 5)]
    html = _render_stage_funnel(stages)
    assert "50.0%" in html or "width:50" in html


def test_render_stage_funnel_empty_returns_callout():
    html = _render_stage_funnel([])
    assert "callout" in html
    assert "No pipeline data" in html


def test_render_stage_funnel_all_zero_returns_callout():
    html = _render_stage_funnel([("A", 0), ("B", 0)])
    assert "callout" in html


def test_render_stage_funnel_escapes_label():
    html = _render_stage_funnel([('<script>', 1)])
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_render_stage_funnel_no_codenames():
    html = _render_stage_funnel(_SAMPLE_STAGES)
    assert _codename_scan(html) == []


def test_render_stage_funnel_no_emoji():
    html = _render_stage_funnel(_SAMPLE_STAGES)
    assert not _emoji_scan(html)
