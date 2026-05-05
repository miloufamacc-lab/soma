#!/usr/bin/env python3
"""
SOMA-INTEL Phase 4 Step 4.5 — Audit Engine

Implements §K tiered sampling and audit workflow:

  K.1 Tiered sampling:
    [0.30, 0.55) → 100% audited
    [0.55, 0.75) →  25% random sample
    [0.75, 0.95) →   5% random sample
    [0.95, 1.00] →   1% random sample
    audited >365d ago → re-sample at original rate × 1.5

  Stratification: edge_type × source_type × confidence_band × ticker.
  No cell goes 90 days without an audit.

  K.2 Audit log:
    Writes approved/rejected/corrected rows to soma_intel_audit_log (append-only).

CLI:
  python3 soma/intel/audit_engine.py --queue               # show what's due
  python3 soma/intel/audit_engine.py --sample N            # pull N edges for review
  python3 soma/intel/audit_engine.py --show EDGE_ID        # show one edge
  python3 soma/intel/audit_engine.py --decide EDGE_ID approved "looks good"
  python3 soma/intel/audit_engine.py --decide EDGE_ID rejected "wrong direction"
  python3 soma/intel/audit_engine.py --decide EDGE_ID corrected "fixed claim"
  python3 soma/intel/audit_engine.py --stats               # audit coverage stats

Auditor: defaults to 'user'. Pass --auditor claude_adversarial for AI refutation runs.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

_HERE    = Path(__file__).resolve().parent
_DABEIBA = _HERE.parent.parent.parent
for _p in [str(_DABEIBA), str(_DABEIBA / "shared")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from soma.intel.store import IntelStore

DB_PATH = (
    Path(os.environ["SOMA_DB_PATH"])
    if "SOMA_DB_PATH" in os.environ
    else _DABEIBA / "shared" / "soma" / "data" / "soma.db"
)

NOW    = datetime.now(timezone.utc).isoformat()
TODAY  = date.today().isoformat()

# ══════════════════════════════════════════════════════════════════════════════
# Sampling thresholds (§K.1)
# ══════════════════════════════════════════════════════════════════════════════

# (lower_inclusive, upper_exclusive_or_inclusive, sample_rate)
_BANDS: list[tuple[float, float, float, str]] = [
    (0.30, 0.55, 1.00, "low"),    # 100% — every edge
    (0.55, 0.75, 0.25, "mid"),    # 25%
    (0.75, 0.95, 0.05, "high"),   # 5%
    (0.95, 1.01, 0.01, "top"),    # 1% (1.01 to include 1.0)
]

NO_AUDIT_CELL_MAX_DAYS = 90     # no stratification cell may go unaudited this long
STALE_AUDIT_DAYS       = 365    # edges audited >this long ago get re-queued at 1.5×


def _confidence_band(confidence: float) -> tuple[float, str]:
    """Return (sample_rate, band_name) for a confidence value."""
    for lo, hi, rate, name in _BANDS:
        if lo <= confidence < hi:
            return rate, name
    return 0.01, "top"   # ≥0.95 fallback


def _should_sample(confidence: float, stale: bool = False) -> bool:
    """
    Bernoulli draw at the tier's sample rate.
    If `stale` (audited >365d ago), rate is multiplied by 1.5 (capped at 1.0).
    """
    rate, _ = _confidence_band(confidence)
    if stale:
        rate = min(1.0, rate * 1.5)
    return random.random() < rate


# ══════════════════════════════════════════════════════════════════════════════
# Queue builder
# ══════════════════════════════════════════════════════════════════════════════

def _build_audit_queue(store: IntelStore, limit: int = 100) -> list[dict]:
    """
    Selects edges that are due for audit according to §K.1 tiering rules.
    Prioritises:
      1. confidence [0.30, 0.55) → 100% sample
      2. Stale edges (last audit > 365d ago)
      3. Cells (edge_type × source × band × ticker) silent > 90d
      4. Probabilistic samples from [0.55+) bands

    Returns list of edge dicts (with last_audit_ts injected).
    """
    # Load edges that haven't been permanently rejected and are unaudited or due
    cutoff_stale = (date.today() - timedelta(days=STALE_AUDIT_DAYS)).isoformat()
    cutoff_cell  = (date.today() - timedelta(days=NO_AUDIT_CELL_MAX_DAYS)).isoformat()

    # Get all unaudited or under-audited edges
    rows = store.list_edges_for_audit(
        min_confidence=0.30,
        audit_status_filter=["unaudited", "approved"],
        limit=5000,
    )

    # Get last audit timestamps per edge
    last_audit_map = store.get_last_audit_ts_map()

    queue: list[dict] = []
    seen_cells: set[tuple] = set()

    for edge in rows:
        eid        = edge["edge_id"]
        conf       = edge.get("confidence", 0.5)
        last_audit = last_audit_map.get(eid)
        band_rate, band_name = _confidence_band(conf)

        # Rule 1: low-confidence (100% band) — always queue
        if conf < 0.55:
            queue.append({**edge, "last_audit_ts": last_audit, "reason": "100pct_band"})
            continue

        # Rule 2: stale (audited >365d ago or never) — re-queue at 1.5×
        is_stale = (last_audit is None or last_audit < cutoff_stale)
        if is_stale and _should_sample(conf, stale=True):
            queue.append({**edge, "last_audit_ts": last_audit, "reason": "stale"})
            continue

        # Rule 3: cell silence >90d
        cell = (
            edge.get("edge_type", ""),
            edge.get("source_type", ""),
            band_name,
            edge.get("dst_node_id", "")[:20],   # ticker approximation
        )
        if cell not in seen_cells and (last_audit is None or last_audit < cutoff_cell):
            seen_cells.add(cell)
            queue.append({**edge, "last_audit_ts": last_audit, "reason": "cell_silence"})
            continue

        # Rule 4: probabilistic sample
        if _should_sample(conf, stale=False):
            queue.append({**edge, "last_audit_ts": last_audit, "reason": f"random_{band_name}"})

    # Deduplicate by edge_id and cap
    seen_ids: set[int] = set()
    final: list[dict] = []
    for item in queue:
        if item["edge_id"] not in seen_ids:
            seen_ids.add(item["edge_id"])
            final.append(item)
        if len(final) >= limit:
            break

    return final


# ══════════════════════════════════════════════════════════════════════════════
# Display helpers
# ══════════════════════════════════════════════════════════════════════════════

def _fmt_edge(edge: dict, verbose: bool = False) -> str:
    eid   = edge.get("edge_id", "?")
    etype = edge.get("edge_type", "?")
    src   = edge.get("source_type", "?")
    conf  = edge.get("confidence", 0.0)
    ts    = (edge.get("ts") or "")[:10]
    src_n = edge.get("src_node_id", "?")
    dst_n = edge.get("dst_node_id", "?")
    evid  = (edge.get("evidence_text") or "")[:80]

    lines = [
        f"  edge_id={eid}  type={etype}  source={src}  conf={conf:.2f}  ts={ts}",
        f"  {src_n} → {dst_n}",
    ]
    if evid:
        lines.append(f"  evidence: {evid}")
    if verbose and edge.get("last_audit_ts"):
        lines.append(f"  last_audit: {edge['last_audit_ts'][:10]}")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# Commands
# ══════════════════════════════════════════════════════════════════════════════

def cmd_queue(store: IntelStore, verbose: bool) -> None:
    queue = _build_audit_queue(store, limit=50)
    reasons: dict[str, int] = {}
    for e in queue:
        r = e.get("reason", "?")
        reasons[r] = reasons.get(r, 0) + 1

    total_edges = store.count_table("soma_intel_edge")
    audited     = store.count_table("soma_intel_audit_log")

    print(f"Audit queue ({len(queue)} edges due):")
    print(f"  Total edges: {total_edges}   Audit log entries: {audited}")
    print(f"  Breakdown: {reasons}\n")

    for edge in queue[:20]:
        print(_fmt_edge(edge, verbose))
        print(f"  reason: {edge.get('reason')}\n")

    if len(queue) > 20:
        print(f"  ... {len(queue) - 20} more. Use --sample to pull a batch.\n")


def cmd_sample(store: IntelStore, n: int) -> None:
    queue = _build_audit_queue(store, limit=n * 3)   # oversample, then pick n
    sample = random.sample(queue, min(n, len(queue)))
    print(f"Sampled {len(sample)} edges for review:\n")
    for edge in sample:
        print(_fmt_edge(edge, verbose=True))
        print(f"  reason: {edge.get('reason')}")
        print(f"  audit with: --decide {edge['edge_id']} approved|rejected|corrected \"rationale\"\n")


def cmd_show(store: IntelStore, edge_id: int) -> None:
    edge = store.get_edge(edge_id)
    if edge is None:
        print(f"ERROR: edge_id={edge_id} not found")
        sys.exit(1)
    print(f"\nEdge {edge_id}:")
    print(_fmt_edge(edge, verbose=True))

    # Show audit history
    log = store.list_audit_log(edge_id=edge_id)
    if log:
        print(f"\n  Audit history ({len(log)} entries):")
        for entry in log:
            print(
                f"    [{entry['ts'][:16]}] {entry['auditor']:<20} "
                f"{entry['decision']:<12} {(entry.get('rationale') or '')[:60]}"
            )
    else:
        print("\n  No audit history (unaudited)")


def cmd_decide(
    store:    IntelStore,
    edge_id:  int,
    decision: str,
    rationale: str,
    auditor:  str,
) -> None:
    valid_decisions = {"approved", "rejected", "corrected", "re_audited"}
    if decision not in valid_decisions:
        print(f"ERROR: decision must be one of {sorted(valid_decisions)}")
        sys.exit(1)

    edge = store.get_edge(edge_id)
    if edge is None:
        print(f"ERROR: edge_id={edge_id} not found")
        sys.exit(1)

    # Get prior audit for chaining
    prior_log = store.list_audit_log(edge_id=edge_id, limit=1)
    prior_id  = prior_log[0]["audit_id"] if prior_log else None

    audit_id = store.record_audit(
        edge_id       = edge_id,
        auditor       = auditor,
        decision      = decision,
        rationale     = rationale or None,
        prior_audit_id= prior_id,
    )
    store.commit()

    # Update edge audit_status
    store.update_edge_audit_status(
        edge_id      = edge_id,
        audit_status = decision,
        audit_ts     = NOW,
        audit_notes  = rationale or None,
    )
    store.commit()

    print(
        f"Recorded: audit_id={audit_id}  edge={edge_id}  "
        f"{decision}  auditor={auditor}"
    )
    if decision == "rejected":
        print(f"  Note: rejected edges remain in graph — use the edge_id to supersede if needed")


def cmd_stats(store: IntelStore) -> None:
    total  = store.count_table("soma_intel_edge")
    log_n  = store.count_table("soma_intel_audit_log")
    by_status = store.audit_coverage_stats()

    print(f"\nAudit coverage stats:")
    print(f"  Total edges:        {total:>6}")
    print(f"  Audit log entries:  {log_n:>6}")
    print()
    for row in by_status:
        pct = row["n"] / total * 100 if total else 0
        print(f"  {row['audit_status']:<15}  {row['n']:>5}  ({pct:.1f}%)")

    # Band breakdown
    bands = store.edge_confidence_band_counts()
    print(f"\n  Confidence band breakdown:")
    for b in bands:
        print(f"    {b['band']:<10}  {b['n']:>5} edges")


# ══════════════════════════════════════════════════════════════════════════════
# Additional IntelStore methods needed (called via new store methods below)
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="SOMA-INTEL audit engine — §K tiered sampling + decision workflow"
    )
    parser.add_argument("--queue",    action="store_true",   help="Show edges due for audit")
    parser.add_argument("--stats",    action="store_true",   help="Audit coverage stats")
    parser.add_argument("--sample",   type=int, metavar="N", help="Pull N edges for review")
    parser.add_argument("--show",     type=int, metavar="EDGE_ID", help="Show one edge + history")
    parser.add_argument("--decide",   type=int, metavar="EDGE_ID", help="Record audit decision")
    parser.add_argument("--decision", metavar="DECISION",
                        choices=["approved", "rejected", "corrected", "re_audited"],
                        help="Decision for --decide (approved|rejected|corrected|re_audited)")
    parser.add_argument("--rationale", default="", metavar="TEXT",
                        help="Rationale text for --decide")
    parser.add_argument("--auditor",  default="user",
                        choices=["user", "claude_adversarial", "meta_learner"])
    parser.add_argument("--verbose",  action="store_true")
    args = parser.parse_args()

    with IntelStore(db_path=DB_PATH) as store:
        if args.queue:
            cmd_queue(store, args.verbose)
        elif args.stats:
            cmd_stats(store)
        elif args.sample is not None:
            cmd_sample(store, args.sample)
        elif args.show is not None:
            cmd_show(store, args.show)
        elif args.decide is not None:
            if not args.decision:
                parser.error("--decide requires --decision (approved|rejected|corrected|re_audited)")
            cmd_decide(
                store,
                edge_id   = args.decide,
                decision  = args.decision,
                rationale = args.rationale,
                auditor   = args.auditor,
            )
        else:
            parser.print_help()


if __name__ == "__main__":
    main()
