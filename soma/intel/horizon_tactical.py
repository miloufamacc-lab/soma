"""
SOMA-INTEL P6.5 — Tactical Horizon Track (3-month)

Spec §J: Tactical track — daily cadence, 3-month outlook.
Features: f1 (5d return z-score) + f2 (20d return z-score) + f4 (volume z-score).
Threshold: z ≥ 2.5 (regime-adjusted).

Produces signals with horizon='tactical'. These are short-term momentum,
mean-reversion, and breakout signals. The dominant axis is recent price action.

Feature weights (tactical):
  f1_ret5d_z  : 0.40  (primary — short-term momentum)
  f2_ret20d_z : 0.30  (secondary — medium-term trend)
  f4_volume_z : 0.30  (confirmation — unusual volume)
  f3_rvol_z   : 0.00  (not used in tactical — too slow)
  f5_sector_z : 0.00  (not used in tactical — cross-sectional, thematic)

Usage (from run_day.py):
    from soma.intel.horizon_tactical import TacticalTrack
    track = TacticalTrack(store, as_of_date="2026-05-05")
    signals = track.run()  # list[dict] of signals written to DB
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

_HERE         = Path(__file__).resolve().parent
_DABEIBA_ROOT = _HERE.parent.parent.parent
for _p in [str(_DABEIBA_ROOT), str(_DABEIBA_ROOT / "shared")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from soma.intel.store import IntelStore

log = logging.getLogger(__name__)

HORIZON          = "tactical"
CADENCE          = "daily"
BASE_THRESHOLD   = 2.5   # regime-adjusted in _regime_threshold()
HALF_LIFE_DAYS   = 15    # 3-month signals decay in ~15 trading days

# Feature weights (must sum to 1.0)
WEIGHTS = {
    "f1_ret5d_z":  0.40,
    "f2_ret20d_z": 0.30,
    "f4_volume_z": 0.30,
}


def _regime_threshold(composite_label: str) -> float:
    """Tactical threshold adjusted for regime volatility."""
    if composite_label.startswith("transition_"):
        return 2.0   # more sensitive during transitions
    if "bear" in composite_label:
        return 2.3
    return BASE_THRESHOLD  # 2.5 for bull regimes


def _compute_tactical_score(features: dict) -> float:
    """Weighted z-score combining f1 + f2 + f4."""
    weighted = sum(
        WEIGHTS.get(f, 0.0) * abs(features.get(f, 0.0))
        for f in WEIGHTS
    )
    return round(weighted, 4)


class TacticalTrack:
    """
    Reads today's anomaly baseline and produces tactical-horizon signals.

    Args:
        store:      Open IntelStore.
        as_of_date: ISO YYYY-MM-DD.
    """

    def __init__(self, store: IntelStore, as_of_date: str) -> None:
        self._store      = store
        self._as_of_date = as_of_date

    def run(self) -> list[dict]:
        """
        Compute tactical scores for all active tickers and write qualifying signals.

        Returns:
            List of written signal dicts.
        """
        regime = self._current_regime()
        threshold = _regime_threshold(regime)

        tickers = self._active_tickers()
        written: list[dict] = []

        for ticker in tickers:
            feats = self._load_features(ticker, regime)
            if feats is None:
                continue
            score = _compute_tactical_score(feats)
            if score < threshold:
                continue

            existing = self._existing_signal(ticker)
            if existing and existing.get("horizon") == HORIZON:
                continue  # already have a tactical signal for today

            notes = (
                f"tactical z={score:.3f} "
                f"f1={feats.get('f1_ret5d_z', 0):.2f} "
                f"f2={feats.get('f2_ret20d_z', 0):.2f} "
                f"f4={feats.get('f4_volume_z', 0):.2f}"
            )
            sig = self._write_signal(ticker, score, feats, notes)
            written.append(sig)

        log.info(
            "horizon_tactical: %d signals written for %s (threshold=%.2f)",
            len(written), self._as_of_date, threshold,
        )
        return written

    def _current_regime(self) -> str:
        """Return today's composite_label from soma_intel_regime."""
        try:
            row = self._store._c.execute(
                "SELECT composite_label FROM soma_intel_regime WHERE date=?",
                (self._as_of_date,),
            ).fetchone()
            return row["composite_label"] if row else "bull_med_neutral"
        except Exception:
            return "bull_med_neutral"

    def _active_tickers(self) -> list[str]:
        """Return active universe tickers."""
        try:
            rows = self._store._c.execute(
                "SELECT ticker FROM soma_intel_universe WHERE active=1"
            ).fetchall()
            return [r["ticker"] for r in rows]
        except Exception:
            return []

    def _load_features(
        self, ticker: str, regime: str
    ) -> Optional[dict]:
        """Load f1, f2, f4 z-scores from soma_intel_baseline for this ticker/regime."""
        try:
            rows = self._store._c.execute(
                """
                SELECT feature, mean, stdev
                FROM soma_intel_baseline
                WHERE ticker=? AND regime_label=?
                  AND feature IN ('f1_ret5d_z', 'f2_ret20d_z', 'f4_volume_z')
                """,
                (ticker, regime),
            ).fetchall()
            if not rows:
                return None
            # Build feature dict from stored mean (z-score proxy)
            return {r["feature"]: round(r["mean"], 4) for r in rows}
        except Exception:
            return None

    def _existing_signal(self, ticker: str) -> Optional[dict]:
        """Check if a tactical signal already exists for this ticker today."""
        try:
            row = self._store._c.execute(
                "SELECT signal_id, horizon FROM soma_intel_signal "
                "WHERE ticker=? AND date=? AND horizon=? AND status='active'",
                (ticker, self._as_of_date, HORIZON),
            ).fetchone()
            return dict(row) if row else None
        except Exception:
            return None

    def _write_signal(
        self, ticker: str, score: float, features: dict, notes: str
    ) -> dict:
        cur = self._store._c.execute(
            """
            INSERT INTO soma_intel_signal
              (ticker, date, priority, anomaly_score, features, corroboration_count,
               half_life_days, status, horizon, notes)
            VALUES (?, ?, 'P3', ?, ?, 0, ?, 'active', ?, ?)
            """,
            (
                ticker, self._as_of_date, score,
                json.dumps(features), HALF_LIFE_DAYS, HORIZON, notes,
            ),
        )
        self._store._conn.commit()
        return {"signal_id": cur.lastrowid, "ticker": ticker, "horizon": HORIZON,
                "anomaly_score": score, "date": self._as_of_date}
