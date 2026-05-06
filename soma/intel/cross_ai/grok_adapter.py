"""
SOMA-INTEL Phase 7.I1.4 — Grok Corroboration Adapter

Reads Grok DeepSearch output files and ingests them as cross-AI corroboration
flags via IntelStore.insert_cross_ai_flag().

Expected input format (JSON, one file per Grok session):
    {
      "generated_at": "2026-05-05T07:15:00Z",   // ISO 8601
      "source": "grok_deepsearch",
      "flags": [
        {
          "ticker":       "TSLA",
          "signal_type":  "tactical",            // 'tactical'|'thematic'|'structural'
          "direction":    "bullish",             // 'bullish'|'bearish'|'neutral'
          "confidence":   0.78,                  // [0, 1]
          "evidence":     "Robotaxi deployment confirmed for Austin June 2025...",
          "ts":           "2026-05-05T07:00:00Z" // when Grok generated this flag
        },
        ...
      ]
    }

Expected file location:
    ~/Desktop/DABEIBA/oracle/output/grok_flags_YYYY-MM-DD.json
    (one file per day; MUSKONOMY daily SITREP writes here after its Chrome MCP run)

STATUS: STUB — no source files found at expected path as of 2026-05-05.
Adapter returns 0 flags ingested with a clear log message.
Once MUSKONOMY or another pipeline writes grok_flags files,
update GROK_OUTPUT_GLOB below and remove the stub guard.

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

# ── Expected output path (update once MUSKONOMY writes here) ──────────────────
_DABEIBA_ROOT = Path(os.environ.get(
    "DABEIBA_ROOT",
    str(Path.home() / "Desktop" / "DABEIBA"),
))

GROK_OUTPUT_DIR  = _DABEIBA_ROOT / "oracle" / "output"
GROK_OUTPUT_GLOB = "grok_flags_*.json"

# Only ingest files from the last N days (avoid re-processing stale files)
_LOOKBACK_DAYS = 3


def ingest_grok(
    store:    "IntelStore",
    dry_run:  bool = False,
    verbose:  bool = False,
) -> dict:
    """
    Ingest Grok DeepSearch corroboration flags into SOMA-INTEL.

    Args:
        store:    Open IntelStore context (caller must manage lifecycle).
        dry_run:  If True, parse and log without writing to DB.
        verbose:  If True, log each flag processed.

    Returns:
        dict with keys:
            files_scanned  (int)
            flags_found    (int)
            flags_inserted (int)
            flags_skipped  (int)   -- duplicates or low-confidence
            errors         (int)
    """
    cutoff = (date.today() - timedelta(days=_LOOKBACK_DAYS)).isoformat()
    pattern = str(GROK_OUTPUT_DIR / GROK_OUTPUT_GLOB)
    files = sorted(glob.glob(pattern))

    result = {"files_scanned": 0, "flags_found": 0,
              "flags_inserted": 0, "flags_skipped": 0, "errors": 0}

    if not files:
        log.info(
            "grok_adapter: no files found at %s — "
            "MUSKONOMY or another Grok pipeline must write grok_flags_YYYY-MM-DD.json "
            "before this adapter can ingest. Returning 0 flags ingested.",
            pattern,
        )
        return result

    for filepath in files:
        # Date filter: skip files older than lookback window
        fname = os.path.basename(filepath)
        try:
            file_date = fname.replace("grok_flags_", "").replace(".json", "")
            if file_date < cutoff:
                log.debug("grok_adapter: skipping old file %s (< %s)", fname, cutoff)
                continue
        except Exception:
            pass

        result["files_scanned"] += 1
        try:
            with open(filepath, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
        except Exception as exc:
            log.error("grok_adapter: failed to parse %s: %s", filepath, exc)
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
                log.debug("grok_adapter: skipping flag missing ticker/ts: %s", flag)
                result["flags_skipped"] += 1
                continue
            if confidence < 0.30:
                log.debug(
                    "grok_adapter: skipping low-confidence flag ticker=%s conf=%.2f",
                    ticker, confidence,
                )
                result["flags_skipped"] += 1
                continue

            if verbose:
                log.info(
                    "grok_adapter: %s flag ticker=%s signal=%s dir=%s conf=%.2f",
                    "DRY-RUN" if dry_run else "INGEST",
                    ticker, signal_type, direction, confidence,
                )

            if dry_run:
                result["flags_inserted"] += 1
                continue

            try:
                _flag_id, is_new = store.insert_cross_ai_flag(
                    ai_source="grok",
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
                        "grok_adapter: duplicate skipped ticker=%s ts=%s",
                        ticker, ts,
                    )
            except Exception as exc:
                log.error(
                    "grok_adapter: insert failed ticker=%s ts=%s: %s",
                    ticker, ts, exc,
                )
                result["errors"] += 1

    log.info(
        "grok_adapter: files=%d found=%d inserted=%d skipped=%d errors=%d",
        result["files_scanned"], result["flags_found"],
        result["flags_inserted"], result["flags_skipped"], result["errors"],
    )
    return result
