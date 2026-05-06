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

_AUDITOR_ID = "claude_adversarial"

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
    store:    IntelStore,
    run_date: date,
    dry_run:  bool = False,
) -> dict:
    """
    Run the weekly adversarial audit pass.

    Samples up to MAX_AUDITS_PER_RUN (50) edges with confidence >=
    MIN_CONFIDENCE_FOR_AUDIT (0.85), sends each to Claude for refutation,
    and marks disputed edges in the DB.

    Idempotent: if audit_log already has rows for (run_date, 'claude_adversarial'),
    returns immediately with skipped_idempotent=True.

    Capability gate: if 'adversarial_audit' capability is disabled, returns
    immediately with skipped_capability_disabled=True.

    Args:
        store:    open IntelStore context-manager instance.
        run_date: the calendar date for this run (used for idempotency key).
        dry_run:  if True, call Claude and parse responses but do NOT write to DB.

    Returns:
        dict with keys:
          audited (int)               — edges sent to Claude
          refuted (int)               — edges where refuted=True (any confidence)
          disputed (int)              — edges flagged audit_status='disputed'
          skipped_idempotent (bool)   — True if run already completed today
          skipped_capability_disabled (bool) — True if capability is off
          errors (int)                — per-edge parse/API errors
          sample_pool_size (int)      — total eligible edges before sampling
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

    # Count pool size before sampling
    all_eligible = store.list_edges_for_audit(
        min_confidence=MIN_CONFIDENCE_FOR_AUDIT,
        audit_status_filter=None,   # will filter disputed inside sample method
    )
    # Exclude disputed manually (sample_high_confidence_edges does this too, but
    # we need the raw count for the result dict before excluding)
    pool = [e for e in all_eligible if e.get("audit_status") != "disputed"]
    result["sample_pool_size"] = len(pool)

    sample = store.sample_high_confidence_edges(
        min_confidence=MIN_CONFIDENCE_FOR_AUDIT,
        exclude_audit_status=("disputed",),
        limit=MAX_AUDITS_PER_RUN,
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

    if len(sample) < MAX_AUDITS_PER_RUN:
        log.info(
            "adversarial_audit: pool < %d (only %d eligible edges found). "
            "Sampling what is available.",
            MAX_AUDITS_PER_RUN,
            len(sample),
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


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "SOMA-INTEL Phase 7 §K.5 — Adversarial Audit Pass\n"
            "Samples high-confidence edges and attempts Claude refutation.\n"
            "Default: disabled. Enable via capability registry before first live run."
        )
    )
    parser.add_argument(
        "--date",
        default=date.today().isoformat(),
        help="Run date YYYY-MM-DD (default: today). Used for idempotency key.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Call Claude and parse responses, but do NOT write to DB. "
            "Reports would-have-disputed counts."
        ),
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show per-edge detail.",
    )
    parser.add_argument(
        "--db",
        default=None,
        help="Override path to soma.db (default: SOMA_DB_PATH env or project default).",
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

    if args.dry_run:
        print("DRY RUN — Claude will be called but no DB writes will occur.")

    print(
        f"\nAdversarial audit | date={run_date.isoformat()} "
        f"| model={CLAUDE_MODEL} | max={MAX_AUDITS_PER_RUN}"
    )

    try:
        with IntelStore(db_path=db_path) as store:
            result = run_adversarial_audit(store, run_date, dry_run=args.dry_run)
    except RuntimeError as e:
        if "ANTHROPIC_API_KEY" in str(e):
            print(
                f"\nERROR: ANTHROPIC_API_KEY environment variable is not set.\n"
                f"Set it with: export ANTHROPIC_API_KEY=<your-key>",
                file=sys.stderr,
            )
            sys.exit(1)
        raise

    # ── Print summary ──────────────────────────────────────────────────────────
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

    pool = result["sample_pool_size"]
    audited   = result["audited"]
    refuted   = result["refuted"]
    disputed  = result["disputed"]
    errors    = result["errors"]
    mode = "DRY RUN" if args.dry_run else "LIVE"

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
