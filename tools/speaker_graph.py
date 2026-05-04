#!/usr/bin/env python3
"""
speaker_graph.py — Speaker Interaction Graph for DABEIBA

Parses multi-speaker transcript dynamics (P4 output) into a structured
interaction matrix. For transcripts with 2+ speakers, tracks:
  - Agreements (Speaker A agrees with Speaker B on topic X)
  - Disagreements (Speaker A contradicts Speaker B on topic X)
  - Build-ons (Speaker A extends Speaker B's point)
  - Deferrals (Speaker A defers to Speaker B's expertise)
  - Interrupts (Speaker A cuts off Speaker B)

Usage:
  # Parse a P4 dynamics JSON file into an interaction matrix
  python3 speaker_graph.py parse dynamics.json --output matrix.json

  # Generate a text-based summary from the matrix
  python3 speaker_graph.py summarize matrix.json

  # Merge multiple transcript matrices for cross-transcript patterns
  python3 speaker_graph.py merge matrix1.json matrix2.json --output merged.json

Input format (dynamics.json — produced by LLM during P4 pass):
{
  "speakers": ["Alice", "Bob", "Carol"],
  "interactions": [
    {"from": "Alice", "to": "Bob", "type": "agree", "topic": "BTC outlook", "quote": "I agree with Bob..."},
    {"from": "Bob", "to": "Carol", "type": "disagree", "topic": "Fed policy", "quote": "I don't think..."},
    {"from": "Carol", "to": "Alice", "type": "build", "topic": "liquidity", "quote": "Building on what Alice said..."},
    {"from": "Bob", "to": "Alice", "type": "defer", "topic": "technical analysis", "quote": "Alice knows more about..."},
    {"from": "Alice", "to": "Bob", "type": "interrupt", "topic": "", "quote": ""}
  ]
}
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

INTERACTION_TYPES = {
    "agree": {"label": "Agreement", "weight": 1.0, "color": "green"},
    "disagree": {"label": "Disagreement", "weight": -1.0, "color": "red"},
    "build": {"label": "Build-on", "weight": 0.5, "color": "blue"},
    "defer": {"label": "Deferral", "weight": 0.3, "color": "grey"},
    "interrupt": {"label": "Interrupt", "weight": -0.3, "color": "orange"},
}


def parse_dynamics(dynamics: dict) -> dict:
    """Parse raw dynamics JSON into a structured interaction matrix."""
    interactions = dynamics.get("interactions", [])
    # Speakers list may be omitted — derive from interaction from/to if so.
    speakers = list(dynamics.get("speakers", []))
    if not speakers:
        derived = []
        for ix in interactions:
            for field in ("from", "to"):
                name = ix.get(field, "")
                if name and name not in derived:
                    derived.append(name)
        speakers = derived

    # Build adjacency matrix
    matrix = {}
    for s1 in speakers:
        for s2 in speakers:
            if s1 != s2:
                key = f"{s1}→{s2}"
                matrix[key] = {
                    "from": s1, "to": s2,
                    "agree": 0, "disagree": 0, "build": 0,
                    "defer": 0, "interrupt": 0,
                    "net_alignment": 0.0,
                    "topics": [],
                }

    for ix in interactions:
        frm = ix.get("from", "")
        to = ix.get("to", "")
        itype = ix.get("type", "").lower()
        topic = ix.get("topic", "")
        key = f"{frm}→{to}"

        if key not in matrix:
            continue
        if itype not in INTERACTION_TYPES:
            continue

        matrix[key][itype] += 1
        matrix[key]["net_alignment"] += INTERACTION_TYPES[itype]["weight"]
        if topic and topic not in matrix[key]["topics"]:
            matrix[key]["topics"].append(topic)

    # Speaker-level summary
    speaker_stats = {}
    for sp in speakers:
        outgoing = [v for k, v in matrix.items() if v["from"] == sp]
        incoming = [v for k, v in matrix.items() if v["to"] == sp]

        total_out = sum(v["agree"] + v["disagree"] + v["build"] + v["defer"] + v["interrupt"] for v in outgoing)
        total_in = sum(v["agree"] + v["disagree"] + v["build"] + v["defer"] + v["interrupt"] for v in incoming)
        agrees_out = sum(v["agree"] for v in outgoing)
        disagrees_out = sum(v["disagree"] for v in outgoing)

        speaker_stats[sp] = {
            "total_interactions": total_out + total_in,
            "outgoing": total_out,
            "incoming": total_in,
            "agrees_given": agrees_out,
            "disagrees_given": disagrees_out,
            "deferred_to_count": sum(v["defer"] for v in incoming),
            "collaboration_score": round(sum(v["net_alignment"] for v in outgoing), 2),
            "role_label": classify_role(agrees_out, disagrees_out, total_out,
                                         sum(v["defer"] for v in incoming)),
        }

    # Topic-level conflict map
    topic_conflicts = defaultdict(lambda: {"agree": 0, "disagree": 0, "speakers": set()})
    for ix in interactions:
        topic = ix.get("topic", "")
        itype = ix.get("type", "").lower()
        if topic and itype in ("agree", "disagree"):
            topic_conflicts[topic][itype] += 1
            topic_conflicts[topic]["speakers"].add(ix.get("from", ""))
            topic_conflicts[topic]["speakers"].add(ix.get("to", ""))

    # Convert sets to lists for JSON
    for t in topic_conflicts:
        topic_conflicts[t]["speakers"] = list(topic_conflicts[t]["speakers"])

    return {
        "speakers": speakers,
        "matrix": matrix,
        "speaker_stats": speaker_stats,
        "topic_conflicts": dict(topic_conflicts),
        "total_interactions": len(interactions),
    }


def classify_role(agrees, disagrees, total, deferred_to):
    """Classify speaker's conversational role."""
    if total == 0:
        return "Observer"
    agree_rate = agrees / total if total > 0 else 0
    disagree_rate = disagrees / total if total > 0 else 0

    if deferred_to >= 3:
        return "Authority"
    if disagree_rate > 0.5:
        return "Contrarian"
    if agree_rate > 0.6:
        return "Consensus builder"
    if total >= 5 and abs(agree_rate - disagree_rate) < 0.15:
        return "Balanced challenger"
    return "Active participant"


def summarize(parsed: dict) -> str:
    """Generate a text summary of the interaction graph."""
    lines = []
    lines.append(f"Speaker Interaction Summary ({parsed['total_interactions']} interactions)")
    lines.append("=" * 60)

    # Speaker roles
    lines.append("\nSpeaker Roles:")
    for sp, stats in parsed["speaker_stats"].items():
        lines.append(f"  {sp}: {stats['role_label']} "
                     f"(+{stats['agrees_given']} agrees, -{stats['disagrees_given']} disagrees, "
                     f"collab score: {stats['collaboration_score']})")

    # Key relationships
    lines.append("\nKey Relationships:")
    sorted_edges = sorted(parsed["matrix"].values(),
                          key=lambda v: abs(v["net_alignment"]), reverse=True)
    for edge in sorted_edges[:5]:
        if edge["agree"] + edge["disagree"] + edge["build"] > 0:
            alignment = "aligned" if edge["net_alignment"] > 0 else "opposed" if edge["net_alignment"] < 0 else "neutral"
            lines.append(f"  {edge['from']} → {edge['to']}: {alignment} "
                         f"(net: {edge['net_alignment']:.1f}, "
                         f"topics: {', '.join(edge['topics'][:3]) or '—'})")

    # Contested topics
    contested = {t: v for t, v in parsed["topic_conflicts"].items() if v["disagree"] > 0}
    if contested:
        lines.append("\nContested Topics:")
        for topic, data in sorted(contested.items(), key=lambda x: x[1]["disagree"], reverse=True):
            lines.append(f"  {topic}: {data['disagree']} disagreement(s) among {', '.join(data['speakers'])}")

    return "\n".join(lines)


def merge_matrices(matrices: list) -> dict:
    """Merge multiple interaction matrices for cross-transcript patterns."""
    all_speakers = set()
    merged_interactions = defaultdict(lambda: {
        "agree": 0, "disagree": 0, "build": 0,
        "defer": 0, "interrupt": 0,
        "net_alignment": 0.0, "topics": [],
        "transcript_count": 0,
    })

    for m in matrices:
        for sp in m.get("speakers", []):
            all_speakers.add(sp)
        for key, edge in m.get("matrix", {}).items():
            merged_interactions[key]["agree"] += edge.get("agree", 0)
            merged_interactions[key]["disagree"] += edge.get("disagree", 0)
            merged_interactions[key]["build"] += edge.get("build", 0)
            merged_interactions[key]["defer"] += edge.get("defer", 0)
            merged_interactions[key]["interrupt"] += edge.get("interrupt", 0)
            merged_interactions[key]["net_alignment"] += edge.get("net_alignment", 0)
            merged_interactions[key]["transcript_count"] += 1
            for t in edge.get("topics", []):
                if t not in merged_interactions[key]["topics"]:
                    merged_interactions[key]["topics"].append(t)

    return {
        "speakers": list(all_speakers),
        "matrix": dict(merged_interactions),
        "total_transcripts": len(matrices),
    }


def main():
    parser = argparse.ArgumentParser(description="DABEIBA Speaker Interaction Graph")
    sub = parser.add_subparsers(dest="command")

    # parse
    pp = sub.add_parser("parse", help="Parse dynamics JSON into interaction matrix")
    pp.add_argument("dynamics_json", help="Path to P4 dynamics JSON")
    pp.add_argument("--output", help="Output JSON path")

    # summarize
    sp = sub.add_parser("summarize", help="Text summary of interaction matrix")
    sp.add_argument("matrix_json", help="Path to parsed matrix JSON")

    # merge
    mp = sub.add_parser("merge", help="Merge multiple matrices")
    mp.add_argument("files", nargs="+", help="Matrix JSON files to merge")
    mp.add_argument("--output", help="Output merged JSON path")

    args = parser.parse_args()

    if args.command == "parse":
        with open(args.dynamics_json) as f:
            dynamics = json.load(f)
        parsed = parse_dynamics(dynamics)
        output = json.dumps(parsed, indent=2)
        if args.output:
            Path(args.output).write_text(output)
            print(f"Matrix written to {args.output}", file=sys.stderr)
        print(output)

    elif args.command == "summarize":
        with open(args.matrix_json) as f:
            parsed = json.load(f)
        print(summarize(parsed))

    elif args.command == "merge":
        matrices = []
        for fp in args.files:
            with open(fp) as f:
                matrices.append(json.load(f))
        merged = merge_matrices(matrices)
        output = json.dumps(merged, indent=2)
        if args.output:
            Path(args.output).write_text(output)
            print(f"Merged matrix written to {args.output}", file=sys.stderr)
        print(output)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
