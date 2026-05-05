"""
SOMA-INTEL P6.5 — Structural Horizon Track (3-year)

Spec §J: Structural track — monthly cadence, 3-year outlook.
Inputs: platform convergence count, Wright's Law cost-decline signal, regime succession.
Trigger: convergence_score ≥ 3 platforms OR Wright's Law inflection point.

Produces signals with horizon='structural'. These are multi-year platform-level
investment theses: AI commoditization, robotics cost curves, energy storage scaling.

Trigger conditions:
  1. Platform convergence: company touches ≥ 3 platforms (high multi-platform count)
  2. Wright's Law inflection: convergence_score trend shows acceleration
  3. Regime succession: current regime succeeds a prior bear → structural re-rating

The convergence_engine already identifies high-platform companies. This module
reads that output and escalates to structural horizon when platform_count ≥ 3.

Feature weights (structural — convergence-first):
  platform_count : primary (number of distinct ARK platforms the company touches)
  convergence_pairs: secondary (platform pair combinations compound the thesis)
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

HORIZON                     = "structural"
CADENCE                     = "monthly"
MIN_PLATFORM_COUNT          = 3      # minimum platforms for structural signal
HALF_LIFE_DAYS              = 90     # 3yr signals decay very slowly
STRUCTURAL_ANOMALY_SCORE    = 3.0    # fixed anomaly score for structural signals
REGIME_SUCCESSION_THRESHOLD = 2      # # of distinct regimes in recent history


class StructuralTrack:
    """
    Reads convergence_engine output and S-curve data to produce structural signals.

    Args:
        store:      Open IntelStore.
        as_of_date: ISO YYYY-MM-DD.
    """

    def __init__(self, store: IntelStore, as_of_date: str) -> None:
        self._store      = store
        self._as_of_date = as_of_date

    def run(self) -> list[dict]:
        """
        Produce structural signals from:
          A. High-platform-count companies (convergence_engine output)
          B. S-curve inflection tickers (soma_intel_scurve_history WoW delta)
          C. Regime succession events (bear → bull transition in recent history)

        Returns list[dict] of written signals.
        """
        written: list[dict] = []

        # A — Platform convergence signals
        written.extend(self._platform_convergence_signals())

        # B — S-curve inflection signals
        written.extend(self._scurve_inflection_signals())

        # C — Regime succession signals (structural re-rating opportunity)
        written.extend(self._regime_succession_signals())

        log.info(
            "horizon_structural: %d signals written for %s",
            len(written), self._as_of_date,
        )
        return written

    # ── A: Platform convergence ─────────────────────────────────────────────

    def _platform_convergence_signals(self) -> list[dict]:
        """
        Find tickers whose today's convergence signal has platform_count ≥ 3.
        These are structural — multi-platform compounding theses.
        """
        results: list[dict] = []
        try:
            rows = self._store._c.execute(
                """
                SELECT ticker, features
                FROM soma_intel_signal
                WHERE date   = ?
                  AND status = 'active'
                  AND notes LIKE '%Platform convergence%'
                """,
                (self._as_of_date,),
            ).fetchall()
        except Exception:
            return []

        for row in rows:
            ticker = row["ticker"]
            try:
                feat = json.loads(row["features"] or "{}")
                platform_count = feat.get("platform_count", 0)
            except Exception:
                continue

            if platform_count < MIN_PLATFORM_COUNT:
                continue
            if self._existing_structural_signal(ticker):
                continue

            convergence_pairs = feat.get("convergence_pairs", [])
            score = min(10.0, STRUCTURAL_ANOMALY_SCORE + (platform_count - MIN_PLATFORM_COUNT) * 0.5)
            notes = (
                f"structural platform_count={platform_count} "
                f"pairs={len(convergence_pairs)} "
                f"convergence_z={score:.2f}"
            )
            sig = self._write_signal(ticker, round(score, 4), feat, notes)
            results.append(sig)
            # Also update the thematic signal to structural
            self._escalate_to_structural(ticker)

        return results

    # ── B: S-curve inflection ───────────────────────────────────────────────

    def _scurve_inflection_signals(self) -> list[dict]:
        """
        Detect tickers where S-curve position changed materially WoW.
        An inflection is when the S-curve derivative (speed of adoption change)
        flips from decelerating to accelerating.
        """
        results: list[dict] = []
        try:
            rows = self._store._c.execute(
                """
                SELECT ticker, phase, score, delta_score_7d
                FROM soma_intel_scurve_history
                WHERE date_recorded = ?
                  AND delta_score_7d IS NOT NULL
                  AND ABS(delta_score_7d) >= 0.15
                ORDER BY ABS(delta_score_7d) DESC
                LIMIT 10
                """,
                (self._as_of_date,),
            ).fetchall()
        except Exception:
            return []

        for row in rows:
            ticker = row["ticker"]
            if self._existing_structural_signal(ticker):
                continue
            delta = row["delta_score_7d"]
            phase = row["phase"]
            notes = (
                f"structural s_curve_inflection ticker={ticker} "
                f"phase={phase} delta_7d={delta:.3f}"
            )
            feat = {"s_curve_phase": phase, "delta_score_7d": delta,
                    "score": row["score"]}
            sig = self._write_signal(ticker, STRUCTURAL_ANOMALY_SCORE, feat, notes)
            results.append(sig)

        return results

    # ── C: Regime succession ────────────────────────────────────────────────

    def _regime_succession_signals(self) -> list[dict]:
        """
        If the current regime follows a bear regime (succeeded_by chain in
        soma_intel_regime history), surface structural re-rating signals for
        top multi-platform tickers.
        """
        results: list[dict] = []
        try:
            # Check if current regime succeeded a bear regime
            rows = self._store._c.execute(
                """
                SELECT composite_label, trend_state
                FROM soma_intel_regime
                ORDER BY date DESC
                LIMIT 10
                """,
            ).fetchall()
            if not rows:
                return []

            labels = [r["trend_state"] for r in rows]
            # Succession: currently bull but recently bear
            is_succession = (
                labels[0] == "bull"
                and "bear" in labels[1:REGIME_SUCCESSION_THRESHOLD + 2]
            )
            if not is_succession:
                return []

            # Surface top multi-platform tickers for structural re-rating
            platform_rows = self._store._c.execute(
                """
                SELECT ticker, platform_tags
                FROM soma_intel_universe
                WHERE active=1 AND platform_tags IS NOT NULL
                ORDER BY ticker
                LIMIT 5
                """,
            ).fetchall()
            for pr in platform_rows:
                ticker = pr["ticker"]
                if self._existing_structural_signal(ticker):
                    continue
                try:
                    tags = json.loads(pr["platform_tags"] or "[]")
                except Exception:
                    tags = []
                if len(tags) < 2:
                    continue
                notes = (
                    f"structural regime_succession bull_following_bear "
                    f"platforms={len(tags)}"
                )
                feat = {"regime_succession": True, "platform_count": len(tags),
                        "platforms": tags}
                sig = self._write_signal(ticker, STRUCTURAL_ANOMALY_SCORE, feat, notes)
                results.append(sig)

        except Exception as exc:
            log.debug("regime_succession check failed: %s", exc)
        return results

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _existing_structural_signal(self, ticker: str) -> bool:
        try:
            row = self._store._c.execute(
                "SELECT signal_id FROM soma_intel_signal "
                "WHERE ticker=? AND date=? AND horizon='structural' AND status='active'",
                (ticker, self._as_of_date),
            ).fetchone()
            return row is not None
        except Exception:
            return False

    def _escalate_to_structural(self, ticker: str) -> None:
        """Promote existing thematic signals for this ticker to structural."""
        try:
            self._store._c.execute(
                """
                UPDATE soma_intel_signal
                SET horizon = 'structural'
                WHERE ticker = ? AND date = ? AND horizon = 'thematic'
                  AND notes LIKE '%Platform convergence%'
                """,
                (ticker, self._as_of_date),
            )
            self._store._conn.commit()
        except Exception:
            pass

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
