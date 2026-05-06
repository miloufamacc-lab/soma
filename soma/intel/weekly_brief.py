"""
SOMA-INTEL P6.6 — Weekly Intelligence Brief

Generates a self-contained HTML brief every Friday covering:
  §1  Market regime
  §2  Top 5 high-conviction signals (last 7 days, deduplicated by ticker)
  §3  New investment theses (soma_intel_belief thesis/conviction predicates)
  §4  Convergence movers (platform convergence × 5d price action)
  §5  Regime transition monitor (placeholder — scheduled future release)
  §6  Structural watch (soma_intel_belief structural_watch; falls back to
      soma_intel_signal horizon='structural')

Output: <dabeiba_root>/cipher/outputs/weekly_brief_YYYY-MM-DD.html

Design system: design/dabeiba.css + design/dabeiba.fonts.css
  - CSS is inlined by default (--inline-css, default True) for email portability
  - External link mode available via --no-inline-css for local development

Legacy path:
  - The pre-design-system builder is preserved behind --legacy flag
  - Legacy path will be removed after 2 Friday production cycles

Rules (hard — carried from DABEIBA feedback files):
  - Zero internal codenames in client-facing output
  - Zero emojis
  - Evidence cited where available
  - Plain prose — no fluff
  - "Data not available this week" callout when DB data is missing; never synthesize

Usage:
    python3 soma/intel/weekly_brief.py                   # generate for today
    python3 soma/intel/weekly_brief.py --date 2026-05-09 # specific date
    python3 soma/intel/weekly_brief.py --force           # write even if not Friday
    python3 soma/intel/weekly_brief.py --legacy          # use pre-design-system builder
    python3 soma/intel/weekly_brief.py --no-inline-css   # link CSS externally (dev)
    python3 soma/intel/weekly_brief.py --apply           # alias for --force
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, timedelta
from html import escape
from pathlib import Path

_HERE         = Path(__file__).resolve().parent
_DABEIBA_ROOT = _HERE.parent.parent.parent
for _p in [str(_DABEIBA_ROOT), str(_DABEIBA_ROOT / "shared")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from soma.intel.store import IntelStore

DB_PATH = (
    Path(os.environ["SOMA_DB_PATH"])
    if "SOMA_DB_PATH" in os.environ
    else _DABEIBA_ROOT / "shared" / "soma" / "data" / "soma.db"
)

OUTPUT_DIR  = _DABEIBA_ROOT / "cipher" / "outputs"
DESIGN_DIR  = _DABEIBA_ROOT / "design"

BRIEF_LOOKBACK_DAYS  = 7
MAX_SIGNALS          = 5
MAX_NEW_THESES       = 3
MAX_CONVERGENCE      = 8
MAX_STRUCTURAL       = 3

# ── Internal codename scrub ───────────────────────────────────────────────────
# These must never appear in client-facing output.
_FORBIDDEN_CODENAMES = {
    "DABEIBA", "SOMA", "ORACLE", "MANTIS", "CIPHER", "RAPTOR",
    "TITAN", "COBALT", "SPECTRE", "PRISM", "DOCTRINE", "HORIZON",
    "BEACON", "VECTOR", "FORGE", "DELTA", "SENTINEL", "MUSKONOMY",
    "DOSSIER", "INTEL", "soma_intel", "soma-intel",
}


def _scrub(text: str) -> str:
    """
    Replace forbidden codenames with neutral placeholders.
    Uses word-boundary matching so 'INTEL' doesn't corrupt 'intelligence',
    'FORGE' doesn't corrupt 'forget', etc.
    """
    import re as _re
    for name in _FORBIDDEN_CODENAMES:
        # Word-boundary replace for the uppercase form
        text = _re.sub(r'\b' + _re.escape(name) + r'\b', "[internal]", text)
        # Word-boundary replace for the lowercase form
        text = _re.sub(r'\b' + _re.escape(name.lower()) + r'\b', "[internal]", text)
    return text


def _esc(text: str) -> str:
    return escape(_scrub(str(text)))


# ── Schema helpers ────────────────────────────────────────────────────────────

def _table_exists(cursor, table_name: str) -> bool:
    row = cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,)
    ).fetchone()
    return row is not None


def _column_exists(cursor, table_name: str, col: str) -> bool:
    cols = cursor.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(c[1] == col for c in cols)


# ── CSS helpers ───────────────────────────────────────────────────────────────

def _strip_css_comments(css: str) -> str:
    """
    Strip all /* ... */ block comments from CSS.
    Applied when inlining CSS for client-facing HTML — keeps file small
    and ensures no internal development notes reach the deliverable.
    """
    import re as _re
    return _re.sub(r"/\*.*?\*/", "", css, flags=_re.DOTALL)


def _inline_css(dabeiba_root: Path, include_fonts: bool = True) -> str:
    """
    Read dabeiba.fonts.css + dabeiba.css, strip block comments, and
    return combined content for embedding inside a <style> tag.

    CSS comments are stripped before inlining so:
      (a) file size is smaller
      (b) no internal development notes appear in client-facing HTML
      (c) codename scrub passes cleanly

    Falls back to empty string if files are not found.
    """
    css_dir   = dabeiba_root / "design"
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
    design_dir = dabeiba_root / "design"
    try:
        rel = design_dir.relative_to(output_path.parent)
    except ValueError:
        # Fallback: compute relative path manually
        rel = Path(os.path.relpath(design_dir, output_path.parent))
    return (
        f'<link rel="stylesheet" href="{rel}/dabeiba.fonts.css">\n'
        f'  <link rel="stylesheet" href="{rel}/dabeiba.css">'
    )


# ── Acronym expansion (QA item a) ─────────────────────────────────────────────

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
}


def _expand_acronyms_once(html: str) -> str:
    """
    Expand each acronym on its first occurrence in the HTML string, then
    leave subsequent occurrences as the short form.
    Applied to the full HTML string before write — single pass per brief.

    Uses word-boundary regex so 'IG' doesn't match inside 'HIGH',
    'CPI' doesn't match inside 'DCPI', etc.
    """
    import re as _re
    seen: set[str] = set()
    for short, expanded in _ACRONYM_EXPANSIONS.items():
        if short in seen:
            continue
        pattern = r'\b' + _re.escape(short) + r'\b'
        if _re.search(pattern, html):
            html = _re.sub(pattern, expanded, html, count=1)
            seen.add(short)
    return html


# ── Regime label formatting ───────────────────────────────────────────────────

_REGIME_PART_MAP: dict[str, str] = {
    "bull":       "Bull",
    "bear":       "Bear",
    "neutral":    "Neutral",
    "low":        "Low Vol",
    "med":        "Med Vol",
    "high":       "High Vol",
    "easing":     "Easing",
    "tightening": "Tightening",
    "stable":     "Stable",
    "risk":       "Risk",
    "off":        "Off",
    "on":         "On",
}


def _format_regime_label(raw: str) -> str:
    """Convert 'bull_med_tightening' to 'Bull · Med Vol · Tightening'."""
    if not raw or raw in ("N/A", "n/a"):
        return "N/A"
    parts = raw.split("_")
    formatted = [_REGIME_PART_MAP.get(p.lower(), p.title()) for p in parts]
    return " · ".join(formatted)  # · (middle dot)


def _format_date_display(iso_date: str) -> str:
    """Convert '2026-05-09' to 'May 9, 2026'."""
    try:
        d = date.fromisoformat(iso_date)
        return d.strftime("%B %-d, %Y")
    except Exception:
        return iso_date


# ── Priority tag mapping ──────────────────────────────────────────────────────

def _priority_tag(priority: str | None) -> str:
    """Map DB priority values (HIGH/MEDIUM/LOW/P2/P3) to display tag."""
    p = (priority or "").upper()
    if p in ("HIGH", "P1"):
        return '<span class="tag tag-p1">P1</span>'
    if p in ("MEDIUM", "P2"):
        return '<span class="tag tag-p2">P2</span>'
    if p in ("LOW", "P3"):
        return '<span class="tag tag-p3">P3</span>'
    return f'<span class="tag tag-p3">{escape(priority or "")}</span>'


def _horizon_tag(h: str | None) -> str:
    """Render horizon as a colored pill tag."""
    h = (h or "").lower()
    if h == "tactical":
        return '<span class="tag tag-tactical">Tactical</span>'
    if h == "thematic":
        return '<span class="tag tag-thematic">Thematic</span>'
    if h == "structural":
        return '<span class="tag tag-structural">Structural</span>'
    return ""


def _clean_notes(notes: str | None) -> str:
    """Strip internal prefixes and scrub codenames from notes text."""
    n = _scrub(notes or "")
    for prefix in ("signal_propagator:", "exploration_channel", "[internal]"):
        n = n.replace(prefix, "")
    return n.strip("; ").strip()


# ── Data queries — shared (also used by legacy path) ─────────────────────────

def _regime_block(store: IntelStore, as_of_date: str) -> dict:
    """Fetch current regime row."""
    try:
        row = store._c.execute(
            "SELECT composite_label, trend_state, vol_state, macro_state, confidence "
            "FROM soma_intel_regime WHERE date <= ? ORDER BY date DESC LIMIT 1",
            (as_of_date,),
        ).fetchone()
        if row:
            return dict(zip(
                ["composite_label", "trend_state", "vol_state", "macro_state", "confidence"],
                row
            ))
    except Exception:
        pass
    return {
        "composite_label": "N/A",
        "trend_state": "N/A",
        "vol_state": "N/A",
        "macro_state": "N/A",
        "confidence": None,
    }


def _p1_carryovers(store: IntelStore, as_of_date: str) -> list[dict]:
    """Legacy: active P1-priority signals from last 7 days."""
    since = (date.fromisoformat(as_of_date) - timedelta(days=BRIEF_LOOKBACK_DAYS)).isoformat()
    try:
        rows = store._c.execute(
            """
            SELECT ticker, date, anomaly_score, horizon, notes
            FROM soma_intel_signal
            WHERE priority = 'P1'
              AND status   = 'active'
              AND date     BETWEEN ? AND ?
            ORDER BY anomaly_score DESC
            LIMIT ?
            """,
            (since, as_of_date, MAX_SIGNALS),
        ).fetchall()
        return [dict(zip(["ticker","date","anomaly_score","horizon","notes"], r)) for r in rows]
    except Exception:
        return []


def _new_theses_legacy(store: IntelStore, as_of_date: str) -> list[dict]:
    """Legacy: thematic + structural signals written this week."""
    since = (date.fromisoformat(as_of_date) - timedelta(days=BRIEF_LOOKBACK_DAYS)).isoformat()
    try:
        rows = store._c.execute(
            """
            SELECT ticker, date, anomaly_score, horizon, notes
            FROM soma_intel_signal
            WHERE horizon IN ('thematic', 'structural')
              AND status = 'active'
              AND date   BETWEEN ? AND ?
            ORDER BY anomaly_score DESC
            LIMIT ?
            """,
            (since, as_of_date, 10),
        ).fetchall()
        return [dict(zip(["ticker","date","anomaly_score","horizon","notes"], r)) for r in rows]
    except Exception:
        return []


def _convergence_movers(store: IntelStore, as_of_date: str) -> list[dict]:
    """Legacy: platform convergence signals this week."""
    since = (date.fromisoformat(as_of_date) - timedelta(days=BRIEF_LOOKBACK_DAYS)).isoformat()
    try:
        rows = store._c.execute(
            """
            SELECT ticker, date, anomaly_score, features, notes
            FROM soma_intel_signal
            WHERE notes  LIKE '%Platform convergence%'
              AND status = 'active'
              AND date   BETWEEN ? AND ?
            ORDER BY anomaly_score DESC
            LIMIT ?
            """,
            (since, as_of_date, MAX_CONVERGENCE),
        ).fetchall()
        result = []
        for r in rows:
            row = dict(zip(["ticker","date","anomaly_score","features","notes"], r))
            try:
                feat = json.loads(row["features"] or "{}")
                row["platform_count"]    = feat.get("platform_count", "?")
                row["convergence_pairs"] = feat.get("convergence_pairs", [])
            except Exception:
                row["platform_count"]    = "?"
                row["convergence_pairs"] = []
            result.append(row)
        return result
    except Exception:
        return []


def _structural_watch(store: IntelStore, as_of_date: str) -> list[dict]:
    """Legacy: active structural signals (90-day lookback)."""
    since = (date.fromisoformat(as_of_date) - timedelta(days=90)).isoformat()
    try:
        rows = store._c.execute(
            """
            SELECT ticker, date, anomaly_score, notes
            FROM soma_intel_signal
            WHERE horizon  = 'structural'
              AND status   = 'active'
              AND date     >= ?
            ORDER BY anomaly_score DESC
            LIMIT ?
            """,
            (since, MAX_STRUCTURAL),
        ).fetchall()
        return [dict(zip(["ticker","date","anomaly_score","notes"], r)) for r in rows]
    except Exception:
        return []


# ── Data queries — v2 ────────────────────────────────────────────────────────

def _coverage_count(store: IntelStore) -> int:
    """Number of active tickers in the universe."""
    try:
        if not _table_exists(store._c, "soma_intel_universe"):
            return 0
        row = store._c.execute(
            "SELECT COUNT(*) FROM soma_intel_universe WHERE active = 1"
        ).fetchone()
        return row[0] if row else 0
    except Exception:
        return 0


def _regime_change_label(store: IntelStore, as_of_date: str) -> str:
    """Compare latest two regime rows; return human-readable change string."""
    try:
        rows = store._c.execute(
            "SELECT date, composite_label FROM soma_intel_regime "
            "WHERE date <= ? ORDER BY date DESC LIMIT 2",
            (as_of_date,),
        ).fetchall()
        if len(rows) >= 2:
            current = rows[0][1]
            prev    = rows[1][1]
            if current == prev:
                return "Unchanged from last week"
            return f"Changed from {_format_regime_label(prev)}"
        return ""
    except Exception:
        return ""


def _top_signals_dedup(store: IntelStore, as_of_date: str) -> list[dict]:
    """
    Top signals from last 7 days, deduplicated by ticker (highest score kept).
    Returns up to MAX_SIGNALS rows.
    """
    since = (date.fromisoformat(as_of_date) - timedelta(days=BRIEF_LOOKBACK_DAYS)).isoformat()
    try:
        rows = store._c.execute(
            """
            SELECT ticker, date, priority, anomaly_score, horizon, notes
            FROM soma_intel_signal
            WHERE status = 'active'
              AND date   BETWEEN ? AND ?
            ORDER BY anomaly_score DESC
            """,
            (since, as_of_date),
        ).fetchall()
        seen:   set[str]  = set()
        result: list[dict] = []
        for r in rows:
            ticker = r[0]
            if ticker not in seen:
                seen.add(ticker)
                result.append(dict(zip(
                    ["ticker","date","priority","anomaly_score","horizon","notes"], r
                )))
                if len(result) >= MAX_SIGNALS:
                    break
        return result
    except Exception:
        return []


def _evidence_cards(store: IntelStore, as_of_date: str) -> list[dict]:
    """
    Fetch soma_intel_belief rows with predicate IN ('thesis','conviction').
    Returns empty list if the predicates don't exist yet (v1 schema).
    """
    since = (date.fromisoformat(as_of_date) - timedelta(days=BRIEF_LOOKBACK_DAYS)).isoformat()
    try:
        if not _table_exists(store._c, "soma_intel_belief"):
            return []
        rows = store._c.execute(
            """
            SELECT subject_node_id, predicate, value, confidence, ts, source_id
            FROM soma_intel_belief
            WHERE predicate IN ('thesis', 'conviction')
              AND ts >= ?
              AND superseded_by IS NULL
            ORDER BY ts DESC LIMIT ?
            """,
            (since, MAX_NEW_THESES),
        ).fetchall()
        return [
            dict(zip(["node_id","predicate","value","confidence","ts","source_id"], r))
            for r in rows
        ]
    except Exception:
        return []


def _convergence_with_price(store: IntelStore, as_of_date: str) -> list[dict]:
    """
    Platform convergence signals × 5-day price action from soma_intel_price_history.
    Deduplicated by ticker (one row per company).
    """
    since       = (date.fromisoformat(as_of_date) - timedelta(days=BRIEF_LOOKBACK_DAYS)).isoformat()
    five_d_ago  = (date.fromisoformat(as_of_date) - timedelta(days=5)).isoformat()
    try:
        rows = store._c.execute(
            """
            SELECT ticker,
                   MAX(date)          AS sig_date,
                   MAX(anomaly_score) AS score,
                   features
            FROM soma_intel_signal
            WHERE notes LIKE '%Platform convergence%'
              AND status = 'active'
              AND date   BETWEEN ? AND ?
            GROUP BY ticker
            ORDER BY score DESC
            LIMIT ?
            """,
            (since, as_of_date, MAX_CONVERGENCE),
        ).fetchall()

        result: list[dict] = []
        for r in rows:
            ticker, sig_date, score, feat_json = r[0], r[1], r[2], r[3]

            # 5-day price change
            p_now = store._c.execute(
                "SELECT close FROM soma_intel_price_history "
                "WHERE ticker = ? AND date <= ? ORDER BY date DESC LIMIT 1",
                (ticker, as_of_date),
            ).fetchone()
            p_5d = store._c.execute(
                "SELECT close FROM soma_intel_price_history "
                "WHERE ticker = ? AND date <= ? ORDER BY date DESC LIMIT 1",
                (ticker, five_d_ago),
            ).fetchone()

            price_chg: float | None = None
            if p_now and p_5d and p_5d[0]:
                price_chg = (p_now[0] - p_5d[0]) / p_5d[0] * 100

            # Parse platform features
            try:
                feat          = json.loads(feat_json or "{}")
                platform_count = feat.get("platform_count", "?")
                names         = feat.get("platform_names", {})
                platforms_str = ", ".join(names.values()) if names else "?"
            except Exception:
                platform_count = "?"
                platforms_str  = "?"

            result.append({
                "ticker":         ticker,
                "date":           sig_date,
                "anomaly_score":  score,
                "platform_count": platform_count,
                "platforms":      platforms_str,
                "price_change_5d": price_chg,
            })
        return result
    except Exception:
        return []


def _structural_watch_cards(store: IntelStore, as_of_date: str) -> list[dict]:
    """
    Structural watch signal cards.

    Priority order:
      1. soma_intel_belief predicate='structural_watch' (curated, when available)
      2. soma_intel_signal horizon='structural' (active, 90-day lookback)

    Returns list of dicts with keys: from_belief, body_text, date_str, source_str
    """
    # 1 — belief table (curated structural watch entries)
    try:
        if _table_exists(store._c, "soma_intel_belief"):
            rows = store._c.execute(
                """
                SELECT subject_node_id, value, confidence, ts, source_id
                FROM soma_intel_belief
                WHERE predicate = 'structural_watch'
                  AND superseded_by IS NULL
                ORDER BY ts DESC LIMIT ?
                """,
                (MAX_STRUCTURAL,),
            ).fetchall()
            if rows:
                return [
                    {
                        "from_belief": True,
                        "body_text":   _clean_notes(r[1]),
                        "date_str":    (r[3] or "")[:10],  # ISO date part only
                        "source_str":  _scrub(r[4] or "Internal knowledge layer"),
                        "ticker":      r[0].replace("co_", "") if r[0] else "",
                    }
                    for r in rows
                ]
    except Exception:
        pass

    # 2 — fallback: structural signals from soma_intel_signal
    # NOTE: structural signals are written with status='expired' by the pipeline
    # (they are long-duration theses, not time-limited alerts), so we do NOT
    # filter by status here — we want all structural signals in the 90-day window.
    since = (date.fromisoformat(as_of_date) - timedelta(days=90)).isoformat()
    try:
        rows = store._c.execute(
            """
            SELECT ticker, date, anomaly_score, notes
            FROM soma_intel_signal
            WHERE horizon = 'structural'
              AND date   >= ?
            GROUP BY ticker
            ORDER BY anomaly_score DESC LIMIT ?
            """,
            (since, MAX_STRUCTURAL),
        ).fetchall()
        return [
            {
                "from_belief": False,
                "body_text":   _clean_notes(r[3]),
                "date_str":    r[1],
                "source_str":  "Internal signal-intelligence layer",
                "ticker":      r[0],
            }
            for r in rows
        ]
    except Exception:
        return []


# ── Legacy CSS + HTML builder ─────────────────────────────────────────────────
# Preserved behind --legacy flag. Will be removed after 2 Friday cycles.

_CSS_LEGACY = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: "Georgia", serif;
    font-size: 14px;
    line-height: 1.65;
    color: #1a1a1a;
    background: #fafaf8;
    padding: 36px 24px;
    max-width: 860px;
    margin: 0 auto;
}
header { border-bottom: 2px solid #1a1a1a; padding-bottom: 10px; margin-bottom: 28px; }
header h1 { font-size: 20px; font-weight: bold; letter-spacing: 0.02em; }
header .meta { font-size: 12px; color: #555; margin-top: 4px; }
h2 {
    font-size: 13px;
    font-weight: bold;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    border-bottom: 1px solid #ccc;
    padding-bottom: 4px;
    margin: 28px 0 12px;
    color: #333;
}
.regime-box {
    background: #fff;
    border: 1px solid #ddd;
    padding: 12px 16px;
    margin-bottom: 8px;
    border-radius: 2px;
}
.regime-box .label { font-size: 16px; font-weight: bold; color: #1a1a1a; }
.regime-box .sub   { font-size: 12px; color: #666; margin-top: 4px; }
table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
    margin-bottom: 4px;
}
th {
    text-align: left;
    font-size: 11px;
    font-weight: bold;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    border-bottom: 1px solid #ccc;
    padding: 4px 8px;
    color: #555;
}
td { padding: 5px 8px; border-bottom: 1px solid #ebebeb; vertical-align: top; }
tr:last-child td { border-bottom: none; }
.score-high { color: #b00; font-weight: bold; }
.score-med  { color: #884400; }
.score-low  { color: #555; }
.horizon-tag {
    display: inline-block;
    font-size: 10px;
    font-weight: bold;
    letter-spacing: 0.04em;
    padding: 1px 5px;
    border-radius: 2px;
    text-transform: uppercase;
}
.h-tactical   { background: #e8f0fe; color: #1a56db; }
.h-thematic   { background: #fef9e7; color: #8a6800; }
.h-structural { background: #fdecea; color: #9c1616; }
.notes { font-size: 12px; color: #444; }
.empty { font-size: 12px; color: #888; font-style: italic; padding: 8px 0; }
.placeholder-box {
    background: #f5f5f5;
    border: 1px dashed #bbb;
    padding: 10px 14px;
    font-size: 12px;
    color: #666;
    border-radius: 2px;
}
footer {
    margin-top: 40px;
    padding-top: 10px;
    border-top: 1px solid #ddd;
    font-size: 11px;
    color: #888;
}
"""


def _score_class_legacy(score: float) -> str:
    if score >= 4.0: return "score-high"
    if score >= 2.5: return "score-med"
    return "score-low"


def _horizon_tag_legacy(h: str | None) -> str:
    h = (h or "").lower()
    if h == "tactical":   return '<span class="horizon-tag h-tactical">tactical</span>'
    if h == "thematic":   return '<span class="horizon-tag h-thematic">thematic</span>'
    if h == "structural": return '<span class="horizon-tag h-structural">structural</span>'
    return ""


def _build_html_legacy(
    as_of_date:    str,
    regime:        dict,
    p1_carryovers: list[dict],
    new_theses:    list[dict],
    conv_movers:   list[dict],
    structural:    list[dict],
) -> str:
    """Pre-design-system HTML builder. Preserved for --legacy flag."""

    ts = (regime.get("trend_state") or "").lower()
    if ts == "bull":   regime_color = "#d4edda"
    elif ts == "bear": regime_color = "#f8d7da"
    else:              regime_color = "#fff3cd"

    def _score_td(score: float) -> str:
        cls = _score_class_legacy(score)
        return f'<td><span class="{cls}">{score:.2f}</span></td>'

    if p1_carryovers:
        p1_rows = "".join(
            f"<tr><td><b>{_esc(r['ticker'])}</b></td>"
            f"{_score_td(r['anomaly_score'])}"
            f"<td>{_horizon_tag_legacy(r['horizon'])}</td>"
            f"<td class='notes'>{_esc(_clean_notes(r['notes']))[:90]}</td>"
            f"<td>{_esc(r['date'])}</td></tr>"
            for r in p1_carryovers
        )
        p1_html = f"""
<table>
  <tr><th>Ticker</th><th>Score</th><th>Track</th><th>Evidence</th><th>Date</th></tr>
  {p1_rows}
</table>"""
    else:
        p1_html = "<p class='empty'>No active P1 signals in the last 7 days.</p>"

    if new_theses:
        thesis_rows = "".join(
            f"<tr><td><b>{_esc(r['ticker'])}</b></td>"
            f"{_score_td(r['anomaly_score'])}"
            f"<td>{_horizon_tag_legacy(r['horizon'])}</td>"
            f"<td class='notes'>{_esc(_clean_notes(r['notes']))[:110]}</td>"
            f"<td>{_esc(r['date'])}</td></tr>"
            for r in new_theses
        )
        theses_html = f"""
<table>
  <tr><th>Ticker</th><th>Score</th><th>Track</th><th>Thesis summary</th><th>Date</th></tr>
  {thesis_rows}
</table>"""
    else:
        theses_html = "<p class='empty'>No new thematic or structural theses this week.</p>"

    if conv_movers:
        conv_rows = "".join(
            f"<tr><td><b>{_esc(r['ticker'])}</b></td>"
            f"<td>{_esc(r['platform_count'])}</td>"
            f"<td>{_esc(', '.join(str(p) for p in (r['convergence_pairs'] or [])))}</td>"
            f"{_score_td(r['anomaly_score'])}"
            f"<td>{_esc(r['date'])}</td></tr>"
            for r in conv_movers
        )
        conv_html = f"""
<table>
  <tr><th>Ticker</th><th>Platforms</th><th>Platform pairs</th><th>Score</th><th>Date</th></tr>
  {conv_rows}
</table>"""
    else:
        conv_html = "<p class='empty'>No new platform convergence signals this week.</p>"

    regime_posterior_html = """
<div class="placeholder-box">
  <b>Note:</b> Regime-shift posterior quantification (Bayesian update on macro state
  transitions) is scheduled for a future release. Current regime data is sourced from
  the daily market regime classifier. See section 1 for the current label.
</div>"""

    if structural:
        struct_rows = "".join(
            f"<tr><td><b>{_esc(r['ticker'])}</b></td>"
            f"{_score_td(r['anomaly_score'])}"
            f"<td class='notes'>{_esc(_clean_notes(r['notes']))[:110]}</td>"
            f"<td>{_esc(r['date'])}</td></tr>"
            for r in structural
        )
        struct_html = f"""
<table>
  <tr><th>Ticker</th><th>Score</th><th>Structural thesis</th><th>Signal date</th></tr>
  {struct_rows}
</table>"""
    else:
        struct_html = "<p class='empty'>No active structural signals in the 90-day lookback window.</p>"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Weekly Intelligence Brief — {as_of_date}</title>
  <style>{_CSS_LEGACY}</style>
</head>
<body>

<header>
  <h1>Weekly Intelligence Brief</h1>
  <div class="meta">Week ending {as_of_date} &nbsp;|&nbsp; Prepared by internal signal-intelligence layer</div>
</header>

<h2>1. Market Regime</h2>
<div class="regime-box" style="border-left: 4px solid {regime_color};">
  <div class="label">{_esc(regime.get('composite_label', 'N/A'))}</div>
  <div class="sub">
    Trend: <b>{_esc(regime.get('trend_state', 'N/A'))}</b>
    &nbsp;|&nbsp; Vol: <b>{_esc(regime.get('vol_state') or 'N/A')}</b>
    &nbsp;|&nbsp; Macro: <b>{_esc(regime.get('macro_state') or 'N/A')}</b>
  </div>
</div>

<h2>2. Active High-Conviction Signals (Last 7 Days)</h2>
{p1_html}

<h2>3. New Investment Theses This Week</h2>
{theses_html}

<h2>4. Platform Convergence Movers</h2>
<p style="font-size:12px;color:#666;margin-bottom:8px;">
  Companies flagged where meaningful research coverage intersects across multiple
  technology platforms simultaneously. Higher platform count = more compounding thesis.
</p>
{conv_html}

<h2>5. Regime Transition Monitor</h2>
{regime_posterior_html}

<h2>6. Structural Watch (3-Year Horizon)</h2>
<p style="font-size:12px;color:#666;margin-bottom:8px;">
  Long-duration platform theses. These signals represent multi-year investment
  arguments — not near-term trade setups.
</p>
{struct_html}

<footer>
  This document is generated from quantitative signal-intelligence models and is
  intended for internal research purposes only. It does not constitute investment
  advice. All scores are anomaly z-scores, not price targets or expected returns.
  &nbsp;|&nbsp; Generated: {as_of_date}
</footer>

</body>
</html>"""


# ── v2 HTML builder ───────────────────────────────────────────────────────────

def _render_signal_rows(signals: list[dict]) -> str:
    if not signals:
        return ""
    rows = []
    for r in signals:
        score_str = f"{r['anomaly_score']:.2f}" if r.get("anomaly_score") is not None else "N/A"
        notes_str = _esc(_clean_notes(r.get("notes", "")))[:120]
        rows.append(
            f"<tr>"
            f"<td class='col-ticker'>{_esc(r['ticker'])}</td>"
            f"<td>{_priority_tag(r.get('priority'))}</td>"
            f"<td>{_horizon_tag(r.get('horizon'))}</td>"
            f"<td class='col-mono col-right'>{score_str}</td>"
            f"<td>{_esc(r['date'])}</td>"
            f"<td>{notes_str}</td>"
            f"</tr>"
        )
    return "\n".join(rows)


def _render_evidence_cards(cards: list[dict]) -> str:
    """
    Render soma_intel_belief thesis/conviction rows as evidence cards.
    If cards is empty, returns a callout-unavailable block.
    """
    if not cards:
        return (
            '<div class="callout callout-unavailable">'
            "Investment thesis data not available this week. "
            "Thesis-level beliefs are populated as the knowledge layer matures."
            "</div>"
        )
    html_parts = []
    for c in cards:
        tag_label = c.get("predicate", "thesis").title()
        date_str  = (c.get("ts") or "")[:10]
        body      = _esc(_clean_notes(c.get("value", "")))
        source    = _esc(_scrub(c.get("source_id") or "Internal knowledge layer"))
        ticker    = c.get("node_id", "").replace("co_", "")
        html_parts.append(f"""
<article class="evidence-card">
  <header class="evidence-header">
    <span class="evidence-tag">{_esc(tag_label)}</span>
    <time class="evidence-date">{_esc(date_str)}</time>
  </header>
  <p class="evidence-body">{_esc(ticker + ": " if ticker else "")}{body}</p>
  <p class="evidence-source">&#8212; {source}</p>
</article>""")
    return "\n".join(html_parts)


def _render_convergence_table(movers: list[dict]) -> str:
    if not movers:
        return (
            '<div class="callout callout-unavailable">'
            "No platform convergence signals this week."
            "</div>"
        )
    rows = []
    for m in movers:
        score_str = f"{m['anomaly_score']:.2f}" if m.get("anomaly_score") is not None else "N/A"
        pc = m.get("price_change_5d")
        if pc is not None:
            sign     = "+" if pc >= 0 else ""
            chg_str  = f"{sign}{pc:.1f}%"
        else:
            chg_str = "N/A"
        rows.append(
            f"<tr>"
            f"<td class='col-ticker'>{_esc(m['ticker'])}</td>"
            f"<td class='col-mono col-right'>{_esc(str(m.get('platform_count','?')))}</td>"
            f"<td>{_esc(m.get('platforms','?'))}</td>"
            f"<td class='col-mono col-right'>{score_str}</td>"
            f"<td class='col-mono col-right'>{chg_str}</td>"
            f"<td>{_esc(m['date'])}</td>"
            f"</tr>"
        )
    return f"""
<div class="table-wrapper">
<table>
  <thead>
    <tr>
      <th>Ticker</th>
      <th class="col-right">Platforms</th>
      <th>Coverage</th>
      <th class="col-right">Score</th>
      <th class="col-right">5d Price</th>
      <th>Date</th>
    </tr>
  </thead>
  <tbody>
    {"".join(rows)}
  </tbody>
</table>
</div>"""


def _render_structural_cards(cards: list[dict]) -> str:
    if not cards:
        return (
            '<div class="callout callout-unavailable">'
            "No active structural signals in the 90-day lookback window."
            "</div>"
        )
    html_parts = []
    for c in cards:
        ticker    = _esc(c.get("ticker", ""))
        body      = _esc(c.get("body_text", ""))
        date_str  = _esc(c.get("date_str", ""))
        source    = _esc(c.get("source_str", "Internal signal-intelligence layer"))
        prefix    = f"{ticker}: " if ticker else ""
        html_parts.append(f"""
<article class="evidence-card evidence-card--green">
  <header class="evidence-header">
    <span class="evidence-tag">Structural</span>
    <time class="evidence-date">{date_str}</time>
  </header>
  <p class="evidence-body">{prefix}{body}</p>
  <p class="evidence-source">&#8212; {source}</p>
</article>""")
    return "\n".join(html_parts)


def _build_html_v2(
    as_of_date:      str,
    regime:          dict,
    change_label:    str,
    coverage_count:  int,
    signals:         list[dict],
    evidence_cards:  list[dict],
    conv_movers:     list[dict],
    structural_cards: list[dict],
    inline_css:      str = "",
    css_links:       str = "",
) -> str:
    """
    Design-system HTML builder.
    Produces a self-contained brief using DABEIBA Design System v1 tokens and components.
    """
    date_display    = _format_date_display(as_of_date).upper()
    regime_label    = _format_regime_label(regime.get("composite_label") or "N/A")
    confidence      = regime.get("confidence")
    conf_str        = f"{confidence * 100:.1f}%" if confidence is not None else "N/A"
    coverage_str    = f"{coverage_count:,}" if coverage_count else "N/A"

    # CSS block: inline (production) or link tags (dev)
    css_block = f"<style>\n{inline_css}\n</style>" if inline_css else css_links

    # §2 signals table
    sig_rows = _render_signal_rows(signals)
    if sig_rows:
        signals_html = f"""
<div class="table-wrapper">
<table>
  <thead>
    <tr>
      <th>Ticker</th>
      <th>Priority</th>
      <th>Track</th>
      <th class="col-right">Score</th>
      <th>Date</th>
      <th>Notes</th>
    </tr>
  </thead>
  <tbody>
    {sig_rows}
  </tbody>
</table>
</div>"""
    else:
        signals_html = (
            '<div class="callout callout-unavailable">'
            "No active signals in the last 7 days."
            "</div>"
        )

    # §3 evidence cards
    evidence_html = _render_evidence_cards(evidence_cards)

    # §4 convergence
    convergence_html = _render_convergence_table(conv_movers)

    # §6 structural watch
    structural_html = _render_structural_cards(structural_cards)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Intelligence Brief &#8212; Equities &amp; Macro &#183; Week ending {_esc(as_of_date)}</title>
  {css_block}
</head>
<body>

<div class="brief-container">

  <!-- HEADER BAND -->
  <header class="brief-header">
    <p class="eyebrow">WEEK ENDING {_esc(date_display)}</p>
    <h1 class="title">Intelligence Brief &#8212; Equities &amp; Macro</h1>
    <p class="subtitle">Internal research summary &#183; {_esc(coverage_str)} securities covered</p>
  </header>

  <!-- §1 MARKET REGIME -->
  <section class="brief-section">
    <div class="section-header">
      <p class="eyebrow">MARKET REGIME</p>
    </div>
    <div class="stat">
      <p class="stat-value-text">{_esc(regime_label)}</p>
      <p class="stat-label">{_esc(change_label or "")}</p>
      <p class="stat-caption">Composite classification &#183; Confidence {_esc(conf_str)} &#183; As of {_esc(as_of_date)}</p>
    </div>
  </section>

  <!-- §2 HIGH-CONVICTION SIGNALS -->
  <section class="brief-section">
    <div class="section-header">
      <p class="eyebrow">HIGH-CONVICTION SIGNALS</p>
    </div>
    {signals_html}
  </section>

  <!-- §3 NEW INVESTMENT THESES -->
  <section class="brief-section">
    <div class="section-header">
      <p class="eyebrow">NEW INVESTMENT THESES</p>
    </div>
    {evidence_html}
  </section>

  <!-- §4 CONVERGENCE MOVERS -->
  <section class="brief-section">
    <div class="section-header">
      <p class="eyebrow">CONVERGENCE MOVERS</p>
    </div>
    <p class="section-desc">
      Companies where research coverage converges across multiple technology
      platforms simultaneously. Convergence score: 1.0 = perfect alignment, 0 = independence.
    </p>
    {convergence_html}
  </section>

  <!-- §5 REGIME TRANSITION MONITOR -->
  <section class="brief-section">
    <div class="section-header">
      <p class="eyebrow">REGIME TRANSITION MONITOR</p>
    </div>
    <div class="callout callout-unavailable">
      Regime-shift posterior quantification (Bayesian update on macro state transitions)
      is scheduled for a future release. Current regime is available in section 1 above.
    </div>
  </section>

  <!-- §6 STRUCTURAL WATCH -->
  <section class="brief-section">
    <div class="section-header">
      <p class="eyebrow">STRUCTURAL WATCH</p>
    </div>
    <p class="section-desc">
      Long-duration platform theses. These signals represent multi-year investment
      arguments, not near-term trade setups.
    </p>
    {structural_html}
  </section>

  <!-- FOOTER -->
  <footer class="brief-footer">
    <p class="brief-footer-meta">
      <strong>Client-facing &#183; Do not redistribute</strong>
    </p>
    <p class="brief-footer-meta">
      Generated: {_esc(as_of_date)} &#183; Internal signal-intelligence layer &#183;
      All scores are anomaly z-scores, not price targets or expected returns.
    </p>
    <ul class="brief-cite-list">
      <li>Market regime classifier &#183; {_esc(as_of_date)}</li>
      <li>Signal-intelligence layer &#183; {_esc(as_of_date)}</li>
      <li>Price history feed &#183; {_esc(as_of_date)}</li>
    </ul>
  </footer>

</div><!-- /brief-container -->

</body>
</html>"""


# ── Dispatcher ────────────────────────────────────────────────────────────────

def build_html(
    as_of_date:      str,
    regime:          dict,
    p1_carryovers:   list[dict],
    new_theses:      list[dict],
    conv_movers:     list[dict],
    structural:      list[dict],
    legacy:          bool = False,
    # v2-only kwargs
    change_label:    str = "",
    coverage_count:  int = 0,
    signals:         list[dict] | None = None,
    evidence_cards:  list[dict] | None = None,
    conv_with_price: list[dict] | None = None,
    structural_cards: list[dict] | None = None,
    inline_css:      str = "",
    css_links:       str = "",
) -> str:
    if legacy:
        return _build_html_legacy(
            as_of_date, regime, p1_carryovers, new_theses, conv_movers, structural
        )
    return _build_html_v2(
        as_of_date      = as_of_date,
        regime          = regime,
        change_label    = change_label,
        coverage_count  = coverage_count,
        signals         = signals or [],
        evidence_cards  = evidence_cards or [],
        conv_movers     = conv_with_price or [],
        structural_cards = structural_cards or [],
        inline_css      = inline_css,
        css_links       = css_links,
    )


# ── Main entry points ─────────────────────────────────────────────────────────

def generate_brief(
    as_of_date:  str,
    store:       IntelStore,
    legacy:      bool = False,
    inline_css:  bool = True,
    output_path: Path | None = None,
) -> str:
    """
    Gather data from DB and build the full HTML brief.
    Returns HTML string.
    """
    # Shared queries (used by both paths)
    regime       = _regime_block(store, as_of_date)
    p1_c         = _p1_carryovers(store, as_of_date)
    theses_legacy = _new_theses_legacy(store, as_of_date)
    conv_legacy  = _convergence_movers(store, as_of_date)
    struct_legacy = _structural_watch(store, as_of_date)

    if legacy:
        return _build_html_legacy(
            as_of_date, regime, p1_c, theses_legacy, conv_legacy, struct_legacy
        )

    # v2 queries
    change_label    = _regime_change_label(store, as_of_date)
    coverage_count  = _coverage_count(store)
    signals         = _top_signals_dedup(store, as_of_date)
    ev_cards        = _evidence_cards(store, as_of_date)
    conv_price      = _convergence_with_price(store, as_of_date)
    struct_cards    = _structural_watch_cards(store, as_of_date)

    # CSS
    if inline_css:
        css_content = _inline_css(_DABEIBA_ROOT)
        css_links   = ""
    else:
        css_content = ""
        out = output_path or (OUTPUT_DIR / f"weekly_brief_{as_of_date}.html")
        css_links = _css_link_tags(_DABEIBA_ROOT, out)

    html = _build_html_v2(
        as_of_date       = as_of_date,
        regime           = regime,
        change_label     = change_label,
        coverage_count   = coverage_count,
        signals          = signals,
        evidence_cards   = ev_cards,
        conv_movers      = conv_price,
        structural_cards = struct_cards,
        inline_css       = css_content,
        css_links        = css_links,
    )

    # QA: expand acronyms on first use
    html = _expand_acronyms_once(html)
    return html


def write_brief(as_of_date: str, html: str) -> Path:
    """Write HTML to OUTPUT_DIR. Returns the output path."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"weekly_brief_{as_of_date}.html"
    out_path.write_text(html, encoding="utf-8")
    return out_path


def run_weekly_brief(
    as_of_date: str | None = None,
    force:      bool = False,
    legacy:     bool = False,
) -> dict:
    """
    Entry point for run_day.py step_weekly_brief_friday().
    Runs only on Fridays unless force=True.
    Returns summary dict: {skipped, output_path, sections, legacy}.
    """
    today = as_of_date or date.today().isoformat()
    d     = date.fromisoformat(today)

    if not force and d.weekday() != 4:   # 4 = Friday
        return {"skipped": True, "reason": "not_friday", "output_path": None}

    with IntelStore(db_path=DB_PATH) as store:
        html = generate_brief(today, store, legacy=legacy)

    out_path = write_brief(today, html)
    return {
        "skipped":     False,
        "output_path": str(out_path),
        "sections":    6,
        "date":        today,
        "legacy":      legacy,
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

def _main() -> None:
    parser = argparse.ArgumentParser(
        description="Weekly intelligence brief generator — produces Friday HTML"
    )
    parser.add_argument("--date",   default=None, metavar="YYYY-MM-DD",
                        help="Date to generate for (default: today)")
    parser.add_argument("--force",  action="store_true",
                        help="Generate even if today is not Friday")
    parser.add_argument("--apply",  action="store_true",
                        help="Alias for --force")
    parser.add_argument("--legacy", action="store_true",
                        help="Use pre-design-system builder (2-cycle deprecation window)")
    parser.add_argument("--no-inline-css", action="store_true", dest="no_inline",
                        help="Link CSS externally instead of inlining (dev mode)")
    parser.add_argument("--db",     default=str(DB_PATH))
    parser.add_argument("--out",    default=str(OUTPUT_DIR),
                        help="Output directory (default: cipher/outputs/)")
    args = parser.parse_args()

    db_path    = Path(args.db)
    output_dir = Path(args.out)
    today      = args.date or date.today().isoformat()
    d          = date.fromisoformat(today)
    force      = args.force or args.apply

    if not force and d.weekday() != 4:
        print(f"Skipping — {today} is not a Friday. Use --force to override.")
        return

    with IntelStore(db_path=db_path) as store:
        out_path = output_dir / f"weekly_brief_{today}.html"
        html = generate_brief(
            today,
            store,
            legacy      = args.legacy,
            inline_css  = not args.no_inline,
            output_path = out_path,
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")

    size_kb = len(html.encode("utf-8")) / 1024
    mode    = "legacy" if args.legacy else "v2 (design system)"
    print(f"Brief written: {out_path}")
    print(f"Mode: {mode} | CSS: {'inline' if not args.no_inline else 'external link'}")
    print(f"Sections: 6 | Size: {size_kb:.1f} KB")


if __name__ == "__main__":
    _main()
