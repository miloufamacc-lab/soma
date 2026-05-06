#!/usr/bin/env python3
"""
SOMA-INTEL Phase 7 §K.5 — Adversarial Audit Pass

Weekly Sunday job that samples 50 high-confidence edges (confidence >= 0.85),
sends each to Claude with a refutation prompt, and flags edges as 'disputed'
when the model successfully refutes the claim.

Spec source: SOMA_INTEL_OPUS_DELIVERABLES.md §K.5
Default state: DISABLED — enable via capability registry before first live run.

Usage:
    python3 -m soma.intel.adversarial_audit --date YYYY-MM-DD
    python3 -m soma.intel.adversarial_audit --date YYYY-MM-DD --dry-run

Design rules (LOCKED per §F):
  - Refutation threshold (0.7) is a quality gate, NOT a §E/§I signal threshold.
    Do NOT adjust without Opus escalation.
  - Sample size 50 is locked. Do NOT tune.
  - Model is claude-sonnet-4-6. Do NOT swap without Opus escalation.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from datetime import date, timezone, datetime
from pathlib import Path
from typing import Optional

# ── Path bootstrap ─────────────────────────────────────────────────────────────
_HERE    = Path(__file__).resolve().parent
_DABEIBA = _HERE.parent.parent.parent
for _p in [str(_DABEIBA), str(_DABEIBA / "shared")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from soma.intel.store import IntelStore

log = logging.getLogger(__name__)

# ── Module constants (LOCKED — §F #6 applies to threshold, §F #2 applies to model) ──

CLAUDE_MODEL                 = "claude-sonnet-4-6"
MAX_AUDITS_PER_RUN           = 50
MIN_CONFIDENCE_FOR_AUDIT     = 0.85
REFUTATION_CONFIDENCE_THRESHOLD = 0.70   # locked — do NOT tune

# Provenance/immutable edge types excluded from adversarial audit pool by default.
# Per §A.2: ∞ half-life, evidence IS the claim — unfalsifiable by design.
# These map to the defaults in store.sample_high_confidence_edges().
PROVENANCE_EDGE_TYPES: tuple[str, ...] = (
    "mentioned_in",
    "regime_was",
    "succeeded_by",
)

_AUDITOR_ID        = "claude_adversarial"   # legacy API path — never reuse for scheduled path
_AUDITOR_SCHEDULED = "claude_scheduled"     # scheduled-task path — distinct auditor type

# Staging directory for the sample→agent→ingest two-stage flow.
# Python writes audit_edges_<date>.json here; agent reads it and writes
# audit_decisions_<date>.json here; Python ingest reads that back.
AUDIT_STAGING_DIR = _DABEIBA / "shared" / "soma" / "intel" / "audit_staging"

# ── DB path ────────────────────────────────────────────────────────────────────
_DEFAULT_DB_PATH = (
    Path(os.environ["SOMA_DB_PATH"])
    if "SOMA_DB_PATH" in os.environ
    else _DABEIBA / "shared" / "soma" / "data" / "soma.db"
)

# ── Locked refutation prompt template ─────────────────────────────────────────

_REFUTATION_SYSTEM = (
    "You are an adversarial auditor for the SOMA-INTEL knowledge graph. Your job\n"
    "is to attempt to refute the following claim using both the evidence cited\n"
    "and your own training knowledge. You are NOT to confirm the claim. Look\n"
    "for: factual errors, outdated information, contradictory evidence, missing\n"
    "context that changes the conclusion, logical flaws, source unreliability.\n\n"
    "Return ONLY valid JSON matching this schema:\n"
    "{\n"
    '  "refuted": true|false,\n'
    '  "refutation_confidence": 0.0-1.0,\n'
    '  "rationale": "<\\u2264500 chars \\u2014 concrete reason for refutation or non-refutation>",\n'
    '  "contradicting_evidence": "<\\u2264300 chars \\u2014 specific fact or source that contradicts the claim, OR null if not refuted>"\n'
    "}"
)

_REFUTATION_USER_TEMPLATE = (
    "CLAIM: {src_node_id} --{edge_type}--> {dst_node_id}\n"
    "SOURCE: {source_id} ({source_type})\n"
    "EVIDENCE CITED: {evidence_text}\n"
    "STATED CONFIDENCE: {confidence}\n"
    "DATE OF CLAIM: {ts}\n\n"
    "Try to refute this claim."
)


# ── Custom exception ───────────────────────────────────────────────────────────

class RefutationParseError(ValueError):
    """Raised when Claude's response cannot be parsed as valid refutation JSON."""


# ── Prompt builder ─────────────────────────────────────────────────────────────

def _build_refutation_prompt(edge: dict) -> str:
    """
    Fill the locked refutation prompt template with edge fields.

    Returns the full prompt string (system + user, newline-separated) suitable
    for passing to _call_claude_for_refutation().
    """
    evidence_text = edge.get("evidence_text") or "(no evidence text recorded)"
    user_block = _REFUTATION_USER_TEMPLATE.format(
        src_node_id=edge.get("src_node_id", ""),
        edge_type=edge.get("edge_type", ""),
        dst_node_id=edge.get("dst_node_id", ""),
        source_id=edge.get("source_id", ""),
        source_type=edge.get("source_type", ""),
        evidence_text=evidence_text[:500],
        confidence=edge.get("confidence", ""),
        ts=edge.get("ts", ""),
    )
    return f"SYSTEM:\n{_REFUTATION_SYSTEM}\n\nUSER:\n{user_block}"


# ── Claude caller ──────────────────────────────────────────────────────────────

# Import _call_claude from edge_extractor — do NOT duplicate the API logic.
# Lazy import avoids circular dependency during module load.
def _call_claude_for_refutation(prompt: str) -> dict:
    """
    Send refutation prompt to Claude and parse the JSON response.

    Reuses _call_claude() from edge_extractor.py — all API key handling,
    anthropic SDK usage, and fallback logic lives there.

    Args:
        prompt: full prompt string (system + user sections).

    Returns:
        Parsed refutation dict with keys:
          refuted (bool), refutation_confidence (float),
          rationale (str), contradicting_evidence (str | None).

    Raises:
        RefutationParseError: if the response is not parseable JSON or
                              does not match the expected schema.
        RuntimeError: if ANTHROPIC_API_KEY is not set (propagated from
                      edge_extractor._call_claude).
    """
    from soma.intel.edge_extractor import _call_claude as _ec_call_claude

    raw = _ec_call_claude(prompt, model=CLAUDE_MODEL)

    # Strip markdown fences if present
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        text = text.strip()

    # Try direct parse
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Try to find a JSON object anywhere in the response
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group())
            except json.JSONDecodeError as e:
                raise RefutationParseError(
                    f"Could not parse JSON from Claude response: {e!r}\n"
                    f"Raw (first 300 chars): {raw[:300]!r}"
                ) from e
        else:
            raise RefutationParseError(
                f"No JSON object found in Claude response.\n"
                f"Raw (first 300 chars): {raw[:300]!r}"
            )

    # Schema validation
    required_keys = {"refuted", "refutation_confidence", "rationale"}
    missing = required_keys - set(data.keys())
    if missing:
        raise RefutationParseError(
            f"Refutation JSON missing required keys: {missing}. "
            f"Got: {list(data.keys())}"
        )

    # Type coercion + bounds check
    try:
        refuted = bool(data["refuted"])
        rc = float(data["refutation_confidence"])
        if not (0.0 <= rc <= 1.0):
            raise RefutationParseError(
                f"refutation_confidence {rc!r} out of [0, 1]"
            )
        rationale = str(data.get("rationale") or "")[:500]
        contradicting = data.get("contradicting_evidence")
        if contradicting is not None:
            contradicting = str(contradicting)[:300]
    except (TypeError, ValueError) as e:
        raise RefutationParseError(
            f"Type error in refutation JSON: {e!r}. Data: {data!r}"
        ) from e

    return {
        "refuted":                refuted,
        "refutation_confidence":  rc,
        "rationale":              rationale,
        "contradicting_evidence": contradicting,
    }


# ── Refutation evaluator ───────────────────────────────────────────────────────

def _evaluate_refutation(response: dict) -> tuple[bool, str]:
    """
    Apply the locked success criterion to a parsed refutation response.

    Disputed if BOTH:
      1. response['refuted'] is True
      2. response['refutation_confidence'] >= REFUTATION_CONFIDENCE_THRESHOLD (0.70)

    Args:
        response: parsed refutation dict (output of _call_claude_for_refutation).

    Returns:
        (is_disputed: bool, summary_text: str)
        summary_text is a short human-readable string for log / notes.
    """
    refuted = response.get("refuted", False)
    rc      = float(response.get("refutation_confidence", 0.0))
    rationale = response.get("rationale", "")[:200]

    is_disputed = refuted and rc >= REFUTATION_CONFIDENCE_THRESHOLD

    if is_disputed:
        summary = (
            f"DISPUTED (refutation_confidence={rc:.2f}): {rationale}"
        )
    elif refuted and rc < REFUTATION_CONFIDENCE_THRESHOLD:
        summary = (
            f"Refutation attempted but confidence too low "
            f"({rc:.2f} < {REFUTATION_CONFIDENCE_THRESHOLD}): {rationale}"
        )
    else:
        summary = f"Not refuted (confidence={rc:.2f}): {rationale}"

    return is_disputed, summary


# ── Main public function ───────────────────────────────────────────────────────

def run_adversarial_audit(
    store:     IntelStore,
    run_date:  date,
    dry_run:   bool = False,
    force:     bool = False,
    max_edges: Optional[int] = None,
) -> dict:
    """
    Run the weekly adversarial audit pass.

    Samples up to MAX_AUDITS_PER_RUN (50) edges with confidence >=
    MIN_CONFIDENCE_FOR_AUDIT (0.85), sends each to Claude for refutation,
    and marks disputed edges in the DB.

    Provenance/immutable edge types (mentioned_in, regime_was, succeeded_by)
    are excluded from the pool by default — per §A.2 these are unfalsifiable.
    See PROVENANCE_EDGE_TYPES constant and store.sample_high_confidence_edges().

    Idempotent: if audit_log already has rows for (run_date, 'claude_adversarial'),
    returns immediately with skipped_idempotent=True.

    Capability gate: if 'adversarial_audit' capability is disabled, returns
    immediately with skipped_capability_disabled=True.

    Args:
        store:     open IntelStore context-manager instance.
        run_date:  the calendar date for this run (used for idempotency key).
        dry_run:   if True, call Claude and parse responses but do NOT write to DB.
        force:     if True, bypass the capability gate (use for dry-run review only).
                   Capability stays at its registered status; no history row added.
        max_edges: override the per-run sample cap (default: MAX_AUDITS_PER_RUN=50).
                   Use a small value (e.g. 10) for API-path validation runs to
                   limit cost. Production runs should always use the default.

    Returns:
        dict with keys:
          audited (int)               — edges sent to Claude
          refuted (int)               — edges where refuted=True (any confidence)
          disputed (int)              — edges flagged audit_status='disputed'
          skipped_idempotent (bool)   — True if run already completed today
          skipped_capability_disabled (bool) — True if capability is off
          errors (int)                — per-edge parse/API errors
          sample_pool_size (int)      — total eligible edges before sampling
                                        (excludes provenance types)
    """
    result: dict = {
        "audited":                    0,
        "refuted":                    0,
        "disputed":                   0,
        "skipped_idempotent":         False,
        "skipped_capability_disabled": False,
        "errors":                     0,
        "sample_pool_size":           0,
    }

    # ── Capability gate ────────────────────────────────────────────────────────
    if not store.is_capability_enabled("adversarial_audit"):
        if force:
            log.info(
                "adversarial_audit capability disabled but --force set "
                "— proceeding with dry-run review (capability stays disabled)"
            )
        else:
            log.info("adversarial_audit capability disabled — skipping")
            result["skipped_capability_disabled"] = True
            return result

    # ── Idempotency check ──────────────────────────────────────────────────────
    prior = store.get_audits_by_date_and_auditor(run_date, _AUDITOR_ID)
    if prior:
        log.info(
            "adversarial_audit already ran on %s (%d log rows) — skipping",
            run_date.isoformat(),
            len(prior),
        )
        result["skipped_idempotent"] = True
        return result

    # ── Sample ────────────────────────────────────────────────────────────────
    # seed = run_date as integer (YYYYMMDD) for reproducibility
    date_seed = int(run_date.strftime("%Y%m%d"))

    # Effective sample cap: allow CLI/test override for validation runs.
    # Production runs should always use MAX_AUDITS_PER_RUN (50).
    effective_limit = max_edges if (max_edges is not None and max_edges > 0) else MAX_AUDITS_PER_RUN

    # Count pool size (after applying the same filters used by sample_high_confidence_edges
    # so that sample_pool_size reflects the actual auditable pool, not the raw edge count).
    # Provenance types are excluded here to match the sample filter.
    all_eligible = store.list_edges_for_audit(
        min_confidence=MIN_CONFIDENCE_FOR_AUDIT,
        audit_status_filter=None,   # will filter disputed below
    )
    pool = [
        e for e in all_eligible
        if e.get("audit_status") != "disputed"
        and e.get("edge_type") not in PROVENANCE_EDGE_TYPES
    ]
    result["sample_pool_size"] = len(pool)

    # sample_high_confidence_edges uses exclude_edge_types default (PROVENANCE_EDGE_TYPES)
    sample = store.sample_high_confidence_edges(
        min_confidence=MIN_CONFIDENCE_FOR_AUDIT,
        exclude_audit_status=("disputed",),
        # exclude_edge_types uses the default (PROVENANCE_EDGE_TYPES) — no override needed
        limit=effective_limit,
        seed=date_seed,
        stratify_by="edge_type",
    )

    if not sample:
        log.info(
            "adversarial_audit: pool is empty (no edges with confidence >= %.2f "
            "that are not already disputed). Nothing to audit.",
            MIN_CONFIDENCE_FOR_AUDIT,
        )
        return result

    if len(sample) < effective_limit:
        log.info(
            "adversarial_audit: pool has fewer edges than requested "
            "(%d returned vs %d requested). Sampling what is available.",
            len(sample),
            effective_limit,
        )

    now_iso = datetime.now(timezone.utc).isoformat()

    # ── Audit loop ─────────────────────────────────────────────────────────────
    for edge in sample:
        edge_id = edge["edge_id"]
        try:
            prompt   = _build_refutation_prompt(edge)
            response = _call_claude_for_refutation(prompt)
        except RefutationParseError as e:
            log.warning(
                "adversarial_audit: edge %d — parse error (skipping DB write): %s",
                edge_id, e,
            )
            result["errors"] += 1
            continue
        except RuntimeError as e:
            # Propagate API key errors loudly; they abort the entire run
            if "ANTHROPIC_API_KEY" in str(e):
                raise
            log.warning(
                "adversarial_audit: edge %d — API error (skipping): %s",
                edge_id, e,
            )
            result["errors"] += 1
            continue
        except Exception as e:
            log.warning(
                "adversarial_audit: edge %d — unexpected error (skipping): %s",
                edge_id, e,
            )
            result["errors"] += 1
            continue

        result["audited"] += 1

        is_disputed, summary = _evaluate_refutation(response)

        if response.get("refuted"):
            result["refuted"] += 1

        if is_disputed:
            result["disputed"] += 1
            log.info(
                "adversarial_audit: edge %d DISPUTED — %s",
                edge_id, summary[:120],
            )

            if not dry_run:
                # Record in audit log (append-only)
                store.insert_audit_log(
                    edge_id=edge_id,
                    auditor=_AUDITOR_ID,
                    decision="rejected",
                    rationale=summary[:500],
                )
                # update_edge_audit_status already called inside record_audit,
                # but we need to set 'disputed' (not 'rejected') on the edge.
                # Override the status set by record_audit.
                store.update_edge_audit_status(
                    edge_id=edge_id,
                    audit_status="disputed",
                    audit_ts=now_iso,
                    audit_notes=f"[{_AUDITOR_ID}] {summary[:450]}",
                )
                store.commit()
                log.info(
                    "adversarial_audit: edge %d set to disputed in DB", edge_id
                )
        else:
            log.debug(
                "adversarial_audit: edge %d not disputed — %s",
                edge_id, summary[:120],
            )

            if not dry_run:
                # Log the audit attempt even when not disputed (audit trail)
                store.insert_audit_log(
                    edge_id=edge_id,
                    auditor=_AUDITOR_ID,
                    decision="approved",
                    rationale=summary[:500],
                )
                store.commit()

    return result


# ── Scheduled-task mode helpers ────────────────────────────────────────────────

def _run_sample_mode(
    store:     IntelStore,
    run_date:  date,
    max_edges: Optional[int] = None,
    output:    Optional[Path] = None,
    overwrite: bool = False,
    force:     bool = False,
) -> dict:
    """
    Sample mode: draw high-confidence edges from DB and write staged JSON for
    the scheduled-task agent to reason over.

    Read-only on the DB. Writes one file to AUDIT_STAGING_DIR.

    Args:
        store:      open IntelStore (context-manager already entered by caller).
        run_date:   ISO date for this run — used in the filename and run_id payload.
        max_edges:  override per-run sample cap (default MAX_AUDITS_PER_RUN=50).
        output:     override output path. Default: AUDIT_STAGING_DIR/audit_edges_<date>.json.
        overwrite:  if True, overwrite existing staging file (else exit code 2).
        force:      if True, bypass capability gate (for dry-run review sessions).

    Returns:
        dict with keys:
          staging_path  (str)  — absolute path written (empty if skipped)
          edges_written (int)  — number of edges in the output file
          pool_size     (int)  — total eligible edges before sampling
          skipped_capability_disabled (bool)
          skipped_file_exists         (bool)
    """
    result: dict = {
        "staging_path":               "",
        "edges_written":              0,
        "pool_size":                  0,
        "skipped_capability_disabled": False,
        "skipped_file_exists":        False,
    }

    # ── Capability gate ────────────────────────────────────────────────────────
    if not store.is_capability_enabled("adversarial_audit"):
        if force:
            log.info(
                "adversarial_audit capability disabled but --force set "
                "— proceeding with sample mode for dry-run review."
            )
        else:
            log.info("adversarial_audit capability disabled — skipping sample mode.")
            result["skipped_capability_disabled"] = True
            return result

    # ── Resolve output path ────────────────────────────────────────────────────
    date_str    = run_date.isoformat()
    staging_dir = AUDIT_STAGING_DIR
    staging_dir.mkdir(parents=True, exist_ok=True)
    out_path    = Path(output) if output else staging_dir / f"audit_edges_{date_str}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if out_path.exists() and not overwrite:
        log.error(
            "Staging file already exists: %s — pass --overwrite to replace.", out_path
        )
        result["skipped_file_exists"] = True
        return result

    # ── Sample ────────────────────────────────────────────────────────────────
    effective_limit = (
        max_edges if (max_edges is not None and max_edges > 0)
        else MAX_AUDITS_PER_RUN
    )
    date_seed = int(run_date.strftime("%Y%m%d"))

    # Pool size (apply same filters as sample_high_confidence_edges for accurate count)
    all_eligible = store.list_edges_for_audit(
        min_confidence=MIN_CONFIDENCE_FOR_AUDIT,
        audit_status_filter=None,
    )
    pool_size = len([
        e for e in all_eligible
        if e.get("audit_status") != "disputed"
        and e.get("edge_type") not in PROVENANCE_EDGE_TYPES
    ])
    result["pool_size"] = pool_size

    sample = store.sample_high_confidence_edges(
        min_confidence=MIN_CONFIDENCE_FOR_AUDIT,
        exclude_audit_status=("disputed",),
        limit=effective_limit,
        seed=date_seed,
        stratify_by="edge_type",
    )

    if not sample:
        log.info(
            "adversarial_audit sample mode: pool empty "
            "(no eligible edges with confidence >= %.2f). Writing empty file.",
            MIN_CONFIDENCE_FOR_AUDIT,
        )

    if len(sample) < effective_limit:
        log.info(
            "adversarial_audit sample mode: pool has fewer edges than requested "
            "(%d returned vs %d requested). Sampling what is available.",
            len(sample), effective_limit,
        )

    # ── Build edges list with rendered prompts ─────────────────────────────────
    import uuid as _uuid
    run_id   = str(_uuid.uuid4())
    now_iso  = datetime.now(timezone.utc).isoformat()

    edges_out: list[dict] = []
    for edge in sample:
        prompt = _build_refutation_prompt(edge)
        edges_out.append({
            "edge_id":           edge.get("edge_id"),
            "src_node_id":       edge.get("src_node_id"),
            "edge_type":         edge.get("edge_type"),
            "dst_node_id":       edge.get("dst_node_id"),
            "confidence":        edge.get("confidence"),
            "ts":                edge.get("ts"),
            "source_id":         edge.get("source_id"),
            "source_type":       edge.get("source_type"),
            "evidence_text":     edge.get("evidence_text") or "",
            "refutation_prompt": prompt,
        })

    payload = {
        "run_id":           run_id,
        "run_date":         date_str,
        "generated_ts":     now_iso,
        "sample_pool_size": pool_size,
        "edges":            edges_out,
    }

    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)

    log.info(
        "adversarial_audit sample mode: wrote %d edges to %s",
        len(edges_out), out_path,
    )
    result["staging_path"] = str(out_path)
    result["edges_written"] = len(edges_out)
    return result


def _run_ingest_mode(
    store:          IntelStore,
    decisions_path: Path,
    dry_run:        bool = False,
    reingest:       bool = False,
    force:          bool = False,
) -> dict:
    """
    Ingest mode: read agent decisions JSON and apply audit outcomes to the DB.

    Validates run_id match, array size match, and all edge_ids before writing.
    Uses auditor='claude_scheduled' — distinct from 'claude_adversarial' (API path).

    Args:
        store:          open IntelStore (context-manager entered by caller).
        decisions_path: path to audit_decisions_<date>.json written by the agent.
        dry_run:        if True, validate and report but write nothing to DB.
        reingest:       if True, allow re-processing a previously ingested file.
        force:          if True, bypass capability gate (for review sessions).

    Returns:
        dict with keys:
          decisions_read  (int)
          valid           (int)  — decisions that passed schema check
          disputed        (int)  — edges flagged audit_status='disputed'
          approved        (int)  — edges logged as 'approved' (not disputed)
          errors          (int)  — per-edge write errors
          skipped_capability_disabled (bool)
          skipped_already_ingested    (bool)
          validation_errors           (list[str])

    Raises:
        FileNotFoundError: if decisions_path or corresponding edges file not found.
        ValueError: on run_id mismatch, size mismatch, or unknown edge_id in decisions.
    """
    result: dict = {
        "decisions_read":              0,
        "valid":                       0,
        "disputed":                    0,
        "approved":                    0,
        "errors":                      0,
        "skipped_capability_disabled": False,
        "skipped_already_ingested":    False,
        "validation_errors":           [],
    }

    # ── Capability gate ────────────────────────────────────────────────────────
    if not store.is_capability_enabled("adversarial_audit"):
        if force:
            log.info(
                "adversarial_audit capability disabled but --force set "
                "— proceeding with ingest mode for dry-run validation."
            )
        else:
            log.info("adversarial_audit capability disabled — skipping ingest.")
            result["skipped_capability_disabled"] = True
            return result

    # ── Load decisions file ────────────────────────────────────────────────────
    decisions_path = Path(decisions_path)
    if not decisions_path.exists():
        raise FileNotFoundError(f"Decisions file not found: {decisions_path}")

    with open(decisions_path, "r", encoding="utf-8") as fh:
        decisions_doc = json.load(fh)

    # Required top-level fields
    for field_name in ("run_id", "run_date", "auditor", "decisions"):
        if field_name not in decisions_doc:
            err = f"Decisions file missing required field: {field_name!r}"
            result["validation_errors"].append(err)
            raise ValueError(err)

    run_date_str     = decisions_doc["run_date"]
    decisions_run_id = decisions_doc["run_id"]
    decisions        = decisions_doc["decisions"]
    result["decisions_read"] = len(decisions)

    # ── Load corresponding edges file for validation ───────────────────────────
    # Look for the edges file alongside the decisions file first (covers test/custom paths),
    # then fall back to the canonical AUDIT_STAGING_DIR (production).
    _edges_filename = f"audit_edges_{run_date_str}.json"
    edges_path_sibling = decisions_path.parent / _edges_filename
    edges_path_canonical = AUDIT_STAGING_DIR / _edges_filename
    if edges_path_sibling.exists():
        edges_path = edges_path_sibling
    elif edges_path_canonical.exists():
        edges_path = edges_path_canonical
    else:
        raise FileNotFoundError(
            f"Corresponding edges file not found in {decisions_path.parent} "
            f"or {AUDIT_STAGING_DIR}. "
            "Cannot validate decisions without the original sample file."
        )

    with open(edges_path, "r", encoding="utf-8") as fh:
        edges_doc = json.load(fh)

    # ── Validation 1: run_id must match ───────────────────────────────────────
    if edges_doc.get("run_id") != decisions_run_id:
        err = (
            f"run_id mismatch: edges file has {edges_doc.get('run_id')!r}, "
            f"decisions file has {decisions_run_id!r}. "
            "Files are from different runs — will not ingest."
        )
        result["validation_errors"].append(err)
        raise ValueError(err)

    # ── Validation 2: array size must match ────────────────────────────────────
    edges = edges_doc.get("edges", [])
    if len(decisions) != len(edges):
        err = (
            f"Size mismatch: {len(edges)} edges sampled, "
            f"{len(decisions)} decisions provided. "
            "Every edge must have exactly one decision."
        )
        result["validation_errors"].append(err)
        raise ValueError(err)

    # ── Validation 3: all decision edge_ids must be in edges file ─────────────
    valid_edge_ids = {e["edge_id"] for e in edges}
    for dec in decisions:
        if dec.get("edge_id") not in valid_edge_ids:
            err = (
                f"Unknown edge_id in decisions: {dec.get('edge_id')!r}. "
                "This edge_id was not in the sampled edges file."
            )
            result["validation_errors"].append(err)
            raise ValueError(err)

    # ── Validation 4: each decision has required fields ────────────────────────
    _required_dec_keys = {"edge_id", "refuted", "refutation_confidence", "rationale"}
    for i, dec in enumerate(decisions):
        missing = _required_dec_keys - set(dec.keys())
        if missing:
            err = f"Decision[{i}] (edge_id={dec.get('edge_id')}) missing keys: {missing}"
            result["validation_errors"].append(err)
            raise ValueError(err)

    # ── Idempotency check ──────────────────────────────────────────────────────
    try:
        from datetime import date as _date_type
        run_date = _date_type.fromisoformat(run_date_str)
    except ValueError:
        raise ValueError(f"Invalid run_date in decisions file: {run_date_str!r}")

    prior = store.get_audits_by_date_and_auditor(run_date, _AUDITOR_SCHEDULED)
    if prior and not reingest:
        log.info(
            "Ingest already completed for %s (%d audit_log rows with auditor='%s'). "
            "Pass --reingest to force re-ingest.",
            run_date_str, len(prior), _AUDITOR_SCHEDULED,
        )
        result["skipped_already_ingested"] = True
        return result

    # ── Apply decisions ────────────────────────────────────────────────────────
    now_iso = datetime.now(timezone.utc).isoformat()

    for dec in decisions:
        edge_id  = dec["edge_id"]
        refuted  = bool(dec["refuted"])
        rc       = float(dec["refutation_confidence"])
        rationale = str(dec.get("rationale") or "")[:500]

        is_disputed = refuted and rc >= REFUTATION_CONFIDENCE_THRESHOLD

        try:
            if not dry_run:
                decision_str = "rejected" if is_disputed else "approved"
                store.insert_audit_log(
                    edge_id=edge_id,
                    auditor=_AUDITOR_SCHEDULED,
                    decision=decision_str,
                    rationale=rationale,
                )
                if is_disputed:
                    # record_audit sets audit_status=decision ('rejected');
                    # override to 'disputed' to match the K5 audit_status contract.
                    store.update_edge_audit_status(
                        edge_id=edge_id,
                        audit_status="disputed",
                        audit_ts=now_iso,
                        audit_notes=f"[{_AUDITOR_SCHEDULED}] {rationale[:450]}",
                    )
                store.commit()

            result["valid"] += 1
            if is_disputed:
                result["disputed"] += 1
                log.info(
                    "ingest: edge %d DISPUTED (refuted=True, conf=%.2f)%s",
                    edge_id, rc,
                    " [DRY RUN]" if dry_run else "",
                )
            else:
                result["approved"] += 1

        except Exception as e:
            log.warning("ingest: edge %d error: %s", edge_id, e)
            result["errors"] += 1

    mode = "DRY RUN" if dry_run else "LIVE"
    log.info(
        "Ingest [%s]: %d valid, %d disputed, %d approved, %d errors",
        mode,
        result["valid"],
        result["disputed"],
        result["approved"],
        result["errors"],
    )
    return result


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "SOMA-INTEL Phase 7 §K.5 — Adversarial Audit Pass\n\n"
            "Three execution modes:\n"
            "  sample     — Read DB, write audit_edges_<date>.json for scheduled-task agent.\n"
            "  ingest     — Read agent decisions JSON, write audit results to DB.\n"
            "  legacy_api — Original one-pass mode (sample + Claude API + write). Requires ANTHROPIC_API_KEY.\n\n"
            "Default: legacy_api (backward compatible). Switch to sample/ingest for scheduled-task flow.\n"
            "Default state: DISABLED. Enable via capability registry before first live run."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # ── Mode ──────────────────────────────────────────────────────────────────
    parser.add_argument(
        "--mode",
        choices=["sample", "ingest", "legacy_api"],
        default="legacy_api",
        help=(
            "Execution mode. "
            "'sample': read DB, write staged JSON. "
            "'ingest': read agent decisions JSON, write to DB. "
            "'legacy_api': original one-pass API path (backward compatible). "
            "Default: legacy_api."
        ),
    )

    # ── Common args ───────────────────────────────────────────────────────────
    parser.add_argument(
        "--date",
        default=date.today().isoformat(),
        help="Run date YYYY-MM-DD (default: today). Used for filenames and idempotency.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate/parse but do NOT write to DB. Supported by all modes.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Bypass capability gate for dry-run/review sessions. "
            "Capability stays at its registered status. Not for production use."
        ),
    )
    parser.add_argument(
        "--db",
        default=None,
        help="Override path to soma.db (default: SOMA_DB_PATH env or project default).",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show per-edge detail.",
    )

    # ── Sample mode args ──────────────────────────────────────────────────────
    parser.add_argument(
        "--max-edges",
        type=int,
        default=None,
        dest="max_edges",
        help=(
            f"Override per-run sample cap (default: {MAX_AUDITS_PER_RUN}). "
            "Use a small value (e.g. 10) for validation runs. "
            "Applies to --mode sample and --mode legacy_api."
        ),
    )
    parser.add_argument(
        "--output",
        default=None,
        help=(
            "Override output path for staged edges JSON "
            "(--mode sample only; default: AUDIT_STAGING_DIR/audit_edges_<date>.json)."
        ),
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing staged edges file (--mode sample only).",
    )

    # ── Ingest mode args ──────────────────────────────────────────────────────
    parser.add_argument(
        "--decisions",
        default=None,
        help="Path to audit_decisions_<date>.json written by agent (--mode ingest only).",
    )
    parser.add_argument(
        "--reingest",
        action="store_true",
        help="Allow re-processing a previously ingested decisions file (--mode ingest only).",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    try:
        run_date = date.fromisoformat(args.date)
    except ValueError:
        print(f"ERROR: --date must be YYYY-MM-DD, got {args.date!r}", file=sys.stderr)
        sys.exit(1)

    db_path = args.db or str(_DEFAULT_DB_PATH)

    # ══════════════════════════════════════════════════════════════════════════
    # SAMPLE mode
    # ══════════════════════════════════════════════════════════════════════════
    if args.mode == "sample":
        effective_max = args.max_edges or MAX_AUDITS_PER_RUN
        print(
            f"\nSample mode | date={run_date.isoformat()} "
            f"| max={effective_max}"
            + (" [CAPPED for review]" if args.max_edges else "")
        )

        with IntelStore(db_path=db_path) as store:
            result = _run_sample_mode(
                store,
                run_date,
                max_edges=args.max_edges,
                output=Path(args.output) if args.output else None,
                overwrite=args.overwrite,
                force=args.force,
            )

        print()
        if result.get("skipped_capability_disabled"):
            print("  SKIPPED: adversarial_audit capability is disabled.")
            print(
                "  To enable: python3 -c \"from soma.intel.store import IntelStore; "
                "s=IntelStore().__enter__(); "
                "s.set_capability_status('adversarial_audit','enabled'); s.commit()\""
            )
            return

        if result.get("skipped_file_exists"):
            print(
                f"  ERROR: staging file already exists. Pass --overwrite to replace.",
                file=sys.stderr,
            )
            sys.exit(2)

        print(f"  Pool:    {result['pool_size']} eligible edges")
        print(f"  Written: {result['edges_written']} edges")
        print(f"  File:    {result['staging_path']}")
        return

    # ══════════════════════════════════════════════════════════════════════════
    # INGEST mode
    # ══════════════════════════════════════════════════════════════════════════
    if args.mode == "ingest":
        if not args.decisions:
            print(
                "ERROR: --decisions <path> is required for --mode ingest.",
                file=sys.stderr,
            )
            sys.exit(1)

        decisions_path = Path(args.decisions)
        print(f"\nIngest mode | decisions={decisions_path}")
        if args.dry_run:
            print("DRY RUN — will validate and report but not write to DB.")

        try:
            with IntelStore(db_path=db_path) as store:
                result = _run_ingest_mode(
                    store,
                    decisions_path,
                    dry_run=args.dry_run,
                    reingest=args.reingest,
                    force=args.force,
                )
        except (FileNotFoundError, ValueError) as e:
            print(f"\nERROR: {e}", file=sys.stderr)
            sys.exit(1)

        print()
        if result.get("skipped_capability_disabled"):
            print("  SKIPPED: adversarial_audit capability is disabled.")
            return

        if result.get("skipped_already_ingested"):
            print(
                "  SKIPPED: already ingested for this date. "
                "Pass --reingest to force re-ingest."
            )
            return

        mode = "DRY RUN" if args.dry_run else "LIVE"
        n = result["decisions_read"]
        v = result["valid"]
        d = result["disputed"]
        a = result["approved"]
        e = result["errors"]

        print(f"  [{mode}] Decisions read: {n}")
        print(f"  [{mode}] Valid:          {v}")
        print(
            f"  [{mode}] Disputed "
            f"(refuted + conf >= {REFUTATION_CONFIDENCE_THRESHOLD}): {d}"
            + (f" ({d / v:.0%})" if v else "")
        )
        print(f"  [{mode}] Approved:       {a}")
        if e:
            print(f"  [{mode}] Errors:         {e}")

        if args.dry_run:
            print(
                f"\n  Validation passed: {v} decisions, "
                f"threshold check passed, {d} disputed (would-be)."
            )
        return

    # ══════════════════════════════════════════════════════════════════════════
    # LEGACY_API mode  (original one-pass behavior — preserved for tests + opt-in)
    # ══════════════════════════════════════════════════════════════════════════
    if args.dry_run:
        print("DRY RUN — Claude will be called but no DB writes will occur.")

    effective_max = args.max_edges if args.max_edges else MAX_AUDITS_PER_RUN
    print(
        f"\nAdversarial audit (legacy API) | date={run_date.isoformat()} "
        f"| model={CLAUDE_MODEL} | max={effective_max}"
        + (" [CAPPED for validation]" if args.max_edges else "")
    )

    try:
        with IntelStore(db_path=db_path) as store:
            result = run_adversarial_audit(
                store, run_date, dry_run=args.dry_run, force=args.force,
                max_edges=args.max_edges,
            )
    except RuntimeError as e:
        if "ANTHROPIC_API_KEY" in str(e):
            print(
                f"\nERROR: ANTHROPIC_API_KEY environment variable is not set.\n"
                f"Set it with: export ANTHROPIC_API_KEY=<your-key>\n"
                f"Or use --mode sample / --mode ingest for scheduled-task flow "
                f"(no API key needed).",
                file=sys.stderr,
            )
            sys.exit(1)
        raise

    # ── Print summary (legacy_api) ─────────────────────────────────────────────
    print()
    if result.get("skipped_capability_disabled"):
        print("  SKIPPED: adversarial_audit capability is disabled.")
        print(
            "  Enable with: python3 -c \"from soma.intel.store import IntelStore; "
            "s=IntelStore().__enter__(); "
            "s.set_capability_status('adversarial_audit','enabled'); s.commit()\""
        )
        return

    if result.get("skipped_idempotent"):
        print(f"  SKIPPED: audit already ran on {run_date.isoformat()} (idempotent).")
        return

    pool     = result["sample_pool_size"]
    audited  = result["audited"]
    refuted  = result["refuted"]
    disputed = result["disputed"]
    errors   = result["errors"]
    mode     = "DRY RUN" if args.dry_run else "LIVE"

    print(f"  [{mode}] Pool: {pool} eligible edges")
    print(f"  [{mode}] Audited: {audited}")
    print(f"  [{mode}] Refuted (any confidence): {refuted}")
    print(
        f"  [{mode}] Disputed (refuted + conf >= {REFUTATION_CONFIDENCE_THRESHOLD}): "
        f"{disputed}"
        + (f" ({disputed / audited:.0%})" if audited else "")
    )
    if errors:
        print(f"  [{mode}] Errors (parse/API): {errors}")

    if args.dry_run and disputed > 0:
        print(
            f"\n  Would have flagged {disputed} edge(s) as disputed. "
            "Re-run without --dry-run to apply."
        )


if __name__ == "__main__":
    main()
