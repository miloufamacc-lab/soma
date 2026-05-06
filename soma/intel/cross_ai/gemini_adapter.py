"""
SOMA-INTEL Phase 7.I1.4 — Gemini Corroboration Adapter

Reads Gemini Deep Research output files and ingests them as cross-AI corroboration
flags via IntelStore.insert_cross_ai_flag().

Expected input format (JSON, one file per Gemini session):
    {
      "generated_at": "2026-05-05T08:00:00Z",   // ISO 8601
      "source": "gemini_deep_research",
      "flags": [
        {
          "ticker":       "PLTR",
          "signal_type":  "thematic",
          "direction":    "bullish",
          "confidence":   0.82,
          "evidence":     "AI government contract expansion confirmed Q1 2026...",
          "ts":           "2026-05-05T08:00:00Z"
        },
        ...
      ]
    }

Expected file location:
    ~/Desktop/DABEIBA/oracle/output/gemini_flags_YYYY-MM-DD.json
    (one file per day; manual export from Gemini Deep Research or automated pipeline)

STATUS: STUB — no source files found at expected path as of 2026-05-05.
Adapter returns 0 flags ingested with a clear log message.
Once a pipeline writes gemini_flags files, update GEMINI_OUTPUT_GLOB below.

Idempotency: duplicate flags (same ticker + signal_type + ts) are skipped by
IntelStore.insert_cross_ai_flag() — safe to re-run on the same file.
"""

from __future__ import annotations

import glob
import json
import logging
import os
from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from soma.intel.store import IntelStore

log = logging.getLogger(__name__)

_DABEIBA_ROOT = Path(os.environ.get(
    "DABEIBA_ROOT",
    str(Path.home() / "Desktop" / "DABEIBA"),
))

GEMINI_OUTPUT_DIR  = _DABEIBA_ROOT / "oracle" / "output"
GEMINI_OUTPUT_GLOB = "gemini_flags_*.json"

_LOOKBACK_DAYS = 3


def ingest_gemini(
    store:   "IntelStore",
    dry_run: bool = False,
    verbose: bool = False,
) -> dict:
    """
    Ingest Gemini Deep Research corroboration flags into SOMA-INTEL.

    Args:
        store:    Open IntelStore context.
        dry_run:  If True, parse and log without writing to DB.
        verbose:  If True, log each flag processed.

    Returns:
        dict: files_scanned, flags_found, flags_inserted, flags_skipped, errors.
    """
    cutoff = (date.today() - timedelta(days=_LOOKBACK_DAYS)).isoformat()
    pattern = str(GEMINI_OUTPUT_DIR / GEMINI_OUTPUT_GLOB)
    files = sorted(glob.glob(pattern))

    result = {"files_scanned": 0, "flags_found": 0,
              "flags_inserted": 0, "flags_skipped": 0, "errors": 0}

    if not files:
        log.info(
            "gemini_adapter: no files found at %s — "
            "a Gemini Deep Research export pipeline must write "
            "gemini_flags_YYYY-MM-DD.json before this adapter can ingest. "
            "Returning 0 flags ingested.",
            pattern,
        )
        return result

    for filepath in files:
        fname = os.path.basename(filepath)
        try:
            file_date = fname.replace("gemini_flags_", "").replace(".json", "")
            if file_date < cutoff:
                log.debug("gemini_adapter: skipping old file %s (< %s)", fname, cutoff)
                continue
        except Exception:
            pass

        result["files_scanned"] += 1
        try:
            with open(filepath, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
        except Exception as exc:
            log.error("gemini_adapter: failed to parse %s: %s", filepath, exc)
            result["errors"] += 1
            continue

        flags = payload.get("flags", [])
        for flag in flags:
            result["flags_found"] += 1
            ticker      = (flag.get("ticker") or "").strip().upper()
            signal_type = (flag.get("signal_type") or "tactical").strip().lower()
            direction   = (flag.get("direction") or "neutral").strip().lower()
            confidence  = float(flag.get("confidence") or 0.0)
            evidence    = (flag.get("evidence") or "")[:500]
            ts          = flag.get("ts") or payload.get("generated_at") or ""

            if not ticker or not ts:
                log.debug("gemini_adapter: skipping flag missing ticker/ts: %s", flag)
                result["flags_skipped"] += 1
                continue
            if confidence < 0.30:
                log.debug(
                    "gemini_adapter: skipping low-confidence flag ticker=%s conf=%.2f",
                    ticker, confidence,
                )
                result["flags_skipped"] += 1
                continue

            if verbose:
                log.info(
                    "gemini_adapter: %s flag ticker=%s signal=%s dir=%s conf=%.2f",
                    "DRY-RUN" if dry_run else "INGEST",
                    ticker, signal_type, direction, confidence,
                )

            if dry_run:
                result["flags_inserted"] += 1
                continue

            try:
                _flag_id, is_new = store.insert_cross_ai_flag(
                    ai_source="gemini",
                    ticker=ticker,
                    signal_type=signal_type,
                    direction=direction,
                    confidence=confidence,
                    ts=ts,
                    evidence_text=evidence or None,
                    source_path=filepath,
                    half_life_days=14,
                )
                if is_new:
                    result["flags_inserted"] += 1
                else:
                    result["flags_skipped"] += 1
                    log.debug(
                        "gemini_adapter: duplicate skipped ticker=%s ts=%s",
                        ticker, ts,
                    )
            except Exception as exc:
                log.error(
                    "gemini_adapter: insert failed ticker=%s ts=%s: %s",
                    ticker, ts, exc,
                )
                result["errors"] += 1

    log.info(
        "gemini_adapter: files=%d found=%d inserted=%d skipped=%d errors=%d",
        result["files_scanned"], result["flags_found"],
        result["flags_inserted"], result["flags_skipped"], result["errors"],
    )
    return result


def validate_gemini(filepath: str) -> dict:
    """
    Read-only schema validation for a Gemini flag file.

    Same structure as validate_grok — JSON file with top-level flags array.
    Writes nothing to the DB.

    Args:
        filepath: Absolute path to a gemini_flags_YYYY-MM-DD.json file.

    Returns:
        dict with keys: valid, flags_found, flags_valid, flags_skipped, errors, flags.
    """
    result: dict = {
        "valid": False,
        "flags_found": 0,
        "flags_valid": 0,
        "flags_skipped": 0,
        "errors": [],
        "flags": [],
    }

    try:
        with open(filepath, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except Exception as exc:
        result["errors"].append(f"Parse error: {exc}")
        return result

    for field in ("generated_at", "source", "flags"):
        if field not in payload:
            result["errors"].append(f"Missing top-level field: {field!r}")
    if result["errors"]:
        return result

    flags = payload.get("flags", [])
    result["flags_found"] = len(flags)

    _valid_directions = {"bullish", "bearish", "neutral"}
    _valid_signal_types = {"tactical", "thematic", "structural"}

    for i, flag in enumerate(flags):
        ticker      = (flag.get("ticker") or "").strip().upper()
        signal_type = (flag.get("signal_type") or "").strip().lower()
        direction   = (flag.get("direction") or "").strip().lower()
        confidence  = flag.get("confidence")
        ts          = flag.get("ts") or payload.get("generated_at") or ""

        flag_errors = []
        if not ticker:
            flag_errors.append(f"flag[{i}]: missing ticker")
        if not ts:
            flag_errors.append(f"flag[{i}]: missing ts")
        if direction not in _valid_directions:
            flag_errors.append(f"flag[{i}]: invalid direction {direction!r}")
        if signal_type not in _valid_signal_types:
            flag_errors.append(f"flag[{i}]: invalid signal_type {signal_type!r}")
        if confidence is None:
            flag_errors.append(f"flag[{i}]: missing confidence")
        elif not (0.0 <= float(confidence) <= 1.0):
            flag_errors.append(f"flag[{i}]: confidence {confidence} out of [0,1]")

        if flag_errors:
            result["errors"].extend(flag_errors)
            result["flags_skipped"] += 1
            continue

        if float(confidence) < 0.30:
            result["flags_skipped"] += 1
            continue

        result["flags_valid"] += 1
        result["flags"].append({
            "ticker": ticker,
            "signal_type": signal_type,
            "direction": direction,
            "confidence": float(confidence),
            "ts": ts,
            "evidence": (flag.get("evidence") or "")[:500],
        })

    result["valid"] = len(result["errors"]) == 0
    log.info(
        "validate_gemini: %s found=%d valid=%d skipped=%d errors=%d",
        filepath, result["flags_found"], result["flags_valid"],
        result["flags_skipped"], len(result["errors"]),
    )
    return result
