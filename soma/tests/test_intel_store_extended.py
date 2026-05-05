"""
SOMA-INTEL R2 — Unit tests for IntelStore extended methods.

Covers every method added during the §H.1 abstraction pass so that no
module in soma/intel/ needs to call store._c.execute() directly.

All tests use an isolated temp DB. No production DB is touched.
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

# ── Path setup ────────────────────────────────────────────────────────────────
_DABEIBA_ROOT = Path(__file__).resolve().parent.parent.parent.parent
for _p in [str(_DABEIBA_ROOT), str(_DABEIBA_ROOT / "shared")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from soma.intel.store import IntelStore


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def store(tmp_path):
    """
    Fresh IntelStore with the minimal soma_intel_* tables + migration 022 tables.
    Uses initialize_tables() for the core graph tables, then applies the
    migration 022 DDL for audit_log + source_calibration.
    Also creates soma_intel_signal + soma_intel_belief + soma_intel_platform +
    soma_intel_scurve_history + soma_intel_universe + soma_intel_baseline +
    soma_intel_regime tables needed by the new methods.
    """
    db_path = str(tmp_path / "soma_intel_test.db")
    with IntelStore(db_path=db_path) as s:
        s.initialize_tables()
        # Bootstrap tables not in initialize_tables() (from migration 021/022)
        s._c.executescript("""
            CREATE TABLE IF NOT EXISTS soma_intel_signal (
                signal_id            INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker               TEXT NOT NULL,
                date                 TEXT NOT NULL,
                priority             TEXT NOT NULL,
                anomaly_score        REAL NOT NULL,
                features             TEXT NOT NULL,
                corroboration_count  INTEGER NOT NULL,
                half_life_days       INTEGER NOT NULL,
                reconfirmation_count INTEGER DEFAULT 0,
                status               TEXT DEFAULT 'active',
                horizon              TEXT DEFAULT 'thematic',
                notes                TEXT
            );
            CREATE TABLE IF NOT EXISTS soma_intel_belief (
                belief_id        INTEGER PRIMARY KEY AUTOINCREMENT,
                subject_node_id  TEXT NOT NULL,
                predicate        TEXT NOT NULL,
                value            TEXT NOT NULL,
                confidence       REAL NOT NULL,
                ts               TEXT NOT NULL,
                source_id        TEXT NOT NULL,
                superseded_by    INTEGER
            );
            CREATE TABLE IF NOT EXISTS soma_intel_platform (
                platform_id      TEXT PRIMARY KEY,
                name             TEXT NOT NULL,
                adoption_metric  TEXT NOT NULL,
                curve_K          REAL,
                curve_r          REAL,
                curve_t0         TEXT,
                wrights_law_rate REAL,
                position         TEXT,
                last_fit_ts      TEXT
            );
            CREATE TABLE IF NOT EXISTS soma_intel_scurve_history (
                history_id       INTEGER PRIMARY KEY AUTOINCREMENT,
                platform_id      TEXT NOT NULL,
                date             TEXT NOT NULL,
                metric_value     REAL NOT NULL,
                cumulative_units REAL,
                unit_cost        REAL,
                source           TEXT NOT NULL,
                UNIQUE(platform_id, date)
            );
            CREATE TABLE IF NOT EXISTS soma_intel_universe (
                ticker           TEXT PRIMARY KEY,
                source           TEXT NOT NULL,
                platform_tags    TEXT,
                added_ts         TEXT NOT NULL,
                active           INTEGER DEFAULT 1,
                tier             TEXT DEFAULT 'core',
                auto_added       INTEGER DEFAULT 0,
                promotion_score  REAL,
                promotion_source TEXT
            );
            CREATE TABLE IF NOT EXISTS soma_intel_baseline (
                ticker        TEXT NOT NULL,
                regime_label  TEXT NOT NULL,
                feature       TEXT NOT NULL,
                mean          REAL NOT NULL,
                stdev         REAL NOT NULL,
                n_days        INTEGER NOT NULL,
                is_provisional INTEGER DEFAULT 0,
                last_updated  TEXT NOT NULL,
                PRIMARY KEY (ticker, regime_label, feature)
            );
            CREATE TABLE IF NOT EXISTS soma_intel_regime (
                date            TEXT PRIMARY KEY,
                trend_state     TEXT NOT NULL,
                vol_state       TEXT NOT NULL,
                macro_state     TEXT NOT NULL,
                composite_label TEXT NOT NULL,
                confidence      REAL NOT NULL,
                features        TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS soma_intel_audit_log (
                audit_id        INTEGER PRIMARY KEY AUTOINCREMENT,
                edge_id         INTEGER NOT NULL,
                auditor         TEXT NOT NULL,
                decision        TEXT NOT NULL,
                rationale       TEXT,
                ts              TEXT NOT NULL,
                prior_audit_id  INTEGER
            );
            CREATE TABLE IF NOT EXISTS soma_intel_source_calibration (
                source_id      TEXT PRIMARY KEY,
                multiplier     REAL NOT NULL DEFAULT 1.0,
                brier_score    REAL,
                n_observations INTEGER NOT NULL DEFAULT 0,
                last_updated   TEXT NOT NULL
            );
            CREATE TRIGGER IF NOT EXISTS soma_intel_audit_log_no_update
                BEFORE UPDATE ON soma_intel_audit_log
                BEGIN SELECT RAISE(ABORT, 'soma_intel_audit_log is append-only'); END;
            CREATE TRIGGER IF NOT EXISTS soma_intel_audit_log_no_delete
                BEFORE DELETE ON soma_intel_audit_log
                BEGIN SELECT RAISE(ABORT, 'soma_intel_audit_log is append-only'); END;
        """)
        s._c.commit()
        yield s


def _seed_nodes(store):
    store.upsert_node("co_TSLA", "company", "Tesla Inc.")
    store.upsert_node("pl_ai",   "platform", "AI Compute")


def _seed_edge(store, src="co_TSLA", dst="pl_ai",
               edge_type="belongs_to_platform", confidence=0.85) -> int:
    return store.upsert_edge(src, dst, edge_type, confidence=confidence,
                             source_id="test/fixture", evidence="test")


# ════════════════════════════════════════════════════════════════════════════
# Signal sweep helpers
# ════════════════════════════════════════════════════════════════════════════

class TestSignalSweepHelpers:

    def _insert_signal(self, store, ticker="TSLA", status="active", date_str=None,
                       notes="propagator_v1 test", horizon="thematic"):
        ds = date_str or date.today().isoformat()
        store._c.execute(
            """INSERT INTO soma_intel_signal
               (ticker, date, priority, anomaly_score, features,
                corroboration_count, half_life_days, status, horizon, notes)
               VALUES (?, ?, 'LOW', 0.5, '{}', 1, 10, ?, ?, ?)""",
            (ticker, ds, status, horizon, notes),
        )
        store._c.commit()
        return store._c.execute(
            "SELECT signal_id FROM soma_intel_signal WHERE ticker=? AND date=? AND notes=?",
            (ticker, ds, notes)
        ).fetchone()[0]

    def test_list_signals_active_excludes_expired(self, store):
        self._insert_signal(store, ticker="NVDA", status="active")
        self._insert_signal(store, ticker="AAPL", status="expired")
        rows = store.list_signals_active()
        tickers = [r["ticker"] for r in rows]
        assert "NVDA" in tickers
        assert "AAPL" not in tickers

    def test_list_signals_active_ticker_filter(self, store):
        self._insert_signal(store, ticker="NVDA", status="active")
        self._insert_signal(store, ticker="MSFT", status="active")
        rows = store.list_signals_active(tickers=["NVDA"])
        assert all(r["ticker"] == "NVDA" for r in rows)

    def test_list_active_signals_not_today(self, store):
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        today = date.today().isoformat()
        sig_id = self._insert_signal(store, ticker="TSLA", status="active",
                                     date_str=yesterday, notes="propagator_v1 X")
        self._insert_signal(store, ticker="TSLA", status="active",
                            date_str=today, notes="propagator_v1 Y")
        rows = store.list_active_signals_not_today(
            today=today, notes_prefix="propagator_v1"
        )
        ids = [r["signal_id"] for r in rows]
        assert sig_id in ids  # yesterday's signal included
        # today's signal excluded
        assert all(r["date"] != today for r in rows)

    def test_expire_signal(self, store):
        sig_id = self._insert_signal(store, ticker="AMD", status="active")
        store.expire_signal(sig_id)
        store.commit()
        row = store._c.execute(
            "SELECT status FROM soma_intel_signal WHERE signal_id=?", (sig_id,)
        ).fetchone()
        assert row[0] == "expired"

    def test_count_signals_by_status(self, store):
        self._insert_signal(store, ticker="T1", status="active")
        self._insert_signal(store, ticker="T2", status="active")
        self._insert_signal(store, ticker="T3", status="expired")
        assert store.count_signals_by_status("active")   == 2
        assert store.count_signals_by_status("expired")  == 1
        assert store.count_signals_by_status("reconfirmed") == 0


# ════════════════════════════════════════════════════════════════════════════
# Belief sweep helpers
# ════════════════════════════════════════════════════════════════════════════

class TestBeliefSweepHelpers:

    def _insert_belief(self, store, node_id="co_TSLA", predicate="test",
                       superseded_by=None, ts=None) -> int:
        ts = ts or datetime.now(timezone.utc).isoformat()
        cur = store._c.execute(
            """INSERT INTO soma_intel_belief
               (subject_node_id, predicate, value, confidence, ts, source_id, superseded_by)
               VALUES (?, ?, 'v', 0.8, ?, 'test', ?)""",
            (node_id, predicate, ts, superseded_by),
        )
        store._c.commit()
        return cur.lastrowid

    def test_list_superseded_beliefs_before(self, store):
        old_ts  = "2020-01-01T00:00:00"
        new_ts  = datetime.now(timezone.utc).isoformat()
        b1 = self._insert_belief(store, predicate="p1", ts=old_ts)
        b2 = self._insert_belief(store, predicate="p2", ts=new_ts)
        # Mark b1 as superseded
        store._c.execute("UPDATE soma_intel_belief SET superseded_by=999 WHERE belief_id=?", (b1,))
        store._c.execute("UPDATE soma_intel_belief SET superseded_by=999 WHERE belief_id=?", (b2,))
        store._c.commit()
        cutoff = "2021-01-01T00:00:00"
        rows = store.list_superseded_beliefs_before(cutoff)
        ids = [r["belief_id"] for r in rows]
        assert b1 in ids      # old + superseded
        assert b2 not in ids  # new — ts > cutoff

    def test_delete_beliefs_by_ids_batches(self, store):
        ids = [self._insert_belief(store, predicate=f"p{i}") for i in range(600)]
        deleted = store.delete_beliefs_by_ids(ids)
        store.commit()
        assert deleted == 600
        remaining = store._c.execute(
            "SELECT COUNT(*) FROM soma_intel_belief"
        ).fetchone()[0]
        assert remaining == 0

    def test_count_beliefs_active_and_superseded(self, store):
        b1 = self._insert_belief(store, predicate="active1")
        b2 = self._insert_belief(store, predicate="active2")
        b3 = self._insert_belief(store, predicate="sup")
        store._c.execute(
            "UPDATE soma_intel_belief SET superseded_by=999 WHERE belief_id=?", (b3,)
        )
        store._c.commit()
        assert store.count_beliefs_active()     == 2
        assert store.count_beliefs_superseded() == 1


# ════════════════════════════════════════════════════════════════════════════
# Platform management
# ════════════════════════════════════════════════════════════════════════════

class TestPlatformManagement:

    def _seed_platform(self, store, pid="pl_ai", name="AI Compute"):
        store.upsert_platform(pid, name, "GPU shipments",
                              curve_K=10000.0, curve_r=0.3, curve_t0="2023-01-01",
                              wrights_law_rate=-0.3, position="acceleration")
        store.commit()

    def test_upsert_and_get_platform(self, store):
        self._seed_platform(store)
        p = store.get_platform("pl_ai")
        assert p is not None
        assert p["name"] == "AI Compute"
        assert p["position"] == "acceleration"

    def test_list_platforms_all(self, store):
        self._seed_platform(store, "pl_ai",      "AI Compute")
        self._seed_platform(store, "pl_robotics","Robotics")
        platforms = store.list_platforms()
        ids = [p["platform_id"] for p in platforms]
        assert "pl_ai" in ids
        assert "pl_robotics" in ids

    def test_list_platforms_filtered(self, store):
        self._seed_platform(store, "pl_ai",      "AI Compute")
        self._seed_platform(store, "pl_robotics","Robotics")
        platforms = store.list_platforms(filter_ids=["pl_ai"])
        assert len(platforms) == 1
        assert platforms[0]["platform_id"] == "pl_ai"

    def test_update_platform_curve(self, store):
        self._seed_platform(store)
        store.update_platform_curve("pl_ai", K=20000.0, r=0.5, t0="2024-01-01",
                                    position="inflection", last_fit_ts="2026-05-04T00:00:00")
        store.commit()
        p = store.get_platform("pl_ai")
        assert p["curve_K"] == 20000.0
        assert p["position"] == "inflection"

    def test_clear_platforms(self, store):
        self._seed_platform(store)
        store.clear_platforms()
        store.commit()
        assert store.list_platforms() == []


# ════════════════════════════════════════════════════════════════════════════
# S-curve history
# ════════════════════════════════════════════════════════════════════════════

class TestScurveHistory:

    def test_insert_and_list(self, store):
        store.insert_scurve_history_row("pl_ai", "2024-01-01", 500.0, "test_source")
        store.insert_scurve_history_row("pl_ai", "2024-02-01", 600.0, "test_source")
        store.commit()
        rows = store.list_scurve_history("pl_ai")
        assert len(rows) == 2
        assert rows[0]["date"] == "2024-01-01"  # ordered ASC
        assert rows[1]["date"] == "2024-02-01"

    def test_insert_idempotent(self, store):
        store.insert_scurve_history_row("pl_ai", "2024-01-01", 500.0, "src")
        store.insert_scurve_history_row("pl_ai", "2024-01-01", 999.0, "src")  # same date
        store.commit()
        rows = store.list_scurve_history("pl_ai")
        assert len(rows) == 1  # OR IGNORE — no duplicate

    def test_count_scurve_history(self, store):
        for i in range(5):
            store.insert_scurve_history_row("pl_ai", f"2024-0{i+1}-01", float(i), "src")
        store.commit()
        assert store.count_scurve_history("pl_ai") == 5
        assert store.count_scurve_history("pl_robotics") == 0

    def test_scurve_history_date_range(self, store):
        store.insert_scurve_history_row("pl_ai", "2022-01-01", 100.0, "src")
        store.insert_scurve_history_row("pl_ai", "2025-12-01", 900.0, "src")
        store.commit()
        min_d, max_d = store.scurve_history_date_range("pl_ai")
        assert min_d == "2022-01-01"
        assert max_d == "2025-12-01"

    def test_scurve_history_date_range_empty(self, store):
        min_d, max_d = store.scurve_history_date_range("pl_missing")
        assert min_d is None and max_d is None

    def test_clear_scurve_history(self, store):
        store.insert_scurve_history_row("pl_ai", "2024-01-01", 100.0, "src")
        store.commit()
        store.clear_scurve_history()
        store.commit()
        assert store.count_scurve_history("pl_ai") == 0


# ════════════════════════════════════════════════════════════════════════════
# Edge management helpers
# ════════════════════════════════════════════════════════════════════════════

class TestEdgeManagement:

    def test_count_edges_by_source_type(self, store):
        _seed_nodes(store)
        store.upsert_edge("co_TSLA", "pl_ai", "belongs_to_platform",
                          confidence=0.9, source_id="wiki/a", evidence="e",
                          source_type="wiki")
        store.upsert_edge("co_TSLA", "pl_ai", "belongs_to_platform",
                          confidence=0.9, source_id="oracle/b", evidence="e",
                          source_type="oracle_titan")
        assert store.count_edges_by_source_type("wiki")         == 1
        assert store.count_edges_by_source_type("oracle_titan") == 1
        assert store.count_edges_by_source_type("missing")      == 0

    def test_count_edges_by_source_types(self, store):
        _seed_nodes(store)
        store.upsert_edge("co_TSLA", "pl_ai", "belongs_to_platform",
                          confidence=0.9, source_id="wiki/a", evidence="e",
                          source_type="wiki")
        store.upsert_edge("co_TSLA", "pl_ai", "belongs_to_platform",
                          confidence=0.9, source_id="oracle/b", evidence="e",
                          source_type="oracle_titan")
        total = store.count_edges_by_source_types(["wiki", "oracle_titan"])
        assert total == 2
        assert store.count_edges_by_source_types([]) == 0

    def test_delete_edges_by_source_type(self, store):
        _seed_nodes(store)
        store.upsert_edge("co_TSLA", "pl_ai", "belongs_to_platform",
                          confidence=0.9, source_id="wiki/a", evidence="e",
                          source_type="wiki")
        store.upsert_edge("co_TSLA", "pl_ai", "belongs_to_platform",
                          confidence=0.9, source_id="oracle/b", evidence="e",
                          source_type="oracle_titan")
        deleted = store.delete_edges_by_source_type("wiki")
        store.commit()
        assert deleted == 1
        assert store.count_edges_by_source_type("wiki")         == 0
        assert store.count_edges_by_source_type("oracle_titan") == 1


# ════════════════════════════════════════════════════════════════════════════
# Universe bootstrap
# ════════════════════════════════════════════════════════════════════════════

class TestUniverseBootstrap:

    def test_universe_is_loaded_empty(self, store):
        assert store.universe_is_loaded() is False

    def test_universe_is_loaded_after_insert(self, store):
        store.load_universe_entry("TSLA", "security_master", ["pl_ai"], "2026-01-01")
        store.commit()
        assert store.universe_is_loaded() is True

    def test_count_active_universe(self, store):
        store.load_universe_entry("TSLA", "security_master", [], "2026-01-01")
        store.load_universe_entry("NVDA", "security_master", [], "2026-01-01")
        store.commit()
        assert store.count_active_universe() == 2

    def test_load_universe_entry_idempotent(self, store):
        store.load_universe_entry("TSLA", "security_master", ["pl_ai"], "2026-01-01")
        store.load_universe_entry("TSLA", "security_master", ["pl_ai", "pl_robotics"], "2026-01-01")
        store.commit()
        assert store.count_active_universe() == 1  # upsert, not duplicate


# ════════════════════════════════════════════════════════════════════════════
# Node listing (edge extractor)
# ════════════════════════════════════════════════════════════════════════════

class TestNodeListing:

    def test_list_nodes_prioritized_order(self, store):
        store.upsert_node("cn_concept",  "concept",  "A Concept")
        store.upsert_node("co_TSLA",     "company",  "Tesla")
        store.upsert_node("pl_ai",       "platform", "AI Compute")
        rows = store.list_nodes_prioritized(limit=10)
        types = [r["node_type"] for r in rows]
        # company (0) must come before platform (1) which before concept (6)
        assert types.index("company") < types.index("platform")
        assert types.index("platform") < types.index("concept")

    def test_list_nodes_prioritized_limit(self, store):
        for i in range(10):
            store.upsert_node(f"co_T{i}", "company", f"Company {i}")
        rows = store.list_nodes_prioritized(limit=5)
        assert len(rows) == 5

    def test_list_nodes_prioritized_keys(self, store):
        store.upsert_node("co_TSLA", "company", "Tesla")
        rows = store.list_nodes_prioritized()
        assert "node_id"   in rows[0]
        assert "node_type" in rows[0]
        assert "name"      in rows[0]


# ════════════════════════════════════════════════════════════════════════════
# Audit log (migration 022)
# ════════════════════════════════════════════════════════════════════════════

class TestAuditLog:

    def _seed_edge(self, store):
        _seed_nodes(store)
        return _seed_edge(store)

    def test_record_audit_writes_log_and_updates_edge(self, store):
        edge_id = self._seed_edge(store)
        audit_id = store.record_audit(edge_id, "user", "approved", "looks good")
        assert audit_id > 0
        # Edge status updated
        edge_row = store._c.execute(
            "SELECT audit_status FROM soma_intel_edge WHERE edge_id=?", (edge_id,)
        ).fetchone()
        assert edge_row[0] == "approved"
        # Log row written
        log_rows = store.list_audit_log(edge_id=edge_id)
        assert len(log_rows) == 1
        assert log_rows[0]["decision"] == "approved"
        assert log_rows[0]["auditor"]  == "user"

    def test_audit_log_append_only_no_update(self, store):
        edge_id  = self._seed_edge(store)
        audit_id = store.record_audit(edge_id, "user", "approved", "ok")
        with pytest.raises(Exception, match="append-only"):
            store._c.execute(
                "UPDATE soma_intel_audit_log SET rationale='bad' WHERE audit_id=?",
                (audit_id,)
            )

    def test_audit_log_append_only_no_delete(self, store):
        edge_id  = self._seed_edge(store)
        audit_id = store.record_audit(edge_id, "user", "approved", "ok")
        with pytest.raises(Exception, match="append-only"):
            store._c.execute(
                "DELETE FROM soma_intel_audit_log WHERE audit_id=?",
                (audit_id,)
            )

    def test_record_audit_invalid_decision(self, store):
        edge_id = self._seed_edge(store)
        with pytest.raises(ValueError, match="decision"):
            store.record_audit(edge_id, "user", "bad_value", "rationale")

    def test_record_audit_chain_prior_audit_id(self, store):
        edge_id  = self._seed_edge(store)
        first    = store.record_audit(edge_id, "user", "approved", "first pass")
        second   = store.record_audit(edge_id, "claude_adversarial", "re_audited",
                                      "re-check", prior_audit_id=first)
        log_rows = store.list_audit_log(edge_id=edge_id)
        assert len(log_rows) == 2
        chained  = next(r for r in log_rows if r["audit_id"] == second)
        assert chained["prior_audit_id"] == first


# ════════════════════════════════════════════════════════════════════════════
# Source calibration (migration 022)
# ════════════════════════════════════════════════════════════════════════════

class TestSourceCalibration:

    def test_upsert_and_get(self, store):
        store.upsert_source_calibration(
            "oracle_titan", 1.0, 0.12, 50, "2026-05-04"
        )
        row = store.get_source_calibration("oracle_titan")
        assert row is not None
        assert row["multiplier"]     == 1.0
        assert row["brier_score"]    == 0.12
        assert row["n_observations"] == 50

    def test_upsert_updates_existing(self, store):
        store.upsert_source_calibration("wiki", 0.9, 0.15, 30, "2026-05-01")
        store.upsert_source_calibration("wiki", 0.75, 0.20, 60, "2026-05-04")
        row = store.get_source_calibration("wiki")
        assert row["multiplier"]     == 0.75
        assert row["n_observations"] == 60

    def test_list_source_calibrations_ordered(self, store):
        store.upsert_source_calibration("good_source", 1.0,  0.05, 100, "2026-05-04")
        store.upsert_source_calibration("bad_source",  0.4,  0.30,  20, "2026-05-04")
        store.upsert_source_calibration("ok_source",   0.8,  0.15,  50, "2026-05-04")
        rows = store.list_source_calibrations()
        multipliers = [r["multiplier"] for r in rows]
        # Ordered multiplier ASC (worst first)
        assert multipliers == sorted(multipliers)


# ════════════════════════════════════════════════════════════════════════════
# Regime + Baseline
# ════════════════════════════════════════════════════════════════════════════

class TestRegime:

    def test_upsert_and_get_regime(self, store):
        store.upsert_regime_row(
            "2026-05-04", "bull", "low", "easing", "bull_low_easing",
            confidence=0.85,
            features={"sp500_200d_slope": 0.05, "vix": 12.3},
        )
        store.commit()
        row = store.get_regime_row("2026-05-04")
        assert row is not None
        assert row["composite_label"] == "bull_low_easing"
        assert row["features"]["vix"] == 12.3

    def test_upsert_regime_idempotent(self, store):
        for _ in range(3):
            store.upsert_regime_row(
                "2026-05-04", "bull", "low", "easing", "bull_low_easing",
                0.85, {"vix": 12.0}
            )
            store.commit()
        rows = store.list_regime_rows()
        assert len(rows) == 1  # idempotent

    def test_list_regime_rows_date_filter(self, store):
        for i in range(1, 6):
            store.upsert_regime_row(
                f"2026-05-0{i}", "bull", "low", "easing", "bull_low_easing",
                0.85, {}
            )
        store.commit()
        rows = store.list_regime_rows(start_date="2026-05-02", end_date="2026-05-04")
        dates = [r["date"] for r in rows]
        assert "2026-05-01" not in dates
        assert "2026-05-02" in dates
        assert "2026-05-04" in dates
        assert "2026-05-05" not in dates


class TestBaseline:

    def test_upsert_and_get(self, store):
        store.upsert_baseline("TSLA", "bull_low_easing", "f1",
                              mean=0.02, stdev=0.01, n_days=50,
                              is_provisional=0, last_updated="2026-05-04")
        store.commit()
        row = store.get_baseline("TSLA", "bull_low_easing", "f1")
        assert row is not None
        assert row["mean"]   == 0.02
        assert row["n_days"] == 50
        assert row["is_provisional"] == 0

    def test_upsert_baseline_updates(self, store):
        store.upsert_baseline("TSLA", "bull_low_easing", "f1",
                              0.02, 0.01, 50, 0, "2026-05-04")
        store.upsert_baseline("TSLA", "bull_low_easing", "f1",
                              0.03, 0.015, 60, 0, "2026-05-05")
        store.commit()
        row = store.get_baseline("TSLA", "bull_low_easing", "f1")
        assert row["mean"]   == 0.03
        assert row["n_days"] == 60

    def test_baseline_provisional_flag(self, store):
        store.upsert_baseline("TINY", "bear_high_tightening", "f2",
                              0.0, 0.01, 15, is_provisional=1, last_updated="2026-05-04")
        store.commit()
        row = store.get_baseline("TINY", "bear_high_tightening", "f2")
        assert row["is_provisional"] == 1

    def test_list_baselines_for_ticker(self, store):
        for f in ["f1", "f2", "f3"]:
            store.upsert_baseline("NVDA", "bull_low_easing", f,
                                  0.01, 0.005, 100, 0, "2026-05-04")
        store.upsert_baseline("NVDA", "bear_high_tightening", "f1",
                              -0.01, 0.01, 40, 0, "2026-05-04")
        store.commit()
        all_rows = store.list_baselines_for_ticker("NVDA")
        assert len(all_rows) == 4
        filtered = store.list_baselines_for_ticker("NVDA", regime_label="bull_low_easing")
        assert len(filtered) == 3
        assert all(r["regime_label"] == "bull_low_easing" for r in filtered)


# ════════════════════════════════════════════════════════════════════════════
# Node type counts
# ════════════════════════════════════════════════════════════════════════════

class TestNodeTypeCounts:

    def test_node_type_counts(self, store):
        store.upsert_node("co_TSLA", "company",  "Tesla")
        store.upsert_node("co_NVDA", "company",  "Nvidia")
        store.upsert_node("pl_ai",   "platform", "AI")
        rows = store.node_type_counts()
        by_type = {r["node_type"]: r["c"] for r in rows}
        assert by_type["company"]  == 2
        assert by_type["platform"] == 1
