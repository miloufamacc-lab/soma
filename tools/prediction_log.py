#!/usr/bin/env python3
"""
prediction_log.py — DABEIBA Prediction Ledger

Logs forward-looking claims from transcript analysis, tracks their expiry,
and maintains speaker accuracy scores over time.

Usage:
  python3 prediction_log.py add "BTC to $100K" --speaker "Mallers" --tier T2 \
      --horizon "6mo" --direction BULLISH --metric "BTC price" --target "$100K" \
      --confidence 0.60 --source "jm-ep113"

  python3 prediction_log.py pending              # open predictions
  python3 prediction_log.py expiring [days=7]    # expiring within N days
  python3 prediction_log.py resolve <id> --outcome TRUE|FALSE|UNCLEAR --notes "..."
  python3 prediction_log.py scorecard             # speaker accuracy table
  python3 prediction_log.py history [--speaker X] # full history
  python3 prediction_log.py stats                 # summary statistics
"""

import argparse
import os
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

# DB location — same soma.db used by SOMA module
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


def get_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn):
    """Create prediction tables if they don't exist."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            claim TEXT NOT NULL,
            speaker TEXT NOT NULL,
            speaker_tier TEXT DEFAULT 'T2',
            source_transcript TEXT,
            source_date TEXT,
            prediction_horizon TEXT,
            expiry_date TEXT,
            direction TEXT CHECK(direction IN ('BULLISH', 'BEARISH', 'NEUTRAL')),
            target_metric TEXT,
            target_value TEXT,
            confidence REAL CHECK(confidence >= 0.0 AND confidence <= 1.0),
            status TEXT DEFAULT 'OPEN' CHECK(status IN ('OPEN', 'TRUE', 'FALSE', 'UNCLEAR', 'EXPIRED')),
            resolution_date TEXT,
            resolution_notes TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS speaker_accuracy (
            speaker TEXT PRIMARY KEY,
            total_predictions INTEGER DEFAULT 0,
            correct INTEGER DEFAULT 0,
            incorrect INTEGER DEFAULT 0,
            unclear INTEGER DEFAULT 0,
            accuracy_rate REAL,
            current_tier TEXT DEFAULT 'T2',
            tier_suggestion TEXT,
            last_updated TEXT DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_predictions_status ON predictions(status);
        CREATE INDEX IF NOT EXISTS idx_predictions_speaker ON predictions(speaker);
        CREATE INDEX IF NOT EXISTS idx_predictions_expiry ON predictions(expiry_date);
    """)
    conn.commit()


def parse_horizon(horizon_str: str, base_date: str = None) -> str:
    """Convert horizon string to expiry date. E.g., '6mo' → 6 months from base."""
    base = datetime.strptime(base_date, "%Y-%m-%d") if base_date else datetime.now()

    h = horizon_str.lower().strip()
    if h.endswith("mo"):
        months = int(h[:-2])
        # Approximate: 30 days per month
        expiry = base + timedelta(days=months * 30)
    elif h.endswith("wk") or h.endswith("w"):
        weeks = int(h.rstrip("wk").rstrip("w"))
        expiry = base + timedelta(weeks=weeks)
    elif h.endswith("d"):
        days = int(h[:-1])
        expiry = base + timedelta(days=days)
    elif h.endswith("yr") or h.endswith("y"):
        years = int(h.rstrip("yr").rstrip("y"))
        expiry = base + timedelta(days=years * 365)
    elif "-" in h:
        # Direct date: "2026-10-15"
        expiry = datetime.strptime(h, "%Y-%m-%d")
    else:
        # Default to 6 months
        expiry = base + timedelta(days=180)

    return expiry.strftime("%Y-%m-%d")


def cmd_add(args):
    conn = get_conn()
    init_db(conn)

    source_date = args.source_date or datetime.now().strftime("%Y-%m-%d")
    expiry = parse_horizon(args.horizon, source_date) if args.horizon else None

    conn.execute("""
        INSERT INTO predictions (claim, speaker, speaker_tier, source_transcript,
            source_date, prediction_horizon, expiry_date, direction,
            target_metric, target_value, confidence)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        args.claim, args.speaker, args.tier or "T2", args.source,
        source_date, args.horizon, expiry, args.direction,
        args.metric, args.target, args.confidence
    ))
    conn.commit()

    pid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    print(f"Prediction #{pid} logged: {args.claim}")
    print(f"  Speaker: {args.speaker} ({args.tier or 'T2'}) | Direction: {args.direction}")
    print(f"  Horizon: {args.horizon} → Expiry: {expiry}")
    print(f"  Confidence: {args.confidence}")
    conn.close()


def cmd_pending(args):
    conn = get_conn()
    init_db(conn)

    rows = conn.execute("""
        SELECT id, claim, speaker, speaker_tier, direction, confidence,
               expiry_date, source_transcript
        FROM predictions WHERE status = 'OPEN'
        ORDER BY expiry_date ASC
    """).fetchall()

    if not rows:
        print("No open predictions.")
        return

    print(f"{'ID':>4} {'Speaker':<15} {'Dir':<8} {'Conf':>5} {'Expiry':<12} {'Claim'}")
    print("-" * 90)
    for r in rows:
        exp = r['expiry_date'] or '—'
        print(f"{r['id']:>4} {r['speaker']:<15} {r['direction'] or '—':<8} {r['confidence'] or 0:.2f} {exp:<12} {r['claim'][:50]}")

    print(f"\n{len(rows)} open prediction(s)")
    conn.close()


def cmd_expiring(args):
    conn = get_conn()
    init_db(conn)

    days = args.days or 7
    cutoff = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
    today = datetime.now().strftime("%Y-%m-%d")

    rows = conn.execute("""
        SELECT id, claim, speaker, direction, confidence, expiry_date, source_transcript
        FROM predictions
        WHERE status = 'OPEN' AND expiry_date IS NOT NULL AND expiry_date <= ?
        ORDER BY expiry_date ASC
    """, (cutoff,)).fetchall()

    if not rows:
        print(f"No predictions expiring within {days} days.")
        return

    # Separate expired vs upcoming
    expired = [r for r in rows if r['expiry_date'] <= today]
    upcoming = [r for r in rows if r['expiry_date'] > today]

    if expired:
        print(f"OVERDUE ({len(expired)}):")
        for r in expired:
            print(f"  #{r['id']} [{r['expiry_date']}] {r['speaker']}: {r['claim'][:60]}")

    if upcoming:
        print(f"\nExpiring within {days} days ({len(upcoming)}):")
        for r in upcoming:
            print(f"  #{r['id']} [{r['expiry_date']}] {r['speaker']}: {r['claim'][:60]}")

    conn.close()


def cmd_resolve(args):
    conn = get_conn()
    init_db(conn)

    outcome = args.outcome.upper()
    if outcome not in ('TRUE', 'FALSE', 'UNCLEAR', 'EXPIRED'):
        print(f"Invalid outcome: {outcome}. Use TRUE, FALSE, UNCLEAR, or EXPIRED.")
        sys.exit(1)

    # Get the prediction first
    pred = conn.execute("SELECT * FROM predictions WHERE id = ?", (args.id,)).fetchone()
    if not pred:
        print(f"Prediction #{args.id} not found.")
        sys.exit(1)

    if pred['status'] != 'OPEN':
        print(f"Prediction #{args.id} already resolved: {pred['status']}")
        sys.exit(1)

    now = datetime.now().strftime("%Y-%m-%d")
    conn.execute("""
        UPDATE predictions SET status = ?, resolution_date = ?, resolution_notes = ?
        WHERE id = ?
    """, (outcome, now, args.notes, args.id))

    # Update speaker accuracy
    speaker = pred['speaker']
    existing = conn.execute("SELECT * FROM speaker_accuracy WHERE speaker = ?", (speaker,)).fetchone()

    if existing:
        total = existing['total_predictions'] + 1
        correct = existing['correct'] + (1 if outcome == 'TRUE' else 0)
        incorrect = existing['incorrect'] + (1 if outcome == 'FALSE' else 0)
        unclear = existing['unclear'] + (1 if outcome in ('UNCLEAR', 'EXPIRED') else 0)
        resolved = correct + incorrect
        rate = correct / resolved if resolved > 0 else None

        # Tier suggestion based on accuracy
        suggestion = None
        if resolved >= 5:
            if rate and rate > 0.70:
                suggestion = "UPGRADE to T1" if existing['current_tier'] != 'T1' else None
            elif rate and rate < 0.30:
                suggestion = "DOWNGRADE to T3" if existing['current_tier'] != 'T3' else None

        conn.execute("""
            UPDATE speaker_accuracy
            SET total_predictions = ?, correct = ?, incorrect = ?, unclear = ?,
                accuracy_rate = ?, tier_suggestion = ?, last_updated = ?
            WHERE speaker = ?
        """, (total, correct, incorrect, unclear, rate, suggestion, now, speaker))
    else:
        correct = 1 if outcome == 'TRUE' else 0
        incorrect = 1 if outcome == 'FALSE' else 0
        unclear = 1 if outcome in ('UNCLEAR', 'EXPIRED') else 0
        resolved = correct + incorrect
        rate = correct / resolved if resolved > 0 else None

        conn.execute("""
            INSERT INTO speaker_accuracy (speaker, total_predictions, correct, incorrect,
                unclear, accuracy_rate, current_tier, last_updated)
            VALUES (?, 1, ?, ?, ?, ?, ?, ?)
        """, (speaker, correct, incorrect, unclear, rate, pred['speaker_tier'] or 'T2', now))

    conn.commit()
    print(f"Prediction #{args.id} resolved: {outcome}")
    if args.notes:
        print(f"  Notes: {args.notes}")
    conn.close()


def cmd_scorecard(args):
    conn = get_conn()
    init_db(conn)

    rows = conn.execute("""
        SELECT * FROM speaker_accuracy ORDER BY accuracy_rate DESC NULLS LAST
    """).fetchall()

    if not rows:
        print("No speaker accuracy data yet. Resolve some predictions first.")
        return

    print(f"{'Speaker':<20} {'Tier':>4} {'Total':>6} {'Right':>6} {'Wrong':>6} {'???':>6} {'Rate':>7} {'Suggestion'}")
    print("-" * 85)
    for r in rows:
        rate_str = f"{r['accuracy_rate']:.0%}" if r['accuracy_rate'] is not None else "—"
        suggestion = r['tier_suggestion'] or ""
        print(f"{r['speaker']:<20} {r['current_tier'] or 'T2':>4} {r['total_predictions']:>6} "
              f"{r['correct']:>6} {r['incorrect']:>6} {r['unclear']:>6} {rate_str:>7} {suggestion}")

    conn.close()


def cmd_history(args):
    conn = get_conn()
    init_db(conn)

    query = "SELECT * FROM predictions"
    params = []
    if args.speaker:
        query += " WHERE speaker = ?"
        params.append(args.speaker)
    query += " ORDER BY source_date DESC, id DESC"

    rows = conn.execute(query, params).fetchall()

    if not rows:
        print("No predictions found.")
        return

    for r in rows:
        status_icon = {"OPEN": "⏳", "TRUE": "✅", "FALSE": "❌", "UNCLEAR": "❓", "EXPIRED": "⏰"}.get(r['status'], '?')
        print(f"#{r['id']} {status_icon} [{r['source_date']}] {r['speaker']} ({r['speaker_tier']})")
        print(f"   {r['claim']}")
        print(f"   {r['direction'] or '—'} | conf {r['confidence'] or 0:.2f} | expires {r['expiry_date'] or '—'}")
        if r['resolution_notes']:
            print(f"   → {r['status']}: {r['resolution_notes']}")
        print()

    print(f"{len(rows)} prediction(s)")
    conn.close()


def cmd_stats(args):
    conn = get_conn()
    init_db(conn)

    total = conn.execute("SELECT COUNT(*) FROM predictions").fetchone()[0]
    open_count = conn.execute("SELECT COUNT(*) FROM predictions WHERE status='OPEN'").fetchone()[0]
    true_count = conn.execute("SELECT COUNT(*) FROM predictions WHERE status='TRUE'").fetchone()[0]
    false_count = conn.execute("SELECT COUNT(*) FROM predictions WHERE status='FALSE'").fetchone()[0]
    unclear_count = conn.execute("SELECT COUNT(*) FROM predictions WHERE status IN ('UNCLEAR','EXPIRED')").fetchone()[0]

    bullish = conn.execute("SELECT COUNT(*) FROM predictions WHERE direction='BULLISH'").fetchone()[0]
    bearish = conn.execute("SELECT COUNT(*) FROM predictions WHERE direction='BEARISH'").fetchone()[0]

    print(f"Prediction Ledger — {total} total")
    print(f"  Open: {open_count} | True: {true_count} | False: {false_count} | Unclear: {unclear_count}")
    print(f"  Bullish: {bullish} | Bearish: {bearish}")

    if true_count + false_count > 0:
        rate = true_count / (true_count + false_count)
        print(f"  Overall accuracy: {rate:.0%} ({true_count}/{true_count + false_count} resolved)")

    # Top speakers by prediction count
    speakers = conn.execute("""
        SELECT speaker, COUNT(*) as cnt FROM predictions
        GROUP BY speaker ORDER BY cnt DESC LIMIT 5
    """).fetchall()
    if speakers:
        print(f"\n  Top speakers: " + ", ".join(f"{s['speaker']} ({s['cnt']})" for s in speakers))

    conn.close()


def main():
    parser = argparse.ArgumentParser(description="DABEIBA Prediction Ledger")
    sub = parser.add_subparsers(dest="command")

    # add
    add_p = sub.add_parser("add", help="Log a new prediction")
    add_p.add_argument("claim", help="The prediction claim text")
    add_p.add_argument("--speaker", required=True, help="Speaker name")
    add_p.add_argument("--tier", help="Speaker tier (T1/T2/T3, default T2)")
    add_p.add_argument("--horizon", help="Prediction horizon (e.g., '6mo', '12wk', '2yr', '2026-10-15')")
    add_p.add_argument("--direction", choices=["BULLISH", "BEARISH", "NEUTRAL"], help="Direction")
    add_p.add_argument("--metric", help="Target metric (e.g., 'BTC price')")
    add_p.add_argument("--target", help="Target value (e.g., '$100K')")
    add_p.add_argument("--confidence", type=float, help="Confidence score 0.0-1.0")
    add_p.add_argument("--source", help="Source transcript slug")
    add_p.add_argument("--source-date", help="Source date YYYY-MM-DD (default today)")

    # pending
    sub.add_parser("pending", help="Show open predictions")

    # expiring
    exp_p = sub.add_parser("expiring", help="Show predictions expiring soon")
    exp_p.add_argument("days", nargs="?", type=int, default=7, help="Days to look ahead (default 7)")

    # resolve
    res_p = sub.add_parser("resolve", help="Resolve a prediction")
    res_p.add_argument("id", type=int, help="Prediction ID")
    res_p.add_argument("--outcome", required=True, choices=["TRUE", "FALSE", "UNCLEAR", "EXPIRED"])
    res_p.add_argument("--notes", help="Resolution notes")

    # scorecard
    sub.add_parser("scorecard", help="Speaker accuracy scorecard")

    # history
    hist_p = sub.add_parser("history", help="Full prediction history")
    hist_p.add_argument("--speaker", help="Filter by speaker name")

    # stats
    sub.add_parser("stats", help="Summary statistics")

    args = parser.parse_args()

    if args.command == "add":
        cmd_add(args)
    elif args.command == "pending":
        cmd_pending(args)
    elif args.command == "expiring":
        cmd_expiring(args)
    elif args.command == "resolve":
        cmd_resolve(args)
    elif args.command == "scorecard":
        cmd_scorecard(args)
    elif args.command == "history":
        cmd_history(args)
    elif args.command == "stats":
        cmd_stats(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
