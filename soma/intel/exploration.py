"""
SOMA-INTEL P6.3 — Exploration Channel

Formalizes the P-X (exploration) signal track per §I.3.

Spec:
  - 5% reserved for low-z signals (1.5 ≤ z < 2.5 — below the P3 threshold of 2.5)
  - Sample 1-2 signals per day, weighted proportionally to novelty_score
  - Surface as priority P-X; tag notes with "exploration_channel"
  - Higher-novelty (ticker, signal_type) pairs are preferentially selected
  - These are training data for the meta-learner; user audits feed back into §I.4

Usage (daily, called from run_day.py step_soma_intel):
    from soma.intel.exploration import ExplorationChannel
    channel = ExplorationChannel(store, as_of_date="2026-05-05")
    signals = channel.sample()  # returns list[dict] of 1-2 signals written to DB
"""

from __future__ import annotations

import json
import logging
import random
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

from soma.intel.novelty import novelty_score
from soma.intel.store import IntelStore

log = logging.getLogger(__name__)

# ── Constants (§I.3) ──────────────────────────────────────────────────────────
EXPLORATION_Z_MIN      = 1.5    # lower bound of low-z band
EXPLORATION_Z_MAX      = 2.5    # upper bound of low-z band (exclusive)
EXPLORATION_DAILY_MIN  = 1      # min signals surfaced per day
EXPLORATION_DAILY_MAX  = 2      # max signals surfaced per day
EXPLORATION_TAG        = "exploration_channel"
EXPLORATION_PRIORITY   = "P-X"


class ExplorationChannel:
    """
    Samples low-z signals for the exploration channel.

    Args:
        store:      Open IntelStore instance.
        as_of_date: ISO YYYY-MM-DD reference date.
        seed:       Optional random seed (for deterministic tests).
    """

    def __init__(
        self,
        store:      IntelStore,
        as_of_date: str,
        seed:       Optional[int] = None,
    ) -> None:
        self._store      = store
        self._as_of_date = as_of_date
        self._rng        = random.Random(seed)

    def get_candidates(self) -> list[dict]:
        """
        Return all active signals in the low-z band (1.5 ≤ anomaly_score < 2.5)
        for today that are not already tagged as exploration_channel.

        Returns list of signal dicts with added 'novelty' key.
        """
        rows = self._store._c.execute(
            """
            SELECT signal_id, ticker, date, priority, anomaly_score,
                   features, horizon, notes
            FROM soma_intel_signal
            WHERE date   = ?
              AND status = 'active'
              AND anomaly_score >= ?
              AND anomaly_score <  ?
              AND (notes IS NULL OR notes NOT LIKE ?)
            ORDER BY anomaly_score DESC
            """,
            (
                self._as_of_date,
                EXPLORATION_Z_MIN,
                EXPLORATION_Z_MAX,
                f"%{EXPLORATION_TAG}%",
            ),
        ).fetchall()

        candidates = []
        for r in rows:
            d = dict(r)
            # Compute novelty for this (ticker, signal_type) pair
            signal_type = d.get("horizon") or "tactical"
            d["novelty"] = novelty_score(
                self._store, d["ticker"], signal_type, self._as_of_date
            )
            candidates.append(d)

        return candidates

    def sample(self, n: Optional[int] = None) -> list[dict]:
        """
        Sample 1-2 candidates weighted by novelty_score and tag them as P-X.

        Args:
            n: Override number to sample (default: random in [1, 2]).

        Returns:
            List of sampled signal dicts (with updated notes in DB).
        """
        candidates = self.get_candidates()
        if not candidates:
            log.info("exploration_channel: no low-z candidates for %s", self._as_of_date)
            return []

        # Weighted sampling by novelty_score
        weights = [c["novelty"] for c in candidates]
        total_weight = sum(weights)

        if total_weight == 0:
            # All candidates have novelty 0 (fully saturated) — uniform sampling
            weights = [1.0] * len(candidates)
            total_weight = float(len(candidates))
            log.debug("exploration_channel: all novelty=0, using uniform sampling")

        n_to_sample = n if n is not None else self._rng.randint(
            EXPLORATION_DAILY_MIN, EXPLORATION_DAILY_MAX
        )
        n_to_sample = min(n_to_sample, len(candidates))

        selected = self._weighted_sample(candidates, weights, n_to_sample)
        self._tag_as_exploration(selected)

        log.info(
            "exploration_channel: sampled %d P-X signals on %s (from %d candidates)",
            len(selected), self._as_of_date, len(candidates),
        )
        return selected

    def _weighted_sample(
        self,
        candidates: list[dict],
        weights:    list[float],
        n:          int,
    ) -> list[dict]:
        """
        Sample n items from candidates without replacement, weighted by weights.
        Uses the roulette-wheel method.
        """
        selected:   list[dict]  = []
        remaining:  list[dict]  = list(candidates)
        rem_weights: list[float] = list(weights)

        for _ in range(n):
            if not remaining:
                break
            total = sum(rem_weights)
            if total == 0:
                break
            r = self._rng.uniform(0, total)
            cumulative = 0.0
            chosen_idx = 0
            for i, w in enumerate(rem_weights):
                cumulative += w
                if r <= cumulative:
                    chosen_idx = i
                    break
            selected.append(remaining.pop(chosen_idx))
            rem_weights.pop(chosen_idx)

        return selected

    def _tag_as_exploration(self, signals: list[dict]) -> None:
        """
        Update selected signals in DB: set priority=P-X, append exploration_channel tag.
        """
        for sig in signals:
            signal_id = sig["signal_id"]
            existing_notes = sig.get("notes") or ""
            new_notes = (
                f"{existing_notes} | {EXPLORATION_TAG}"
                if existing_notes
                else EXPLORATION_TAG
            )
            self._store._c.execute(
                """
                UPDATE soma_intel_signal
                SET priority = ?, notes = ?
                WHERE signal_id = ?
                """,
                (EXPLORATION_PRIORITY, new_notes, signal_id),
            )
            sig["priority"] = EXPLORATION_PRIORITY
            sig["notes"]    = new_notes

        self._store._conn.commit()


# ── CLI (daily spot-check) ────────────────────────────────────────────────────

def _main() -> None:
    import argparse
    from soma.intel.store import IntelStore

    _SOMA_DB = _DABEIBA_ROOT / "shared" / "soma" / "data" / "soma.db"

    parser = argparse.ArgumentParser(description="SOMA-INTEL exploration channel sampler")
    parser.add_argument("--as-of", required=True, help="ISO YYYY-MM-DD")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print candidates without writing to DB")
    parser.add_argument("--db", default=str(_SOMA_DB))
    args = parser.parse_args()

    with IntelStore(db_path=args.db) as store:
        channel = ExplorationChannel(store, as_of_date=args.as_of)
        candidates = channel.get_candidates()
        print(f"Low-z candidates for {args.as_of}: {len(candidates)}")
        for c in candidates[:10]:
            print(f"  {c['ticker']:6s} z={c['anomaly_score']:.2f} "
                  f"horizon={c.get('horizon','?'):10s} novelty={c['novelty']:.2f}")

        if args.dry_run:
            print("(dry-run: no DB writes)")
        else:
            sampled = channel.sample()
            print(f"Sampled {len(sampled)} P-X signal(s):")
            for s in sampled:
                print(f"  {s['ticker']:6s} z={s['anomaly_score']:.2f} novelty={s['novelty']:.2f}")


if __name__ == "__main__":
    _main()
