#!/usr/bin/env python3
"""
prediction_backtest.py — Weekly Prediction Backtest for DABEIBA

Runs as a scheduled job (Sunday 8AM) to check expired/expiring predictions
and generate a resolution report. For clear-cut predictions (price targets,
binary events), attempts auto-resolution. Flags ambiguous cases for human review.

Usage:
  # Full backtest run (what the scheduled job calls)
  python3 prediction_backtest.py run

  # Dry run — show what would be resolved without making changes
  python3 prediction_backtest.py dry-run

  # Generate a markdown scorecard report
  python3 prediction_backtest.py report --output scorecard.md

The script does NOT auto-resolve predictions. It produces a resolution
recommendation that the user confirms. This prevents bad auto-resolutions.

Output: Markdown report with:
  - Overdue predictions needing resolution
  - Expiring-soon predictions needing attention
  - Resolution recommendations for clear-cut cases
  - Speaker accuracy scorecard
  - Tier change suggestions
"""

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

def _resolve_dabeiba_root() -> Path:
    """3-tier fallback: $DABEIBA_ROOT -> ~/Desktop/DABEIBA -> walk up from __file__."""
    env = os.environ.get("DABEIBA_ROOT")
    if env:
        return Path(env)
    default_home = Path.home() / "Desktop" / "DABEIBA"
    if default_home.exists():
        return default_home
    here = Path(__file__).resolve()
    for parent in here.parents:
        if parent.name == "DABEIBA":
            return parent
    return default_home


_DABEIBA = _resolve_dabeiba_root()
# Canonical SOMA DB (migrated from legacy shared/soma/soma.db on 2026-04-18)
# Overridable via SOMA_DB_PATH env var for testing.
DB_PATH = Path(os.environ.get("SOMA_DB_PATH", str(_DABEIBA / "shared" / "soma" / "data" / "soma.db")))
REPORT_DIR = _DABEIBA / "shared" / "soma" / "reports"


def get_conn():
    if not DB_PATH.exists():
        print(f"Error: soma.db not found at {DB_PATH}", file=sys.stderr)
        sys.exit(1)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def get_overdue(conn):
    """Predictions past their expiry date that are still OPEN."""
    today = datetime.now().strftime("%Y-%m-%d")
    return conn.execute("""
        SELECT * FROM predictions
        WHERE status = 'OPEN' AND expiry_date IS NOT NULL AND expiry_date <= ?
        ORDER BY expiry_date ASC
    """, (today,)).fetchall()


def get_expiring_soon(conn, days=14):
    """Predictions expiring within N days."""
    today = datetime.now().strftime("%Y-%m-%d")
    cutoff = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
    return conn.execute("""
        SELECT * FROM predictions
        WHERE status = 'OPEN' AND expiry_date IS NOT NULL
          AND expiry_date > ? AND expiry_date <= ?
        ORDER BY expiry_date ASC
    """, (today, cutoff)).fetchall()


def get_scorecard(conn):
    """Speaker accuracy data."""
    return conn.execute("""
        SELECT * FROM speaker_accuracy ORDER BY accuracy_rate DESC NULLS LAST
    """).fetchall()


def get_stats(conn):
    """Overall prediction stats."""
    total = conn.execute("SELECT COUNT(*) FROM predictions").fetchone()[0]
    by_status = {}
    for status in ('OPEN', 'TRUE', 'FALSE', 'UNCLEAR', 'EXPIRED'):
        by_status[status] = conn.execute(
            "SELECT COUNT(*) FROM predictions WHERE status = ?", (status,)
        ).fetchone()[0]
    return {"total": total, **by_status}


def classify_prediction(pred):
    """
    Classify how easily a prediction can be resolved.

    Returns:
      - "auto_price": price target for a known asset → can check via web
      - "auto_binary": binary event (happened or not) → can check via web
      - "manual": requires human judgment
    """
    claim = (pred['claim'] or '').lower()
    metric = (pred['target_metric'] or '').lower()
    target = (pred['target_value'] or '').lower()

    # Price target predictions
    price_keywords = ['price', 'btc', 'eth', 'sol', 'tsla', 'gold', 'oil', 'spy', 'qqq']
    if any(kw in metric for kw in price_keywords) or any(kw in claim for kw in price_keywords):
        if '$' in target or '$' in claim:
            return "auto_price"

    # Binary event predictions
    binary_keywords = ['rate cut', 'rate hike', 'qe', 'reopens', 'closes', 'launches',
                       'resigns', 'elected', 'approved', 'rejected', 'passes', 'fails']
    if any(kw in claim for kw in binary_keywords):
        return "auto_binary"

    return "manual"


def generate_report(conn, dry_run=False):
    """Generate the full backtest report."""
    now = datetime.now()
    overdue = get_overdue(conn)
    expiring = get_expiring_soon(conn, days=14)
    scorecard = get_scorecard(conn)
    stats = get_stats(conn)

    lines = [
        f"# Prediction Backtest Report",
        f"",
        f"**Generated:** {now.strftime('%Y-%m-%d %H:%M')}",
        f"**Mode:** {'DRY RUN' if dry_run else 'LIVE'}",
        f"",
        f"---",
        f"",
        f"## Summary",
        f"",
        f"| Metric | Count |",
        f"|--------|-------|",
        f"| Total predictions | {stats['total']} |",
        f"| Open | {stats['OPEN']} |",
        f"| Resolved TRUE | {stats['TRUE']} |",
        f"| Resolved FALSE | {stats['FALSE']} |",
        f"| Unclear/Expired | {stats['UNCLEAR'] + stats['EXPIRED']} |",
        f"| **Overdue** | **{len(overdue)}** |",
        f"| Expiring (14 days) | {len(expiring)} |",
        f"",
    ]

    # Overdue section
    if overdue:
        lines.extend([
            f"## Overdue Predictions ({len(overdue)})",
            f"",
            f"These predictions have passed their expiry date and need resolution.",
            f"",
            f"| ID | Speaker | Claim | Direction | Expiry | Classification | Action |",
            f"|---|---------|-------|-----------|--------|---------------|--------|",
        ])
        for p in overdue:
            cls = classify_prediction(p)
            action = {
                "auto_price": "Web search for current price → resolve",
                "auto_binary": "Web search for event status → resolve",
                "manual": "Human review required",
            }[cls]
            lines.append(
                f"| {p['id']} | {p['speaker']} | {p['claim'][:50]}{'...' if len(p['claim']) > 50 else ''} "
                f"| {p['direction'] or '—'} | {p['expiry_date']} | {cls} | {action} |"
            )
        lines.append("")

        # Generate resolution commands for overdue
        lines.extend([
            f"### Resolution Commands",
            f"",
            f"Copy-paste these after verifying each prediction's outcome:",
            f"",
            f"```bash",
        ])
        for p in overdue:
            lines.append(
                f"# #{p['id']}: {p['claim'][:60]}"
            )
            lines.append(
                f"python3 ~/Desktop/DABEIBA/shared/tools/prediction_log.py resolve {p['id']} "
                f"--outcome TRUE  --notes \"VERIFY: ...\""
            )
            lines.append(
                f"# OR: --outcome FALSE --notes \"...\"  |  --outcome UNCLEAR --notes \"...\""
            )
            lines.append("")
        lines.append("```")
        lines.append("")
    else:
        lines.extend([
            "## Overdue Predictions",
            "",
            "None — all predictions within their horizon.",
            "",
        ])

    # Expiring soon section
    if expiring:
        lines.extend([
            f"## Expiring Soon ({len(expiring)} within 14 days)",
            f"",
            f"| ID | Speaker | Claim | Direction | Expiry | Days Left |",
            f"|---|---------|-------|-----------|--------|-----------|",
        ])
        for p in expiring:
            days_left = (datetime.strptime(p['expiry_date'], "%Y-%m-%d") - now).days
            lines.append(
                f"| {p['id']} | {p['speaker']} | {p['claim'][:50]}{'...' if len(p['claim']) > 50 else ''} "
                f"| {p['direction'] or '—'} | {p['expiry_date']} | {days_left} |"
            )
        lines.append("")

    # Scorecard section
    if scorecard:
        lines.extend([
            f"## Speaker Accuracy Scorecard",
            f"",
            f"| Speaker | Tier | Total | Correct | Incorrect | Unclear | Rate | Suggestion |",
            f"|---------|------|-------|---------|-----------|---------|------|------------|",
        ])
        for s in scorecard:
            rate = f"{s['accuracy_rate']:.0%}" if s['accuracy_rate'] is not None else "—"
            suggestion = s['tier_suggestion'] or "—"
            lines.append(
                f"| {s['speaker']} | {s['current_tier'] or 'T2'} | {s['total_predictions']} "
                f"| {s['correct']} | {s['incorrect']} | {s['unclear']} | {rate} | {suggestion} |"
            )
        lines.append("")

    # Tier change suggestions
    tier_changes = [s for s in scorecard if s['tier_suggestion']]
    if tier_changes:
        lines.extend([
            f"## Tier Change Recommendations",
            f"",
        ])
        for s in tier_changes:
            lines.append(
                f"- **{s['speaker']}**: {s['tier_suggestion']} "
                f"(accuracy: {s['accuracy_rate']:.0%} over {s['correct'] + s['incorrect']} resolved)"
            )
        lines.append("")
        lines.extend([
            f"To apply tier changes, update the speaker's wiki article:",
            f"```bash",
            f"python3 ~/Desktop/DABEIBA/shared/tools/transcript_index.py update \"SPEAKER\" --tier T1",
            f"```",
            f"",
        ])

    lines.extend([
        f"---",
        f"",
        f"*Report generated by prediction_backtest.py. Review before acting on any resolution.*",
    ])

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="DABEIBA Prediction Backtest")
    sub = parser.add_subparsers(dest="command")

    # run
    sub.add_parser("run", help="Full backtest run — generates report")

    # dry-run
    sub.add_parser("dry-run", help="Preview without changes")

    # report
    rp = sub.add_parser("report", help="Generate markdown scorecard report")
    rp.add_argument("--output", help="Output path (default: reports/prediction_backtest_YYYYMMDD.md)")

    args = parser.parse_args()

    if args.command in ("run", "dry-run", "report"):
        conn = get_conn()
        dry_run = args.command == "dry-run"
        report = generate_report(conn, dry_run=dry_run)

        # Determine output path
        if args.command == "report" and args.output:
            out_path = Path(args.output)
        else:
            REPORT_DIR.mkdir(parents=True, exist_ok=True)
            date_str = datetime.now().strftime("%Y%m%d")
            out_path = REPORT_DIR / f"prediction_backtest_{date_str}.md"

        out_path.write_text(report)
        print(f"Report written to: {out_path}", file=sys.stderr)

        # Also print to stdout for scheduled task capture
        print(report)

        conn.close()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
