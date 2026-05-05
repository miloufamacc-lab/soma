#!/usr/bin/env python3
"""
SOMA-INTEL Phase 4 Step 4.6 — Source Calibration (§K.3)

CFA-grade monthly calibration of edge source reliability:

  For each source_type:
  1. Bin all edges by stated confidence:
       low  [0.30, 0.55)
       mid  [0.55, 0.75)
       high [0.75, 0.95)
       top  [0.95, 1.00]
  2. Compute actual accuracy per bin = n_approved / (n_approved + n_rejected)
  3. Compute Brier score: mean((stated_conf - was_correct)²) across all audited edges
  4. Derive recalibration multiplier:
       multiplier = mean(actual_accuracy_bin) / mean(stated_conf_bin)
       capped to [0.50, 1.50] to prevent extreme corrections
  5. Store to soma_intel_source_calibration via IntelStore

Outputs a calibration report per source. Flags sources where:
  - Brier score > 0.25  (poor calibration)
  - multiplier < 0.70   (systematic overconfidence — §L escalation trigger)

Usage:
  python3 soma/intel/calibration.py               # dry run — print results only
  python3 soma/intel/calibration.py --apply       # write to soma_intel_source_calibration
  python3 soma/intel/calibration.py --source wiki # single source
  python3 soma/intel/calibration.py --verbose
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
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

NOW = datetime.now(timezone.utc).isoformat()

# Brier score threshold above which source is flagged
BRIER_WARN_THRESHOLD = 0.25

# Multiplier bounds — prevent extreme recalibration
MULTIPLIER_MIN = 0.50
MULTIPLIER_MAX = 1.50

# §L escalation trigger: source is systematically overconfident
ESCALATION_MULTIPLIER_THRESHOLD = 0.70

# Minimum audited edges to attempt calibration
MIN_AUDITED = 5

# Confidence bands for binning
BANDS = [
    ("low",  0.30, 0.55),
    ("mid",  0.55, 0.75),
    ("high", 0.75, 0.95),
    ("top",  0.95, 1.01),
]


# ══════════════════════════════════════════════════════════════════════════════
# Data structures
# ══════════════════════════════════════════════════════════════════════════════

from dataclasses import dataclass, field


@dataclass
class BinStats:
    band:         str
    n_approved:   int = 0
    n_rejected:   int = 0
    sum_conf:     float = 0.0

    @property
    def n_audited(self) -> int:
        return self.n_approved + self.n_rejected

    @property
    def actual_accuracy(self) -> Optional[float]:
        if self.n_audited == 0:
            return None
        return self.n_approved / self.n_audited

    @property
    def mean_stated_conf(self) -> Optional[float]:
        if self.n_audited == 0:
            return None
        return self.sum_conf / self.n_audited


@dataclass
class SourceCalibration:
    source_id:    str
    n_audited:    int
    brier_score:  float
    multiplier:   float
    is_escalate:  bool
    bins:         dict[str, BinStats] = field(default_factory=dict)
    error:        Optional[str] = None


# ══════════════════════════════════════════════════════════════════════════════
# Core computation
# ══════════════════════════════════════════════════════════════════════════════

def _band_name(conf: float) -> str:
    for name, lo, hi in BANDS:
        if lo <= conf < hi:
            return name
    return "top"


def _calibrate_source(source_id: str, edges: list[dict]) -> SourceCalibration:
    """
    Compute Brier score and calibration multiplier for a single source.
    `edges` must have been audited (audit_status in approved|rejected).
    """
    audited = [
        e for e in edges
        if e.get("audit_status") in ("approved", "rejected")
    ]

    if len(audited) < MIN_AUDITED:
        return SourceCalibration(
            source_id   = source_id,
            n_audited   = len(audited),
            brier_score = 0.0,
            multiplier  = 1.0,
            is_escalate = False,
            error       = f"insufficient audited edges ({len(audited)} < {MIN_AUDITED})",
        )

    # Initialise bins
    bins: dict[str, BinStats] = {name: BinStats(band=name) for name, _, _ in BANDS}

    brier_sum   = 0.0
    brier_count = 0

    for edge in audited:
        conf   = edge.get("confidence", 0.5)
        is_ok  = 1 if edge.get("audit_status") == "approved" else 0
        band   = _band_name(conf)

        # Brier score contribution
        brier_sum   += (conf - is_ok) ** 2
        brier_count += 1

        # Bin accumulation
        b = bins[band]
        b.n_approved += is_ok
        b.n_rejected += (1 - is_ok)
        b.sum_conf   += conf

    brier_score = brier_sum / brier_count if brier_count > 0 else 0.0

    # Multiplier: ratio of mean actual accuracy to mean stated confidence
    # Uses only bins with ≥3 audited edges for stability
    weighted_actual = 0.0
    weighted_stated = 0.0
    total_weight    = 0

    for b in bins.values():
        if b.n_audited >= 3 and b.actual_accuracy is not None:
            weighted_actual += b.actual_accuracy * b.n_audited
            weighted_stated += b.mean_stated_conf * b.n_audited
            total_weight    += b.n_audited

    if total_weight >= MIN_AUDITED and weighted_stated > 0:
        raw_multiplier = weighted_actual / weighted_stated
    else:
        raw_multiplier = 1.0

    multiplier  = max(MULTIPLIER_MIN, min(MULTIPLIER_MAX, raw_multiplier))
    is_escalate = multiplier < ESCALATION_MULTIPLIER_THRESHOLD

    return SourceCalibration(
        source_id   = source_id,
        n_audited   = len(audited),
        brier_score = round(brier_score, 6),
        multiplier  = round(multiplier, 4),
        is_escalate = is_escalate,
        bins        = bins,
    )


# ══════════════════════════════════════════════════════════════════════════════
# Runner
# ══════════════════════════════════════════════════════════════════════════════

def run_calibration(
    store:    IntelStore,
    sources:  Optional[list[str]],
    dry_run:  bool,
    verbose:  bool,
) -> list[SourceCalibration]:
    """
    Load all audited edges, group by source_type, compute calibration,
    and optionally write to soma_intel_source_calibration.
    """
    # Load all edges with audit decisions
    all_edges = store.list_edges_for_audit(
        min_confidence      = 0.30,
        audit_status_filter = ["approved", "rejected"],
        limit               = 100_000,
    )

    if not all_edges:
        print("  No audited edges found — run audit_engine.py to build audit history first.")
        return []

    # Group by source_type
    by_source: dict[str, list[dict]] = defaultdict(list)
    for edge in all_edges:
        src = edge.get("source_type") or "unknown"
        by_source[src].append(edge)

    work_sources = sources if sources else sorted(by_source.keys())
    results: list[SourceCalibration] = []

    print(f"  Sources to calibrate: {', '.join(work_sources)}\n")

    for source_id in work_sources:
        edges = by_source.get(source_id, [])
        cal   = _calibrate_source(source_id, edges)
        results.append(cal)

        if cal.error:
            print(f"  {source_id:<22}  SKIP: {cal.error}")
            continue

        flag = " *** ESCALATE" if cal.is_escalate else ""
        flag += " [BRIER_WARN]" if cal.brier_score > BRIER_WARN_THRESHOLD else ""

        print(
            f"  {source_id:<22}  n={cal.n_audited:>4}  "
            f"Brier={cal.brier_score:.4f}  "
            f"mult={cal.multiplier:.3f}{flag}"
        )

        if verbose:
            for bname, b in cal.bins.items():
                if b.n_audited > 0:
                    acc_str = f"{b.actual_accuracy:.2f}" if b.actual_accuracy is not None else " n/a"
                    print(
                        f"    [{bname:<4}]  n={b.n_audited:>3}  "
                        f"actual={acc_str}  stated_mean={b.mean_stated_conf:.2f}"
                    )

        if not dry_run:
            store.upsert_source_calibration(
                source_id      = source_id,
                multiplier     = cal.multiplier,
                brier_score    = cal.brier_score,
                n_observations = cal.n_audited,
                last_updated   = NOW,
            )

    if not dry_run:
        store.commit()

    return results


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="SOMA-INTEL calibration — CFA-grade §K.3 source Brier scoring + multipliers"
    )
    parser.add_argument("--apply",   action="store_true",
                        help="Write multipliers to soma_intel_source_calibration (default: dry run)")
    parser.add_argument("--source",  nargs="+", metavar="SOURCE_ID",
                        help="Limit to specific sources (e.g. wiki oracle_titan)")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    dry_run = not args.apply
    if dry_run:
        print("DRY RUN — pass --apply to write multipliers to soma_intel_source_calibration\n")

    with IntelStore(db_path=DB_PATH) as store:
        print("[Calibration] Computing per-source Brier scores...\n")
        results = run_calibration(
            store,
            sources = args.source,
            dry_run = dry_run,
            verbose = args.verbose,
        )

        ok      = [r for r in results if not r.error]
        skipped = [r for r in results if r.error]
        flagged = [r for r in ok if r.is_escalate]

        print(f"\n  Sources calibrated: {len(ok)}/{len(results)}")
        print(f"  Sources skipped:    {len(skipped)} (insufficient audits)")

        if flagged:
            print(f"\n  *** ESCALATION REQUIRED ({len(flagged)} sources) ***")
            for r in flagged:
                print(f"    {r.source_id}: mult={r.multiplier:.3f} (below {ESCALATION_MULTIPLIER_THRESHOLD:.2f} threshold)")
            print("    → Source calibration multiplier <0.50 is a §L escalation trigger.")
            print("    → Freeze ingest from flagged sources and surface to user for review.")

    if dry_run:
        print("\nDRY RUN complete — pass --apply to write.")
    else:
        print("\ncalibration: OK")


if __name__ == "__main__":
    main()
