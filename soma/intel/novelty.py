"""
SOMA-INTEL P6.2 — Novelty Score

Computes how "novel" a (ticker, signal_type) pair is relative to its recent
history.  A pair that has fired many times in the last 90 days is stale;
one that hasn't fired recently is novel.

Formula (§I.2):
    novelty_score = 1.0 - min(1.0, count_in_last_90d(ticker, signal_type) / 10)

Range: [0, 1].
- 1.0 → brand-new pair (no prior signals in 90d)
- 0.5 → 5 prior signals in 90d
- 0.0 → saturated at ≥ 10 prior signals in 90d

signal_type (v1) = horizon ('tactical' | 'thematic' | 'structural').
When signal_propagator is updated to write f1..f5 features into live signals,
signal_type should be upgraded to the dominant f1..f5 feature per that signal.

Usage:
    from soma.intel.novelty import novelty_score
    score = novelty_score(store, 'TSLA', 'tactical', '2026-05-05')
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from soma.intel.store import IntelStore

# ── Path bootstrap ─────────────────────────────────────────────────────────────
_HERE         = Path(__file__).resolve().parent
_DABEIBA_ROOT = _HERE.parent.parent.parent
for _p in [str(_DABEIBA_ROOT), str(_DABEIBA_ROOT / "shared")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ── Constants (§I.2) ──────────────────────────────────────────────────────────
NOVELTY_WINDOW_DAYS   = 90   # look-back window
NOVELTY_SATURATION_N  = 10   # count at which novelty = 0


def novelty_score(
    store:       "IntelStore",
    ticker:      str,
    signal_type: str,
    as_of_date:  str,
) -> float:
    """
    Compute novelty score for a (ticker, signal_type) pair.

    novelty_score = 1.0 - min(1.0, count_in_last_90d(ticker, signal_type) / 10)

    Args:
        store:       Open IntelStore instance.
        ticker:      Ticker symbol (e.g. 'TSLA').
        signal_type: Horizon string — 'tactical' | 'thematic' | 'structural'.
        as_of_date:  ISO YYYY-MM-DD reference date (today for live use,
                     sim_date for backtest use).

    Returns:
        Float in [0.0, 1.0].
    """
    since = _days_before(as_of_date, NOVELTY_WINDOW_DAYS)
    count = store.count_signals_by_ticker_type(ticker, signal_type, since)
    return 1.0 - min(1.0, count / NOVELTY_SATURATION_N)


def _days_before(iso_date: str, n_days: int) -> str:
    """Return ISO date string n_days before iso_date."""
    d = date.fromisoformat(iso_date)
    return (d - timedelta(days=n_days)).isoformat()


# ── CLI (quick spot-check) ────────────────────────────────────────────────────

def _main() -> None:
    import argparse
    from soma.intel.store import IntelStore

    _SOMA_DB = _DABEIBA_ROOT / "shared" / "soma" / "data" / "soma.db"

    parser = argparse.ArgumentParser(description="SOMA-INTEL novelty score spot-check")
    parser.add_argument("--ticker",      required=True)
    parser.add_argument("--signal-type", required=True,
                        choices=["tactical", "thematic", "structural"])
    parser.add_argument("--as-of",       required=True, help="ISO YYYY-MM-DD")
    parser.add_argument("--db",          default=str(_SOMA_DB))
    args = parser.parse_args()

    with IntelStore(db_path=args.db) as store:
        score = novelty_score(store, args.ticker, args.signal_type, args.as_of)
        since = _days_before(args.as_of, NOVELTY_WINDOW_DAYS)
        count = store.count_signals_by_ticker_type(args.ticker, args.signal_type, since)
        print(f"ticker={args.ticker} type={args.signal_type} as_of={args.as_of}")
        print(f"count_in_last_90d={count}  novelty_score={score:.3f}")


if __name__ == "__main__":
    _main()
