"""
SOMA-INTEL Phase 7.I1W-G — Grok Flag Extractor

Parses a MUSKONOMY daily SITREP HTML (oracle/output/muskonomy_sitrep_YYYY-MM-DD.html)
and extracts Grok-generated ticker calls into the canonical cross-AI corroboration
format (oracle/output/grok_flags_YYYY-MM-DD.json) that grok_adapter.ingest_grok()
already validates and ingests.

This module is READ-ONLY on the SITREP HTML. It never modifies MUSKONOMY.
It is decoupled: MUSKONOMY runs first, writes HTML, then this extractor runs.

IMPORTANT: Capability cross_ai_corroboration stays DEFAULT OFF.
This extractor produces the JSON; grok_adapter.ingest_grok gates DB writes behind
the capability flag. No rows land in soma_intel_cross_ai_flag until the user
explicitly enables the capability.

Usage:
    python3 -m soma.intel.cross_ai.grok_flag_extractor \\
        --date 2026-05-06 [--input <html>] [--output <json>] [--overwrite]

Output schema (matches grok_adapter.validate_grok expectations):
    {
      "generated_at": "2026-05-06T07:00:00Z",   # MUSKONOMY runs at 7AM ET
      "source": "grok_deepsearch",
      "run_date": "2026-05-06",
      "extracted_ts": "2026-05-06T08:15:00Z",    # when this extractor ran
      "source_path": "/path/to/muskonomy_sitrep_2026-05-06.html",
      "flags": [
        {
          "ticker":      "TSLA",
          "signal_type": "tactical",             # tactical | thematic | structural
          "direction":   "bullish",              # bullish | bearish | neutral
          "confidence":  0.72,                   # [0, 1] — see calibration table below
          "ts":          "2026-05-06T07:00:00Z",
          "evidence":    "..."                   # <= 500 chars, from seg-note or signal-text
        }
      ]
    }

Confidence calibration table:
    Badge / tone                                     | Range
    -------------------------------------------------|-------------
    badge-bull + high-conviction keywords            | 0.75 – 0.85
      (confirmed, live, mass production, record,
       on track, rolling out, rolling broadly)
    badge-bull + standard factual claim              | 0.60 – 0.70
    badge-bull + speculative / forward-looking       | 0.45 – 0.55
      (anticipated, expected, target, if X, may)
    badge-neu / neutral                              | 0.45 – 0.55
    badge-bear + factual bearish claim               | 0.55 – 0.65
    badge-bear + speculative risk / may slip         | 0.40 – 0.50

Segment → signal_type map:
    AUTO, ENERGY, SERVICES           → structural  (business fundamentals)
    ROBOTAXI, FSD                    → tactical    (near-term operational)
    OPTIMUS, DIGITAL OPTIMUS, TERAFAB → thematic   (long-term thesis)
    Signals section rows              → tactical   (breaking news / insider)

HTML format resilience:
    The SITREP HTML format evolved across dates. This extractor handles
    all observed variants via prioritised fallback selector chains:

    | Date range       | Card cls     | Title cls    | Evidence cls         |
    |------------------|--------------|--------------|----------------------|
    | 2026-04-27       | seg-card     | seg-name     | seg-metric (joined)  |
    | 2026-05-01/02    | segment-card | segment-name | segment-delta        |
    | 2026-05-05       | seg-card     | seg-title    | seg-body             |
    | 2026-05-06+      | seg-card     | seg-title    | seg-note             |
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

# ── Path constants ──────────────────────────────────────────────────────────────
_DABEIBA_ROOT = Path(os.environ.get(
    "DABEIBA_ROOT",
    str(Path.home() / "Desktop" / "DABEIBA"),
))
_ORACLE_OUTPUT = _DABEIBA_ROOT / "oracle" / "output"


# ── Segment → signal_type map ───────────────────────────────────────────────────
_SEGMENT_SIGNAL_TYPE: dict[str, str] = {
    "AUTO":            "structural",
    "ENERGY":          "structural",
    "SERVICES":        "structural",
    "ROBOTAXI":        "tactical",
    "FSD":             "tactical",
    "OPTIMUS":         "thematic",
    "DIGITAL OPTIMUS": "thematic",
    "TERAFAB":         "thematic",
}

# ── High-conviction keywords that boost confidence ─────────────────────────────
_HIGH_CONVICTION_RE = re.compile(
    r"\b(confirmed|live|mass production|mass prod|record|rolling out|"
    r"rolling broadly|on track|launched|complete|deployed|ramping|"
    r"groundbreaking|milestone|cross[e]?[sd]|beat|rebound|universal)\b",
    re.IGNORECASE,
)

# ── Speculative keywords that lower confidence ──────────────────────────────────
_SPECULATIVE_RE = re.compile(
    r"\b(anticipated|expected|target[s]?|if [a-z]|may slip|may delay|"
    r"at risk|speculative|pending|awaiting|TBD|rumored|likely|could|"
    r"projected|timeline risk|planning|seeking|pushing|aiming)\b",
    re.IGNORECASE,
)


# ── Direction normalisation ─────────────────────────────────────────────────────
# Maps CSS class names → canonical direction strings.
# Covers all observed SITREP format variants (2026-04-27 through 2026-05-06+).
_DIRECTION_CLASS_MAP: dict[str, str] = {
    # badge variants
    "badge-bull":     "bullish",
    "badge-bullish":  "bullish",
    "badge-bear":     "bearish",
    "badge-bearish":  "bearish",
    "badge-neu":      "neutral",
    "badge-neutral":  "neutral",
    "badge-watch":    "neutral",   # watch = informational, treat as neutral
    # signal dot variants
    "sig-bull":       "bullish",
    "sig-bear":       "bearish",
    "sig-neu":        "neutral",
    "sig-neutral":    "neutral",
    # signal icon variants (2026-05-02 style)
    "icon-green":     "bullish",
    "icon-red":       "bearish",
    "icon-blue":      "neutral",
    # direction embedded directly in card class (2026-04-27 style)
    "bullish":        "bullish",
    "bearish":        "bearish",
    "neutral":        "neutral",
}


def _class_to_direction(class_list: list[str]) -> Optional[str]:
    """Return the first direction found in the class list, or None."""
    for cls in (class_list or []):
        d = _DIRECTION_CLASS_MAP.get(cls)
        if d:
            return d
    return None


def _calibrate_confidence(direction: str, text: str) -> float:
    """
    Assign a confidence score based on direction and text cues.

    High-conviction keywords push toward the upper end of the range;
    speculative keywords push toward the lower end.
    """
    has_high = bool(_HIGH_CONVICTION_RE.search(text))
    has_spec = bool(_SPECULATIVE_RE.search(text))

    if direction == "bullish":
        base = 0.65
        if has_high and not has_spec:
            base = 0.78
        elif has_spec and not has_high:
            base = 0.48
    elif direction == "bearish":
        base = 0.58
        if has_spec:
            base = 0.43
    else:  # neutral
        base = 0.50

    return round(base, 2)


def _truncate(text: str, max_len: int = 500) -> str:
    """Truncate text to max_len characters, appending ellipsis if truncated."""
    text = text.strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"  # …


def _extract_run_ts(run_date: str) -> str:
    """Return the canonical MUSKONOMY run timestamp (7AM ET on run_date)."""
    return f"{run_date}T07:00:00Z"


def _get_evidence_from_card(card) -> Optional[str]:
    """
    Try multiple selector strategies to extract the evidence/narrative text
    from a segment card.  Returns None if nothing useful found.

    Priority order matches observed format evolution:
      1. .seg-note      (2026-05-06+, current format)
      2. .seg-body      (2026-05-05)
      3. .segment-delta (2026-05-01 / 2026-05-02)
      4. join all .seg-metric / .segment-metric divs (2026-04-27 bullet style)
    """
    for sel in (".seg-note", ".seg-body", ".segment-delta"):
        el = card.select_one(sel)
        if el:
            text = el.get_text(separator=" ", strip=True)
            if len(text) >= 30:
                return text

    # Bullet-style fallback: join all metric rows
    metrics = card.select(".seg-metric, .segment-metric")
    if metrics:
        joined = " | ".join(m.get_text(separator=" ", strip=True) for m in metrics)
        if len(joined) >= 30:
            return joined

    return None


def _get_title_from_card(card) -> Optional[str]:
    """
    Try multiple selector strategies to extract the segment name.
    Returns normalised uppercase name (e.g. "AUTO", "ROBOTAXI").
    """
    for sel in (".seg-title", ".seg-name", ".segment-name"):
        el = card.select_one(sel)
        if el:
            raw = el.get_text(separator=" ", strip=True)
            # Strip leading number + whitespace: "01   AUTO" / "1 — Auto" → "AUTO"
            cleaned = re.sub(r"^\d+\s*[—\-\.]?\s*", "", raw).strip().upper()
            if cleaned:
                return cleaned
    return None


def _get_direction_from_card(card) -> Optional[str]:
    """
    Try multiple strategies to extract direction from a segment card:
    1. .badge element inside the card
    2. Direction class on the card element itself (2026-04-27 style)
    """
    badge = card.select_one(".badge")
    if badge:
        d = _class_to_direction(badge.get("class", []))
        if d:
            return d
    # Fallback: direction embedded in card's own classes
    return _class_to_direction(card.get("class", []))


def _extract_segment_flags(soup: BeautifulSoup, run_ts: str) -> tuple[list[dict], dict]:
    """
    Extract one flag per segment card, using resilient selector fallbacks.

    Returns: (flags, skipped_reasons)
    """
    flags: list[dict] = []
    skipped: dict[str, int] = {}

    # Card selector: try current format first, then older format
    seg_cards = soup.select(".seg-card") or soup.select(".segment-card")

    for card in seg_cards:
        seg_name = _get_title_from_card(card)
        if not seg_name:
            skipped["missing_seg_title"] = skipped.get("missing_seg_title", 0) + 1
            continue

        direction = _get_direction_from_card(card)
        if direction is None:
            skipped["missing_direction"] = skipped.get("missing_direction", 0) + 1
            log.debug("grok_flag_extractor: no direction in segment %r — skipping", seg_name)
            continue

        evidence_raw = _get_evidence_from_card(card)
        if not evidence_raw:
            skipped["missing_evidence"] = skipped.get("missing_evidence", 0) + 1
            log.debug("grok_flag_extractor: no evidence in segment %r — skipping", seg_name)
            continue

        evidence = _truncate(evidence_raw)
        signal_type = _SEGMENT_SIGNAL_TYPE.get(seg_name, "tactical")
        confidence = _calibrate_confidence(direction, evidence_raw)

        flags.append({
            "ticker":      "TSLA",
            "signal_type": signal_type,
            "direction":   direction,
            "confidence":  confidence,
            "ts":          run_ts,
            "evidence":    evidence,
        })
        log.debug(
            "grok_flag_extractor: segment=%r dir=%s conf=%.2f type=%s",
            seg_name, direction, confidence, signal_type,
        )

    return flags, skipped


def _extract_signal_flags(soup: BeautifulSoup, run_ts: str) -> tuple[list[dict], dict]:
    """
    Extract one flag per market signal row, using resilient selector fallbacks.

    Handles all observed signal section variants:
      - .signal-row + .signal-dot (2026-05-06+, current format)
      - .signal-row + .signal-badge (2026-04-27)
      - .signal-item (2026-05-01 — no direction dot, skipped cleanly)
      - .signal-icon (2026-05-02 — direction encoded in icon colour class)

    Returns: (flags, skipped_reasons)
    """
    flags: list[dict] = []
    skipped: dict[str, int] = {}

    signal_rows = soup.select(".signal-row") or soup.select(".signal-item")

    for row in signal_rows:
        # Direction: try dot, badge, then icon selectors
        direction = None
        for dot_sel in (".signal-dot", ".signal-badge", ".signal-icon"):
            dot = row.select_one(dot_sel)
            if dot:
                direction = _class_to_direction(dot.get("class", []))
                if direction:
                    break

        if direction is None:
            skipped["ambiguous_signal_direction"] = (
                skipped.get("ambiguous_signal_direction", 0) + 1
            )
            log.debug("grok_flag_extractor: ambiguous signal direction — skipping")
            continue

        # Evidence text: .signal-text (current) or full row text minus meta
        text_el = row.select_one(".signal-text")
        if text_el:
            evidence_raw = text_el.get_text(separator=" ", strip=True)
        else:
            # Fallback: full row text, strip meta labels
            meta_el = row.select_one(".signal-meta, .signal-type, .signal-label")
            if meta_el:
                meta_el.extract()
            # Also remove icon/dot elements
            for sel in (".signal-dot", ".signal-badge", ".signal-icon"):
                for el in row.select(sel):
                    el.extract()
            evidence_raw = row.get_text(separator=" ", strip=True)

        if len(evidence_raw) < 30:
            skipped["signal_evidence_too_short"] = (
                skipped.get("signal_evidence_too_short", 0) + 1
            )
            continue

        evidence = _truncate(evidence_raw)
        confidence = _calibrate_confidence(direction, evidence_raw)

        flags.append({
            "ticker":      "TSLA",
            "signal_type": "tactical",
            "direction":   direction,
            "confidence":  confidence,
            "ts":          run_ts,
            "evidence":    evidence,
        })

    return flags, skipped


def extract_grok_flags(
    sitrep_html_path: str,
    run_date: str,
    output_path: Optional[str] = None,
    overwrite: bool = False,
) -> dict:
    """
    Parse a MUSKONOMY SITREP HTML, extract ticker calls, write grok_flags JSON.

    Args:
        sitrep_html_path: Absolute path to muskonomy_sitrep_YYYY-MM-DD.html
        run_date:         YYYY-MM-DD string matching the SITREP date
        output_path:      Optional override for output JSON path.
                          Defaults to oracle/output/grok_flags_<run_date>.json
        overwrite:        If False (default), refuses to overwrite an existing file
                          (exits with code 2). Pass True to allow overwrite.

    Returns:
        {
            extracted: int,   -- total flags written
            written:   int,   -- 1 if JSON written, 0 if skipped
            skipped_reasons: dict,
            output_path: str,
        }

    Read-only on SITREP HTML input. Idempotent JSON write (refuses overwrite
    without --overwrite flag).
    """
    # ── Resolve paths ───────────────────────────────────────────────────────────
    html_path = Path(sitrep_html_path)
    if not html_path.exists():
        msg = f"grok_flag_extractor: SITREP HTML not found: {html_path}"
        log.error(msg)
        sys.exit(f"ERROR: {msg}")

    if output_path is None:
        resolved_output = _ORACLE_OUTPUT / f"grok_flags_{run_date}.json"
    else:
        resolved_output = Path(output_path)

    if resolved_output.exists() and not overwrite:
        msg = (
            f"grok_flag_extractor: output already exists: {resolved_output}\n"
            "  Re-run with --overwrite to replace it."
        )
        log.error(msg)
        sys.exit(2)

    # ── Parse HTML ──────────────────────────────────────────────────────────────
    with open(html_path, "r", encoding="utf-8") as fh:
        soup = BeautifulSoup(fh, "html.parser")

    run_ts = _extract_run_ts(run_date)
    extracted_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # ── Extract flags ───────────────────────────────────────────────────────────
    seg_flags, seg_skipped = _extract_segment_flags(soup, run_ts)
    sig_flags, sig_skipped = _extract_signal_flags(soup, run_ts)
    all_flags = seg_flags + sig_flags

    # Merge skipped reasons
    all_skipped: dict[str, int] = {}
    for k, v in {**seg_skipped, **sig_skipped}.items():
        all_skipped[k] = all_skipped.get(k, 0) + v

    # ── Build output payload ────────────────────────────────────────────────────
    # generated_at + source are required by grok_adapter.validate_grok.
    # Extra fields (run_date, extracted_ts, source_path) are metadata only.
    payload = {
        "generated_at": run_ts,
        "source":        "grok_deepsearch",
        "run_date":      run_date,
        "extracted_ts":  extracted_ts,
        "source_path":   str(html_path),
        "flags":         all_flags,
    }

    # ── Write JSON ──────────────────────────────────────────────────────────────
    resolved_output.parent.mkdir(parents=True, exist_ok=True)
    with open(resolved_output, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)

    log.info(
        "grok_flag_extractor: wrote %d flags to %s (seg=%d sig=%d skipped=%s)",
        len(all_flags), resolved_output, len(seg_flags), len(sig_flags), all_skipped,
    )

    return {
        "extracted":       len(all_flags),
        "written":         1,
        "skipped_reasons": all_skipped,
        "output_path":     str(resolved_output),
    }


# ── CLI ─────────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Extract Grok ticker flags from a MUSKONOMY SITREP HTML.",
    )
    p.add_argument("--date", required=True, help="YYYY-MM-DD run date")
    p.add_argument(
        "--input",
        help="Path to SITREP HTML. Defaults to oracle/output/muskonomy_sitrep_<date>.html",
    )
    p.add_argument(
        "--output",
        help="Path for output JSON. Defaults to oracle/output/grok_flags_<date>.json",
    )
    p.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow overwriting an existing output file",
    )
    p.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    return p


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    # Resolve input HTML
    if args.input:
        html_path = args.input
    else:
        html_path = str(_ORACLE_OUTPUT / f"muskonomy_sitrep_{args.date}.html")

    result = extract_grok_flags(
        sitrep_html_path=html_path,
        run_date=args.date,
        output_path=args.output,
        overwrite=args.overwrite,
    )

    print(f"Extracted {result['extracted']} flags -> {result['output_path']}")
    if result["skipped_reasons"]:
        print(f"Skipped: {result['skipped_reasons']}")


if __name__ == "__main__":
    main()
