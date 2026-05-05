"""
SOMA-INTEL P6.5 — Thematic Horizon Track (12-month)

Spec §J: Thematic track — weekly cadence, 12-month outlook.
Features: f5 (sector-relative z-score) + S-curve position deltas.
Threshold: z ≥ 2.0 over 20-day rolling window.

Produces signals with horizon='thematic'. These are sector-rotation and
platform-thesis signals — investment themes that play out over 12 months.
Convergence engine signals are thematic by nature (cross-platform compound theses).

Feature weights (thematic):
  f5_sector_z  : 0.50  (primary — sector-relative momentum)
  f2_ret20d_z  : 0.30  (secondary — 20-day trend, monthly drift)
  f1_ret5d_z   : 0.10  (noise filter — suppress pure noise)
  f3_rvol_z    : 0.10  (conviction check — vol expansion on themes)

Usage (from run_day.py, runs weekly):
    from soma.intel.horizon_thematic import ThematicTrack
    track = ThematicTrack(store, as_of_date="2026-05-05")
    signals = track.run()
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Optional

_HERE         = Path(__file__).resolve().parent
_DABEIBA_ROOT = _HERE.parent.parent.parent
for _p in [str(_DABEIBA_ROOT), str(_DABEIBA_ROOT / "shared")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from soma.intel.store import IntelStore

log = logging.getLogger(__name__)

HORIZON        = "thematic"
CADENCE        = "weekly"
BASE_THRESHOLD = 2.0
HALF_LIFE_DAYS = 40   # 12-month signals decay over ~40 trading days

WEIGHTS = {
    "f5_sector_z": 0.50,
    "f2_ret20d_z": 0.30,
    "f1_ret5d_z":  0.10,
    "f3_rvol_z":   0.10,
}


def _compute_thematic_score(features: dict) -> float:
    """Weighted z-score combining f5 (primary) + f2, f1, f3 (supporting)."""
    weighted = sum(
        WEIGHTS.get(f, 0.0) * abs(features.get(f, 0.0))
        for f in WEIGHTS
    )
    return round(weighted, 4)


class ThematicTrack:
    """
    Reads today's sector-relative anomaly baseline and writes thematic signals.

    Args:
        store:      Open IntelStore.
        as_of_date: ISO YYYY-MM-DD.
    """

    def __init__(self, store: IntelStore, as_of_date: str) -> None:
        self._store      = store
        self._as_of_date = as_of_date

    def run(self) -> list[dict]:
        """
        Compute thematic scores and write qualifying signals. Also promotes
        convergence_engine signals to horizon='thematic' if not already set.

        Returns:
            List of written/promoted signal dicts.
        """
        regime  = self._current_regime()
        written: list[dict] = []

        # A — z-score based thematic signals from baseline
        for ticker in self._active_tickers():
            feats = self._load_features(ticker, regime)
            if feats is None:
                continue
            score = _compute_thematic_score(feats)
            if score < BASE_THRESHOLD:
                continue
            if self._existing_signal(ticker):
                continue
            notes = (
                f"thematic z={score:.3f} "
                f"f5={feats.get('f5_sector_z', 0):.2f} "
                f"f2={feats.get('f2_ret20d_z', 0):.2f}"
            )
            sig = self._write_signal(ticker, score, feats, notes)
            written.append(sig)

        # B — Promote convergence_engine signals to thematic horizon
        promoted = self._promote_convergence_signals()
        written.extend(promoted)

        log.info(
            "horizon_thematic: %d signals written/promoted for %s",
            len(written), self._as_of_date,
        )
        return written

    def _current_regime(self) -> str:
        try:
            row = self._store._c.execute(
                "SELECT composite_label FROM soma_intel_regime WHERE date=?",
                (self._as_of_date,),
            ).fetchone()
            return row["composite_label"] if row else "bull_med_neutral"
        except Exception:
            return "bull_med_neutral"

    def _active_tickers(self) -> list[str]:
        try:
            rows = self._store._c.execute(
                "SELECT ticker FROM soma_intel_universe WHERE active=1"
            ).fetchall()
            return [r["ticker"] for r in rows]
        except Exception:
            return []

    def _load_features(self, ticker: str, regime: str) -> Optional[dict]:
        try:
            rows = self._store._c.execute(
                """
                SELECT feature, mean
                FROM soma_intel_baseline
                WHERE ticker=? AND regime_label=?
                  AND feature IN ('f5_sector_z', 'f2_ret20d_z', 'f1_ret5d_z', 'f3_rvol_z')
                """,
                (ticker, regime),
            ).fetchall()
            if not rows:
                return None
            return {r["feature"]: round(r["mean"], 4) for r in rows}
        except Exception:
            return None

    def _existing_signal(self, ticker: str) -> Optional[dict]:
        try:
            row = self._store._c.execute(
                "SELECT signal_id FROM soma_intel_signal "
                "WHERE ticker=? AND date=? AND horizon=? AND status='active'",
                (ticker, self._as_of_date, HORIZON),
            ).fetchone()
            return dict(row) if row else None
        except Exception:
            return None

    def _promote_convergence_signals(self) -> list[dict]:
        """
        Convergence engine writes signals with horizon='thematic' already.
        This method ensures any that were written with a stale horizon get updated.
        """
        try:
            rows = self._store._c.execute(
                """
                UPDATE soma_intel_signal
                SET horizon = 'thematic'
                WHERE date   = ?
                  AND notes  LIKE '%Platform convergence%'
                  AND (horizon IS NULL OR horizon != 'thematic')
                """,
                (self._as_of_date,),
            )
            self._store._conn.commit()
            if rows.rowcount > 0:
                log.info("horizon_thematic: promoted %d convergence signals to thematic",
                         rows.rowcount)
            return []
        except Exception:
            return []

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
            (ticker, self._as_of_date, score, json.dumps(features),
             HALF_LIFE_DAYS, HORIZON, notes),
        )
        self._store._conn.commit()
        return {"signal_id": cur.lastrowid, "ticker": ticker, "horizon": HORIZON,
                "anomaly_score": score, "date": self._as_of_date}
