#!/usr/bin/env python3
"""
transcript_index.py — Cross-Transcript Speaker Index for DABEIBA Wiki

Creates/updates a wiki article per speaker that tracks their appearances
across transcripts, key claims, stance drift, and prediction history.

Usage:
  python3 transcript_index.py update <speaker> --transcript <slug> --date <YYYY-MM-DD> \
      --claims '["claim1", "claim2"]' --stances '{"BTC": "BULLISH", "Fed": "BEARISH"}' \
      --tier T2 --role "CEO Strike & 21 Inc"

  python3 transcript_index.py query <speaker>                    # full speaker profile
  python3 transcript_index.py query <speaker> --topic "private credit"  # filter by topic
  python3 transcript_index.py drift <speaker>                    # stance drift timeline
  python3 transcript_index.py list                               # all indexed speakers

Articles are written to: wiki/compiled/finance/speakers/{speaker-slug}.md
and indexed into wiki/indexes/articles.sqlite for FTS5 search.
"""

import argparse
import json
import os
import re
import sqlite3
import sys
from datetime import datetime
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
WIKI_ROOT = _DABEIBA / "wiki"
SPEAKERS_DIR = WIKI_ROOT / "compiled" / "finance" / "speakers"
ARTICLES_DB = WIKI_ROOT / "indexes" / "articles.sqlite"


def slugify(name: str) -> str:
    """Convert speaker name to wiki slug."""
    return re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')


def load_speaker_article(speaker_slug: str) -> dict | None:
    """Load existing speaker article frontmatter + body."""
    path = SPEAKERS_DIR / f"{speaker_slug}.md"
    if not path.exists():
        return None

    text = path.read_text()
    # Parse YAML frontmatter
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            import yaml
            try:
                fm = yaml.safe_load(parts[1])
                body = parts[2].strip()
                return {"frontmatter": fm, "body": body, "path": str(path)}
            except Exception:
                pass
    return {"frontmatter": {}, "body": text, "path": str(path)}


def save_speaker_article(speaker_slug: str, speaker_name: str, tier: str,
                          role: str, appearances: list, stances: dict):
    """Write/overwrite the speaker wiki article."""
    SPEAKERS_DIR.mkdir(parents=True, exist_ok=True)
    path = SPEAKERS_DIR / f"{speaker_slug}.md"
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    # Build frontmatter
    tags = ["speaker", f"tier-{tier.lower()}"]
    fm = {
        "title": speaker_name,
        "aliases": [speaker_name, speaker_slug],
        "tags": tags,
        "domain": "finance",
        "subdomain": "speakers",
        "entity_type": "person",
        "sources": [],
        "concept_links": [],
        "created": appearances[0]["date"] if appearances else now,
        "updated": now,
        "freshness_policy": "weekly",
        "confidence": 0.80,
        "review_status": "auto",
        "speaker_tier": tier,
        "role": role,
        "total_appearances": len(appearances),
    }

    # Add sources from appearances
    for app in appearances:
        fm["sources"].append({
            "raw_path": f"intel/{app['transcript']}",
            "source_hash": "",
            "retrieved_at": app["date"],
            "source_url": "",
            "adapter": "transcript",
        })

    # Build body
    body_lines = [f"# {speaker_name}\n"]
    body_lines.append(f"**Role:** {role}  ")
    body_lines.append(f"**Tier:** {tier}  ")
    body_lines.append(f"**Appearances:** {len(appearances)}\n")

    # Appearance table
    body_lines.append("## Transcript Appearances\n")
    body_lines.append("| Date | Transcript | Key Claims |")
    body_lines.append("|------|-----------|------------|")
    for app in sorted(appearances, key=lambda a: a["date"], reverse=True):
        claims_str = "; ".join(app.get("claims", [])[:3])
        if len(app.get("claims", [])) > 3:
            claims_str += f" (+{len(app['claims']) - 3} more)"
        body_lines.append(f"| {app['date']} | {app['transcript']} | {claims_str} |")

    # Stance tracker
    if stances:
        body_lines.append("\n## Current Stances\n")
        body_lines.append("| Topic | Stance | Last Updated |")
        body_lines.append("|-------|--------|-------------|")
        for topic, info in sorted(stances.items()):
            if isinstance(info, dict):
                body_lines.append(f"| {topic} | {info.get('stance', '—')} | {info.get('date', '—')} |")
            else:
                body_lines.append(f"| {topic} | {info} | — |")

    # Stance drift section (if multiple appearances)
    if len(appearances) > 1:
        body_lines.append("\n## Stance Drift\n")
        body_lines.append("Track how this speaker's positions have evolved across appearances.")
        body_lines.append("Cross-reference with prediction accuracy in `prediction_log.py scorecard`.\n")

    # Build YAML
    import yaml
    frontmatter = yaml.dump(fm, default_flow_style=False, sort_keys=False, allow_unicode=True)
    full_text = f"---\n{frontmatter}---\n\n" + "\n".join(body_lines) + "\n"

    path.write_text(full_text)
    return str(path)


def index_article(speaker_slug: str, path: str):
    """Add/update the article in the FTS5 index."""
    if not ARTICLES_DB.exists():
        print(f"WARNING: articles.sqlite not found at {ARTICLES_DB}. Skipping index.")
        return

    text = Path(path).read_text()
    # Extract body (after frontmatter)
    body = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            body = parts[2].strip()

    conn = sqlite3.connect(str(ARTICLES_DB))
    try:
        # Check if exists in meta
        existing = conn.execute("SELECT slug FROM articles_meta WHERE slug = ?",
                                (speaker_slug,)).fetchone()

        content_hash = str(hash(body))[:16]
        now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

        if existing:
            # Delete old FTS entry and re-insert
            conn.execute("DELETE FROM articles_fts WHERE slug = ?", (speaker_slug,))
            conn.execute("""UPDATE articles_meta SET path = ?, indexed_at = ?, content_hash = ?
                           WHERE slug = ?""", (path, now, content_hash, speaker_slug))
        else:
            conn.execute("""INSERT INTO articles_meta (slug, path, indexed_at, content_hash)
                           VALUES (?, ?, ?, ?)""", (speaker_slug, path, now, content_hash))

        # Insert into FTS
        conn.execute("""INSERT INTO articles_fts (slug, title, domain, entity_type, ticker, tags, body)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                     (speaker_slug, speaker_slug.replace("-", " ").title(),
                      "finance", "person", "", "speaker", body))
        conn.commit()
    except Exception as e:
        print(f"WARNING: FTS index update failed: {e}")
    finally:
        conn.close()


def cmd_update(args):
    """Create or update a speaker's cross-transcript article."""
    speaker_slug = slugify(args.speaker)

    # Parse claims and stances from JSON
    claims = json.loads(args.claims) if args.claims else []
    new_stances = json.loads(args.stances) if args.stances else {}

    # Load existing article
    existing = load_speaker_article(speaker_slug)
    appearances = []
    stances = {}

    if existing and existing["frontmatter"]:
        # Extract existing appearances from body (parse table)
        fm = existing["frontmatter"]
        # Rebuild appearances from sources
        for src in fm.get("sources", []):
            # Try to find claims in body
            transcript = src.get("raw_path", "").replace("intel/", "")
            date = src.get("retrieved_at", "")
            appearances.append({
                "transcript": transcript,
                "date": date,
                "claims": [],  # Can't reliably re-parse from table, but that's OK
            })

    # Check for duplicate transcript
    transcript_slugs = [a["transcript"] for a in appearances]
    if args.transcript not in transcript_slugs:
        appearances.append({
            "transcript": args.transcript,
            "date": args.date or datetime.now().strftime("%Y-%m-%d"),
            "claims": claims,
        })
    else:
        # Update existing appearance's claims
        for a in appearances:
            if a["transcript"] == args.transcript:
                a["claims"] = claims
                break

    # Merge stances
    for topic, stance in new_stances.items():
        stances[topic] = {"stance": stance, "date": args.date or datetime.now().strftime("%Y-%m-%d")}

    # Save
    path = save_speaker_article(
        speaker_slug, args.speaker,
        args.tier or "T2", args.role or "—",
        appearances, stances
    )

    # Index in FTS
    index_article(speaker_slug, path)

    print(f"Speaker article updated: {speaker_slug}")
    print(f"  Path: {path}")
    print(f"  Appearances: {len(appearances)}")
    if new_stances:
        print(f"  Stances updated: {list(new_stances.keys())}")


def cmd_query(args):
    """Query a speaker's profile."""
    speaker_slug = slugify(args.speaker)
    article = load_speaker_article(speaker_slug)

    if not article:
        print(f"No article found for '{args.speaker}'. Run 'update' first.")
        # Search FTS for close matches
        if ARTICLES_DB.exists():
            conn = sqlite3.connect(str(ARTICLES_DB))
            matches = conn.execute("""
                SELECT slug, title FROM articles_fts
                WHERE entity_type = 'person' AND articles_fts MATCH ?
                LIMIT 5
            """, (args.speaker,)).fetchall()
            if matches:
                print("Similar speakers:")
                for m in matches:
                    print(f"  {m[1]} ({m[0]})")
            conn.close()
        return

    if args.topic:
        # Filter body for topic mentions
        lines = article["body"].split("\n")
        matches = [l for l in lines if args.topic.lower() in l.lower()]
        if matches:
            print(f"'{args.speaker}' on '{args.topic}':")
            for m in matches:
                print(f"  {m.strip()}")
        else:
            print(f"No mentions of '{args.topic}' in {args.speaker}'s profile.")
    else:
        print(article["body"])


def cmd_drift(args):
    """Show stance drift timeline for a speaker."""
    speaker_slug = slugify(args.speaker)
    article = load_speaker_article(speaker_slug)

    if not article:
        print(f"No article found for '{args.speaker}'.")
        return

    # Extract stance table from body
    in_stance = False
    for line in article["body"].split("\n"):
        if "Current Stances" in line:
            in_stance = True
        elif in_stance:
            if line.startswith("#"):
                break
            if line.strip():
                print(line)


def _count_appearances(text: str) -> int:
    """Count appearances from an article. Prefer YAML frontmatter, fall back to
    the auto-generated table row count. Works for both hand-authored prose
    articles and pipeline-generated table articles.
    """
    # 1. Prefer explicit total_appearances in frontmatter
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            try:
                import yaml
                fm = yaml.safe_load(parts[1]) or {}
                if isinstance(fm.get("total_appearances"), int):
                    return fm["total_appearances"]
                # Fall back: count sources[] entries in frontmatter
                srcs = fm.get("sources") or []
                if isinstance(srcs, list):
                    real = [s for s in srcs if isinstance(s, dict)
                            and s.get("adapter") == "transcript"]
                    if real:
                        return len(real)
            except Exception:
                pass
    # 2. Fall back: count table rows like "| 2026-01-01 | ..."
    table_rows = text.count("| 20")
    if table_rows:
        return table_rows
    # 3. Last resort: scan prose for date-stamped transcript mentions
    return len(re.findall(r"20\d{2}-\d{2}-\d{2}\s+[Tt]ranscript", text))


def cmd_list(args):
    """List all indexed speakers."""
    if not SPEAKERS_DIR.exists():
        print("No speakers indexed yet.")
        return

    articles = sorted(SPEAKERS_DIR.glob("*.md"))
    if not articles:
        print("No speakers indexed yet.")
        return

    print(f"{'Speaker':<25} {'Appearances':>12}")
    print("-" * 40)
    for a in articles:
        text = a.read_text()
        app_count = _count_appearances(text)
        name = a.stem.replace("-", " ").title()
        print(f"{name:<25} {app_count:>12}")


def main():
    # Check for PyYAML
    try:
        import yaml  # noqa
    except ImportError:
        print("Installing PyYAML...")
        os.system(f"{sys.executable} -m pip install pyyaml -q --break-system-packages")

    parser = argparse.ArgumentParser(description="Cross-Transcript Speaker Index")
    sub = parser.add_subparsers(dest="command")

    # update
    up = sub.add_parser("update", help="Create/update speaker article")
    up.add_argument("speaker", help="Speaker name")
    up.add_argument("--transcript", required=True, help="Transcript slug")
    up.add_argument("--date", help="Transcript date YYYY-MM-DD")
    up.add_argument("--claims", help="JSON array of key claims")
    up.add_argument("--stances", help='JSON object of stances: {"topic": "BULLISH"}')
    up.add_argument("--tier", help="Speaker tier (T1/T2/T3)")
    up.add_argument("--role", help="Speaker role/title")

    # query
    q = sub.add_parser("query", help="Query speaker profile")
    q.add_argument("speaker", help="Speaker name")
    q.add_argument("--topic", help="Filter by topic")

    # drift
    d = sub.add_parser("drift", help="Show stance drift")
    d.add_argument("speaker", help="Speaker name")

    # list
    sub.add_parser("list", help="List all indexed speakers")

    args = parser.parse_args()

    if args.command == "update":
        cmd_update(args)
    elif args.command == "query":
        cmd_query(args)
    elif args.command == "drift":
        cmd_drift(args)
    elif args.command == "list":
        cmd_list(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
