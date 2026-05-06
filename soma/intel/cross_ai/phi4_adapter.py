"""
SOMA-INTEL Phase 7.I1.4 — Phi-4 Mini (Local) Corroboration Adapter

Reads Phi-4 Mini classification output files and ingests them as cross-AI
corroboration flags via IntelStore.insert_cross_ai_flag().

Phi-4 Mini (3.8B, Ollama, http://localhost:11434) is used in CIPHER INTEL for
tagging and summarization. Its outputs are currently in-memory only — there is
no filesystem sink for Phi-4 classification results as of 2026-05-05.

Expected input format (JSONL, one line per classification):
    {"ticker":"TSLA","signal_type":"tactical","direction":"bullish","confidence":0.65,"evidence":"FSD v13 adoption rate accelerating...","ts":"2026-05-05T06:00:00Z"}
    {"ticker":"IREN","signal_type":"tactical","direction":"bullish","confidence":0.71,"evidence":"Hash rate growth above consensus...","ts":"2026-05-05T06:00:00Z"}

Expected file location:
    ~/Desktop/DABEIBA/oracle/output/phi4_flags_YYYY-MM-DD.jsonl
    (one JSONL file per day; written by CIPHER INTEL if configured to export flags)

STATUS: STUB — no source files found at expected path as of 2026-05-05.
Phi-4 outputs are currently in-memory only. To activate this adapter:
  1. Add a file-export step to CIPHER INTEL's tagging pipeline
  2. Write output to the path above in the JSONL format documented here
  3. Remove the stub guard below

Confidence calibration note: Phi-4 Mini has higher hallucination rates than
frontier models. Apply a 0.85x calibration multiplier to stated confidence before
inserting (per soma_intel_source_calibration when available). Default minimum
confidence threshold: 0.40 (higher than grok/gemini default of 0.30).

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

PHI4_OUTPUT_DIR  = _DABEIBA_ROOT / "oracle" / "output"
PHI4_OUTPUT_GLOB = "phi4_flags_*.jsonl"

_LOOKBACK_DAYS = 3

# Phi-4 confidence calibration multiplier (conservative — higher hallucination rate)
_PHI4_CALIBRATION = 0.85
_PHI4_MIN_CONFIDENCE = 0.40   # higher bar than grok/gemini (0.30)


def ingest_phi4(
    store:   "IntelStore",
    dry_run: bool = False,
    verbose: bool = False,
) -> dict:
    """
    Ingest Phi-4 Mini corroboration flags into SOMA-INTEL.

    Args:
        store:    Open IntelStore context.
        dry_run:  If True, parse and log without writing to DB.
        verbose:  If True, log each flag processed.

    Returns:
        dict: files_scanned, flags_found, flags_inserted, flags_skipped, errors.
    """
    cutoff = (date.today() - timedelta(days=_LOOKBACK_DAYS)).isoformat()
    pattern = str(PHI4_OUTPUT_DIR / PHI4_OUTPUT_GLOB)
    files = sorted(glob.glob(pattern))

    result = {"files_scanned": 0, "flags_found": 0,
              "flags_inserted": 0, "flags_skipped": 0, "errors": 0}

    if not files:
        log.info(
            "phi4_adapter: no files found at %s — "
            "CIPHER INTEL must be configured to export phi4_flags_YYYY-MM-DD.jsonl "
            "before this adapter can ingest. Returning 0 flags ingested.",
            pattern,
        )
        return result

    for filepath in files:
        fname = os.path.basename(filepath)
        try:
            file_date = fname.replace("phi4_flags_", "").replace(".jsonl", "")
            if file_date < cutoff:
                log.debug("phi4_adapter: skipping old file %s (< %s)", fname, cutoff)
                continue
        except Exception:
            pass

        result["files_scanned"] += 1
        try:
            with open(filepath, "r", encoding="utf-8") as fh:
                lines = [line.strip() for line in fh if line.strip()]
        except Exception as exc:
            log.error("phi4_adapter: failed to read %s: %s", filepath, exc)
            result["errors"] += 1
            continue

        for line in lines:
            result["flags_found"] += 1
            try:
                flag = json.loads(line)
            except json.JSONDecodeError as exc:
                log.debug("phi4_adapter: invalid JSON line: %s — %s", line[:80], exc)
                result["errors"] += 1
                continue

            ticker      = (flag.get("ticker") or "").strip().upper()
            signal_type = (flag.get("signal_type") or "tactical").strip().lower()
            direction   = (flag.get("direction") or "neutral").strip().lower()
            raw_conf    = float(flag.get("confidence") or 0.0)
            confidence  = round(raw_conf * _PHI4_CALIBRATION, 4)
            evidence    = (flag.get("evidence") or "")[:500]
            ts          = flag.get("ts") or ""

            if not ticker or not ts:
                log.debug("phi4_adapter: skipping flag missing ticker/ts: %s", flag)
                result["flags_skipped"] += 1
                continue
            if confidence < _PHI4_MIN_CONFIDENCE:
                log.debug(
                    "phi4_adapter: skipping low-confidence flag ticker=%s "
                    "raw_conf=%.2f calibrated=%.2f (min=%.2f)",
                    ticker, raw_conf, confidence, _PHI4_MIN_CONFIDENCE,
                )
                result["flags_skipped"] += 1
                continue

            if verbose:
                log.info(
                    "phi4_adapter: %s flag ticker=%s signal=%s dir=%s "
                    "raw_conf=%.2f cal_conf=%.2f",
                    "DRY-RUN" if dry_run else "INGEST",
                    ticker, signal_type, direction, raw_conf, confidence,
                )

            if dry_run:
                result["flags_inserted"] += 1
                continue

            try:
                _flag_id, is_new = store.insert_cross_ai_flag(
                    ai_source="phi4",
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
                        "phi4_adapter: duplicate skipped ticker=%s ts=%s",
                        ticker, ts,
                    )
            except Exception as exc:
                log.error(
                    "phi4_adapter: insert failed ticker=%s ts=%s: %s",
                    ticker, ts, exc,
                )
                result["errors"] += 1

    log.info(
        "phi4_adapter: files=%d found=%d inserted=%d skipped=%d errors=%d",
        result["files_scanned"], result["flags_found"],
        result["flags_inserted"], result["flags_skipped"], result["errors"],
    )
    return result


def validate_phi4(filepath: str) -> dict:
    """
    Read-only schema validation for a Phi-4 flag file (JSONL format).

    Phi-4 uses JSONL (one JSON object per line) rather than a top-level array.
    Applies the same field checks as ingest_phi4 plus the 0.85x calibration
    multiplier, but writes nothing to the DB.

    Args:
        filepath: Absolute path to a phi4_flags_YYYY-MM-DD.jsonl file.

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
            lines = [ln.strip() for ln in fh if ln.strip()]
    except Exception as exc:
        result["errors"].append(f"Read error: {exc}")
        return result

    if not lines:
        result["errors"].append("File is empty — no JSONL lines found")
        return result

    _valid_directions = {"bullish", "bearish", "neutral"}
    _valid_signal_types = {"tactical", "thematic", "structural"}

    for i, line in enumerate(lines):
        try:
            flag = json.loads(line)
        except Exception as exc:
            result["errors"].append(f"line[{i}]: JSON parse error: {exc}")
            result["flags_skipped"] += 1
            continue

        result["flags_found"] += 1
        ticker      = (flag.get("ticker") or "").strip().upper()
        signal_type = (flag.get("signal_type") or "").strip().lower()
        direction   = (flag.get("direction") or "").strip().lower()
        confidence  = flag.get("confidence")
        ts          = flag.get("ts") or ""

        flag_errors = []
        if not ticker:
            flag_errors.append(f"line[{i}]: missing ticker")
        if not ts:
            flag_errors.append(f"line[{i}]: missing ts")
        if direction not in _valid_directions:
            flag_errors.append(f"line[{i}]: invalid direction {direction!r}")
        if signal_type not in _valid_signal_types:
            flag_errors.append(f"line[{i}]: invalid signal_type {signal_type!r}")
        if confidence is None:
            flag_errors.append(f"line[{i}]: missing confidence")
        elif not (0.0 <= float(confidence) <= 1.0):
            flag_errors.append(f"line[{i}]: confidence {confidence} out of [0,1]")

        if flag_errors:
            result["errors"].extend(flag_errors)
            result["flags_skipped"] += 1
            continue

        # Apply Phi-4 calibration multiplier (conservative — higher hallucination rate)
        calibrated_conf = float(confidence) * _PHI4_CALIBRATION
        if calibrated_conf < 0.40:
            result["flags_skipped"] += 1
            continue

        result["flags_valid"] += 1
        result["flags"].append({
            "ticker": ticker,
            "signal_type": signal_type,
            "direction": direction,
            "confidence": round(calibrated_conf, 4),
            "confidence_raw": float(confidence),
            "ts": ts,
            "evidence": (flag.get("evidence") or "")[:500],
        })

    result["valid"] = len(result["errors"]) == 0
    log.info(
        "validate_phi4: %s found=%d valid=%d skipped=%d errors=%d",
        filepath, result["flags_found"], result["flags_valid"],
        result["flags_skipped"], len(result["errors"]),
    )
    return result
