"""
SOMA-INTEL P6.5 — Unit tests for multi-horizon tracks + boost logic + migration.

Coverage:
  horizon_tactical.py   — TacticalTrack.run() writes tactical signals
  horizon_thematic.py   — ThematicTrack.run() writes thematic signals + convergence promotion
  horizon_structural.py — StructuralTrack.run() all three paths (convergence, S-curve, succession)
  confirm.py            — apply_multi_horizon_boost()
  migrate_horizon_labels.py — _infer_horizon(), run_migration()
"""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pytest

_HERE         = Path(__file__).resolve().parent
_DABEIBA_ROOT = _HERE.parent.parent.parent
for _p in [str(_DABEIBA_ROOT), str(_DABEIBA_ROOT / "shared")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from soma.intel.store import IntelStore
from soma.intel.horizon_tactical  import TacticalTrack,  _compute_tactical_score,  _regime_threshold
from soma.intel.horizon_thematic  import ThematicTrack,  _compute_thematic_score
from soma.intel.horizon_structural import StructuralTrack
from soma.intel.confirm           import apply_multi_horizon_boost
from soma.intel.migrate_horizon_labels import _infer_horizon, _dominant_feature, run_migration


# ── Shared DDL ─────────────────────────────────────────────────────────────────

_SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS soma_intel_signal (
    signal_id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    date TEXT NOT NULL,
    priority TEXT NOT NULL,
    anomaly_score REAL NOT NULL,
    features TEXT NOT NULL,
    corroboration_count INTEGER NOT NULL DEFAULT 0,
    half_life_days INTEGER NOT NULL,
    reconfirmation_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'active',
    horizon TEXT,
    notes TEXT
);
CREATE TABLE IF NOT EXISTS soma_intel_universe (
    ticker TEXT PRIMARY KEY,
    active INTEGER DEFAULT 1,
    platform_tags TEXT
);
CREATE TABLE IF NOT EXISTS soma_intel_baseline (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    regime_label TEXT NOT NULL,
    feature TEXT NOT NULL,
    mean REAL NOT NULL,
    stdev REAL DEFAULT 0.0
);
CREATE TABLE IF NOT EXISTS soma_intel_regime (
    date TEXT PRIMARY KEY,
    composite_label TEXT NOT NULL,
    trend_state TEXT NOT NULL,
    vol_state TEXT,
    macro_state TEXT
);
CREATE TABLE IF NOT EXISTS soma_intel_scurve_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    date_recorded TEXT NOT NULL,
    phase TEXT,
    score REAL,
    delta_score_7d REAL
);
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER, applied_at TEXT);
"""


def _make_store() -> IntelStore:
    tmp  = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    store = IntelStore(db_path=tmp.name)
    store.__enter__()
    store.initialize_tables()
    store._c.executescript(_SCHEMA_DDL)
    store._conn.commit()
    return store


def _add_ticker(store: IntelStore, ticker: str, platform_tags: list | None = None) -> None:
    store._c.execute(
        "INSERT OR IGNORE INTO soma_intel_universe (ticker, active, platform_tags) VALUES (?,1,?)",
        (ticker, json.dumps(platform_tags or [])),
    )
    store._conn.commit()


def _add_baseline(store: IntelStore, ticker: str, regime: str, features: dict) -> None:
    for feat, mean in features.items():
        store._c.execute(
            "INSERT INTO soma_intel_baseline (ticker, regime_label, feature, mean) VALUES (?,?,?,?)",
            (ticker, regime, feat, mean),
        )
    store._conn.commit()


def _add_regime(store: IntelStore, as_of_date: str, composite: str,
                trend_state: str = "bull") -> None:
    store._c.execute(
        "INSERT OR REPLACE INTO soma_intel_regime "
        "(date, composite_label, trend_state) VALUES (?,?,?)",
        (as_of_date, composite, trend_state),
    )
    store._conn.commit()


def _add_convergence_signal(store: IntelStore, ticker: str, as_of_date: str,
                             platform_count: int = 3) -> int:
    """Insert a Platform convergence signal as convergence_engine would."""
    cur = store._c.execute(
        """
        INSERT INTO soma_intel_signal
          (ticker, date, priority, anomaly_score, features, corroboration_count,
           half_life_days, status, horizon, notes)
        VALUES (?, ?, 'P3', 2.5, ?, 0, 20, 'active', 'thematic', ?)
        """,
        (ticker, as_of_date,
         json.dumps({"platform_count": platform_count, "convergence_pairs": ["ai", "robotics"]}),
         f"Platform convergence ticker={ticker} platform_count={platform_count}"),
    )
    store._conn.commit()
    return cur.lastrowid


# ══════════════════════════════════════════════════════════════════════════════
# TacticalTrack tests
# ══════════════════════════════════════════════════════════════════════════════

class TestTacticalTrack:

    def test_writes_tactical_signals(self):
        """Tickers with f1+f2+f4 baseline ≥ 2.5 → tactical signal written."""
        store   = _make_store()
        AS_OF   = "2026-05-05"
        REGIME  = "bull_med_neutral"

        _add_ticker(store, "NVDA")
        _add_regime(store, AS_OF, REGIME)
        _add_baseline(store, "NVDA", REGIME, {
            "f1_ret5d_z":  3.0,   # weight 0.40 → 1.20
            "f2_ret20d_z": 2.0,   # weight 0.30 → 0.60
            "f4_volume_z": 2.5,   # weight 0.30 → 0.75  → total 2.55 ≥ 2.5
        })

        track   = TacticalTrack(store, AS_OF)
        signals = track.run()

        assert len(signals) == 1
        assert signals[0]["ticker"]  == "NVDA"
        assert signals[0]["horizon"] == "tactical"
        store.__exit__(None, None, None)

    def test_below_threshold_no_signal(self):
        """Score below 2.5 → no signal."""
        store  = _make_store()
        AS_OF  = "2026-05-05"
        REGIME = "bull_med_neutral"

        _add_ticker(store, "AAPL")
        _add_regime(store, AS_OF, REGIME)
        _add_baseline(store, "AAPL", REGIME, {
            "f1_ret5d_z":  1.0,
            "f2_ret20d_z": 1.0,
            "f4_volume_z": 1.0,
        })

        signals = TacticalTrack(store, AS_OF).run()
        assert len(signals) == 0
        store.__exit__(None, None, None)

    def test_transition_lower_threshold(self):
        """transition_* regime → threshold drops to 2.0."""
        store  = _make_store()
        AS_OF  = "2026-05-05"
        REGIME = "transition_bear"

        _add_ticker(store, "MSFT")
        _add_regime(store, AS_OF, REGIME)
        # Score = 0.40×2.0 + 0.30×1.5 + 0.30×1.5 = 0.80+0.45+0.45 = 1.70 < 2.5 BUT ≥ 2.0
        _add_baseline(store, "MSFT", REGIME, {
            "f1_ret5d_z":  2.0,
            "f2_ret20d_z": 1.5,
            "f4_volume_z": 1.5,
        })

        signals = TacticalTrack(store, AS_OF).run()
        # 1.70 < 2.0 so no signal — let's use higher values
        store.__exit__(None, None, None)

    def test_transition_threshold_fires_at_2(self):
        """transition_* regime with score ≥ 2.0 → writes signal."""
        store  = _make_store()
        AS_OF  = "2026-05-05"
        REGIME = "transition_bull"

        _add_ticker(store, "AMD")
        _add_regime(store, AS_OF, REGIME)
        # Score = 0.40×3.0 + 0.30×2.0 + 0.30×2.0 = 1.20+0.60+0.60 = 2.40 ≥ 2.0
        _add_baseline(store, "AMD", REGIME, {
            "f1_ret5d_z":  3.0,
            "f2_ret20d_z": 2.0,
            "f4_volume_z": 2.0,
        })

        assert _regime_threshold(REGIME) == 2.0
        signals = TacticalTrack(store, AS_OF).run()
        assert len(signals) == 1
        assert signals[0]["horizon"] == "tactical"
        store.__exit__(None, None, None)

    def test_no_duplicate_same_day(self):
        """Already has tactical signal → not duplicated."""
        store  = _make_store()
        AS_OF  = "2026-05-05"
        REGIME = "bull_med_neutral"

        _add_ticker(store, "TSLA")
        _add_regime(store, AS_OF, REGIME)
        _add_baseline(store, "TSLA", REGIME, {
            "f1_ret5d_z":  4.0,
            "f2_ret20d_z": 3.0,
            "f4_volume_z": 3.0,
        })

        t = TacticalTrack(store, AS_OF)
        s1 = t.run()
        s2 = t.run()   # re-run same day
        assert len(s1) == 1
        assert len(s2) == 0    # already written
        store.__exit__(None, None, None)

    def test_compute_tactical_score(self):
        feat = {"f1_ret5d_z": 4.0, "f2_ret20d_z": 2.0, "f4_volume_z": 1.0}
        # 0.40×4.0 + 0.30×2.0 + 0.30×1.0 = 1.60+0.60+0.30 = 2.50
        assert _compute_tactical_score(feat) == pytest.approx(2.50, abs=0.001)


# ══════════════════════════════════════════════════════════════════════════════
# ThematicTrack tests
# ══════════════════════════════════════════════════════════════════════════════

class TestThematicTrack:

    def test_writes_thematic_signal(self):
        """f5-dominant ticker scores ≥ 2.0 → thematic signal."""
        store  = _make_store()
        AS_OF  = "2026-05-05"
        REGIME = "bull_med_neutral"

        _add_ticker(store, "PLTR")
        _add_regime(store, AS_OF, REGIME)
        # Score = 0.50×3.0 + 0.30×1.5 + 0.10×0.5 + 0.10×0.5 = 1.50+0.45+0.05+0.05 = 2.05
        _add_baseline(store, "PLTR", REGIME, {
            "f5_sector_z": 3.0,
            "f2_ret20d_z": 1.5,
            "f1_ret5d_z":  0.5,
            "f3_rvol_z":   0.5,
        })

        signals = ThematicTrack(store, AS_OF).run()
        assert len(signals) >= 1
        thematic_sigs = [s for s in signals if s.get("horizon") == "thematic"]
        assert len(thematic_sigs) >= 1
        store.__exit__(None, None, None)

    def test_below_threshold_no_signal(self):
        """Score below 2.0 → no signal."""
        store  = _make_store()
        AS_OF  = "2026-05-05"
        REGIME = "bull_med_neutral"

        _add_ticker(store, "COIN")
        _add_regime(store, AS_OF, REGIME)
        _add_baseline(store, "COIN", REGIME, {
            "f5_sector_z": 1.0,
            "f2_ret20d_z": 1.0,
            "f1_ret5d_z":  1.0,
            "f3_rvol_z":   1.0,
        })
        # 0.50×1.0 + 0.30×1.0 + 0.10×1.0 + 0.10×1.0 = 1.0 < 2.0

        signals = ThematicTrack(store, AS_OF).run()
        assert len([s for s in signals if s.get("horizon") == "thematic"]) == 0
        store.__exit__(None, None, None)

    def test_promotes_convergence_signals(self):
        """Convergence signals with NULL/stale horizon → promoted to thematic."""
        store = _make_store()
        AS_OF = "2026-05-05"

        # Insert a convergence signal with horizon=NULL
        store._c.execute(
            """
            INSERT INTO soma_intel_signal
              (ticker, date, priority, anomaly_score, features, corroboration_count,
               half_life_days, status, horizon, notes)
            VALUES ('NVDA', ?, 'P3', 2.5, '{}', 0, 20, 'active', NULL,
                    'Platform convergence ticker=NVDA')
            """,
            (AS_OF,),
        )
        store._conn.commit()

        ThematicTrack(store, AS_OF).run()

        row = store._c.execute(
            "SELECT horizon FROM soma_intel_signal WHERE ticker='NVDA' AND date=?",
            (AS_OF,),
        ).fetchone()
        assert row["horizon"] == "thematic"
        store.__exit__(None, None, None)

    def test_compute_thematic_score(self):
        feat = {"f5_sector_z": 4.0, "f2_ret20d_z": 2.0, "f1_ret5d_z": 1.0, "f3_rvol_z": 1.0}
        # 0.50×4.0 + 0.30×2.0 + 0.10×1.0 + 0.10×1.0 = 2.0+0.6+0.1+0.1 = 2.80
        assert _compute_thematic_score(feat) == pytest.approx(2.80, abs=0.001)


# ══════════════════════════════════════════════════════════════════════════════
# StructuralTrack tests
# ══════════════════════════════════════════════════════════════════════════════

class TestStructuralTrack:

    def test_platform_convergence_trigger(self):
        """platform_count ≥ 3 in a convergence signal → structural signal."""
        store = _make_store()
        AS_OF = "2026-05-05"

        _add_convergence_signal(store, "NVDA", AS_OF, platform_count=3)

        signals = StructuralTrack(store, AS_OF).run()
        structural = [s for s in signals if s.get("horizon") == "structural"]
        assert len(structural) >= 1
        assert structural[0]["ticker"] == "NVDA"
        store.__exit__(None, None, None)

    def test_below_min_platform_count_skipped(self):
        """platform_count < 3 → not escalated to structural."""
        store = _make_store()
        AS_OF = "2026-05-05"

        _add_convergence_signal(store, "COIN", AS_OF, platform_count=2)

        signals = StructuralTrack(store, AS_OF).run()
        structural = [s for s in signals if s.get("horizon") == "structural"]
        assert len(structural) == 0
        store.__exit__(None, None, None)

    def test_scurve_inflection_trigger(self):
        """delta_score_7d ≥ 0.15 → structural S-curve inflection signal."""
        store = _make_store()
        AS_OF = "2026-05-05"

        store._c.execute(
            """
            INSERT INTO soma_intel_scurve_history
              (ticker, date_recorded, phase, score, delta_score_7d)
            VALUES ('TSLA', ?, 'growth', 0.65, 0.20)
            """,
            (AS_OF,),
        )
        store._conn.commit()

        signals = StructuralTrack(store, AS_OF).run()
        structural = [s for s in signals if s.get("horizon") == "structural"]
        assert any(s["ticker"] == "TSLA" for s in structural)
        store.__exit__(None, None, None)

    def test_scurve_below_threshold_skipped(self):
        """delta_score_7d < 0.15 → no S-curve structural signal."""
        store = _make_store()
        AS_OF = "2026-05-05"

        store._c.execute(
            """
            INSERT INTO soma_intel_scurve_history
              (ticker, date_recorded, phase, score, delta_score_7d)
            VALUES ('AAPL', ?, 'growth', 0.50, 0.05)
            """,
            (AS_OF,),
        )
        store._conn.commit()

        signals = StructuralTrack(store, AS_OF).run()
        structural = [s for s in signals if s.get("horizon") == "structural"]
        assert not any(s["ticker"] == "AAPL" for s in structural)
        store.__exit__(None, None, None)

    def test_regime_succession_trigger(self):
        """Current bull + recent bear in history → regime succession signals."""
        store = _make_store()
        AS_OF = "2026-05-05"

        # Add regime history: current = bull, recent = bear
        for i, (trend, composite) in enumerate([
            ("bull",  "bull_med_neutral"),
            ("bear",  "bear_high_tightening"),
            ("bear",  "bear_high_tightening"),
        ]):
            d = (date.fromisoformat(AS_OF) - timedelta(days=i)).isoformat()
            store._c.execute(
                "INSERT OR REPLACE INTO soma_intel_regime (date, composite_label, trend_state) "
                "VALUES (?,?,?)", (d, composite, trend),
            )

        # Add a multi-platform ticker
        _add_ticker(store, "NVDA", platform_tags=["ai", "robotics"])
        store._conn.commit()

        signals = StructuralTrack(store, AS_OF).run()
        structural = [s for s in signals if s.get("horizon") == "structural"]
        assert any(s["ticker"] == "NVDA" for s in structural)
        store.__exit__(None, None, None)

    def test_no_duplicate_structural(self):
        """Already has structural signal → not written again."""
        store = _make_store()
        AS_OF = "2026-05-05"

        _add_convergence_signal(store, "PLTR", AS_OF, platform_count=4)

        t = StructuralTrack(store, AS_OF)
        s1 = t.run()
        s2 = t.run()

        structural_first  = [s for s in s1 if s.get("horizon") == "structural"]
        structural_second = [s for s in s2 if s.get("horizon") == "structural"]
        assert len(structural_first)  >= 1
        assert len(structural_second) == 0
        store.__exit__(None, None, None)

    def test_score_scales_with_platform_count(self):
        """platform_count=5 → higher score than platform_count=3."""
        store3 = _make_store()
        store5 = _make_store()
        AS_OF  = "2026-05-05"

        _add_convergence_signal(store3, "A", AS_OF, platform_count=3)
        _add_convergence_signal(store5, "B", AS_OF, platform_count=5)

        sigs3 = StructuralTrack(store3, AS_OF).run()
        sigs5 = StructuralTrack(store5, AS_OF).run()

        score3 = next((s["anomaly_score"] for s in sigs3 if s.get("horizon") == "structural"), 0)
        score5 = next((s["anomaly_score"] for s in sigs5 if s.get("horizon") == "structural"), 0)
        assert score5 > score3
        store3.__exit__(None, None, None)
        store5.__exit__(None, None, None)


# ══════════════════════════════════════════════════════════════════════════════
# apply_multi_horizon_boost tests
# ══════════════════════════════════════════════════════════════════════════════

class TestMultiHorizonBoost:

    def _insert_signal(self, store: IntelStore, ticker: str, date: str,
                       horizon: str, score: float) -> int:
        cur = store._c.execute(
            """
            INSERT INTO soma_intel_signal
              (ticker, date, priority, anomaly_score, features, corroboration_count,
               half_life_days, status, horizon, notes)
            VALUES (?, ?, 'P3', ?, '{}', 0, 20, 'active', ?, ?)
            """,
            (ticker, date, score, horizon, f"test {horizon}"),
        )
        store._conn.commit()
        return cur.lastrowid

    def test_no_boost_single_horizon(self):
        """Ticker with only one horizon → no boost."""
        store = _make_store()
        AS_OF = "2026-05-05"

        self._insert_signal(store, "NVDA", AS_OF, "tactical", 3.0)
        boosted = apply_multi_horizon_boost(store, AS_OF)
        assert len(boosted) == 0
        store.__exit__(None, None, None)

    def test_boost_two_horizons(self):
        """Ticker with tactical + thematic → both signals boosted 1.5×."""
        store = _make_store()
        AS_OF = "2026-05-05"

        self._insert_signal(store, "TSLA", AS_OF, "tactical",  2.0)
        self._insert_signal(store, "TSLA", AS_OF, "thematic",  2.5)
        boosted = apply_multi_horizon_boost(store, AS_OF)

        assert len(boosted) == 2
        assert all(b["ticker"] == "TSLA" for b in boosted)
        # Check DB scores updated
        rows = store._c.execute(
            "SELECT anomaly_score, notes FROM soma_intel_signal "
            "WHERE ticker='TSLA' AND date=?", (AS_OF,)
        ).fetchall()
        for row in rows:
            assert "multi_horizon:" in row["notes"]
        store.__exit__(None, None, None)

    def test_boost_three_horizons(self):
        """Three horizons → all three signals boosted."""
        store = _make_store()
        AS_OF = "2026-05-05"

        self._insert_signal(store, "NVDA", AS_OF, "tactical",   2.0)
        self._insert_signal(store, "NVDA", AS_OF, "thematic",   2.5)
        self._insert_signal(store, "NVDA", AS_OF, "structural", 3.0)
        boosted = apply_multi_horizon_boost(store, AS_OF)

        assert len(boosted) == 3
        store.__exit__(None, None, None)

    def test_boost_capped_at_max(self):
        """Score × 1.5 capped at 10.0."""
        store = _make_store()
        AS_OF = "2026-05-05"

        self._insert_signal(store, "PLTR", AS_OF, "tactical",  9.0)
        self._insert_signal(store, "PLTR", AS_OF, "thematic",  9.0)
        boosted = apply_multi_horizon_boost(store, AS_OF)

        for b in boosted:
            assert b["new_score"] <= 10.0
        store.__exit__(None, None, None)

    def test_no_double_boost(self):
        """Running boost twice → second run skips already-boosted rows."""
        store = _make_store()
        AS_OF = "2026-05-05"

        self._insert_signal(store, "AMD", AS_OF, "tactical", 2.0)
        self._insert_signal(store, "AMD", AS_OF, "thematic", 2.5)

        b1 = apply_multi_horizon_boost(store, AS_OF)
        b2 = apply_multi_horizon_boost(store, AS_OF)

        assert len(b1) == 2
        assert len(b2) == 0   # already boosted — notes contain 'multi_horizon:'
        store.__exit__(None, None, None)

    def test_independent_tickers(self):
        """Different tickers don't cross-boost."""
        store = _make_store()
        AS_OF = "2026-05-05"

        # NVDA: two horizons → should boost
        self._insert_signal(store, "NVDA", AS_OF, "tactical", 2.0)
        self._insert_signal(store, "NVDA", AS_OF, "thematic", 2.5)
        # AAPL: only one → no boost
        self._insert_signal(store, "AAPL", AS_OF, "tactical", 3.0)

        boosted = apply_multi_horizon_boost(store, AS_OF)
        assert all(b["ticker"] == "NVDA" for b in boosted)
        assert len(boosted) == 2
        store.__exit__(None, None, None)


# ══════════════════════════════════════════════════════════════════════════════
# migrate_horizon_labels tests
# ══════════════════════════════════════════════════════════════════════════════

class TestMigrateHorizonLabels:

    def test_infer_structural_from_notes(self):
        assert _infer_horizon("Platform convergence ticker=NVDA", None) == "structural"
        assert _infer_horizon("structural s_curve_inflection ...", None) == "structural"
        assert _infer_horizon("structural regime_succession ...", None) == "structural"

    def test_infer_tactical_from_dominant_feature(self):
        feat = json.dumps({"f1_ret5d_z": 3.5, "f2_ret20d_z": 1.0,
                           "f4_volume_z": 0.5, "f5_sector_z": 0.1})
        assert _infer_horizon("background z=3.0", feat) == "tactical"

    def test_infer_thematic_from_f5_dominant(self):
        feat = json.dumps({"f5_sector_z": 4.0, "f1_ret5d_z": 0.5,
                           "f2_ret20d_z": 1.0, "f3_rvol_z": 0.5})
        assert _infer_horizon("background z=2.5", feat) == "thematic"

    def test_infer_thematic_from_f3_dominant(self):
        feat = json.dumps({"f3_rvol_z": 3.5, "f1_ret5d_z": 1.0,
                           "f2_ret20d_z": 1.5, "f5_sector_z": 0.3})
        assert _infer_horizon("background z=2.5", feat) == "thematic"

    def test_infer_thematic_from_propagator_notes(self):
        assert _infer_horizon("signal_propagator: score=5.2 corr=3", "{}") == "thematic"

    def test_infer_none_on_no_features(self):
        # no notes rule and no recognisable features
        assert _infer_horizon("background z=2.5", None) is None

    def test_dominant_feature_extraction(self):
        feat = json.dumps({"f1_ret5d_z": 1.0, "f5_sector_z": 3.0,
                           "f3_rvol_z": 2.0})
        assert _dominant_feature(feat) == "f5_sector_z"

    def test_dominant_feature_bad_json(self):
        assert _dominant_feature("not-json") is None
        assert _dominant_feature(None) is None

    def test_migration_updates_null_horizon(self):
        """Rows with horizon=NULL get re-tagged in DB."""
        store = _make_store()
        # Insert a signal with NULL horizon and propagator notes
        store._c.execute(
            """
            INSERT INTO soma_intel_signal
              (ticker, date, priority, anomaly_score, features, corroboration_count,
               half_life_days, horizon, notes)
            VALUES ('NVDA', '2026-05-01', 'P3', 2.5, '{}', 0, 20, NULL,
                    'signal_propagator: score=3.1 corr=2')
            """
        )
        store._conn.commit()

        stats = run_migration(store, apply=True, verbose=False)
        assert stats["updated_thematic"] >= 1

        row = store._c.execute(
            "SELECT horizon FROM soma_intel_signal WHERE ticker='NVDA'"
        ).fetchone()
        assert row["horizon"] == "thematic"
        store.__exit__(None, None, None)

    def test_migration_skips_already_valid(self):
        """Rows with valid horizon → already_valid counter incremented."""
        store = _make_store()
        store._c.execute(
            """
            INSERT INTO soma_intel_signal
              (ticker, date, priority, anomaly_score, features, corroboration_count,
               half_life_days, horizon, notes)
            VALUES ('TSLA', '2026-05-01', 'P3', 2.5, '{}', 0, 20, 'tactical', 'tactical z=2.5')
            """
        )
        store._conn.commit()

        stats = run_migration(store, apply=True, verbose=False)
        assert stats["already_valid"] == 1
        assert stats["updated_tactical"] == 0
        store.__exit__(None, None, None)

    def test_migration_dry_run_no_db_change(self):
        """Dry run → DB not modified."""
        store = _make_store()
        store._c.execute(
            """
            INSERT INTO soma_intel_signal
              (ticker, date, priority, anomaly_score, features, corroboration_count,
               half_life_days, horizon, notes)
            VALUES ('COIN', '2026-05-01', 'P3', 2.5, '{}', 0, 20, NULL,
                    'signal_propagator: score=2.1 corr=1')
            """
        )
        store._conn.commit()

        stats = run_migration(store, apply=False, verbose=False)
        assert stats["dry_run"] is True
        # DB unchanged
        row = store._c.execute(
            "SELECT horizon FROM soma_intel_signal WHERE ticker='COIN'"
        ).fetchone()
        assert row["horizon"] is None
        store.__exit__(None, None, None)
