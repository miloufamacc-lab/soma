#!/usr/bin/env python3
"""
PRISM — Pipeline for Raw Intelligence Sorting & Materiality
Pipeline: SOMA/PRISM | Module: SOMA | Status: PLANNED (this tool is built; full PRISM pipeline pending)

DABEIBA — Universal YouTube Transcript Extractor

Extracts transcripts from any YouTube video (short or multi-hour),
formats them for CIPHER ingestion, and optionally writes to SOMA.

Usage:
    python3 youtube_extractor.py <URL_or_ID>
    python3 youtube_extractor.py <URL_or_ID> --summary
    python3 youtube_extractor.py <URL_or_ID> --chunks 3000
    python3 youtube_extractor.py <URL_or_ID> --output /path/to/file.txt
    python3 youtube_extractor.py <URL_or_ID> --json

Supports:
    - Any YouTube URL format (regular, short, embed, playlist item)
    - Any video length (2 min to 8+ hours)
    - Auto-selects best available language (prefers English manual captions)
    - Chunked output for long videos (configurable token target per chunk)
    - Timestamped segments for easy reference
    - JSON output mode for programmatic use
    - Plain text output mode for CIPHER paste-in

Dependencies:
    pip install youtube-transcript-api
"""

import argparse
import json
import os
import re
import sys
import textwrap
from datetime import datetime
from pathlib import Path

try:
    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api.formatters import TextFormatter
except ImportError:
    print("ERROR: youtube-transcript-api not installed.")
    print("Run: pip install youtube-transcript-api")
    sys.exit(1)


# ── Helpers ───────────────────────────────────────────────────────────────

def extract_video_id(url_or_id: str) -> str:
    """Extract YouTube video ID from any URL format or raw ID."""
    # Already a raw ID (11 chars, no slashes)
    if re.match(r'^[A-Za-z0-9_-]{11}$', url_or_id):
        return url_or_id

    # Standard patterns
    patterns = [
        r'(?:youtube\.com/watch\?.*v=)([A-Za-z0-9_-]{11})',
        r'(?:youtu\.be/)([A-Za-z0-9_-]{11})',
        r'(?:youtube\.com/embed/)([A-Za-z0-9_-]{11})',
        r'(?:youtube\.com/v/)([A-Za-z0-9_-]{11})',
        r'(?:youtube\.com/shorts/)([A-Za-z0-9_-]{11})',
        r'(?:youtube\.com/live/)([A-Za-z0-9_-]{11})',
    ]
    for pattern in patterns:
        match = re.search(pattern, url_or_id)
        if match:
            return match.group(1)

    # Last resort: look for 11-char alphanumeric sequence
    match = re.search(r'([A-Za-z0-9_-]{11})', url_or_id)
    if match:
        return match.group(1)

    raise ValueError(f"Could not extract video ID from: {url_or_id}")


def format_timestamp(seconds: float) -> str:
    """Convert seconds to HH:MM:SS or MM:SS."""
    seconds = int(seconds)
    h, remainder = divmod(seconds, 3600)
    m, s = divmod(remainder, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 chars per token for English)."""
    return len(text) // 4


# ── Core extraction ───────────────────────────────────────────────────────

def get_transcript(video_id: str, preferred_lang: str = "en") -> dict:
    """
    Fetch the best available transcript for a video.

    Priority:
    1. Manual captions in preferred language
    2. Auto-generated captions in preferred language
    3. Manual captions in any language
    4. Auto-generated captions in any language

    Returns dict with keys: segments, language, is_generated, video_id
    """
    ytt = YouTubeTranscriptApi()
    transcript_list = ytt.list(video_id)

    # Try manual captions in preferred language first
    try:
        transcript = transcript_list.find_manually_created_transcript([preferred_lang])
        segments = transcript.fetch()
        return {
            "segments": segments,
            "language": transcript.language_code,
            "is_generated": False,
            "video_id": video_id,
        }
    except Exception as e:
        pass

    # Try auto-generated in preferred language
    try:
        transcript = transcript_list.find_generated_transcript([preferred_lang])
        segments = transcript.fetch()
        return {
            "segments": segments,
            "language": transcript.language_code,
            "is_generated": True,
            "video_id": video_id,
        }
    except Exception as e:
        pass

    # Try any available transcript (manual first)
    for transcript in transcript_list:
        try:
            segments = transcript.fetch()
            return {
                "segments": segments,
                "language": transcript.language_code,
                "is_generated": transcript.is_generated,
                "video_id": video_id,
            }
        except Exception as e:
            continue

    raise RuntimeError(f"No transcript available for video: {video_id}")


# ── Formatting ────────────────────────────────────────────────────────────

def segments_to_timestamped_text(segments: list) -> str:
    """Convert segments to timestamped plain text."""
    lines = []
    for seg in segments:
        ts = format_timestamp(seg.start)
        text = seg.text.strip()
        if text:
            lines.append(f"[{ts}] {text}")
    return "\n".join(lines)


def segments_to_plain_text(segments: list) -> str:
    """Convert segments to flowing plain text (no timestamps)."""
    parts = []
    for seg in segments:
        text = seg.text.strip()
        if text:
            parts.append(text)
    # Join and clean up double spaces
    raw = " ".join(parts)
    raw = re.sub(r'\s+', ' ', raw)
    return raw


def segments_to_paragraphs(segments: list, gap_threshold: float = 4.0) -> str:
    """
    Convert segments to paragraphed text.
    Inserts paragraph breaks when there's a gap > threshold seconds
    between segments (indicating a pause/topic change).
    """
    paragraphs = []
    current_paragraph = []

    for i, seg in enumerate(segments):
        text = seg.text.strip()
        if not text:
            continue

        # Check for gap from previous segment
        if i > 0 and current_paragraph:
            prev = segments[i - 1]
            prev_end = prev.start + prev.duration
            gap = seg.start - prev_end
            if gap > gap_threshold:
                paragraphs.append(" ".join(current_paragraph))
                current_paragraph = []

        current_paragraph.append(text)

    # Don't forget the last paragraph
    if current_paragraph:
        paragraphs.append(" ".join(current_paragraph))

    return "\n\n".join(paragraphs)


def chunk_segments(segments: list, target_tokens: int = 3000) -> list:
    """
    Split segments into chunks of approximately target_tokens each.
    Each chunk includes start/end timestamps.

    Returns list of dicts: {start_time, end_time, text, token_estimate}
    """
    chunks = []
    current_texts = []
    current_tokens = 0
    chunk_start = 0.0

    for seg in segments:
        text = seg.text.strip()
        if not text:
            continue

        seg_tokens = estimate_tokens(text)

        # Start new chunk if this would exceed target
        if current_tokens > 0 and current_tokens + seg_tokens > target_tokens:
            chunks.append({
                "start_time": format_timestamp(chunk_start),
                "end_time": format_timestamp(seg.start),
                "text": " ".join(current_texts),
                "token_estimate": current_tokens,
            })
            current_texts = []
            current_tokens = 0
            chunk_start = seg.start

        if not current_texts:
            chunk_start = seg.start

        current_texts.append(text)
        current_tokens += seg_tokens

    # Final chunk
    if current_texts:
        last_seg = segments[-1]
        chunks.append({
            "start_time": format_timestamp(chunk_start),
            "end_time": format_timestamp(last_seg.start + last_seg.duration),
            "text": " ".join(current_texts),
            "token_estimate": current_tokens,
        })

    return chunks


# ── Output formatters ─────────────────────────────────────────────────────

def format_cipher_output(result: dict, mode: str = "paragraphs",
                         chunk_size: int = 0) -> str:
    """
    Format transcript for CIPHER ingestion.

    Modes:
        paragraphs  — flowing text with paragraph breaks at pauses
        timestamped — every line has a [MM:SS] prefix
        plain       — single continuous text block
        chunks      — split into numbered sections with timestamps
    """
    segments = result["segments"]
    video_id = result["video_id"]
    lang = result["language"]
    generated = "auto-generated" if result["is_generated"] else "manual"

    total_duration = 0
    if segments:
        last = segments[-1]
        total_duration = last.start + last.duration

    total_words = sum(len(seg.text.split()) for seg in segments)

    # Header
    header = (
        f"--- YOUTUBE TRANSCRIPT ---\n"
        f"Video: https://youtube.com/watch?v={video_id}\n"
        f"Duration: {format_timestamp(total_duration)}\n"
        f"Words: {total_words:,}\n"
        f"Language: {lang} ({generated})\n"
        f"Extracted: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        f"--------------------------\n\n"
    )

    if mode == "chunks" or (chunk_size > 0):
        target = chunk_size if chunk_size > 0 else 3000
        chunks = chunk_segments(segments, target_tokens=target)
        body_parts = []
        for i, chunk in enumerate(chunks, 1):
            body_parts.append(
                f"=== PART {i}/{len(chunks)} "
                f"[{chunk['start_time']} — {chunk['end_time']}] "
                f"(~{chunk['token_estimate']} tokens) ===\n\n"
                f"{chunk['text']}"
            )
        body = "\n\n".join(body_parts)
    elif mode == "timestamped":
        body = segments_to_timestamped_text(segments)
    elif mode == "plain":
        body = segments_to_plain_text(segments)
    else:  # paragraphs (default)
        body = segments_to_paragraphs(segments)

    # Footer with stats
    footer = (
        f"\n\n--- END TRANSCRIPT ---\n"
        f"Total: {len(segments)} segments, {total_words:,} words, "
        f"{format_timestamp(total_duration)} duration"
    )

    return header + body + footer


def format_json_output(result: dict, chunk_size: int = 0) -> dict:
    """Format transcript as structured JSON for programmatic use."""
    segments = result["segments"]
    total_duration = 0
    if segments:
        last = segments[-1]
        total_duration = last.start + last.duration

    output = {
        "video_id": result["video_id"],
        "url": f"https://youtube.com/watch?v={result['video_id']}",
        "language": result["language"],
        "is_auto_generated": result["is_generated"],
        "duration_seconds": round(total_duration),
        "duration_formatted": format_timestamp(total_duration),
        "word_count": sum(len(seg.text.split()) for seg in segments),
        "segment_count": len(segments),
        "extracted_at": datetime.now().isoformat(),
    }

    if chunk_size > 0:
        output["chunks"] = chunk_segments(segments, target_tokens=chunk_size)
    else:
        output["full_text"] = segments_to_paragraphs(segments)
        output["segments"] = [
            {
                "start": round(seg.start, 1),
                "duration": round(seg.duration, 1),
                "text": seg.text.strip(),
            }
            for seg in segments
            if seg.text.strip()
        ]

    return output


# ── CLI ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="DABEIBA — Universal YouTube Transcript Extractor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples:
              %(prog)s "https://youtube.com/watch?v=abc123"
              %(prog)s abc123 --mode timestamped
              %(prog)s abc123 --chunks 3000 --output transcript.txt
              %(prog)s abc123 --json --output data.json
              %(prog)s abc123 --lang fr
        """))

    parser.add_argument("url", help="YouTube URL or video ID")
    parser.add_argument("--mode", choices=["paragraphs", "timestamped", "plain", "chunks"],
                        default="paragraphs",
                        help="Output format (default: paragraphs)")
    parser.add_argument("--chunks", type=int, default=0, metavar="TOKENS",
                        help="Split into chunks of ~N tokens (implies --mode chunks)")
    parser.add_argument("--json", action="store_true",
                        help="Output as JSON instead of plain text")
    parser.add_argument("--output", "-o", metavar="FILE",
                        help="Write output to file instead of stdout")
    parser.add_argument("--lang", default="en",
                        help="Preferred language code (default: en)")
    parser.add_argument("--quiet", "-q", action="store_true",
                        help="Suppress progress messages on stderr")

    args = parser.parse_args()

    # Extract video ID
    try:
        video_id = extract_video_id(args.url)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    if not args.quiet:
        print(f"Extracting transcript for: {video_id}", file=sys.stderr)

    # Fetch transcript
    try:
        result = get_transcript(video_id, preferred_lang=args.lang)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    segments = result["segments"]
    total_duration = 0
    if segments:
        last = segments[-1]
        total_duration = last.start + last.duration

    if not args.quiet:
        word_count = sum(len(seg.text.split()) for seg in segments)
        print(
            f"  Language: {result['language']} "
            f"({'auto' if result['is_generated'] else 'manual'})",
            file=sys.stderr)
        print(
            f"  Duration: {format_timestamp(total_duration)} | "
            f"Words: {word_count:,} | "
            f"Segments: {len(segments)}",
            file=sys.stderr)

    # Format output
    if args.json:
        output = json.dumps(
            format_json_output(result, chunk_size=args.chunks),
            indent=2, ensure_ascii=False)
    else:
        mode = "chunks" if args.chunks > 0 else args.mode
        output = format_cipher_output(
            result, mode=mode, chunk_size=args.chunks)

    # Write or print
    if args.output:
        out_path = Path(args.output)
        out_path.write_text(output, encoding="utf-8")
        if not args.quiet:
            print(f"  Written to: {out_path}", file=sys.stderr)
    else:
        print(output)

    if not args.quiet:
        print("  Done.", file=sys.stderr)


if __name__ == "__main__":
    main()
