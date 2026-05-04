#!/usr/bin/env python3
"""
density_heatmap.py — Topic Density Scanner for transcript-to-intel V3.0

Calculates claim-impact-per-1000-tokens by segment. Identifies which parts of a
transcript are information-rich vs sparse so users can prioritize rewatching.

Two source modes:
  1. SCRATCHPAD MODE (preferred) — parse the canonical Phase-1 scratchpad,
     anchor each CLAIM by its verbatim_anchor, weight density by impact score.
  2. SCANNER MODE (fallback) — count p5_numeric claims + p2b pivots from the
     five_pass_scanner JSON by substring/position match.

Usage:
  python3 density_heatmap.py scan <transcript.txt> <scanner_results.json> \\
      [--scratchpad <path>] [--output density.json] [--segments N]
  python3 density_heatmap.py report <density.json>

Commands:
  scan    — Analyze transcript segments, produce density JSON.
  report  — Print a human-readable summary (no emoji, text chips only).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter


# ── Helpers ───────────────────────────────────────────────────────────────
def estimate_tokens(text: str) -> int:
    """Rough token estimate: 1 token ≈ 4 chars."""
    return max(1, len(text) // 4)


def split_into_segments(text: str, num_segments: int | None = None) -> list:
    """
    Split transcript into segments at natural boundaries.
    Returns list of dicts: { index, start_char, end_char, text, tokens }.
    """
    total_tokens = estimate_tokens(text)

    if num_segments is None:
        if total_tokens < 8000:
            num_segments = 3
        elif total_tokens < 25000:
            num_segments = 5
        elif total_tokens < 50000:
            num_segments = 8
        else:
            num_segments = 10

    target_size = len(text) // num_segments
    segments = []
    start = 0

    for i in range(num_segments - 1):
        target_end = start + target_size
        search_start = max(start, target_end - 1000)
        search_end = min(len(text), target_end + 1000)
        search_region = text[search_start:search_end]

        best_break = None
        for pattern in ['\n\n', '\n', '. ']:
            idx = search_region.rfind(pattern)
            if idx != -1:
                best_break = search_start + idx + len(pattern)
                break

        if best_break is None:
            best_break = target_end

        seg_text = text[start:best_break]
        segments.append({
            "index": i + 1,
            "start_char": start,
            "end_char": best_break,
            "text": seg_text,
            "tokens": estimate_tokens(seg_text),
        })
        start = best_break

    seg_text = text[start:]
    segments.append({
        "index": num_segments,
        "start_char": start,
        "end_char": len(text),
        "text": seg_text,
        "tokens": estimate_tokens(seg_text),
    })
    return segments


# ── Scratchpad parser ─────────────────────────────────────────────────────
CLAIM_HEADER_RE = re.compile(
    r"^#{1,4}?\s*\*{0,2}\s*CLAIM\s*#?\s*(\d+)", re.IGNORECASE
)
IMPACT_RE = re.compile(r"Impact[:\s]+(\d+(?:\.\d+)?)", re.IGNORECASE)
CONFIDENCE_RE = re.compile(r"Confidence[:\s]+(\d+(?:\.\d+)?)", re.IGNORECASE)
ANCHOR_RE = re.compile(
    r"verbatim[_\s]anchor[:\s]+[\"\'\u201c]?(.+?)[\"\'\u201d]?\s*(?:\n|$)",
    re.IGNORECASE,
)
CLAIM_TYPE_RE = re.compile(r"claim[_\s]type[:\s]+(\w+)", re.IGNORECASE)


def parse_scratchpad_claims(scratchpad_path: str) -> list:
    """
    Parse scratchpad into a list of claims with:
      { id, impact, confidence, anchor, claim_type }
    Works loosely — tolerates markdown variation.
    """
    if not os.path.exists(scratchpad_path):
        return []

    with open(scratchpad_path, 'r', encoding='utf-8', errors='replace') as f:
        text = f.read()

    # Find the CLAIMS section (header can be "# CLAIMS" or "## CLAIMS", tolerate suffixes)
    claims_start = re.search(r"^#{1,3}\s*CLAIMS\b", text, re.MULTILINE | re.IGNORECASE)
    if claims_start:
        rest = text[claims_start.end():]
        # Stop at next TOP-level "# " or "## " section header that isn't a claim sub-header
        stop = re.search(
            r"\n#{1,2}\s+(?!CLAIM\b|CLAIMS\b|Claim\b)[A-Za-z]",
            rest,
        )
        claims_block = rest[:stop.start()] if stop else rest
    else:
        claims_block = text  # no header — scan whole doc (forgiving)

    # Split into per-claim chunks using CLAIM # markers
    chunks = []
    current: list[str] = []
    current_id = None
    for line in claims_block.split('\n'):
        m = CLAIM_HEADER_RE.match(line)
        if m:
            if current:
                chunks.append((current_id, '\n'.join(current)))
            current_id = m.group(1)
            current = [line]
        elif current_id is not None:
            current.append(line)
    if current:
        chunks.append((current_id, '\n'.join(current)))

    parsed = []
    for cid, body in chunks:
        impact_m = IMPACT_RE.search(body)
        conf_m = CONFIDENCE_RE.search(body)
        anchor_m = ANCHOR_RE.search(body)
        type_m = CLAIM_TYPE_RE.search(body)
        parsed.append({
            "id": cid,
            "impact": float(impact_m.group(1)) if impact_m else 5.0,
            "confidence": float(conf_m.group(1)) if conf_m else 0.0,
            "anchor": (anchor_m.group(1).strip() if anchor_m else "")[:300],
            "claim_type": (type_m.group(1).lower() if type_m else "explicit"),
        })
    return parsed


def _anchor_in_segment(anchor: str, segment_text: str) -> bool:
    """Fuzzy contains: try full anchor, then shortened prefixes."""
    if not anchor:
        return False
    norm = re.sub(r"\s+", " ", anchor).strip().lower()
    seg = re.sub(r"\s+", " ", segment_text).lower()
    if not norm:
        return False
    # Try full, then 80-char, 40-char, 20-char prefix
    for length in (len(norm), 80, 40, 20):
        if length <= 0:
            continue
        probe = norm[:length]
        if len(probe) >= 12 and probe in seg:
            return True
    return False


# ── Claim counting ────────────────────────────────────────────────────────
def count_claims_scratchpad(segment_text: str, claims: list) -> dict:
    """
    Match scratchpad claims to the segment by verbatim_anchor substring.
    Returns counts + summed-impact-weight for density calculation.
    """
    matched = []
    impact_sum = 0.0
    implicit = 0
    for c in claims:
        if _anchor_in_segment(c["anchor"], segment_text):
            matched.append(c)
            impact_sum += c["impact"]
            if c["claim_type"] == "implicit":
                implicit += 1
    return {
        "claims_matched": len(matched),
        "impact_sum": round(impact_sum, 1),
        "implicit_claims": implicit,
        "matched_ids": [c["id"] for c in matched],
    }


def _pass_data(scanner_data: dict, short_key: str, long_key: str):
    """Accept both short (p2b_pivots) and long (pass_2b_pivots) schema keys."""
    if long_key in scanner_data:
        return scanner_data[long_key]
    return scanner_data.get(short_key, {})


def _numeric_claims(scanner_data: dict) -> list:
    """
    Flatten P5 numeric block into a single claim list regardless of shape.
    New scanner: { money_amounts: ["$500 ", ...], percentages: ["40%"], ... }
    Old scanner: { claims: [{value, context, raw, line}, ...] }
    Always returns list[dict] so downstream code can call .get() safely.
    """
    p5 = _pass_data(scanner_data, "p5_numeric", "pass_5_numerics")
    if not isinstance(p5, dict):
        return []
    if "claims" in p5 and isinstance(p5["claims"], list):
        return p5["claims"]
    claims = []
    for bucket in ("money_amounts", "percentages", "large_numbers",
                   "multipliers", "time_references"):
        for item in p5.get(bucket, []) or []:
            if isinstance(item, dict):
                claims.append(item)
            else:
                claims.append({"value": str(item), "raw": str(item),
                               "context": ""})
    return claims


def _pivot_list(scanner_data: dict) -> list:
    """P2b may be a top-level list OR a dict with .pivots."""
    p2b = _pass_data(scanner_data, "p2b_pivots", "pass_2b_pivots")
    if isinstance(p2b, list):
        return p2b
    if isinstance(p2b, dict):
        return p2b.get("pivots", [])
    return []


def count_claims_scanner(segment_text: str, scanner_data: dict) -> dict:
    """Fallback: count scanner-detected items falling within a segment."""
    counts = Counter()

    for num_claim in _numeric_claims(scanner_data):
        if not isinstance(num_claim, dict):
            continue
        context = num_claim.get("context", "") or ""
        if context and len(context) >= 20:
            if context[:40] in segment_text:
                counts["numerics"] += 1
        elif context and context in segment_text:
            counts["numerics"] += 1

    for pivot in _pivot_list(scanner_data):
        if not isinstance(pivot, dict):
            continue
        # Skip raw speaker-change markers — they're noise at segment granularity
        if pivot.get("kind") == "speaker_change":
            continue
        context = pivot.get("context", "") or ""
        if context and context[:30] in segment_text:
            counts["pivots"] += 1

    rhetoric = _pass_data(scanner_data, "p2a_rhetoric", "pass_2a_rhetoric")
    rhetoric_values = rhetoric.values() if isinstance(rhetoric, dict) else []
    for speaker_data in rhetoric_values:
        if isinstance(speaker_data, dict):
            for hedge_word, _n in speaker_data.get("top_hedges", []):
                counts["hedges"] += segment_text.lower().count(hedge_word.lower())
            for abs_word, _n in speaker_data.get("top_absolutes", []):
                counts["absolutes"] += segment_text.lower().count(abs_word.lower())

    counts["total"] = counts["numerics"] + counts["pivots"]
    return dict(counts)


# ── Main scan ─────────────────────────────────────────────────────────────
def scan(transcript_path: str, scanner_path: str,
         output_path: str | None = None, num_segments: int | None = None,
         scratchpad_path: str | None = None) -> dict:
    """Split transcript, count claims per segment, compute density."""

    with open(transcript_path, 'r', encoding='utf-8', errors='replace') as f:
        text = f.read()

    with open(scanner_path, 'r', encoding='utf-8') as f:
        scanner_data = json.load(f)

    scratchpad_claims = parse_scratchpad_claims(scratchpad_path) if scratchpad_path else []
    mode = "scratchpad" if scratchpad_claims else "scanner"

    total_tokens = estimate_tokens(text)
    segments = split_into_segments(text, num_segments)

    results = []
    max_density = 0.0

    for seg in segments:
        if mode == "scratchpad":
            sp = count_claims_scratchpad(seg["text"], scratchpad_claims)
            sc = count_claims_scanner(seg["text"], scanner_data)
            claims = {**sc, **sp}
            # Weighted density: impact / 1k tokens (impact scale 0-10)
            density = round((sp["impact_sum"] / seg["tokens"]) * 1000, 2) if seg["tokens"] > 0 else 0
        else:
            claims = count_claims_scanner(seg["text"], scanner_data)
            density = round((claims["total"] / seg["tokens"]) * 1000, 2) if seg["tokens"] > 0 else 0

        max_density = max(max_density, density)

        preview = seg["text"][:200].replace('\n', ' ').strip()
        if len(preview) > 150:
            preview = preview[:147] + "..."

        results.append({
            "segment": seg["index"],
            "tokens": seg["tokens"],
            "token_pct": round(seg["tokens"] / total_tokens * 100, 1),
            "claims": claims,
            "density_per_1k": density,
            "preview": preview,
        })

    if max_density > 0:
        for r in results:
            ratio = r["density_per_1k"] / max_density
            if ratio >= 0.70:
                r["level"] = "HIGH"
            elif ratio >= 0.35:
                r["level"] = "MEDIUM"
            else:
                r["level"] = "LOW"
    else:
        for r in results:
            r["level"] = "LOW"

    sorted_segs = sorted(results, key=lambda x: x["density_per_1k"], reverse=True)
    top_segs = [s["segment"] for s in sorted_segs[:3] if s["level"] in ("HIGH", "MEDIUM")]

    output = {
        "transcript": os.path.basename(transcript_path),
        "mode": mode,
        "scratchpad_claims_parsed": len(scratchpad_claims),
        "total_tokens": total_tokens,
        "num_segments": len(results),
        "segments": results,
        "rewatch_recommendation": top_segs,
        "rewatch_note": (
            f"Segments {', '.join(str(s) for s in top_segs)} are highest density — "
            "rewatch if time-limited"
        ) if top_segs else "Density is evenly distributed — no priority segments",
    }

    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2)
        print(f"Density analysis saved to {output_path} (mode: {mode})")
    else:
        print(json.dumps(output, indent=2))

    return output


# ── Report (no-emoji) ─────────────────────────────────────────────────────
def report(density_path: str):
    """Print human-readable density report (text chips, no emoji)."""
    with open(density_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    print(f"\n{'='*60}")
    print(f"DENSITY HEATMAP — {data['transcript']}")
    mode = data.get("mode", "scanner")
    print(f"Mode: {mode} | Total tokens: {data['total_tokens']:,} | Segments: {data['num_segments']}")
    print(f"{'='*60}\n")

    bar_width = 30
    max_density = max(s["density_per_1k"] for s in data["segments"]) or 1

    level_chip = {"HIGH": "[HIGH]", "MEDIUM": "[ MED]", "LOW": "[ LOW]"}

    for seg in data["segments"]:
        filled = int((seg["density_per_1k"] / max_density) * bar_width) if max_density > 0 else 0
        bar = "#" * filled + "-" * (bar_width - filled)
        chip = level_chip.get(seg["level"], "[   ?]")

        print(f"  Seg {seg['segment']:2d}  {chip} [{bar}] {seg['density_per_1k']:.1f}/1k tokens")
        c = seg["claims"]
        if mode == "scratchpad":
            print(f"          {seg['tokens']:,} tokens ({seg['token_pct']}%) | "
                  f"matched: {c.get('claims_matched', 0)} | "
                  f"impact: {c.get('impact_sum', 0)} | "
                  f"implicit: {c.get('implicit_claims', 0)}")
        else:
            print(f"          {seg['tokens']:,} tokens ({seg['token_pct']}%) | "
                  f"numerics: {c.get('numerics', 0)} | "
                  f"pivots: {c.get('pivots', 0)}")
        print()

    print(f"  >> {data['rewatch_note']}")
    print()


# ── CLI ───────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Topic density scanner for transcripts")
    subparsers = parser.add_subparsers(dest="command")

    scan_p = subparsers.add_parser("scan", help="Analyze transcript density")
    scan_p.add_argument("transcript", help="Path to transcript text file")
    scan_p.add_argument("scanner_json", help="Path to five_pass_scanner output JSON")
    scan_p.add_argument("--output", "-o", help="Output JSON path")
    scan_p.add_argument("--segments", "-n", type=int, help="Number of segments (auto if omitted)")
    scan_p.add_argument("--scratchpad", "-s", help="Path to Phase-1 scratchpad (preferred source)")

    report_p = subparsers.add_parser("report", help="Print density report")
    report_p.add_argument("density_json", help="Path to density JSON from scan command")

    args = parser.parse_args()

    if args.command == "scan":
        scan(args.transcript, args.scanner_json, args.output,
             args.segments, getattr(args, "scratchpad", None))
    elif args.command == "report":
        report(args.density_json)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
