#!/usr/bin/env python3
"""
prior_intel.py — Cross-Transcript Prior Intelligence Lookup for DABEIBA

Queries the wiki speaker index and FTS5 to surface what DABEIBA already knows
about speakers and topics BEFORE extraction begins. Used in transcript-to-intel
Phase 0.5 to ground the extraction in existing knowledge.

Usage:
  # Look up prior intel for speakers about to appear in a new transcript
  python3 prior_intel.py speakers "Jack Mallers" "Arthur Hayes"

  # Look up prior intel for topics
  python3 prior_intel.py topics "private credit" "bitcoin" "strait of hormuz"

  # Full pre-extraction brief (speakers + topics combined)
  python3 prior_intel.py brief --speakers "Jack Mallers,Arthur Hayes" \
      --topics "bitcoin,liquidity,iran"

Output: JSON with prior claims, stances, stance drift, and related wiki articles.
This feeds directly into the scratchpad's PRIOR INTEL section.
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
    """Resolve DABEIBA root with fallback chain so this works in sandboxes too.

    1. $DABEIBA_ROOT env var (explicit override).
    2. ~/Desktop/DABEIBA (the macOS default).
    3. Walk up from this file — handy when $HOME != user's real home
       (Cowork sandbox). This script lives at DABEIBA/shared/tools/...
    """
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
    return default_home  # last resort; downstream code will warn if missing


_DABEIBA = _resolve_dabeiba_root()
WIKI_ROOT = _DABEIBA / "wiki"
SPEAKERS_DIR = WIKI_ROOT / "compiled" / "finance" / "speakers"
ARTICLES_DB = WIKI_ROOT / "indexes" / "articles.sqlite"


def slugify(name: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')


def get_db():
    if not ARTICLES_DB.exists():
        print(f"Warning: articles.sqlite not found at {ARTICLES_DB}", file=sys.stderr)
        return None
    return sqlite3.connect(str(ARTICLES_DB))


def lookup_speaker(name: str) -> dict:
    """Retrieve prior intel for a speaker from their wiki article."""
    slug = slugify(name)
    path = SPEAKERS_DIR / f"{slug}.md"
    result = {
        "speaker": name,
        "slug": slug,
        "found": False,
        "prior_appearances": [],
        "prior_stances": {},
        "stance_drift": [],
        "prior_claims": [],
        "tier": None,
        "role": None,
    }

    if not path.exists():
        return result

    text = path.read_text()
    result["found"] = True

    # Parse YAML frontmatter
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            fm = parts[1]
            for line in fm.strip().split('\n'):
                if line.startswith("speaker_tier:"):
                    result["tier"] = line.split(":", 1)[1].strip().strip('"')
                elif line.startswith("role:"):
                    result["role"] = line.split(":", 1)[1].strip().strip('"')
                elif line.startswith("total_appearances:"):
                    try:
                        result["total_appearances"] = int(line.split(":", 1)[1].strip())
                    except ValueError:
                        pass

    # Parse appearances table
    in_appearances = False
    for line in text.split('\n'):
        if '## Appearances' in line or '## Transcript Appearances' in line:
            in_appearances = True
            continue
        if in_appearances and line.startswith('## '):
            in_appearances = False
            continue
        if in_appearances and '|' in line and not line.strip().startswith('|--'):
            cols = [c.strip() for c in line.split('|')]
            cols = [c for c in cols if c]  # remove empty
            if len(cols) >= 3 and cols[0] not in ('Date', 'Transcript', '---'):
                result["prior_appearances"].append({
                    "date": cols[0] if len(cols) > 0 else "",
                    "transcript": cols[1] if len(cols) > 1 else "",
                    "claims": cols[2] if len(cols) > 2 else "",
                })

    # Parse stances table
    in_stances = False
    for line in text.split('\n'):
        if '## Current Stances' in line or '## Stances' in line:
            in_stances = True
            continue
        if in_stances and line.startswith('## '):
            in_stances = False
            continue
        if in_stances and '|' in line and not line.strip().startswith('|--'):
            cols = [c.strip() for c in line.split('|')]
            cols = [c for c in cols if c]
            if len(cols) >= 3 and cols[0] not in ('Topic', '---'):
                topic = cols[0]
                direction = cols[1] if len(cols) > 1 else ""
                date = cols[2] if len(cols) > 2 else ""
                result["prior_stances"][topic] = {
                    "direction": direction,
                    "as_of": date,
                }

    # Extract claims from body (look for bullet points under appearances)
    for line in text.split('\n'):
        line_s = line.strip()
        if line_s.startswith('- ') and ('"' in line_s or 'claims' not in line_s.lower()):
            claim = line_s[2:].strip()
            if len(claim) > 20:  # skip short items like headers
                result["prior_claims"].append(claim)

    return result


def lookup_topic(topic: str) -> dict:
    """Search FTS5 for prior articles mentioning this topic."""
    result = {
        "topic": topic,
        "matching_articles": [],
    }

    conn = get_db()
    if not conn:
        return result

    try:
        c = conn.cursor()
        # FTS5 search
        c.execute("""
            SELECT m.slug, m.path, snippet(articles_fts, 0, '>>>', '<<<', '...', 30)
            FROM articles_fts f
            JOIN articles_meta m ON f.rowid = m.rowid
            WHERE articles_fts MATCH ?
            ORDER BY rank
            LIMIT 10
        """, (topic,))

        for row in c.fetchall():
            result["matching_articles"].append({
                "slug": row[0],
                "path": row[1],
                "snippet": row[2],
            })
    except Exception as e:
        result["error"] = str(e)
    finally:
        conn.close()

    return result


def generate_brief(speakers: list, topics: list) -> dict:
    """Generate a full pre-extraction intelligence brief."""
    brief = {
        "generated_at": datetime.now().isoformat(),
        "speakers": {},
        "topics": {},
        "cross_references": [],
        "extraction_guidance": [],
    }

    # Speaker lookups
    for name in speakers:
        name = name.strip()
        if not name:
            continue
        intel = lookup_speaker(name)
        brief["speakers"][name] = intel

        # Generate extraction guidance based on prior intel
        if intel["found"]:
            n_appearances = len(intel["prior_appearances"])
            if n_appearances >= 2:
                brief["extraction_guidance"].append(
                    f"REPEAT SPEAKER: {name} has {n_appearances} prior appearances. "
                    f"Watch for stance drift on: {', '.join(intel['prior_stances'].keys())}."
                )
            for topic, stance in intel["prior_stances"].items():
                brief["extraction_guidance"].append(
                    f"PRIOR STANCE: {name} was {stance['direction']} on {topic} "
                    f"(as of {stance['as_of']}). Flag if changed."
                )

    # Topic lookups
    for topic in topics:
        topic = topic.strip()
        if not topic:
            continue
        intel = lookup_topic(topic)
        brief["topics"][topic] = intel

        if intel["matching_articles"]:
            n = len(intel["matching_articles"])
            brief["extraction_guidance"].append(
                f"KNOWN TOPIC: '{topic}' appears in {n} existing wiki article(s). "
                f"Cross-reference new claims against existing knowledge."
            )

    # Cross-references: speakers who share topics
    all_speaker_topics = {}
    for name, intel in brief["speakers"].items():
        if intel["found"]:
            for topic in intel["prior_stances"].keys():
                if topic not in all_speaker_topics:
                    all_speaker_topics[topic] = []
                all_speaker_topics[topic].append(name)

    for topic, names in all_speaker_topics.items():
        if len(names) >= 2:
            brief["cross_references"].append({
                "topic": topic,
                "speakers": names,
                "note": f"Multiple speakers have prior stances on '{topic}' — "
                        f"compare for convergence or divergence.",
            })

    return brief


def main():
    parser = argparse.ArgumentParser(description="Prior Intelligence Lookup for transcript-to-intel")
    sub = parser.add_subparsers(dest="command")

    # speakers command
    sp = sub.add_parser("speakers", help="Look up prior intel for speakers")
    sp.add_argument("names", nargs="+", help="Speaker names to look up")

    # topics command
    tp = sub.add_parser("topics", help="Search wiki for topic coverage")
    tp.add_argument("queries", nargs="+", help="Topics to search for")

    # brief command
    bp = sub.add_parser("brief", help="Full pre-extraction intelligence brief")
    bp.add_argument("--speakers", required=True, help="Comma-separated speaker names")
    bp.add_argument("--topics", default="", help="Comma-separated topics")
    bp.add_argument("--output", help="Output JSON path")

    args = parser.parse_args()

    if args.command == "speakers":
        results = [lookup_speaker(n) for n in args.names]
        print(json.dumps(results, indent=2))

    elif args.command == "topics":
        results = [lookup_topic(t) for t in args.queries]
        print(json.dumps(results, indent=2))

    elif args.command == "brief":
        speakers = [s.strip() for s in args.speakers.split(",")]
        topics = [t.strip() for t in args.topics.split(",") if t.strip()]
        brief = generate_brief(speakers, topics)

        output = json.dumps(brief, indent=2)
        if args.output:
            Path(args.output).write_text(output)
            print(f"Brief written to {args.output}", file=sys.stderr)
        else:
            print(output)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
