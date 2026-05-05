"""
SOMA-INTEL P6.5 — One-shot horizon label migration

Re-tags soma_intel_signal rows that have NULL or stale horizon values,
using the dominant feature (highest-abs f1..f5 z-score) to infer the
correct horizon track.

Mapping rules (applied in order):
  1. notes LIKE '%Platform convergence%'  → structural
  2. notes LIKE '%s_curve_inflection%'    → structural
  3. notes LIKE '%regime_succession%'     → structural
  4. dominant feature = f1/f2/f4          → tactical
  5. dominant feature = f5/f3             → thematic
  6. notes LIKE '%signal_propagator:%'    → thematic  (propagator default)
  7. horizon already set and valid        → skip (no change)

Updates soma_intel_signal only — soma_intel_signal_backtest is append-only
for audit integrity and is not touched.

Usage:
    python3 soma/intel/migrate_horizon_labels.py            # dry run
    python3 soma/intel/migrate_horizon_labels.py --apply    # write to DB
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_HERE         = Path(__file__).resolve().parent
_DABEIBA_ROOT = _HERE.parent.parent.parent
for _p in [str(_DABEIBA_ROOT), str(_DABEIBA_ROOT / "shared")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from soma.intel.store import IntelStore

DB_PATH = (
    Path(os.environ["SOMA_DB_PATH"])
    if "SOMA_DB_PATH" in os.environ
    else _DABEIBA_ROOT / "shared" / "soma" / "data" / "soma.db"
)

_VALID_HORIZONS = {"tactical", "thematic", "structural"}

# Features whose dominance implies a horizon
_FEATURE_HORIZON: dict[str, str] = {
    "f1_ret5d_z":  "tactical",
    "f2_ret20d_z": "tactical",   # used in both, but primary tactical weight
    "f4_volume_z": "tactical",
    "f5_sector_z": "thematic",
    "f3_rvol_z":   "thematic",   # used in thematic weights
}

# (notes_substring, horizon) — checked in order, first match wins
_NOTES_RULES: list[tuple[str, str]] = [
    ("Platform convergence", "structural"),
    ("s_curve_inflection",   "structural"),
    ("regime_succession",    "structural"),
    ("structural platform",  "structural"),
    ("structural s_curve",   "structural"),
    ("signal_propagator:",   "thematic"),
]


def _dominant_feature(features_json: str | None) -> str | None:
    """Return the feature with the highest abs value from f1..f5, or None."""
    if not features_json:
        return None
    try:
        feat = json.loads(features_json)
        candidates = {f: abs(feat.get(f, 0.0)) for f in _FEATURE_HORIZON}
        best = max(candidates, key=candidates.get)
        return best if candidates[best] > 0 else None
    except Exception:
        return None


def _infer_horizon(notes: str | None, features_json: str | None) -> str | None:
    """Return inferred horizon or None if undecidable."""
    n = (notes or "").lower()

    # Notes-based rules first (highest confidence)
    for substring, horizon in _NOTES_RULES:
        if substring.lower() in n:
            return horizon

    # Feature-dominant mapping
    dom = _dominant_feature(features_json)
    if dom:
        return _FEATURE_HORIZON.get(dom)

    return None


def run_migration(store: IntelStore, apply: bool, verbose: bool) -> dict:
    """
    Scan soma_intel_signal for rows needing horizon re-labelling.

    Returns summary dict:
      {total_rows, already_valid, updated_tactical, updated_thematic,
       updated_structural, undecidable, dry_run}
    """
    rows = store._c.execute(
        "SELECT signal_id, horizon, notes, features FROM soma_intel_signal"
    ).fetchall()

    stats = {
        "total_rows":         len(rows),
        "already_valid":      0,
        "updated_tactical":   0,
        "updated_thematic":   0,
        "updated_structural": 0,
        "undecidable":        0,
        "dry_run":            not apply,
    }

    for row in rows:
        current_horizon = row["horizon"]

        # Skip rows already correctly labelled
        if current_horizon in _VALID_HORIZONS:
            stats["already_valid"] += 1
            continue

        inferred = _infer_horizon(row["notes"], row["features"])

        if inferred is None:
            stats["undecidable"] += 1
            if verbose:
                print(f"  [skip] signal_id={row['signal_id']}  "
                      f"horizon={current_horizon!r}  notes={str(row['notes'])[:60]!r}")
            continue

        if verbose:
            print(f"  [{inferred}] signal_id={row['signal_id']}  "
                  f"{current_horizon!r} → {inferred!r}")

        if apply:
            store._c.execute(
                "UPDATE soma_intel_signal SET horizon=? WHERE signal_id=?",
                (inferred, row["signal_id"]),
            )

        if inferred == "tactical":
            stats["updated_tactical"] += 1
        elif inferred == "thematic":
            stats["updated_thematic"] += 1
        elif inferred == "structural":
            stats["updated_structural"] += 1

    if apply:
        store._conn.commit()

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate soma_intel_signal horizon labels based on dominant feature"
    )
    parser.add_argument("--apply",   action="store_true",
                        help="Write changes to DB (default: dry run)")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Print per-row decisions")
    parser.add_argument("--db",      default=str(DB_PATH),
                        help="Path to soma.db")
    args = parser.parse_args()

    if not args.apply:
        print("DRY RUN — pass --apply to write to DB\n")

    with IntelStore(db_path=args.db) as store:
        stats = run_migration(store, apply=args.apply, verbose=args.verbose)

    print("Migration complete:")
    for k, v in stats.items():
        print(f"  {k}: {v}")

    if not args.apply:
        total_changes = (stats["updated_tactical"] + stats["updated_thematic"]
                         + stats["updated_structural"])
        print(f"\nDRY RUN: would update {total_changes} rows. Pass --apply to commit.")


if __name__ == "__main__":
    main()
