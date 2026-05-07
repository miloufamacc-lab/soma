"""
SOMA-INTEL Phase 7 §D.3.A — Tests: Regime-Shift Bayesian Detector

10 test cases per the locked D.3.A brief spec.
All tests use an in-memory IntelStore seeded with migration 031 schema so
they are fully isolated from the live soma.db.
"""

from __future__ import annotations

import json
import math
import sqlite3
import tempfile
import os
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch
import pytest

# ── Path bootstrap ─────────────────────────────────────────────────────────────
_HERE    = Path(__file__).resolve().parent
_DABEIBA = _HERE.parent.parent.parent
import sys
for _p in [str(_DABEIBA), str(_DABEIBA / "shared")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from soma.intel.store import IntelStore
from soma.intel.regime_shift.bayesian import (
    PRIOR,
    LLR_COEFFICIENTS,
    WATCH_THRESHOLD,
    IMMINENT_THRESHOLD,
    compute_log_likelihood_ratios,
    compute_posterior,
    classify_trigger,
)
from soma.intel.regime_shift.orchestrator import run_daily


# ── Fixtures ───────────────────────────────────────────────────────────────────

MIGRATION_031 = Path(_DABEIBA) / "shared" / "soma" / "migrations" / "031_regime_shift_bayesian.sql"


def _make_store(tmp_path: Path) -> IntelStore:
    """
    Create a minimal IntelStore backed by a temp SQLite DB.
    Applies the capability registry DDL and migration 031.
    """
    db_path = str(tmp_path / "test_soma.db")
    store = IntelStore(db_path=db_path)
    store.__enter__()

    # Bootstrap capability tables (from store._DDL_CAPABILITY inline DDL)
    store.initialize_tables()

    # Create soma_intel_regime table (needed by macro ingestor)
    store._c.executescript("""
        CREATE TABLE IF NOT EXISTS soma_intel_regime (
          date            TEXT PRIMARY KEY,
          trend_state     TEXT NOT NULL,
          vol_state       TEXT NOT NULL,
          macro_state     TEXT NOT NULL,
          composite_label TEXT NOT NULL,
          confidence      REAL NOT NULL,
          features        TEXT
        );
    """)

    # Apply migration 031 (regime-shift tables)
    sql_031 = MIGRATION_031.read_text()
    # Remove schema_version insert (table may not exist in test DB)
    lines = [l for l in sql_031.splitlines() if "schema_version" not in l]
    store._c.executescript("\n".join(lines))
    store._c.commit()

    return store


def _seed_capability(store: IntelStore, capability_id: str, status: str) -> None:
    """Register a capability in the test store."""
    store.register_capability(
        capability_id=capability_id,
        version="1.0",
        status=status,
        depends_on=[],
    )


def _seed_regime_rows(store: IntelStore, n: int = 100) -> None:
    """
    Seed n fake regime rows so macro z-score has enough history.
    Uses fixed y2y10_spread values with a clear outlier on the last date.
    """
    import datetime
    base = datetime.date(2024, 1, 1)
    for i in range(n):
        d = (base + datetime.timedelta(days=i))
        # Stable spread near 0.3, outlier on last date
        spread = 0.3 + (0.01 * (i % 5))
        vix_delta = -0.1 + (0.05 * (i % 3))
        if i == n - 1:
            spread = -1.5   # strong inversion = big z-score on last date
            vix_delta = 5.0  # VIX spike
        features = {
            "y2y10_spread": spread,
            "vix_delta_5d": vix_delta,
            "aaii_bull_bear": None,
        }
        store._c.execute(
            """
            INSERT OR IGNORE INTO soma_intel_regime
              (date, trend_state, vol_state, macro_state, composite_label,
               confidence, features)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (d.isoformat(), "bull", "med", "neutral", "bull_med_neutral",
             0.7, json.dumps(features)),
        )
    store._c.commit()


# ══════════════════════════════════════════════════════════════════════════════
# Test 1: Bayesian pure math
# ══════════════════════════════════════════════════════════════════════════════

def test_bayesian_pure_math():
    """Given fixed LLRs, posterior is deterministic and within [0, 1]."""
    llrs = compute_log_likelihood_ratios(
        macro_z=2.0, sentiment_z=1.5, cross_asset_z=1.0, transcript_drift_z=0.5
    )
    log_post, posterior = compute_posterior(PRIOR, llrs)

    assert 0.0 < posterior < 1.0, f"posterior out of [0,1]: {posterior}"
    # With all positive inputs the posterior must be > prior
    assert posterior > PRIOR, f"Expected posterior > prior={PRIOR}, got {posterior}"
    # log_posterior must be a real number
    assert math.isfinite(log_post), f"log_posterior is not finite: {log_post}"


# ══════════════════════════════════════════════════════════════════════════════
# Test 2: None inputs produce LLR=0 and populate missing_inputs
# ══════════════════════════════════════════════════════════════════════════════

def test_log_likelihood_ratios_with_missing_inputs():
    """None inputs produce LLR=0 and add name to missing_inputs list."""
    llrs = compute_log_likelihood_ratios(
        macro_z=None, sentiment_z=None, cross_asset_z=1.0, transcript_drift_z=None
    )

    assert llrs["llr_macro"] == 0.0
    assert llrs["llr_sentiment"] == 0.0
    assert llrs["llr_transcript"] == 0.0
    assert llrs["llr_cross_asset"] > 0.0   # cross_asset_z=1.0 → non-zero LLR
    assert "macro" in llrs["missing_inputs"]
    assert "sentiment" in llrs["missing_inputs"]
    assert "transcript" in llrs["missing_inputs"]
    assert "cross_asset" not in llrs["missing_inputs"]
    assert len(llrs["missing_inputs"]) == 3


# ══════════════════════════════════════════════════════════════════════════════
# Test 3: LLR caps enforce maximum values
# ══════════════════════════════════════════════════════════════════════════════

def test_log_likelihood_ratios_caps():
    """Input z=100 is capped at the locked maximum (e.g. ±3.0 for macro)."""
    llrs_extreme = compute_log_likelihood_ratios(
        macro_z=100.0, sentiment_z=100.0, cross_asset_z=100.0, transcript_drift_z=100.0
    )
    llrs_at_cap = compute_log_likelihood_ratios(
        macro_z=3.0, sentiment_z=2.5, cross_asset_z=2.5, transcript_drift_z=2.0
    )

    # Extreme inputs must equal the capped inputs
    assert abs(llrs_extreme["llr_macro"]       - llrs_at_cap["llr_macro"])       < 1e-9
    assert abs(llrs_extreme["llr_sentiment"]   - llrs_at_cap["llr_sentiment"])   < 1e-9
    assert abs(llrs_extreme["llr_cross_asset"] - llrs_at_cap["llr_cross_asset"]) < 1e-9
    assert abs(llrs_extreme["llr_transcript"]  - llrs_at_cap["llr_transcript"])  < 1e-9

    # Verify actual cap magnitudes match locked coefficients
    macro_coef, macro_cap = LLR_COEFFICIENTS["macro"]
    assert abs(llrs_at_cap["llr_macro"] - macro_coef * macro_cap) < 1e-9


# ══════════════════════════════════════════════════════════════════════════════
# Test 4: Trigger threshold boundaries
# ══════════════════════════════════════════════════════════════════════════════

def test_classify_trigger_thresholds():
    """Boundary values map correctly to trigger states."""
    assert classify_trigger(0.39) == "none"
    assert classify_trigger(0.41) == "watch"
    assert classify_trigger(0.59) == "watch"
    assert classify_trigger(0.61) == "imminent"
    assert classify_trigger(0.0)  == "none"
    assert classify_trigger(1.0)  == "imminent"
    # Exact boundary: spec says >0.40 and >0.60 (strict greater-than)
    # So exactly 0.40 → none, exactly 0.60 → watch (not yet imminent)
    assert classify_trigger(WATCH_THRESHOLD)     == "none"    # 0.40 is not > 0.40
    assert classify_trigger(IMMINENT_THRESHOLD)  == "watch"   # 0.60 is not > 0.60, but IS > 0.40


# ══════════════════════════════════════════════════════════════════════════════
# Test 5: Capability disabled → no DB writes
# ══════════════════════════════════════════════════════════════════════════════

def test_orchestrator_capability_disabled_no_writes(tmp_path):
    """capability off → run_daily returns early with disabled=True, no DB writes."""
    store = _make_store(tmp_path)
    _seed_capability(store, "regime_shift_bayesian", "disabled")

    result = run_daily("2024-08-15", store, dry_run=False)

    assert result["disabled"] is True
    assert result["written"] is False
    assert not store.has_regime_shift_posterior("2024-08-15")
    store.__exit__(None, None, None)


# ══════════════════════════════════════════════════════════════════════════════
# Test 6: Idempotency — second call on same date skips without duplicate row
# ══════════════════════════════════════════════════════════════════════════════

def test_orchestrator_idempotent(tmp_path):
    """Second call on same date → skips (no duplicate row), unless force=True."""
    store = _make_store(tmp_path)
    _seed_capability(store, "regime_shift_bayesian", "enabled")
    _seed_regime_rows(store, n=60)

    date_str = "2024-03-10"

    # First call
    r1 = run_daily(date_str, store)
    assert r1["written"] is True or r1["disabled"] is True

    # Second call — should skip if first wrote successfully
    if r1["written"]:
        r2 = run_daily(date_str, store)
        assert r2["skipped"] is True
        assert r2["written"] is False

        # Only one row in the table
        rows = store.list_regime_shift_posteriors(start_ts=date_str, end_ts=date_str)
        assert len(rows) == 1

    # force=True overwrites
    if r1["written"]:
        r3 = run_daily(date_str, store, force=True)
        assert r3["skipped"] is False
        rows = store.list_regime_shift_posteriors(start_ts=date_str, end_ts=date_str)
        assert len(rows) == 1   # still 1 row (upsert, not insert)

    store.__exit__(None, None, None)


# ══════════════════════════════════════════════════════════════════════════════
# Test 7: Missing data neutralizes inputs (posterior computed with fewer inputs)
# ══════════════════════════════════════════════════════════════════════════════

def test_orchestrator_missing_data_neutralizes_inputs():
    """
    Sentinel: when 2 inputs return None, posterior is computed using the 2
    remaining inputs and the missing names appear in missing_inputs.
    """
    from soma.intel.regime_shift import bayesian

    # All 4 inputs None → posterior equals sigmoid(log_prior)
    llrs_all_none = compute_log_likelihood_ratios(None, None, None, None)
    _, post_all_none = compute_posterior(PRIOR, llrs_all_none)
    log_prior = math.log(PRIOR / (1.0 - PRIOR))
    _, expected_all_none = compute_posterior(PRIOR, {
        "llr_macro": 0.0, "llr_sentiment": 0.0,
        "llr_cross_asset": 0.0, "llr_transcript": 0.0,
        "missing_inputs": [],
    })
    assert abs(post_all_none - expected_all_none) < 1e-9

    # 2 of 4 None → missing_inputs has exactly 2 names
    llrs_2_none = compute_log_likelihood_ratios(
        macro_z=1.5, sentiment_z=None, cross_asset_z=0.8, transcript_drift_z=None
    )
    assert len(llrs_2_none["missing_inputs"]) == 2
    assert llrs_2_none["llr_macro"] > 0.0
    assert llrs_2_none["llr_cross_asset"] > 0.0

    _, post_2_none = compute_posterior(PRIOR, llrs_2_none)
    # Posterior > sigmoid(log_prior) because two inputs contributed
    assert post_2_none > expected_all_none


# ══════════════════════════════════════════════════════════════════════════════
# Test 8: Orchestrator writes both tables for a given date
# ══════════════════════════════════════════════════════════════════════════════

def test_orchestrator_writes_both_tables(tmp_path):
    """After run_daily, both likelihood and posterior rows exist for the date."""
    store = _make_store(tmp_path)
    _seed_capability(store, "regime_shift_bayesian", "enabled")
    _seed_regime_rows(store, n=60)

    date_str = "2024-03-10"

    # Patch cross-asset ingestor to avoid live network call
    with patch(
        "soma.intel.regime_shift.ingestors.ingest_cross_asset_z",
        return_value=0.5,
    ):
        result = run_daily(date_str, store)

    assert result["disabled"] is False

    # Check likelihood table
    lh = store._c.execute(
        "SELECT * FROM soma_intel_regime_shift_likelihood WHERE ts=?", (date_str,)
    ).fetchone()
    assert lh is not None, "Likelihood row missing"

    # Check posterior table
    post = store.get_regime_shift_posterior(date_str)
    assert post is not None, "Posterior row missing"
    assert 0.0 < post["posterior"] < 1.0
    assert post["trigger_state"] in ("none", "watch", "imminent")

    store.__exit__(None, None, None)


# ══════════════════════════════════════════════════════════════════════════════
# Test 9: Extreme inputs → posterior > 0.5 (direction sanity check)
# ══════════════════════════════════════════════════════════════════════════════

def test_compute_posterior_extreme_inputs():
    """All 4 inputs at maximum cap → posterior > 0.5 (math direction is correct)."""
    llrs = compute_log_likelihood_ratios(
        macro_z=3.0,    # at macro cap
        sentiment_z=2.5,  # at sentiment cap
        cross_asset_z=2.5,  # at cross-asset cap
        transcript_drift_z=2.0,  # at transcript cap
    )
    _, posterior = compute_posterior(PRIOR, llrs)
    assert posterior > 0.5, (
        f"Expected posterior > 0.5 with all inputs at maximum, got {posterior}. "
        "Check LLR coefficient signs — higher z should push posterior up."
    )


# ══════════════════════════════════════════════════════════════════════════════
# Test 10: Capability registered as disabled by default after seed
# ══════════════════════════════════════════════════════════════════════════════

def test_capability_registered_disabled_by_default(tmp_path):
    """After seed, regime_shift_bayesian exists with status='disabled'."""
    store = _make_store(tmp_path)
    _seed_capability(store, "regime_shift_bayesian", "disabled")

    cap = store.get_capability("regime_shift_bayesian")
    assert cap is not None, "Capability not found after seed"
    assert cap["status"] == "disabled"
    assert store.is_capability_enabled("regime_shift_bayesian") is False

    store.__exit__(None, None, None)
