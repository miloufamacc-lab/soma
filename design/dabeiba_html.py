"""
design/dabeiba_html.py — DABEIBA Design System Python Companion
===============================================================
Shared HTML rendering helpers for all DABEIBA deliverables:
  - shared/soma/intel/weekly_brief.py (weekly intelligence brief)
  - raptor/raptor_lead_brief.py (prospect lead brief)
  - raptor/raptor_dashboard.py (acquisition dashboard — future)

Design tokens live in design/dabeiba.css.
This module provides Python-side helpers that produce HTML strings
consistent with those tokens.

Rules (hard — inherited from DABEIBA feedback files):
  - Zero internal codenames in any output
  - Zero emojis
  - WCAG AA contrast on all rendered text
  - Single accent per section (§6.3 design system)
  - `--text-muted` reserved for timestamps and citations only

Usage:
    from design.dabeiba_html import (
        _html_escape, _inline_css, _expand_acronyms_once,
        _render_section_header, _render_stat_block,
        _render_evidence_card, _render_data_table,
        _render_inline_tag, _render_callout,
        _format_currency, _format_percent,
        _codename_scan, _emoji_scan,
    )
"""

from __future__ import annotations

import hashlib
import os
import re
import unicodedata
from datetime import date
from html import escape
from pathlib import Path

# ── Internal codename scrub ───────────────────────────────────────────────────
# These must never appear in client-facing output.
_FORBIDDEN_CODENAMES: frozenset[str] = frozenset({
    "DABEIBA", "SOMA", "ORACLE", "MANTIS", "CIPHER", "RAPTOR",
    "TITAN", "COBALT", "SPECTRE", "PRISM", "DOCTRINE", "HORIZON",
    "BEACON", "VECTOR", "FORGE", "DELTA", "SENTINEL", "MUSKONOMY",
    "DOSSIER", "INTEL", "soma_intel", "soma-intel",
})


def _scrub(text: str) -> str:
    """
    Replace forbidden codenames with neutral placeholders.
    Uses word-boundary matching so 'INTEL' doesn't corrupt 'intelligence',
    'FORGE' doesn't corrupt 'forget', etc.
    Identical logic to weekly_brief.py — single source of truth.
    """
    for name in _FORBIDDEN_CODENAMES:
        text = re.sub(r'\b' + re.escape(name) + r'\b', "[internal]", text)
        text = re.sub(r'\b' + re.escape(name.lower()) + r'\b', "[internal]", text)
    return text


def _html_escape(text: str) -> str:
    """HTML-escape + scrub codenames. Use on all user-supplied text."""
    return escape(_scrub(str(text)))


# ── CSS helpers ───────────────────────────────────────────────────────────────

def _strip_css_comments(css: str) -> str:
    """Strip all /* ... */ block comments from CSS before inlining."""
    return re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)


def _inline_css(dabeiba_root: Path, include_fonts: bool = True) -> str:
    """
    Read dabeiba.fonts.css + dabeiba.css, strip block comments, and
    return combined content for embedding inside a <style> tag.

    Comments stripped so:
      (a) file size is smaller
      (b) no internal dev notes reach client-facing HTML
      (c) codename scan passes cleanly
    """
    css_dir   = dabeiba_root / "shared" / "design"
    fonts_css = ""
    base_css  = ""

    if include_fonts:
        fonts_path = css_dir / "dabeiba.fonts.css"
        if fonts_path.exists():
            fonts_css = _strip_css_comments(fonts_path.read_text(encoding="utf-8"))

    base_path = css_dir / "dabeiba.css"
    if base_path.exists():
        base_css = _strip_css_comments(base_path.read_text(encoding="utf-8"))

    return fonts_css + "\n" + base_css


def _css_link_tags(dabeiba_root: Path, output_path: Path) -> str:
    """Return <link> tags for dev/external-CSS mode (relative to output_path)."""
    design_dir = dabeiba_root / "shared" / "design"
    try:
        rel = design_dir.relative_to(output_path.parent)
    except ValueError:
        rel = Path(os.path.relpath(design_dir, output_path.parent))
    return (
        f'<link rel="stylesheet" href="{rel}/dabeiba.fonts.css">\n'
        f'  <link rel="stylesheet" href="{rel}/dabeiba.css">'
    )


# ── Acronym expansion ─────────────────────────────────────────────────────────

_ACRONYM_EXPANSIONS: dict[str, str] = {
    "FOMC": "Federal Open Market Committee (FOMC)",
    "CPI":  "Consumer Price Index (CPI)",
    "OAS":  "option-adjusted spread (OAS)",
    "IG":   "investment grade (IG)",
    "YoY":  "year-over-year (YoY)",
    "HY":   "high yield (HY)",
    "DXY":  "U.S. Dollar Index (DXY)",
    "VIX":  "Cboe Volatility Index (VIX)",
    "GDP":  "gross domestic product (GDP)",
    "PCE":  "Personal Consumption Expenditures (PCE)",
    "AUM":  "assets under management (AUM)",
    "MER":  "management expense ratio (MER)",
    "CLV":  "client lifetime value (CLV)",
    "CASL": "Canada's Anti-Spam Legislation (CASL)",
    "AMF":  "Autorité des marchés financiers (AMF)",
    "CIRO": "Canadian Investment Regulatory Organization (CIRO)",
}


def _expand_acronyms_once(html: str) -> str:
    """
    Expand each acronym on its first occurrence in the HTML string.
    Word-boundary regex prevents partial matches (e.g., 'IG' inside 'HIGH').
    Single pass per document.
    """
    seen: set[str] = set()
    for short, expanded in _ACRONYM_EXPANSIONS.items():
        if short in seen:
            continue
        pattern = r'\b' + re.escape(short) + r'\b'
        if re.search(pattern, html):
            html = re.sub(pattern, expanded, html, count=1)
            seen.add(short)
    return html


# ── Formatting helpers ────────────────────────────────────────────────────────

def _format_currency(amount: float | int, ccy: str = "CAD", decimals: int = 0) -> str:
    """
    Format a monetary amount with SI suffix.
    Examples:
        _format_currency(2_350_000)        → "$2.35M CAD"
        _format_currency(850_000)          → "$850K CAD"
        _format_currency(12_000, "USD")    → "$12K USD"
        _format_currency(500, "USD")       → "$500 USD"
        _format_currency(2.5e9)            → "$2.5B CAD"
    """
    abs_val = abs(amount)
    sign = "-" if amount < 0 else ""
    if abs_val >= 1_000_000_000:
        num = abs_val / 1_000_000_000
        suffix = "B"
    elif abs_val >= 1_000_000:
        num = abs_val / 1_000_000
        suffix = "M"
    elif abs_val >= 1_000:
        num = abs_val / 1_000
        suffix = "K"
    else:
        num = abs_val
        suffix = ""
    # Choose decimal places: show 2 if < 10, else 1, unless overridden
    if decimals == 0:
        if suffix and num < 10:
            fmt = f"{sign}${num:.2f}{suffix}"
        elif suffix and num < 100:
            fmt = f"{sign}${num:.1f}{suffix}"
        elif suffix:
            fmt = f"{sign}${num:.0f}{suffix}"
        else:
            fmt = f"{sign}${num:,.0f}"
    else:
        fmt = f"{sign}${num:.{decimals}f}{suffix}"
    return f"{fmt} {ccy}" if ccy else fmt


def _format_percent(value: float, decimals: int = 1) -> str:
    """
    Format a decimal (0–1) or percentage (0–100) as a percent string.
    Auto-detects scale: if |value| <= 1.5, treats as decimal; else as percent.
    Examples:
        _format_percent(0.684)  → "68.4%"
        _format_percent(68.4)   → "68.4%"
        _format_percent(-0.05)  → "-5.0%"
    """
    if abs(value) <= 1.5:
        pct = value * 100
    else:
        pct = value
    return f"{pct:.{decimals}f}%"


def _format_date_display(iso_date: str) -> str:
    """Convert '2026-05-09' to 'May 9, 2026'."""
    try:
        d = date.fromisoformat(iso_date)
        return d.strftime("%B %-d, %Y")
    except Exception:
        return iso_date


# ── Component renderers ───────────────────────────────────────────────────────

def _render_section_header(eyebrow: str, title: str, subtitle: str = "") -> str:
    """
    Render a section header per design system §5.1.
    eyebrow: all-caps label (e.g. "PROSPECT DOSSIER") — accent color, small
    title:   main heading — serif, --text-2xl
    subtitle: supporting line — sans, --text-sm, muted
    """
    sub_html = (
        f'\n  <p class="subtitle">{_html_escape(subtitle)}</p>'
        if subtitle else ""
    )
    return (
        f'<header class="section-header">\n'
        f'  <p class="eyebrow">{_html_escape(eyebrow)}</p>\n'
        f'  <h2 class="title">{_html_escape(title)}</h2>'
        f'{sub_html}\n'
        f'</header>'
    )


def _render_stat_block(
    value: str,
    label: str,
    caption: str = "",
    mono: bool = True,
    size: str = "3xl",
) -> str:
    """
    Render a stat block per design system §5.2.
    value:   the numeric/data value (string, already formatted)
    label:   short description line
    caption: optional supporting detail (muted color)
    mono:    if True, wraps value in font-mono class
    size:    css text size class suffix (3xl = --text-3xl, 2xl, xl, etc.)
    """
    mono_class = " stat-value--mono" if mono else ""
    cap_html = (
        f'\n  <p class="stat-caption">{_html_escape(caption)}</p>'
        if caption else ""
    )
    return (
        f'<div class="stat">\n'
        f'  <p class="stat-value stat-value--{size}{mono_class}">'
        f'{_html_escape(value)}</p>\n'
        f'  <p class="stat-label">{_html_escape(label)}</p>'
        f'{cap_html}\n'
        f'</div>'
    )


def _render_evidence_card(
    tag: str,
    date_str: str,
    body: str,
    source: str = "",
) -> str:
    """
    Render an evidence card per design system §5.3.
    tag:      category label (e.g. "Fit", "Intent", "Referral")
    date_str: ISO date string — displayed as "Month D, YYYY"
    body:     main claim text — serif prose
    source:   citation / data source attribution
    """
    date_display = _format_date_display(date_str) if date_str else ""
    source_html = (
        f'\n  <footer class="evidence-source">— {_html_escape(source)}</footer>'
        if source else ""
    )
    return (
        f'<article class="evidence-card">\n'
        f'  <header class="evidence-header">\n'
        f'    <span class="evidence-tag">{_html_escape(tag)}</span>\n'
        f'    <time class="evidence-date">{_html_escape(date_display)}</time>\n'
        f'  </header>\n'
        f'  <p class="evidence-body">{_html_escape(body)}</p>'
        f'{source_html}\n'
        f'</article>'
    )


def _render_data_table(
    headers: list[str],
    rows: list[list[str]],
    numeric_cols: list[int] | None = None,
) -> str:
    """
    Render a data table per design system §5.4.
    headers:      list of column header strings
    rows:         list of row lists (each inner list = one row of cells)
    numeric_cols: indices of columns that should use mono font (right-aligned)
    """
    numeric_cols = numeric_cols or []
    th_cells = "".join(
        f'<th scope="col">{_html_escape(h)}</th>' for h in headers
    )
    rows_html = ""
    for row in rows:
        cells = ""
        for i, cell in enumerate(row):
            cls = ' class="mono"' if i in numeric_cols else ""
            cells += f"<td{cls}>{_html_escape(str(cell))}</td>"
        rows_html += f"<tr>{cells}</tr>\n"
    return (
        f'<div class="table-wrapper">\n'
        f'<table class="data-table">\n'
        f'  <thead><tr>{th_cells}</tr></thead>\n'
        f'  <tbody>\n{rows_html}  </tbody>\n'
        f'</table>\n'
        f'</div>'
    )


def _render_inline_tag(label: str, variant: str = "default") -> str:
    """
    Render an inline pill/tag.
    variant: p1 / p2 / p3 / horizon / success / warn / danger / default
    """
    _VARIANT_CLASS: dict[str, str] = {
        "p1":      "tag tag-p1",
        "p2":      "tag tag-p2",
        "p3":      "tag tag-p3",
        "horizon": "tag tag-structural",
        "success": "tag tag-success",
        "warn":    "tag tag-warn",
        "warning": "tag tag-warn",
        "danger":  "tag tag-danger",
        "default": "tag",
    }
    cls = _VARIANT_CLASS.get(variant, "tag")
    return f'<span class="{cls}">{_html_escape(label)}</span>'


def _render_callout(severity: str, title: str, body: str) -> str:
    """
    Render a callout box.
    severity: success / warning / danger / info
    title:    bold heading line
    body:     explanatory text
    """
    _SEV_CLASS: dict[str, str] = {
        "success": "callout callout--success",
        "warning": "callout callout--warning",
        "warn":    "callout callout--warning",
        "danger":  "callout callout--danger",
        "info":    "callout callout--info",
    }
    cls = _SEV_CLASS.get(severity, "callout callout--info")
    return (
        f'<div class="{cls}">\n'
        f'  <p class="callout-title">{_html_escape(title)}</p>\n'
        f'  <p class="callout-body">{_html_escape(body)}</p>\n'
        f'</div>'
    )


# ── Stage funnel ─────────────────────────────────────────────────────────────

def _render_stage_funnel(stages: list[tuple[str, int]]) -> str:
    """
    Render a CSS-only horizontal bar funnel showing count per pipeline stage.

    stages: ordered list of (display_label, count) tuples.
            Example: [("Identified", 12), ("Researched", 8), ("Contacted", 5),
                      ("Meeting Scheduled", 3), ("Proposal Sent", 1)]

    Design choices (per DABEIBA Design System §6.3 single-accent rule):
      - Bar track: --bg-subtle (neutral, all stages visible simultaneously)
      - Proportional fill: --accent (single accent element per chart, the fill)
      - Label: --text, --text-sm
      - Count: --text-muted, mono
      - Widths: inline style calc(N / MAX * 100%) — pure CSS, no JS, no var()

    Returns _render_callout('info', ...) if stages list is empty or all counts are 0.
    """
    if not stages or all(count == 0 for _, count in stages):
        return _render_callout(
            "info",
            "No pipeline data",
            "Stage counts will appear here once prospects are added.",
        )

    max_count = max(count for _, count in stages)
    if max_count == 0:
        max_count = 1  # prevent division by zero

    rows_html = ""
    for label, count in stages:
        pct = round((count / max_count) * 100, 1)
        rows_html += (
            f'<div class="funnel-row">\n'
            f'  <span class="funnel-label">{_html_escape(label)}</span>\n'
            f'  <div class="funnel-track">'
            f'<div class="funnel-fill" style="width:{pct}%"></div>'
            f'</div>\n'
            f'  <span class="funnel-count">{_html_escape(str(count))}</span>\n'
            f'</div>\n'
        )

    return f'<div class="funnel">\n{rows_html}</div>'


# ── Security / compliance scans ───────────────────────────────────────────────

def _codename_scan(text: str) -> list[str]:
    """
    Scan text for forbidden internal codenames.
    Returns list of violations (empty = clean).
    Case-sensitive word-boundary match.
    """
    violations: list[str] = []
    for name in sorted(_FORBIDDEN_CODENAMES):
        if re.search(r'\b' + re.escape(name) + r'\b', text):
            violations.append(name)
        if re.search(r'\b' + re.escape(name.lower()) + r'\b', text):
            lower = name.lower()
            if lower not in violations:
                violations.append(lower)
    return violations


def _emoji_scan(text: str) -> bool:
    """
    Return True if text contains any emoji codepoints.
    Uses Unicode category detection — no external deps.
    """
    for char in text:
        cat = unicodedata.category(char)
        cp  = ord(char)
        # Emoji ranges: emoticons, misc symbols, supplemental symbols, etc.
        if cat in ("So",) or (0x1F300 <= cp <= 0x1FBFF) or (0x2600 <= cp <= 0x27BF):
            return True
    return False


# ── ID utilities ──────────────────────────────────────────────────────────────

def _opaque_id(raw_id: str, length: int = 8) -> str:
    """
    Return an opaque uppercase hex reference derived from raw_id.
    Example: _opaque_id("a3f7b2c1-...") → "A3F7B2C1"
    Never expose the raw ID in client-facing output.
    """
    digest = hashlib.sha256(raw_id.encode()).hexdigest()
    return digest[:length].upper()
