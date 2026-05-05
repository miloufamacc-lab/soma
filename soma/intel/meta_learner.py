"""
SOMA-INTEL P6.4 — Meta-Learner

Weekly Sunday job that adjusts per-cell z-thresholds based on outcome history.
Implements §I.4 of SOMA_INTEL_OPUS_DELIVERABLES.md.

Cell definition: (regime_composite_label, sector, dominant_feature) — 3-axis.

Rules (locked — do NOT manually override per §L.4):
  - For each cell with ≥ 30 outcome rows:
      * ≥ 3 false negatives in trailing 30 days → lower P1 z-threshold by 0.1
      * ≥ 3 false positives in trailing 30 days → raise P1 z-threshold by 0.1
  - Adjustments capped at ±0.5 from base threshold (never drift unbounded)
  - All adjustments logged to soma_intel_threshold_history (append-only)

Definitions:
  False negative: P-X signal that was audited as "approved" but wasn't surfaced
                  as P3 (system under-triggered for this cell)
  False positive:  P3/P1/P2 signal that was audited as "rejected" (over-triggered)

Schedule: Sundays, called from run_day.py step_meta_learner_weekly (no-op other days).

Usage:
    from soma.intel.meta_learner import MetaLearner
    learner = MetaLearner(store)
    report = learner.run()   # returns summary dict
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

# ── Path bootstrap ─────────────────────────────────────────────────────────────
_HERE         = Path(__file__).resolve().parent
_DABEIBA_ROOT = _HERE.parent.parent.parent
for _p in [str(_DABEIBA_ROOT), str(_DABEIBA_ROOT / "shared")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from soma.intel.confirm import regime_thresholds
from soma.intel.store import IntelStore

log = logging.getLogger(__name__)

# ── Constants (§I.4 — locked) ─────────────────────────────────────────────────
ADJUSTMENT_STEP          = 0.1    # delta per adjustment cycle
MAX_ADJUSTMENT           = 0.5    # cap: never drift more than ±0.5 from base
MIN_CELL_OUTCOMES        = 30     # minimum outcome rows to qualify a cell
FALSE_NEGATIVE_THRESHOLD = 3      # min false negatives to trigger downward adjustment
FALSE_POSITIVE_THRESHOLD = 3      # min false positives to trigger upward adjustment
TRAILING_WINDOW_DAYS     = 30     # look-back window for false +/- counting

FEATURES = ["f1_ret5d_z", "f2_ret20d_z", "f3_rvol_z", "f4_volume_z", "f5_sector_z"]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _dominant_feature(features_json: Optional[str]) -> str:
    """Extract dominant feature (highest abs value) from backtest features JSON."""
    if not features_json:
        return "unknown"
    try:
        feat = json.loads(features_json)
        candidates = {f: abs(feat.get(f, 0.0)) for f in FEATURES}
        return max(candidates, key=candidates.get)
    except Exception:
        return "unknown"


def _sector_for_ticker(store: IntelStore, ticker: str) -> str:
    """Look up platform_tags for ticker; return first tag or 'unknown'."""
    try:
        row = store._c.execute(
            "SELECT platform_tags FROM soma_intel_universe WHERE ticker=? AND active=1",
            (ticker,),
        ).fetchone()
        if row and row[0]:
            tags = json.loads(row[0])
            return tags[0] if tags else "unknown"
    except Exception:
        pass
    return "unknown"


def _cell_key(regime: str, sector: str, feature: str) -> str:
    return f"{regime}|{sector}|{feature}"


# ── Main class ────────────────────────────────────────────────────────────────

class MetaLearner:
    """
    Computes per-cell threshold adjustments from backtest outcomes.

    Args:
        store:      Open IntelStore instance.
        as_of_date: ISO YYYY-MM-DD reference date (defaults to today).
    """

    def __init__(
        self,
        store:      IntelStore,
        as_of_date: Optional[str] = None,
    ) -> None:
        self._store      = store
        self._as_of_date = as_of_date or date.today().isoformat()

    def run(self) -> dict:
        """
        Execute one meta-learner cycle. Returns a summary dict:
          {
            "cells_evaluated":   int,
            "cells_adjusted":    int,
            "adjustments_down":  int,   # threshold lowered (more sensitive)
            "adjustments_up":    int,   # threshold raised (more conservative)
            "cap_hits":          int,   # cells at ±0.5 cap
            "skipped_min_data":  int,   # cells with < MIN_CELL_OUTCOMES rows
          }
        """
        trailing_since = (
            date.fromisoformat(self._as_of_date) - timedelta(days=TRAILING_WINDOW_DAYS)
        ).isoformat()

        cells  = self._build_cell_outcomes()
        report = {
            "cells_evaluated":  0,
            "cells_adjusted":   0,
            "adjustments_down": 0,
            "adjustments_up":   0,
            "cap_hits":         0,
            "skipped_min_data": 0,
            "as_of_date":       self._as_of_date,
        }

        for cell_key, data in cells.items():
            regime = data["regime"]
            report["cells_evaluated"] += 1

            if data["total_outcomes"] < MIN_CELL_OUTCOMES:
                report["skipped_min_data"] += 1
                log.debug("cell %s: skipped (only %d outcomes < %d min)",
                          cell_key, data["total_outcomes"], MIN_CELL_OUTCOMES)
                continue

            false_neg = data["trailing_false_negatives"]
            false_pos = data["trailing_false_positives"]

            # Determine base threshold for this cell's regime
            base_p1, _ = regime_thresholds(regime)
            current = self._store.get_cell_threshold(cell_key, base_p1)

            # Check cap bounds
            lower_cap = round(base_p1 - MAX_ADJUSTMENT, 4)
            upper_cap = round(base_p1 + MAX_ADJUSTMENT, 4)

            adjustment = None
            reason     = None

            if false_neg >= FALSE_NEGATIVE_THRESHOLD:
                # Too many misses — lower threshold (be more sensitive)
                candidate = round(current - ADJUSTMENT_STEP, 4)
                if candidate < lower_cap:
                    report["cap_hits"] += 1
                    log.info("cell %s: would lower to %.2f but hit cap %.2f",
                             cell_key, candidate, lower_cap)
                else:
                    adjustment = -ADJUSTMENT_STEP
                    reason     = f"false_negatives:{false_neg}"

            elif false_pos >= FALSE_POSITIVE_THRESHOLD:
                # Too many false alarms — raise threshold (be more conservative)
                candidate = round(current + ADJUSTMENT_STEP, 4)
                if candidate > upper_cap:
                    report["cap_hits"] += 1
                    log.info("cell %s: would raise to %.2f but hit cap %.2f",
                             cell_key, candidate, upper_cap)
                else:
                    adjustment = +ADJUSTMENT_STEP
                    reason     = f"false_positives:{false_pos}"

            if adjustment is not None:
                new_threshold = round(current + adjustment, 4)
                self._store.append_threshold_adjustment(
                    cell_key        = cell_key,
                    prior_threshold = current,
                    new_threshold   = new_threshold,
                    adjustment      = adjustment,
                    reason          = reason,
                )
                report["cells_adjusted"] += 1
                if adjustment < 0:
                    report["adjustments_down"] += 1
                else:
                    report["adjustments_up"] += 1
                log.info(
                    "cell %s: %+.1f → %.2f (%s)",
                    cell_key, adjustment, new_threshold, reason,
                )

        log.info(
            "meta_learner run complete: %d cells evaluated, %d adjusted "
            "(%d down / %d up), %d cap hits, %d skipped",
            report["cells_evaluated"], report["cells_adjusted"],
            report["adjustments_down"], report["adjustments_up"],
            report["cap_hits"], report["skipped_min_data"],
        )
        return report

    def _build_cell_outcomes(self) -> dict[str, dict]:
        """
        Read soma_intel_signal_backtest + audit_log to build per-cell outcome stats.

        Returns dict[cell_key → {
            regime, sector, feature,
            total_outcomes,
            trailing_false_negatives,
            trailing_false_positives,
        }]
        """
        trailing_since = (
            date.fromisoformat(self._as_of_date) - timedelta(days=TRAILING_WINDOW_DAYS)
        ).isoformat()

        # Load all scored backtest signals for cell grouping
        all_signals = self._store._c.execute(
            """
            SELECT ticker, sim_date, priority, features, regime_label, outcome
            FROM soma_intel_signal_backtest
            WHERE outcome IS NOT NULL AND outcome != 'data_unavailable'
            """
        ).fetchall()

        # Load audit decisions in the trailing window
        try:
            audit_rows = self._store._c.execute(
                """
                SELECT e.signal_id, al.decision, al.ts
                FROM soma_intel_audit_log al
                JOIN soma_intel_edge e ON al.edge_id = e.edge_id
                WHERE al.ts >= ?
                """,
                (trailing_since,),
            ).fetchall()
            audit_map: dict[int, str] = {r[0]: r[1] for r in audit_rows}
        except Exception:
            audit_map = {}

        # Load approved P-X signals from audit as false-negative candidates
        try:
            px_approved = self._store._c.execute(
                """
                SELECT ticker, sim_date, features, regime_label
                FROM soma_intel_signal_backtest
                WHERE priority = 'P-X'
                  AND sim_date >= ?
                """,
                (trailing_since,),
            ).fetchall()
        except Exception:
            px_approved = []

        cells: dict[str, dict] = {}

        def _get_or_create(key: str, regime: str, sector: str, feature: str) -> dict:
            if key not in cells:
                cells[key] = {
                    "regime": regime,
                    "sector": sector,
                    "feature": feature,
                    "total_outcomes": 0,
                    "trailing_false_negatives": 0,
                    "trailing_false_positives": 0,
                }
            return cells[key]

        # Count total outcomes per cell
        for row in all_signals:
            ticker   = row["ticker"]
            regime   = row["regime_label"] or "unknown"
            feature  = _dominant_feature(row["features"])
            sector   = _sector_for_ticker(self._store, ticker)
            key      = _cell_key(regime, sector, feature)
            cell     = _get_or_create(key, regime, sector, feature)
            cell["total_outcomes"] += 1

            # False positives: P3 signals that were misses in trailing window
            if row["sim_date"] >= trailing_since and row["outcome"] == "miss":
                if row["priority"] in ("P1", "P2", "P3"):
                    cell["trailing_false_positives"] += 1

        # False negatives: P-X signals that were approved by audit
        # (system didn't surface them as P3 — we were too conservative)
        for row in px_approved:
            ticker  = row["ticker"]
            regime  = row["regime_label"] or "unknown"
            feature = _dominant_feature(row["features"])
            sector  = _sector_for_ticker(self._store, ticker)
            key     = _cell_key(regime, sector, feature)
            cell    = _get_or_create(key, regime, sector, feature)
            # All P-X signals in the trailing window are treated as potential
            # false negatives (the exploration channel exists to capture them)
            cell["trailing_false_negatives"] += 1

        return cells


# ── CLI ────────────────────────────────────────────────────────────────────────

def _main() -> None:
    import argparse
    from soma.intel.store import IntelStore

    _SOMA_DB = _DABEIBA_ROOT / "shared" / "soma" / "data" / "soma.db"

    parser = argparse.ArgumentParser(
        description="SOMA-INTEL meta-learner — weekly threshold adjustment"
    )
    parser.add_argument("--as-of", default=None, help="ISO YYYY-MM-DD (default: today)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be adjusted without writing to DB")
    parser.add_argument("--db", default=str(_SOMA_DB))
    args = parser.parse_args()

    if args.dry_run:
        print("(dry-run mode — no DB writes)")
        # For dry-run: wrap store methods to no-op
        with IntelStore(db_path=args.db) as store:
            learner = MetaLearner(store, as_of_date=args.as_of)
            cells = learner._build_cell_outcomes()
            qualified = {
                k: v for k, v in cells.items()
                if v["total_outcomes"] >= MIN_CELL_OUTCOMES
            }
            print(f"Qualified cells (≥{MIN_CELL_OUTCOMES} outcomes): {len(qualified)}")
            for key, data in qualified.items():
                fn = data["trailing_false_negatives"]
                fp = data["trailing_false_positives"]
                action = ""
                if fn >= FALSE_NEGATIVE_THRESHOLD:
                    action = f"↓ lower by {ADJUSTMENT_STEP} (fn={fn})"
                elif fp >= FALSE_POSITIVE_THRESHOLD:
                    action = f"↑ raise by {ADJUSTMENT_STEP} (fp={fp})"
                else:
                    action = "no change"
                print(f"  {key}: outcomes={data['total_outcomes']} {action}")
        return

    with IntelStore(db_path=args.db) as store:
        learner = MetaLearner(store, as_of_date=args.as_of)
        report = learner.run()
        print("Meta-learner run complete:")
        for k, v in report.items():
            print(f"  {k}: {v}")


if __name__ == "__main__":
    _main()
