#!/usr/bin/env python3
"""
SOMA-INTEL Phase 4 Step 4.4 — Confirmation Gate

Applies the §I.1 regime-conditional gate to a candidate anomaly, classifying
the result as P1 / P2 / P3 / P-X / None.

Gate rules (§C.2 + §I.1):
  P1 if ANY of:
    1. Standard:       anomaly_score ≥ p1_z AND corroborations ≥ 2
                       AND no exclusion edge AND ticker_edges ≥ 5
    2. High-confidence: anomaly_score ≥ 3.5 AND single-source confidence ≥ 0.85
                       AND novelty_score ≥ 0.7
    3. Leading-indicator: SPECTRE/transcript fires before price (price still flat)
                       → early_warning sub-tag, daily cap of 2

  P2 if: anomaly_score ≥ p2_z AND corroborations ≥ 1  (daily count ≤10)
  P3 if: anomaly_score ≥ 2.0 (logged only)
  P-X if: 1.5 ≤ anomaly_score < 2.5 AND novelty sampled (5% exploration channel)
  None: below all thresholds

Regime-conditional thresholds (§I.1):
  bull_low_easing           → P1: 3.0  P2: 2.5  (many FPs possible)
  bull_med_neutral          → P1: 2.8  P2: 2.4  (standard)
  transition_*              → P1: 2.3  P2: 1.9  (breakdowns are real)
  bear_high_tightening      → P1: 2.5  P2: 2.0  (systemic moves)
  default                   → P1: 2.8  P2: 2.4

Novelty score (§I.2):
  novelty(ticker, signal_type, date) = 1.0 - min(1.0, count_last_90d / 10)

Module design: importable, no raw SQL — uses IntelStore exclusively.

Usage as standalone:
  python3 soma/intel/confirm.py --help   (see anomaly.py for main runner)
"""

from __future__ import annotations

import math
import random
from datetime import date, timedelta
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from soma.intel.store import IntelStore


# ══════════════════════════════════════════════════════════════════════════════
# Thresholds
# ══════════════════════════════════════════════════════════════════════════════

# (p1_threshold, p2_threshold)
_EXACT_THRESHOLDS: dict[str, tuple[float, float]] = {
    "bull_low_easing":    (3.0, 2.5),
    "bull_med_neutral":   (2.8, 2.4),
    "bear_high_tightening": (2.5, 2.0),
}
_DEFAULT_THRESHOLDS = (2.8, 2.4)
_TRANSITION_THRESHOLDS = (2.3, 1.9)


def regime_thresholds(composite_label: str) -> tuple[float, float]:
    """Return (p1_z, p2_z) for a composite regime label."""
    if composite_label in _EXACT_THRESHOLDS:
        return _EXACT_THRESHOLDS[composite_label]
    if composite_label.startswith("transition_"):
        return _TRANSITION_THRESHOLDS
    return _DEFAULT_THRESHOLDS


# ══════════════════════════════════════════════════════════════════════════════
# Half-life table
# ══════════════════════════════════════════════════════════════════════════════

HALF_LIFE: dict[str, int] = {"P1": 5, "P2": 10, "P3": 20, "P-X": 20}


# ══════════════════════════════════════════════════════════════════════════════
# Novelty score
# ══════════════════════════════════════════════════════════════════════════════

def compute_novelty(
    store:       "IntelStore",
    ticker:      str,
    signal_type: str,
    as_of_date:  str,        # ISO YYYY-MM-DD
) -> float:
    """
    Novelty = 1 - min(1, count_last_90d / 10)  per §I.2.
    Counts active signals for (ticker, signal_type) in last 90 calendar days.
    """
    cutoff = (date.fromisoformat(as_of_date) - timedelta(days=90)).isoformat()
    count = store.count_recent_signals(ticker=ticker, notes_prefix=signal_type,
                                        since_date=cutoff)
    return max(0.0, 1.0 - min(1.0, count / 10.0))


# ══════════════════════════════════════════════════════════════════════════════
# Corroboration check
# ══════════════════════════════════════════════════════════════════════════════

# Source types that count as ORACLE pipeline corroboration
_CORROBORATION_SOURCES = {
    "oracle_titan",
    "oracle_cobalt",
    "oracle_spectre",
    "muskonomy",
    "transcript_intel",
    "wiki_article",
    "grok_insight",
    "gemini_insight",
}


def count_corroborations(
    store:      "IntelStore",
    ticker:     str,
    as_of_date: str,
    window_hours: int = 48,
) -> int:
    """
    Count independent ORACLE pipeline edges referencing `ticker` within
    `window_hours` hours before `as_of_date`.

    Returns the number of distinct source_type buckets that fired, which
    counts as independent corroboration even if multiple edges come from
    the same pipeline.
    """
    cutoff_ts = (
        date.fromisoformat(as_of_date) - timedelta(hours=window_hours)
    ).isoformat()
    edges = store.list_recent_edges_for_ticker(
        ticker=ticker, since_ts=cutoff_ts, as_of_date=as_of_date
    )
    sources_seen: set[str] = set()
    for edge in edges:
        src = (edge.get("source_type") or "").lower()
        if src in _CORROBORATION_SOURCES:
            sources_seen.add(src)
    return len(sources_seen)


# ══════════════════════════════════════════════════════════════════════════════
# Exclusion check
# ══════════════════════════════════════════════════════════════════════════════

_EXCLUSION_EDGE_TYPES = {"earnings_overshadow", "halt", "corporate_action"}


def has_exclusion_edge(
    store:      "IntelStore",
    ticker:     str,
    as_of_date: str,
    window_hours: int = 24,
) -> bool:
    """
    Returns True if an exclusion-type edge exists for ticker within ±24h.
    """
    cutoff_ts = (
        date.fromisoformat(as_of_date) - timedelta(hours=window_hours)
    ).isoformat()
    edges = store.list_recent_edges_for_ticker(
        ticker=ticker, since_ts=cutoff_ts, as_of_date=as_of_date
    )
    for edge in edges:
        if (edge.get("edge_type") or "").lower() in _EXCLUSION_EDGE_TYPES:
            return True
    return False


# ══════════════════════════════════════════════════════════════════════════════
# Main gate function
# ══════════════════════════════════════════════════════════════════════════════

def classify_signal(
    anomaly_score:        float,
    n_corroborations:     int,
    ticker_edge_count:    int,
    has_exclusion:        bool,
    regime_label:         str,
    novelty_score:        float,
    top_source_confidence: Optional[float] = None,
    is_leading_indicator:  bool = False,
    daily_p1_count:       int = 0,
    daily_p2_count:       int = 0,
    daily_early_warning_count: int = 0,
    # Meta-learner §I.4: cell-specific threshold overrides
    cell_p1_threshold:    Optional[float] = None,
    cell_p2_threshold:    Optional[float] = None,
) -> tuple[Optional[str], int, str]:
    """
    Apply §I.1 gate. Returns (priority, half_life_days, notes).
    priority is one of: "P1" | "P2" | "P3" | "P-X" | None

    `top_source_confidence`: confidence of the single highest-confidence source
                              (used for High-confidence single-source path)

    `cell_p1_threshold` / `cell_p2_threshold`: optional per-cell overrides from
    the meta-learner (soma_intel_threshold_history). When provided, these replace
    the regime-derived thresholds. Call store.get_cell_threshold() to obtain them.
    """
    base_p1_z, base_p2_z = regime_thresholds(regime_label)
    p1_z = cell_p1_threshold if cell_p1_threshold is not None else base_p1_z
    p2_z = cell_p2_threshold if cell_p2_threshold is not None else base_p2_z
    notes_parts: list[str] = []
    if cell_p1_threshold is not None:
        notes_parts.append(f"cell_adj_p1={cell_p1_threshold:.2f}")

    # --- P1 path 1: Standard ---
    if (
        anomaly_score >= p1_z
        and n_corroborations >= 2
        and not has_exclusion
        and ticker_edge_count >= 5
        and daily_p1_count < 5    # daily cap 3-5, use 5 as ceiling
    ):
        notes_parts.append(f"standard z={anomaly_score:.2f} corr={n_corroborations}")
        return "P1", HALF_LIFE["P1"], "; ".join(notes_parts)

    # --- P1 path 2: High-confidence single-source ---
    if (
        anomaly_score >= 3.5
        and top_source_confidence is not None
        and top_source_confidence >= 0.85
        and novelty_score >= 0.7
        and not has_exclusion
        and daily_p1_count < 5
    ):
        notes_parts.append(
            f"high_conf z={anomaly_score:.2f} "
            f"src_conf={top_source_confidence:.2f} "
            f"novelty={novelty_score:.2f}"
        )
        return "P1", HALF_LIFE["P1"], "; ".join(notes_parts)

    # --- P1 path 3: Leading indicator (early_warning) ---
    if (
        is_leading_indicator
        and daily_early_warning_count < 2
        and not has_exclusion
    ):
        notes_parts.append(f"early_warning z={anomaly_score:.2f}")
        return "P1", HALF_LIFE["P1"], "early_warning; " + "; ".join(notes_parts)

    # --- P2 ---
    if (
        anomaly_score >= p2_z
        and n_corroborations >= 1
        and daily_p2_count < 10
    ):
        notes_parts.append(f"watch z={anomaly_score:.2f} corr={n_corroborations}")
        return "P2", HALF_LIFE["P2"], "; ".join(notes_parts)

    # --- P3 (background log) ---
    if anomaly_score >= 2.0:
        notes_parts.append(f"background z={anomaly_score:.2f}")
        return "P3", HALF_LIFE["P3"], "; ".join(notes_parts)

    # --- P-X exploration channel (5% reserve, 1.5 ≤ z < 2.5) ---
    if 1.5 <= anomaly_score < 2.5 and novelty_score > 0.3:
        if random.random() < 0.05:   # 5% sample probability
            notes_parts.append(f"exploration z={anomaly_score:.2f} novelty={novelty_score:.2f}")
            return "P-X", HALF_LIFE["P-X"], "; ".join(notes_parts)

    return None, 0, ""


# ══════════════════════════════════════════════════════════════════════════════
# Multi-horizon boost (§J)
# ══════════════════════════════════════════════════════════════════════════════

MULTI_HORIZON_BOOST   = 1.5    # multiplier when ≥2 horizons fire same ticker
MULTI_HORIZON_CAP     = 10.0   # anomaly_score ceiling after boost
MULTI_HORIZON_MIN     = 2      # minimum distinct horizons to trigger boost


def apply_multi_horizon_boost(
    store:      "IntelStore",
    as_of_date: str,
) -> list[dict]:
    """
    §J boost: if a ticker has active signals on ≥2 distinct horizons today,
    multiply anomaly_score × 1.5 (capped at MULTI_HORIZON_CAP) and append
    'multi_horizon:<h1,h2,...>' to the signal notes.

    Only boosts signals that have NOT already been boosted (notes must not
    already contain 'multi_horizon:').

    Returns list of dicts for each boosted signal:
      {signal_id, ticker, horizons, old_score, new_score}
    """
    boosted: list[dict] = []

    # Collect all active signals today grouped by ticker
    try:
        rows = store._c.execute(
            """
            SELECT signal_id, ticker, horizon, anomaly_score, notes
            FROM soma_intel_signal
            WHERE date = ? AND status = 'active'
              AND horizon IS NOT NULL
              AND notes NOT LIKE '%multi_horizon:%'
            """,
            (as_of_date,),
        ).fetchall()
    except Exception:
        return []

    # Group by ticker → {horizon: [signal_id, ...]}
    from collections import defaultdict
    ticker_horizons: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        h = row["horizon"]
        if h:
            ticker_horizons[row["ticker"]][h].append(
                {"signal_id": row["signal_id"],
                 "anomaly_score": row["anomaly_score"],
                 "notes": row["notes"] or ""}
            )

    for ticker, horizon_map in ticker_horizons.items():
        distinct_horizons = list(horizon_map.keys())
        if len(distinct_horizons) < MULTI_HORIZON_MIN:
            continue

        horizons_tag = ",".join(sorted(distinct_horizons))
        # Boost every signal for this ticker today
        for h, sigs in horizon_map.items():
            for sig in sigs:
                old_score = sig["anomaly_score"]
                new_score = round(min(MULTI_HORIZON_CAP, old_score * MULTI_HORIZON_BOOST), 4)
                new_notes = (sig["notes"].rstrip("; ") + f"; multi_horizon:{horizons_tag}").lstrip("; ")
                try:
                    store._c.execute(
                        "UPDATE soma_intel_signal "
                        "SET anomaly_score=?, notes=? WHERE signal_id=?",
                        (new_score, new_notes, sig["signal_id"]),
                    )
                    boosted.append({
                        "signal_id": sig["signal_id"],
                        "ticker":    ticker,
                        "horizons":  horizons_tag,
                        "old_score": old_score,
                        "new_score": new_score,
                    })
                except Exception:
                    pass

    if boosted:
        try:
            store._conn.commit()
        except Exception:
            pass

    return boosted
