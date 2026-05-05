"""
Unit tests — RAPTOR Phase 3: COI Network & Referral Intelligence
Tests: get_coi_leaderboard, get_reciprocity_report, suggest_coi_touchpoints,
       get_referral_funnel, seed_coi_strategy_rule.
20 tests total.
"""
from __future__ import annotations

import sys
import os
import uuid
import json
import sqlite3
import pytest
from datetime import date, timedelta
from pathlib import Path

_DABEIBA_ROOT = Path(__file__).resolve().parent.parent.parent.parent
for _p in [str(_DABEIBA_ROOT), str(_DABEIBA_ROOT / "shared")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from soma.soma_bridge import SomaBridge
from soma.raptor_engine import (
    RaptorEngine,
    seed_coi_strategy_rule,
    COI_STALE_DAYS,
)

_MIG_DIR = _DABEIBA_ROOT / "shared" / "soma" / "migrations"


@pytest.fixture
def db(tmp_path):
    """Isolated test DB with RAPTOR schema."""
    db_file = str(tmp_path / "test_raptor_p3.db")
    os.environ["SOMA_DB_PATH"] = db_file

    conn = sqlite3.connect(db_file)
    for mig_name in [
        "001_initial_schema.sql",
        "003_kb_rules.sql",
        "012_raptor_core.sql",
        "017_consent_idempotency.sql",
        "018_pipeline_trigger_touchpoint.sql",
    ]:
        conn.executescript((_MIG_DIR / mig_name).read_text())
    conn.commit()
    conn.close()

    bridge = SomaBridge(db_path=db_file)
    bridge.__enter__()
    yield bridge
    bridge.__exit__(None, None, None)


def _new_id():
    return str(uuid.uuid4())


def _today():
    return date.today().isoformat()


def _days_ago(n: int) -> str:
    return (date.today() - timedelta(days=n)).isoformat()


def _make_active_prospect(db, coi_id=None, assets_band="1M-2M") -> str:
    """Create a prospect in 'active' stage, optionally linked to a COI."""
    pid = _new_id()
    db.write_prospect(pid, first_name="Client", estimated_assets_band=assets_band)
    # Move to active (bypass gates by direct write to pipeline_log + update)
    db.conn.execute(
        "UPDATE raptor_prospects SET pipeline_stage='active' WHERE prospect_id=?", (pid,)
    )
    db.conn.commit()
    if coi_id:
        db.write_referral(coi_id, pid, _today(), disclosure_delivered=True, outcome="converted")
    return pid


# ── get_coi_leaderboard ───────────────────────────────────────────────────────

def test_leaderboard_empty(db):
    """No COIs → empty list."""
    engine = RaptorEngine(db)
    assert engine.get_coi_leaderboard() == []


def test_leaderboard_single_coi_no_referrals(db):
    """A COI with no referrals has composite_score 0."""
    coi_id = _new_id()
    db.write_coi(coi_id, "Solo COI", profession="accountant")
    leaders = RaptorEngine(db).get_coi_leaderboard()
    assert len(leaders) == 1
    assert leaders[0]["composite_score"] == 0.0
    assert leaders[0]["total_referrals"] == 0


def test_leaderboard_composite_score_computed(db):
    """COI with 1 converted referral at 1M-2M band → composite > 0."""
    coi_id = _new_id()
    db.write_coi(coi_id, "Good COI", referral_agreement_signed=True)
    _make_active_prospect(db, coi_id=coi_id, assets_band="1M-2M")
    leaders = RaptorEngine(db).get_coi_leaderboard()
    assert leaders[0]["composite_score"] > 0
    assert leaders[0]["converted"] == 1
    assert leaders[0]["conversion_rate"] == 1.0


def test_leaderboard_ranking_by_composite(db):
    """COI with higher AUM prospects ranks above COI with lower AUM."""
    coi_high = _new_id()
    coi_low  = _new_id()
    db.write_coi(coi_high, "High AUM COI", referral_agreement_signed=True)
    db.write_coi(coi_low,  "Low AUM COI",  referral_agreement_signed=True)

    # coi_high → 5M+ prospect (converted)
    pid_h = _new_id()
    db.write_prospect(pid_h, first_name="Rich", estimated_assets_band="5M+")
    db.conn.execute(
        "UPDATE raptor_prospects SET pipeline_stage='active' WHERE prospect_id=?", (pid_h,)
    )
    db.conn.commit()
    db.write_referral(coi_high, pid_h, _today(), disclosure_delivered=True, outcome="converted")

    # coi_low → 500K-1M prospect (converted)
    pid_l = _new_id()
    db.write_prospect(pid_l, first_name="Small", estimated_assets_band="500K-1M")
    db.conn.execute(
        "UPDATE raptor_prospects SET pipeline_stage='active' WHERE prospect_id=?", (pid_l,)
    )
    db.conn.commit()
    db.write_referral(coi_low, pid_l, _today(), disclosure_delivered=True, outcome="converted")

    leaders = RaptorEngine(db).get_coi_leaderboard()
    names = [l["name"] for l in leaders]
    assert names.index("High AUM COI") < names.index("Low AUM COI")


def test_leaderboard_conversion_rate_matters(db):
    """Two COIs, same total referrals but different conversion rates → higher rate ranks first."""
    coi_a = _new_id()
    coi_b = _new_id()
    db.write_coi(coi_a, "COI Alpha", referral_agreement_signed=True)
    db.write_coi(coi_b, "COI Beta",  referral_agreement_signed=True)

    # coi_a: 1 converted / 1 total
    pid_a = _new_id()
    db.write_prospect(pid_a, first_name="A", estimated_assets_band="1M-2M")
    db.conn.execute("UPDATE raptor_prospects SET pipeline_stage='active' WHERE prospect_id=?", (pid_a,))
    db.conn.commit()
    db.write_referral(coi_a, pid_a, _today(), disclosure_delivered=True, outcome="converted")

    # coi_b: 1 lost / 1 total
    pid_b = _new_id()
    db.write_prospect(pid_b, first_name="B", estimated_assets_band="1M-2M")
    db.write_referral(coi_b, pid_b, _today(), outcome="lost")

    leaders = RaptorEngine(db).get_coi_leaderboard()
    names = [l["name"] for l in leaders]
    assert names.index("COI Alpha") < names.index("COI Beta")


# ── get_reciprocity_report ────────────────────────────────────────────────────

def test_reciprocity_balanced(db):
    coi_id = _new_id()
    db.write_coi(coi_id, "Balanced COI", reciprocity_given=3, reciprocity_received=3)
    report = RaptorEngine(db).get_reciprocity_report()
    assert report[0]["status"] == "BALANCED"
    assert report[0]["balance"] == 0


def test_reciprocity_under_investing(db):
    """received > given → UNDER_INVESTING (we should reciprocate more)."""
    coi_id = _new_id()
    db.write_coi(coi_id, "Imbalanced COI", reciprocity_given=1, reciprocity_received=4)
    report = RaptorEngine(db).get_reciprocity_report()
    assert report[0]["status"] == "UNDER_INVESTING"
    assert report[0]["balance"] == 3   # received - given


def test_reciprocity_over_investing(db):
    """given > received → OVER_INVESTING."""
    coi_id = _new_id()
    db.write_coi(coi_id, "Generous COI", reciprocity_given=5, reciprocity_received=1)
    report = RaptorEngine(db).get_reciprocity_report()
    assert report[0]["status"] == "OVER_INVESTING"
    assert report[0]["balance"] == -4


def test_reciprocity_ordered_by_abs_imbalance(db):
    """Largest absolute imbalance appears first."""
    coi_a = _new_id()
    coi_b = _new_id()
    db.write_coi(coi_a, "Big Gap",   reciprocity_given=0, reciprocity_received=8)
    db.write_coi(coi_b, "Small Gap", reciprocity_given=2, reciprocity_received=3)
    report = RaptorEngine(db).get_reciprocity_report()
    names = [r["name"] for r in report]
    assert names.index("Big Gap") < names.index("Small Gap")


# ── suggest_coi_touchpoints ───────────────────────────────────────────────────

def test_suggest_stale_coi_by_referral_date(db):
    """COI whose last referral is older than COI_STALE_DAYS → suggested."""
    coi_id = _new_id()
    pid    = _new_id()
    db.write_coi(coi_id, "Stale COI", referral_agreement_signed=True)
    db.write_prospect(pid, first_name="Old")
    db.write_referral(coi_id, pid, _days_ago(COI_STALE_DAYS + 10), outcome="pending")

    suggestions = RaptorEngine(db).suggest_coi_touchpoints()
    coi_ids = [s["coi_id"] for s in suggestions]
    assert coi_id in coi_ids


def test_suggest_recent_coi_excluded(db):
    """COI whose last referral was within COI_STALE_DAYS → NOT suggested."""
    coi_id = _new_id()
    pid    = _new_id()
    db.write_coi(coi_id, "Fresh COI", referral_agreement_signed=True)
    db.write_prospect(pid, first_name="New")
    db.write_referral(coi_id, pid, _days_ago(COI_STALE_DAYS - 5), outcome="pending")

    suggestions = RaptorEngine(db).suggest_coi_touchpoints()
    assert coi_id not in [s["coi_id"] for s in suggestions]


def test_suggest_stale_coi_no_referrals_uses_start_date(db):
    """COI with no referrals uses relationship_start_date as proxy."""
    coi_id = _new_id()
    db.write_coi(
        coi_id, "Old Relationship",
        relationship_start_date=_days_ago(COI_STALE_DAYS + 30),
    )
    suggestions = RaptorEngine(db).suggest_coi_touchpoints()
    assert coi_id in [s["coi_id"] for s in suggestions]


def test_suggest_empty_no_cois(db):
    suggestions = RaptorEngine(db).suggest_coi_touchpoints()
    assert suggestions == []


# ── get_referral_funnel ───────────────────────────────────────────────────────

def test_funnel_empty_no_referrals(db):
    result = RaptorEngine(db).get_referral_funnel()
    assert result["total_referrals"] == 0
    assert result["by_outcome"] == {}
    assert result["avg_days_to_convert"] is None
    assert "coi_breakdown" in result


def test_funnel_outcome_counts(db):
    """Converted, lost, pending referrals each counted correctly."""
    coi_id = _new_id()
    db.write_coi(coi_id, "Test COI", referral_agreement_signed=True)

    for outcome in ["converted", "lost", "pending"]:
        pid = _new_id()
        db.write_prospect(pid, first_name=outcome.capitalize())
        if outcome == "converted":
            db.conn.execute(
                "UPDATE raptor_prospects SET pipeline_stage='active' WHERE prospect_id=?", (pid,)
            )
            db.conn.commit()
        db.write_referral(coi_id, pid, _today(), outcome=outcome)

    result = RaptorEngine(db).get_referral_funnel()
    assert result["total_referrals"] == 3
    assert result["by_outcome"]["converted"] == 1
    assert result["by_outcome"]["lost"]      == 1
    assert result["by_outcome"]["pending"]   == 1


def test_funnel_filtered_by_coi(db):
    """Filtered funnel returns only that COI's referrals."""
    coi_a = _new_id()
    coi_b = _new_id()
    db.write_coi(coi_a, "COI A", referral_agreement_signed=True)
    db.write_coi(coi_b, "COI B", referral_agreement_signed=True)

    for coi in [coi_a, coi_b, coi_b]:   # coi_a: 1, coi_b: 2
        pid = _new_id()
        db.write_prospect(pid, first_name="P")
        db.write_referral(coi, pid, _today(), outcome="pending")

    result_a = RaptorEngine(db).get_referral_funnel(coi_id=coi_a)
    result_b = RaptorEngine(db).get_referral_funnel(coi_id=coi_b)
    assert result_a["total_referrals"] == 1
    assert result_b["total_referrals"] == 2
    # Filtered view should NOT have coi_breakdown
    assert "coi_breakdown" not in result_a


def test_funnel_avg_days_to_convert(db):
    """avg_days_to_convert calculated from referral_date → active transition."""
    coi_id = _new_id()
    db.write_coi(coi_id, "Timing COI", referral_agreement_signed=True)
    pid = _new_id()
    db.write_prospect(pid, first_name="Conv")
    ref_date = _days_ago(30)
    db.write_referral(coi_id, pid, ref_date, outcome="converted")

    # Manually log the 'active' transition
    db.conn.execute(
        "UPDATE raptor_prospects SET pipeline_stage='active' WHERE prospect_id=?", (pid,)
    )
    db.conn.execute(
        "INSERT INTO raptor_pipeline_log "
        "(prospect_id, from_stage, to_stage, transition_date, reason, transitioned_by, write_timestamp) "
        "VALUES (?, 'proposal_sent', 'active', ?, 'converted', 'test', datetime('now'))",
        (pid, _today()),
    )
    db.conn.commit()

    result = RaptorEngine(db).get_referral_funnel(coi_id=coi_id)
    assert result["avg_days_to_convert"] is not None
    assert result["avg_days_to_convert"] >= 30.0


def test_funnel_coi_breakdown_present(db):
    """All-COI funnel includes coi_breakdown list."""
    coi_id = _new_id()
    db.write_coi(coi_id, "Any COI")
    result = RaptorEngine(db).get_referral_funnel()
    assert "coi_breakdown" in result
    assert isinstance(result["coi_breakdown"], list)
    assert len(result["coi_breakdown"]) == 1


# ── Rule seeding ──────────────────────────────────────────────────────────────

def test_seed_coi_strategy_inserts(db):
    inserted = seed_coi_strategy_rule(db)
    assert inserted is True
    row = db.conn.execute(
        "SELECT rule_data FROM kb_rules WHERE rule_id = 'RAPTOR_COI_STRATEGY_V1'"
    ).fetchone()
    assert row is not None
    data = json.loads(row["rule_data"])
    assert "network_size" in data
    assert "profession_priority" in data
    assert "reciprocity" in data


def test_seed_coi_strategy_idempotent(db):
    seed_coi_strategy_rule(db)
    assert seed_coi_strategy_rule(db) is False
