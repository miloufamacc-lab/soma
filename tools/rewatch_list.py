#!/usr/bin/env python3
"""
rewatch_list.py — Audio-Cue Flag List for transcript-to-intel V3.0

Compiles a list of high-stakes timestamps that the user should audio-verify.
Only works for YouTube transcripts (which have timestamps). Pasted text: skip.

Usage:
  python3 rewatch_list.py build <scanner_results.json> [--scratchpad scratchpad.md] [--output rewatch.json]
  python3 rewatch_list.py report <rewatch.json>

Triggers:
  - Numerical claim >$1B or >5% change
  - Speaker contradicts prior position (stance drift)
  - Forward prediction with high conviction
  - Red flag triggered (PROMOTER, CONFLICT)
  - Implicit claim with high impact (8+)

Output: 5-10 timestamps with one-line reason, sorted by importance.
"""

import argparse
import json
import os
import re
import sys


def parse_timestamp(context: str) -> str:
    """
    Try to extract a timestamp from context text.
    YouTube transcript lines often start with timestamps like [0:15:32] or (15:32).
    Returns timestamp string or None.
    """
    patterns = [
        r'\[?(\d{1,2}:\d{2}:\d{2})\]?',   # 1:15:32 or [1:15:32]
        r'\[?(\d{1,2}:\d{2})\]?',            # 15:32 or [15:32]
        r'\((\d{1,2}:\d{2}:\d{2})\)',         # (1:15:32)
        r'\((\d{1,2}:\d{2})\)',               # (15:32)
    ]
    for pat in patterns:
        m = re.search(pat, context)
        if m:
            return m.group(1)
    return None


def estimate_timestamp_from_position(char_pos: int, total_chars: int,
                                      duration_minutes: float = 60) -> str:
    """Estimate timestamp from character position in transcript."""
    if total_chars == 0:
        return "0:00"
    fraction = char_pos / total_chars
    total_seconds = int(fraction * duration_minutes * 60)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def build_rewatch_list(scanner_path: str, scratchpad_path: str = None,
                        output_path: str = None, duration_minutes: float = 60,
                        transcript_path: str = None) -> dict:
    """
    Build the rewatch list from scanner results and optional scratchpad.
    """
    with open(scanner_path, 'r') as f:
        scanner = json.load(f)

    # Tolerate both old (p5_numeric.claims=[{value,context,...}]) and new
    # (pass_5_numerics.money_amounts=["$500"]) schemas by normalizing to dicts.
    def _numeric_claims(s):
        p5 = s.get("pass_5_numerics") or s.get("p5_numeric") or {}
        if "claims" in p5 and isinstance(p5.get("claims"), list):
            return p5["claims"]
        out = []
        for bucket in ("money_amounts", "percentages", "large_numbers",
                       "multipliers", "time_references"):
            for item in p5.get(bucket, []) or []:
                if isinstance(item, dict):
                    out.append(item)
                elif isinstance(item, (list, tuple)) and item:
                    out.append({"value": str(item[0]), "raw": str(item[0]),
                                "context": ""})
                else:
                    out.append({"value": str(item), "raw": str(item),
                                "context": ""})
        return out

    def _pivot_list(s):
        p2b = s.get("pass_2b_pivots") or s.get("p2b_pivots") or {}
        if isinstance(p2b, list):
            return p2b
        return p2b.get("pivots", []) if isinstance(p2b, dict) else []

    total_chars = (scanner.get("meta", {}).get("total_chars")
                   or scanner.get("metadata", {}).get("total_chars")
                   or 100000)
    flags = []

    # --- Trigger 1: Large numerical claims ($1B+ or >5% change) ---
    for claim in _numeric_claims(scanner):
        value = claim.get("value", "")
        context = claim.get("context", "")
        raw = claim.get("raw", "")

        is_large = False
        reason = None

        # Check for billion+ amounts
        if re.search(r'\$\d+(\.\d+)?\s*[BT]', value, re.IGNORECASE):
            is_large = True
            reason = f"Large financial claim: {raw}"
        elif re.search(r'\$\d{10,}', value.replace(',', '')):
            is_large = True
            reason = f"Large financial claim: {raw}"

        # Check for >5% changes
        pct_match = re.search(r'(\d+(?:\.\d+)?)\s*%', value)
        if pct_match:
            pct_val = float(pct_match.group(1))
            if pct_val > 5:
                is_large = True
                reason = reason or f"Significant percentage claim: {raw}"

        # Check multipliers
        if re.search(r'\d+[xX]', value):
            is_large = True
            reason = reason or f"Multiplier claim: {raw}"

        if is_large:
            timestamp = parse_timestamp(context)
            if not timestamp:
                # Prefer offset (new schema), fall back to line*80 (old)
                char_pos = claim.get("offset") or (claim.get("line", 0) * 80)
                timestamp = estimate_timestamp_from_position(
                    char_pos, total_chars, duration_minutes
                )

            flags.append({
                "timestamp": timestamp,
                "reason": reason,
                "trigger": "NUMERICAL",
                "priority": 2,  # medium-high
                "raw_data": raw,
            })

    # --- Trigger 2: Topic pivots (potential deflection/avoidance) ---
    for pivot in _pivot_list(scanner):
        # Skip raw YT speaker-change markers — they're turn-taking, not deflection
        if isinstance(pivot, dict) and pivot.get("kind") == "speaker_change":
            continue
        marker = pivot.get("marker", "")
        context = pivot.get("context", "")
        # New schema: offset (char pos). Old schema: line. Fall back to 0.
        char_pos = pivot.get("offset") or (pivot.get("line", 0) * 80)

        # Only flag deflection-style pivots
        deflection_words = ["but anyway", "the better question", "let me redirect",
                           "that's not the point", "what really matters"]
        is_deflection = any(d in marker.lower() for d in deflection_words)

        if is_deflection:
            timestamp = parse_timestamp(context)
            if not timestamp:
                timestamp = estimate_timestamp_from_position(
                    char_pos, total_chars, duration_minutes
                )
            flags.append({
                "timestamp": timestamp,
                "reason": f"Topic deflection: \"{marker[:50]}\"",
                "trigger": "DEFLECTION",
                "priority": 3,  # medium
            })

    # --- Trigger 3-5: Parse scratchpad for stance drift, predictions, red flags ---
    if scratchpad_path and os.path.exists(scratchpad_path):
        with open(scratchpad_path, 'r') as f:
            scratchpad = f.read()

        # Stance drift
        drift_pattern = r'STANCE DRIFT:?\s*(?:was\s+)?(\w+).*?now\s+(\w+)'
        for m in re.finditer(drift_pattern, scratchpad, re.IGNORECASE):
            flags.append({
                "timestamp": "~see scratchpad",
                "reason": f"Stance drift detected: was {m.group(1)}, now {m.group(2)}",
                "trigger": "STANCE_DRIFT",
                "priority": 1,  # highest
            })

        # High-conviction forward predictions
        pred_pattern = r'Conviction:\s*(H|HIGH).*?claim.type:\s*(forward|conditional)'
        for m in re.finditer(pred_pattern, scratchpad, re.IGNORECASE | re.DOTALL):
            flags.append({
                "timestamp": "~see scratchpad",
                "reason": "High-conviction forward prediction — verify speaker tone",
                "trigger": "PREDICTION",
                "priority": 2,
            })

        # Red flags (PROMOTER, CONFLICT)
        for flag_type in ["PROMOTER", "CONFLICT", "Authority Overreach"]:
            if flag_type.upper() in scratchpad.upper():
                flags.append({
                    "timestamp": "~see scratchpad",
                    "reason": f"Red flag: {flag_type} — verify context and tone",
                    "trigger": "RED_FLAG",
                    "priority": 1,
                })

        # Implicit claims with high impact
        implicit_pattern = r'claim_type:\s*implicit.*?Impact:\s*(\d+)'
        for m in re.finditer(implicit_pattern, scratchpad, re.IGNORECASE | re.DOTALL):
            impact = int(m.group(1))
            if impact >= 8:
                flags.append({
                    "timestamp": "~see scratchpad",
                    "reason": f"High-impact implicit claim (impact {impact}) — verify speaker actually implies this",
                    "trigger": "IMPLICIT",
                    "priority": 2,
                })

    # Deduplicate and sort by priority (1=highest), then limit to 10
    # Remove near-duplicate timestamps
    seen_reasons = set()
    unique_flags = []
    for f in flags:
        key = f["reason"][:40]
        if key not in seen_reasons:
            seen_reasons.add(key)
            unique_flags.append(f)

    unique_flags.sort(key=lambda x: x["priority"])
    final_flags = unique_flags[:10]

    output = {
        "source": os.path.basename(scanner_path),
        "total_flags": len(final_flags),
        "has_timestamps": any(
            f["timestamp"] != "~see scratchpad" for f in final_flags
        ),
        "flags": final_flags,
        "note": (
            "Rewatch these segments to verify tone, emphasis, and non-verbal cues. "
            "Timestamps are estimates based on transcript position."
            if final_flags else
            "No high-stakes segments flagged for audio verification."
        ),
    }

    if output_path:
        with open(output_path, 'w') as f:
            json.dump(output, f, indent=2)
        print(f"Rewatch list saved to {output_path} ({len(final_flags)} flags)")
    else:
        print(json.dumps(output, indent=2))

    return output


def report(rewatch_path: str):
    """Print human-readable rewatch list."""
    with open(rewatch_path, 'r') as f:
        data = json.load(f)

    print(f"\n{'='*60}")
    print(f"REWATCH LIST — {data['source']}")
    print(f"{'='*60}\n")

    if not data["flags"]:
        print("  No high-stakes segments flagged.")
        return

    trigger_icons = {
        "NUMERICAL": "💰",
        "DEFLECTION": "↩️",
        "STANCE_DRIFT": "🔄",
        "PREDICTION": "🔮",
        "RED_FLAG": "🚩",
        "IMPLICIT": "💭",
    }

    for i, flag in enumerate(data["flags"], 1):
        icon = trigger_icons.get(flag["trigger"], "📌")
        priority_label = {1: "HIGH", 2: "MED", 3: "LOW"}.get(flag["priority"], "—")
        print(f"  {i:2d}. {icon} [{flag['timestamp']}] [{priority_label}]")
        print(f"      {flag['reason']}")
        print()

    print(f"  {data['note']}")
    print()


def main():
    parser = argparse.ArgumentParser(description="Audio-cue flag list for transcripts")
    subparsers = parser.add_subparsers(dest="command")

    # build
    build_p = subparsers.add_parser("build", help="Build rewatch list")
    build_p.add_argument("scanner_json", help="Path to five_pass_scanner output JSON")
    build_p.add_argument("--scratchpad", "-s", help="Path to scratchpad markdown")
    build_p.add_argument("--output", "-o", help="Output JSON path")
    build_p.add_argument("--duration", "-d", type=float, default=60.0,
                         help="Transcript duration in minutes (for timestamp estimation)")
    build_p.add_argument("--transcript", "-t", help="Path to transcript (for position mapping)")

    # report
    report_p = subparsers.add_parser("report", help="Print rewatch report")
    report_p.add_argument("rewatch_json", help="Path to rewatch JSON from build command")

    args = parser.parse_args()

    if args.command == "build":
        build_rewatch_list(
            args.scanner_json,
            scratchpad_path=args.scratchpad,
            output_path=args.output,
            duration_minutes=args.duration,
        )
    elif args.command == "report":
        report(args.rewatch_json)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
