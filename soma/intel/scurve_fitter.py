#!/usr/bin/env python3
"""
SOMA-INTEL Phase 4 Step 4.2 — S-Curve Fitter

Fits a logistic growth curve to each platform's scurve_history data:

    P(t) = K / (1 + exp(-r * (t - t0)))

  K   = saturation level (upper asymptote)
  r   = adoption rate (steepness of S)
  t0  = inflection point (decimal year when P = K/2)

For pl_blockchain (high volatility), fits on log(metric_value) to stabilize.

After fitting, classifies each platform's current position on the S-curve:
  pre-takeoff    — P(now) < 0.10 × K
  acceleration   — 0.10 ≤ P(now) < 0.40 × K
  inflection     — 0.40 ≤ P(now) < 0.60 × K
  deceleration   — 0.60 ≤ P(now) < 0.90 × K
  saturation     — P(now) ≥ 0.90 × K

Writes curve_K, curve_r, curve_t0, position, last_fit_ts back to
soma_intel_platform.

Requires: scipy (scipy.optimize.curve_fit) and numpy.

Usage:
  python3 soma/intel/scurve_fitter.py           # fit + print, no DB write
  python3 soma/intel/scurve_fitter.py --apply   # write results to DB
  python3 soma/intel/scurve_fitter.py --platform pl_ai  # single platform
  python3 soma/intel/scurve_fitter.py --verbose
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from datetime import date, datetime, timezone
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

NOW      = datetime.now(timezone.utc).isoformat()
TODAY_YR = date.today().year + date.today().month / 12.0

# Platforms that benefit from log-transform before fitting
LOG_TRANSFORM_PLATFORMS = {"pl_blockchain"}

# Position thresholds (fraction of K)
POSITIONS = [
    (0.10, "pre-takeoff"),
    (0.40, "acceleration"),
    (0.60, "inflection"),
    (0.90, "deceleration"),
    (1.01, "saturation"),
]


# ══════════════════════════════════════════════════════════════════════════════
# Math
# ══════════════════════════════════════════════════════════════════════════════

def _logistic(t: float, K: float, r: float, t0: float) -> float:
    """Standard logistic function."""
    try:
        return K / (1.0 + math.exp(-r * (t - t0)))
    except OverflowError:
        return 0.0 if r * (t - t0) < 0 else K


def _date_to_year(date_str: str) -> float:
    """YYYY-MM → decimal year (e.g. 2023-06 → 2023.458)."""
    parts = date_str.split("-")
    y, m = int(parts[0]), int(parts[1])
    return y + (m - 1) / 12.0


def _position_label(current_frac: float) -> str:
    for threshold, label in POSITIONS:
        if current_frac < threshold:
            return label
    return "saturation"


# ══════════════════════════════════════════════════════════════════════════════
# Fitter
# ══════════════════════════════════════════════════════════════════════════════

from dataclasses import dataclass

@dataclass
class FitResult:
    platform_id: str
    K:           float
    r:           float
    t0:          float          # decimal year
    t0_date:     str            # ISO approx (YYYY-MM)
    r_squared:   float
    position:    str
    current_val: float          # P(now) in original units
    current_frac: float         # P(now) / K
    log_fit:     bool
    error:       Optional[str] = None


def _fit_platform(platform_id: str, rows: list[dict]) -> FitResult:
    """Fit logistic curve to a platform's history rows."""
    try:
        import numpy as np
        from scipy.optimize import curve_fit
    except ImportError:
        return FitResult(
            platform_id=platform_id, K=0, r=0, t0=0, t0_date="",
            r_squared=0, position="unknown", current_val=0,
            current_frac=0, log_fit=False,
            error="scipy/numpy not installed — run: pip install scipy numpy",
        )

    if len(rows) < 4:
        return FitResult(
            platform_id=platform_id, K=0, r=0, t0=0, t0_date="",
            r_squared=0, position="unknown", current_val=0,
            current_frac=0, log_fit=False,
            error=f"insufficient data ({len(rows)} rows, need ≥ 4)",
        )

    use_log = platform_id in LOG_TRANSFORM_PLATFORMS
    t_vals  = np.array([_date_to_year(r["date"]) for r in rows])
    y_raw   = np.array([r["metric_value"] for r in rows], dtype=float)
    y_vals  = np.log(y_raw + 1) if use_log else y_raw

    # Initial parameter guesses
    K_guess  = y_vals.max() * 2.0
    t0_guess = t_vals[len(t_vals) // 2]
    r_guess  = 0.5

    try:
        popt, _ = curve_fit(
            lambda t, K, r, t0: np.array([_logistic(ti, K, r, t0) for ti in t]),
            t_vals, y_vals,
            p0=[K_guess, r_guess, t0_guess],
            bounds=([y_vals.max() * 0.8, 0.01, t_vals[0] - 5],
                    [y_vals.max() * 20,  5.0,  t_vals[-1] + 30]),
            maxfev=10000,
        )
        K_fit, r_fit, t0_fit = float(popt[0]), float(popt[1]), float(popt[2])
    except Exception as e:
        return FitResult(
            platform_id=platform_id, K=0, r=0, t0=0, t0_date="",
            r_squared=0, position="unknown", current_val=0,
            current_frac=0, log_fit=use_log,
            error=f"curve_fit failed: {e}",
        )

    # R²
    y_pred    = np.array([_logistic(t, K_fit, r_fit, t0_fit) for t in t_vals])
    ss_res    = float(np.sum((y_vals - y_pred) ** 2))
    ss_tot    = float(np.sum((y_vals - y_vals.mean()) ** 2))
    r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

    # Current position
    p_now_fit = _logistic(TODAY_YR, K_fit, r_fit, t0_fit)
    if use_log:
        # Convert back: log_fit value → original scale
        p_now_orig = math.exp(p_now_fit) - 1
        K_orig     = math.exp(K_fit) - 1
        frac       = p_now_orig / K_orig if K_orig > 0 else 0.0
        current_val = p_now_orig
    else:
        frac        = p_now_fit / K_fit if K_fit > 0 else 0.0
        current_val = p_now_fit

    position = _position_label(frac)

    # t0 → approximate date string
    t0_year  = int(t0_fit)
    t0_month = max(1, min(12, int((t0_fit - t0_year) * 12) + 1))
    t0_date  = f"{t0_year}-{t0_month:02d}"

    return FitResult(
        platform_id  = platform_id,
        K            = round(K_fit, 4),
        r            = round(r_fit, 4),
        t0           = round(t0_fit, 3),
        t0_date      = t0_date,
        r_squared    = round(r_squared, 4),
        position     = position,
        current_val  = round(current_val, 3),
        current_frac = round(frac, 4),
        log_fit      = use_log,
    )


# ══════════════════════════════════════════════════════════════════════════════
# Runner
# ══════════════════════════════════════════════════════════════════════════════

def run_fitter(
    store:      IntelStore,
    platforms:  Optional[list[str]],
    dry_run:    bool,
    verbose:    bool,
) -> list[FitResult]:

    # Which platforms to fit
    if platforms:
        pid_filter = tuple(platforms)
        rows_q = store._c.execute(
            f"SELECT platform_id, name FROM soma_intel_platform "
            f"WHERE platform_id IN ({','.join('?' * len(pid_filter))})",
            pid_filter,
        ).fetchall()
    else:
        rows_q = store._c.execute(
            "SELECT platform_id, name FROM soma_intel_platform ORDER BY platform_id"
        ).fetchall()

    results: list[FitResult] = []

    for prow in rows_q:
        pid = prow["platform_id"]

        history = store._c.execute(
            """
            SELECT date, metric_value FROM soma_intel_scurve_history
            WHERE platform_id = ?
            ORDER BY date ASC
            """,
            (pid,),
        ).fetchall()

        fr = _fit_platform(pid, [dict(r) for r in history])
        results.append(fr)

        if fr.error:
            print(f"  {pid:<22}  ERROR: {fr.error}")
            continue

        metric = store._c.execute(
            "SELECT adoption_metric FROM soma_intel_platform WHERE platform_id=?",
            (pid,),
        ).fetchone()["adoption_metric"]
        metric_short = metric[:35]

        print(
            f"  {pid:<22}  K={fr.K:<10.2f}  r={fr.r:.4f}  "
            f"t0={fr.t0_date}  R²={fr.r_squared:.3f}  "
            f"pos={fr.position:<14}  now={fr.current_frac:.1%}"
            + (" [log]" if fr.log_fit else "")
        )

        if verbose:
            print(f"    metric: {metric_short}  current_val={fr.current_val:.2f}")

        if not dry_run:
            store._c.execute(
                """
                UPDATE soma_intel_platform
                SET curve_K      = ?,
                    curve_r      = ?,
                    curve_t0     = ?,
                    position     = ?,
                    last_fit_ts  = ?
                WHERE platform_id = ?
                """,
                (fr.K, fr.r, fr.t0_date, fr.position, NOW, pid),
            )

    if not dry_run:
        store._c.commit()

    return results


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="SOMA-INTEL S-curve fitter — fit logistic curves to platform adoption data"
    )
    parser.add_argument("--apply",    action="store_true",
                        help="Write fit results to DB (default: dry run / print only)")
    parser.add_argument("--platform", nargs="+", metavar="PLATFORM_ID",
                        help="Fit specific platforms only (e.g. pl_ai pl_robotics)")
    parser.add_argument("--verbose",  action="store_true")
    args = parser.parse_args()

    dry_run = not args.apply
    if dry_run:
        print("DRY RUN — pass --apply to write results to soma_intel_platform\n")

    with IntelStore(db_path=DB_PATH) as store:
        print("[S-Curve Fitter] Fitting logistic curves...\n")
        results = run_fitter(
            store,
            platforms = args.platform,
            dry_run   = dry_run,
            verbose   = args.verbose,
        )

        ok   = [r for r in results if not r.error]
        fail = [r for r in results if r.error]

        print(f"\n  Fitted:  {len(ok)}/{len(results)} platforms")
        if fail:
            print(f"  Failed:  {len(fail)} ({', '.join(r.platform_id for r in fail)})")

        if ok:
            print("\n  Position summary:")
            for fr in sorted(ok, key=lambda r: r.current_frac, reverse=True):
                bar_n = int(fr.current_frac * 20)
                bar   = "█" * bar_n + "░" * (20 - bar_n)
                print(f"    {fr.platform_id:<22} [{bar}] {fr.current_frac:.1%}  {fr.position}")

    if dry_run:
        print("\nDRY RUN complete — pass --apply to write.")
    else:
        print("\nscurve_fitter: OK")


if __name__ == "__main__":
    main()
