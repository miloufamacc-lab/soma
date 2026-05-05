"""
Unit tests — RAPTOR Phase 1: Lead Scoring Engine
Tests: factor scores, weighted calculation, decay, buckets,
       score_all, action queue, pipeline analytics, kb_rule seeding.
22 tests total.
"""
from __future__ import annotations

import json
import sys
import os
import uuid
import pytest
from datetime import date, timedelta
from pathlib import Path

_DABEIBA_ROOT = Path(__file__).resolve().parent.parent.parent.parent
for _p in [str(_DABEIBA_ROOT), str(_DABEIBA_ROOT / "shared")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from soma.soma_bridge import SomaBridge
from soma.raptor_engine import (
    RaptorEngine, seed_scoring_rule,
    THRESHOLD_IMMEDIATE, THRESHOLD_NURTURE, OVERDUE_DAYS, DECAY_FLOOR,
)

_MIG_DIR  = _DABEIBA_ROOT / "shared" / "soma" / "migrations"
_MIG_001  = _MIG_DIR / "001_initial_schema.sql"
_MIG_003  = _MIG_DIR / "003_kb_rules.sql"
_MIG_012  = _MIG_DIR / "012_raptor_core.sql"
_MIG_017  = _MIG_DIR / "017_consent_idempotency.sql"
_MIG_018  = _MIG_DIR / "018_pipeline_trigger_touchpoint.sql"


@pytest.fixture
def db(tmp_path):
    """Isolated test DB with RAPTOR schema + kb_rules table."""
    db_file = str(tmp_path / "test_raptor_p1.db")
    os.environ["SOMA_DB_PATH"] = db_file

    import sqlite3
    conn = sqlite3.connect(db_file)
    for mig in [_MIG_001, _MIG_003, _MIG_012, _MIG_017, _MIG_018]:
        conn.executescript(mig.read_text())
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


# ── Factor scoring ───────────────────────────────────────────────────────────

def test_score_assets_known_bands():
    assert RaptorEngine._score_assets("5M+")     == 100.0
    assert RaptorEngine._score_assets("2M-5M")   == 80.0
    assert RaptorEngine._score_assets("1M-2M")   == 60.0
    assert RaptorEngine._score_assets("500K-1M") == 40.0
    assert RaptorEngine._score_assets(None)       == 20.0
    assert RaptorEngine._score_assets("unknown")  == 20.0


def test_score_source_known_types():
    assert RaptorEngine._score_source("referral") == 100.0
    assert RaptorEngine._score_source("coi")      == 90.0
    assert RaptorEngine._score_source("inbound")  == 80.0
    assert RaptorEngine._score_source("cold")     == 20.0
    assert RaptorEngine._score_source(None)       == 10.0


def test_score_recency_buckets():
    assert RaptorEngine._score_recency(_days_ago(3))   == 100.0
    assert RaptorEngine._score_recency(_days_ago(15))  == 75.0
    assert RaptorEngine._score_recency(_days_ago(60))  == 50.0
    assert RaptorEngine._score_recency(_days_ago(120)) == 25.0
    assert RaptorEngine._score_recency(_days_ago(200)) == 10.0
    assert RaptorEngine._score_recency(None)           == 10.0


def test_score_engagement_counts():
    assert RaptorEngine._score_engagement(0) == 0.0
    assert RaptorEngine._score_engagement(1) == 25.0
    assert RaptorEngine._score_engagement(2) == 50.0
    assert RaptorEngine._score_engagement(3) == 75.0
    assert RaptorEngine._score_engagement(5) == 100.0
    assert RaptorEngine._score_engagement(9) == 100.0


def test_score_geo_lang():
    assert RaptorEngine._score_geo_lang("QC", "FR") == 100.0
    assert RaptorEngine._score_geo_lang("QC", "EN") == 80.0
    assert RaptorEngine._score_geo_lang("ON", "FR") == 70.0
    assert RaptorEngine._score_geo_lang("ON", "EN") == 65.0
    assert RaptorEngine._score_geo_lang("MB", "EN") == 50.0   # known province, no match
    assert RaptorEngine._score_geo_lang(None, None) == 40.0


# ── Decay ────────────────────────────────────────────────────────────────────

def test_decay_no_inactivity():
    """Score today → no decay applied."""
    raw = 80.0
    result = RaptorEngine._apply_decay(raw, _today())
    assert result == pytest.approx(raw, rel=0.001)


def test_decay_three_months():
    """90 days inactive → 0.90^3 ≈ 0.729 factor."""
    raw    = 80.0
    result = RaptorEngine._apply_decay(raw, _days_ago(90))
    assert result == pytest.approx(raw * (0.90 ** 3), rel=0.01)


def test_decay_floor():
    """Very old prospect → floor at DECAY_FLOOR, never below."""
    result = RaptorEngine._apply_decay(50.0, _days_ago(3650))
    assert result == DECAY_FLOOR


# ── Full score calculation ────────────────────────────────────────────────────

def test_calculate_high_value_prospect(db):
    """QC/FR/5M+/referral/fresh → score should be well above 80."""
    pid = _new_id()
    db.write_prospect(pid,
        first_name="Sophie", last_name="Tremblay",
        province="QC", language_pref="FR",
        estimated_assets_band="5M+", source_type="referral",
    )
    # Add a fresh touchpoint to boost recency + engagement
    db.write_touchpoint(pid, _today(), "meeting", "inbound", subject="Intro")
    engine = RaptorEngine(db)
    score = engine.calculate_lead_score(pid, write_back=False)
    assert score > THRESHOLD_IMMEDIATE


def test_calculate_low_value_prospect(db):
    """Cold/unknown/no touchpoints → score below THRESHOLD_NURTURE."""
    pid = _new_id()
    db.write_prospect(pid, source_type="cold")
    engine = RaptorEngine(db)
    score = engine.calculate_lead_score(pid, write_back=False)
    assert score < THRESHOLD_NURTURE


def test_calculate_writes_back_to_db(db):
    """write_back=True → lead_score persisted on prospect row."""
    pid = _new_id()
    db.write_prospect(pid, source_type="referral")
    engine = RaptorEngine(db)
    score = engine.calculate_lead_score(pid, write_back=True)
    p = db.get_prospect(pid)
    assert p["lead_score"] == pytest.approx(score, rel=0.001)
    assert p["lead_score_updated"] == _today()


def test_calculate_unknown_prospect_raises(db):
    engine = RaptorEngine(db)
    with pytest.raises(ValueError, match="Unknown prospect_id"):
        engine.calculate_lead_score("bad-id")


# ── Batch scoring ────────────────────────────────────────────────────────────

def test_score_all_skips_terminal_stages(db):
    """score_all_prospects skips active/lost/dormant prospects."""
    pid_active  = _new_id()
    pid_pending = _new_id()
    db.write_prospect(pid_active,  pipeline_stage="active")
    db.write_prospect(pid_pending, pipeline_stage="researched")
    engine  = RaptorEngine(db)
    results = engine.score_all_prospects()
    assert pid_active  not in results
    assert pid_pending in results


def test_score_all_updates_db(db):
    """score_all_prospects writes scores back to each prospect."""
    pid = _new_id()
    db.write_prospect(pid, source_type="referral", province="QC", language_pref="FR")
    RaptorEngine(db).score_all_prospects()
    p = db.get_prospect(pid)
    assert p["lead_score"] is not None and p["lead_score"] > 0


# ── Action queue ─────────────────────────────────────────────────────────────

def _make_scored_prospect(db, score: float, stage: str = "researched") -> str:
    """Helper: write a prospect with a pre-set lead_score."""
    pid = _new_id()
    db.write_prospect(pid, pipeline_stage=stage, lead_score=score)
    return pid


def test_action_queue_immediate_bucket(db):
    pid = _make_scored_prospect(db, 85.0)
    queue = RaptorEngine(db).get_action_queue()
    ids = [e["prospect_id"] for e in queue["immediate_outreach"]]
    assert pid in ids


def test_action_queue_nurture_bucket(db):
    pid = _make_scored_prospect(db, 65.0)
    queue = RaptorEngine(db).get_action_queue()
    ids = [e["prospect_id"] for e in queue["nurture"]]
    assert pid in ids


def test_action_queue_passive_bucket(db):
    pid = _make_scored_prospect(db, 30.0)
    queue = RaptorEngine(db).get_action_queue()
    ids = [e["prospect_id"] for e in queue["passive"]]
    assert pid in ids


def test_action_queue_re_consent(db):
    """Prospect with consent expiring in 10 days → appears in re_consent."""
    pid = _new_id()
    db.write_prospect(pid)
    expiry = (date.today() + timedelta(days=10)).isoformat()
    db.write_consent(pid, "casl_implied", "2024-01-01", expiry_date=expiry)
    queue = RaptorEngine(db).get_action_queue()
    ids = [e["prospect_id"] for e in queue["re_consent"]]
    assert pid in ids


def test_action_queue_overdue_followup(db):
    """Mid-funnel prospect with no touchpoint in 35 days → overdue."""
    pid = _new_id()
    db.write_prospect(pid, lead_score=60.0)
    db.write_consent(pid, "casl_express", "2026-01-01")
    db.write_pipeline_transition(pid, "contacted")
    tp_id = db.write_touchpoint(
        pid, _days_ago(35), "email", "outbound",
        compliance_approved=True, approval_principal="Compliance"
    )
    queue = RaptorEngine(db).get_action_queue()
    ids = [e["prospect_id"] for e in queue["overdue_followup"]]
    assert pid in ids


def test_action_queue_excludes_terminal(db):
    """active/lost/dormant never appear in any queue bucket."""
    for stage in ["active", "lost", "dormant"]:
        pid = _make_scored_prospect(db, 90.0, stage=stage)
    queue = RaptorEngine(db).get_action_queue()
    all_ids = set()
    for key in ["immediate_outreach", "nurture", "passive"]:
        all_ids.update(e["prospect_id"] for e in queue[key])
    # Terminal prospects should not appear
    for p in db.get_all_prospects(stage="active"):
        assert p["prospect_id"] not in all_ids


# ── Pipeline analytics ────────────────────────────────────────────────────────

def test_pipeline_analytics_stage_distribution(db):
    for _ in range(3):
        db.write_prospect(_new_id(), pipeline_stage="identified")
    for _ in range(2):
        db.write_prospect(_new_id(), pipeline_stage="researched")
    analytics = RaptorEngine(db).get_pipeline_analytics()
    dist = analytics["stage_distribution"]
    assert dist.get("identified") == 3
    assert dist.get("researched") == 2


def test_pipeline_analytics_source_effectiveness(db):
    pid1 = _new_id()
    pid2 = _new_id()
    db.write_prospect(pid1, source_type="referral", pipeline_stage="active")
    db.write_prospect(pid2, source_type="referral", pipeline_stage="identified")
    analytics = RaptorEngine(db).get_pipeline_analytics()
    src = analytics["source_effectiveness"]
    assert "referral" in src
    assert src["referral"]["total"] == 2
    assert src["referral"]["converted"] == 1
    assert src["referral"]["rate"] == pytest.approx(0.5, rel=0.01)


def test_coi_leaderboard_ordering(db):
    """COI with more referrals appears first in leaderboard."""
    coi1, coi2 = _new_id(), _new_id()
    db.write_coi(coi1, "Top Notaire")
    db.write_coi(coi2, "Low Notaire")
    for _ in range(3):
        pid = _new_id()
        db.write_prospect(pid)
        db.write_referral(coi1, pid, _today())
    pid = _new_id()
    db.write_prospect(pid)
    db.write_referral(coi2, pid, _today())
    analytics = RaptorEngine(db).get_pipeline_analytics()
    board = analytics["coi_leaderboard"]
    assert board[0]["name"] == "Top Notaire"
    assert board[0]["total"] == 3


# ── KB rule seeding ───────────────────────────────────────────────────────────

def test_seed_scoring_rule_inserts(db):
    """seed_scoring_rule() returns True on first call, rule exists in DB."""
    inserted = seed_scoring_rule(db)
    assert inserted is True
    row = db.conn.execute(
        "SELECT rule_data FROM kb_rules WHERE rule_id = 'RAPTOR_LEAD_SCORING_V1'"
    ).fetchone()
    assert row is not None
    data = json.loads(row["rule_data"])
    assert abs(sum(data["weights"].values()) - 1.0) < 0.01


def test_seed_scoring_rule_idempotent(db):
    """Second call returns False (already exists), no error."""
    seed_scoring_rule(db)
    assert seed_scoring_rule(db) is False


def test_engine_loads_custom_weights_from_kb(db):
    """Engine reads custom weights from kb_rules when available."""
    custom_weights = {
        "assets": 0.50, "source": 0.20, "recency": 0.10,
        "engagement": 0.10, "geo_lang": 0.05, "complexity": 0.05,
    }
    rule_data = json.dumps({"weights": custom_weights})
    db.conn.execute(
        "INSERT OR REPLACE INTO kb_rules "
        "(rule_id, source_file, source_module, rule_data, confidence, parsed_at, schema_version) "
        "VALUES (?,?,?,?,?,?,?)",
        ("RAPTOR_LEAD_SCORING_V1", "test", "RAPTOR", rule_data, 0.9, "2026-01-01", 3),
    )
    db.conn.commit()
    engine = RaptorEngine(db)
    assert engine._weights["assets"] == pytest.approx(0.50)
    assert engine._weights["source"] == pytest.approx(0.20)
