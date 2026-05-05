"""
SOMA-INTEL P6.6 — Weekly Intelligence Brief

Generates a self-contained HTML brief every Friday covering:
  §1  Market regime
  §2  Top 5 P1 carry-overs (active P1 signals from last 7 days)
  §3  New theses (thematic + structural signals from this week)
  §4  Convergence movers (platform convergence signals)
  §5  Regime-shift posterior (placeholder — §I.5 TBD)
  §6  Structural watch (all active structural signals)

Output: <dabeiba_root>/cipher/outputs/weekly_brief_YYYY-MM-DD.html

Rules (hard):
  - Zero internal codenames (DABEIBA / SOMA / ORACLE / MANTIS / CIPHER /
    RAPTOR / TITAN / COBALT / SPECTRE / PRISM / DOCTRINE / HORIZON …)
  - Zero emojis
  - Evidence cited where available
  - Plain prose sections — no fluff

Usage:
    python3 soma/intel/weekly_brief.py                  # generate for today
    python3 soma/intel/weekly_brief.py --date 2026-05-09 # specific date
    python3 soma/intel/weekly_brief.py --force          # write even if not Friday
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

OUTPUT_DIR = _DABEIBA_ROOT / "cipher" / "outputs"

BRIEF_LOOKBACK_DAYS = 7          # signals window for "new this week"
MAX_P1_CARRYOVERS   = 5
MAX_NEW_THESES      = 10
MAX_CONVERGENCE     = 8
MAX_STRUCTURAL      = 8


# ── Internal codename scrub ───────────────────────────────────────────────────
# These must never appear in client-facing output.
_FORBIDDEN_CODENAMES = {
    "DABEIBA", "SOMA", "ORACLE", "MANTIS", "CIPHER", "RAPTOR",
    "TITAN", "COBALT", "SPECTRE", "PRISM", "DOCTRINE", "HORIZON",
    "BEACON", "VECTOR", "FORGE", "DELTA", "SENTINEL", "MUSKONOMY",
    "DOSSIER", "INTEL", "soma_intel", "soma-intel",
}


def _scrub(text: str) -> str:
    """Replace forbidden codenames with neutral placeholders."""
    for name in _FORBIDDEN_CODENAMES:
        text = text.replace(name, "[internal]")
        text = text.replace(name.lower(), "[internal]")
    return text


def _esc(text: str) -> str:
    return escape(_scrub(str(text)))


# ── Data queries ──────────────────────────────────────────────────────────────

def _regime_block(store: IntelStore, as_of_date: str) -> dict:
    """Fetch current regime row."""
    try:
        row = store._c.execute(
            "SELECT composite_label, trend_state, vol_state, macro_state "
            "FROM soma_intel_regime WHERE date <= ? ORDER BY date DESC LIMIT 1",
            (as_of_date,),
        ).fetchone()
        if row:
            return dict(row)
    except Exception:
        pass
    return {"composite_label": "N/A", "trend_state": "N/A",
            "vol_state": "N/A", "macro_state": "N/A"}


def _p1_carryovers(store: IntelStore, as_of_date: str) -> list[dict]:
    """Active P1 signals from last 7 days."""
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
            (since, as_of_date, MAX_P1_CARRYOVERS),
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []


def _new_theses(store: IntelStore, as_of_date: str) -> list[dict]:
    """Thematic + structural signals written this week."""
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
            (since, as_of_date, MAX_NEW_THESES),
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []


def _convergence_movers(store: IntelStore, as_of_date: str) -> list[dict]:
    """Platform convergence signals this week."""
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
            row = dict(r)
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
    """All active structural signals (multi-week lookback)."""
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
        return [dict(r) for r in rows]
    except Exception:
        return []


# ── HTML builder ──────────────────────────────────────────────────────────────

_CSS = """
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


def _score_class(score: float) -> str:
    if score >= 4.0: return "score-high"
    if score >= 2.5: return "score-med"
    return "score-low"


def _horizon_tag(h: str | None) -> str:
    h = (h or "").lower()
    if h == "tactical":   return '<span class="horizon-tag h-tactical">tactical</span>'
    if h == "thematic":   return '<span class="horizon-tag h-thematic">thematic</span>'
    if h == "structural": return '<span class="horizon-tag h-structural">structural</span>'
    return ""


def _clean_notes(notes: str | None) -> str:
    """Strip internal prefixes and scrub codenames from notes for display."""
    n = _scrub(notes or "")
    # Remove internal tags like "signal_propagator: ", "exploration_channel"
    for prefix in ("signal_propagator:", "exploration_channel", "[internal]"):
        n = n.replace(prefix, "")
    return n.strip("; ").strip()


def build_html(
    as_of_date:   str,
    regime:       dict,
    p1_carryovers: list[dict],
    new_theses:   list[dict],
    conv_movers:  list[dict],
    structural:   list[dict],
) -> str:
    """Assemble the complete HTML brief. Returns HTML string."""

    # ── Regime color hint
    ts = (regime.get("trend_state") or "").lower()
    if ts == "bull":   regime_color = "#d4edda"
    elif ts == "bear": regime_color = "#f8d7da"
    else:              regime_color = "#fff3cd"

    def _score_td(score: float) -> str:
        cls = _score_class(score)
        return f'<td><span class="{cls}">{score:.2f}</span></td>'

    # ── §2 P1 carry-overs table
    if p1_carryovers:
        p1_rows = "".join(
            f"<tr><td><b>{_esc(r['ticker'])}</b></td>"
            f"{_score_td(r['anomaly_score'])}"
            f"<td>{_horizon_tag(r['horizon'])}</td>"
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

    # ── §3 New theses table
    if new_theses:
        thesis_rows = "".join(
            f"<tr><td><b>{_esc(r['ticker'])}</b></td>"
            f"{_score_td(r['anomaly_score'])}"
            f"<td>{_horizon_tag(r['horizon'])}</td>"
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

    # ── §4 Convergence movers
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

    # ── §5 Regime-shift posterior (placeholder)
    regime_posterior_html = """
<div class="placeholder-box">
  <b>Note:</b> Regime-shift posterior quantification (Bayesian update on macro state
  transitions) is scheduled for a future release. Current regime data is sourced from
  the daily market regime classifier. See section 1 for the current label.
</div>"""

    # ── §6 Structural watch table
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

    # ── Assemble full document
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Weekly Intelligence Brief — {as_of_date}</title>
  <style>{_CSS}</style>
</head>
<body>

<header>
  <h1>Weekly Intelligence Brief</h1>
  <div class="meta">Week ending {as_of_date} &nbsp;|&nbsp; Prepared by internal signal-intelligence layer</div>
</header>

<!-- §1 Regime -->
<h2>1. Market Regime</h2>
<div class="regime-box" style="border-left: 4px solid; border-left-color: {regime_color};">
  <div class="label">{_esc(regime.get('composite_label', 'N/A'))}</div>
  <div class="sub">
    Trend: <b>{_esc(regime.get('trend_state', 'N/A'))}</b>
    &nbsp;|&nbsp; Vol: <b>{_esc(regime.get('vol_state') or 'N/A')}</b>
    &nbsp;|&nbsp; Macro: <b>{_esc(regime.get('macro_state') or 'N/A')}</b>
  </div>
</div>

<!-- §2 P1 carry-overs -->
<h2>2. Active High-Conviction Signals (Last 7 Days)</h2>
{p1_html}

<!-- §3 New theses -->
<h2>3. New Investment Theses This Week</h2>
{theses_html}

<!-- §4 Convergence movers -->
<h2>4. Platform Convergence Movers</h2>
<p style="font-size:12px;color:#666;margin-bottom:8px;">
  Companies flagged where meaningful research coverage intersects across multiple
  technology platforms simultaneously. Higher platform count = more compounding thesis.
</p>
{conv_html}

<!-- §5 Regime-shift posterior -->
<h2>5. Regime Transition Monitor</h2>
{regime_posterior_html}

<!-- §6 Structural watch -->
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


# ── Main ──────────────────────────────────────────────────────────────────────

def generate_brief(as_of_date: str, store: IntelStore) -> str:
    """Gather data and build the HTML brief. Returns HTML string."""
    regime       = _regime_block(store, as_of_date)
    p1_c         = _p1_carryovers(store, as_of_date)
    theses       = _new_theses(store, as_of_date)
    conv         = _convergence_movers(store, as_of_date)
    structural   = _structural_watch(store, as_of_date)
    return build_html(as_of_date, regime, p1_c, theses, conv, structural)


def write_brief(as_of_date: str, html: str) -> Path:
    """Write HTML to OUTPUT_DIR. Returns the output path."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"weekly_brief_{as_of_date}.html"
    out_path.write_text(html, encoding="utf-8")
    return out_path


def run_weekly_brief(as_of_date: str | None = None, force: bool = False) -> dict:
    """
    Entry point for run_day.py step_weekly_brief_friday().

    Runs only on Fridays unless force=True.
    Returns summary dict: {skipped, output_path, sections}.
    """
    today = as_of_date or date.today().isoformat()
    d     = date.fromisoformat(today)

    if not force and d.weekday() != 4:   # 4 = Friday
        return {"skipped": True, "reason": "not_friday", "output_path": None}

    with IntelStore(db_path=DB_PATH) as store:
        html = generate_brief(today, store)

    out_path = write_brief(today, html)
    return {
        "skipped":     False,
        "output_path": str(out_path),
        "sections":    6,
        "date":        today,
    }


def _main() -> None:
    parser = argparse.ArgumentParser(
        description="SOMA-INTEL weekly brief generator — produces Friday HTML"
    )
    parser.add_argument("--date",  default=None, metavar="YYYY-MM-DD",
                        help="Date to generate for (default: today)")
    parser.add_argument("--force", action="store_true",
                        help="Generate even if today is not Friday")
    parser.add_argument("--db",    default=str(DB_PATH))
    parser.add_argument("--out",   default=str(OUTPUT_DIR),
                        help="Output directory (default: cipher/outputs/)")
    args = parser.parse_args()

    # Allow CLI override of DB and output path
    db_path    = Path(args.db)
    output_dir = Path(args.out)

    today = args.date or date.today().isoformat()
    d     = date.fromisoformat(today)

    if not args.force and d.weekday() != 4:
        print(f"Skipping — {today} is not a Friday. Use --force to override.")
        return

    with IntelStore(db_path=db_path) as store:
        html = generate_brief(today, store)

    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"weekly_brief_{today}.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"Brief written to: {out_path}")
    print(f"Sections: 6 (regime, P1 carry-overs, new theses, convergence, "
          f"regime posterior, structural watch)")


if __name__ == "__main__":
    _main()
