"""
Unit tests — RAPTOR Phase 9: Analytics & Economics Layer
Tests: CLV, payback period, churn risk, at-risk clients,
       retention ROI, growth scenario model, channel effectiveness.
~24 tests total.
"""
from __future__ import annotations

import sys
import os
import uuid
import sqlite3
import pytest
from datetime import date, timedelta
from pathlib import Path

_DABEIBA_ROOT = Path(__file__).resolve().parent.parent.parent.parent
for _p in [str(_DABEIBA_ROOT), str(_DABEIBA_ROOT / "shared")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from soma.soma_bridge import SomaBridge
from soma.raptor_analytics import (
    RaptorAnalytics,
    CHURN_RISK_THRESHOLD,
    DEFAULT_FEE_RATE,
    DEFAULT_TENURE_YEARS,
    DEFAULT_REFERRAL_MULTIPLIER,
    _aum_mid,
)

_MIG_DIR = _DABEIBA_ROOT / "shared" / "soma" / "migrations"


@pytest.fixture
def db(tmp_path):
    """Isolated test DB with RAPTOR schema (no onboarding table needed)."""
    db_file = str(tmp_path / "test_raptor_p9.db")
    os.environ["SOMA_DB_PATH"] = db_file

    conn = sqlite3.connect(db_file)
    for mig_name in [
        "001_initial_schema.sql",
        "003_kb_rules.sql",
        "012_raptor_core.sql",
        "017_consent_idempotency.sql",
        "018_pipeline_trigger_touchpoint.sql",
        "019_soma_events_pubsub.sql",
    ]:
        conn.executescript((_MIG_DIR / mig_name).read_text())
    conn.commit()
    conn.close()

    bridge = SomaBridge(db_path=db_file)
    bridge.__enter__()
    yield bridge
    bridge.__exit__(None, None, None)


def _new_id() -> str:
    return str(uuid.uuid4())


def _make_prospect(db, *, stage="identified", assets_band="1m_3m",
                   source_type="cold_outreach") -> str:
    pid = _new_id()
    db.write_prospect(pid, first_name="Test", last_name="Client",
                      estimated_assets_band=assets_band, source_type=source_type)
    return pid


def _add_consent(db, prospect_id):
    db.conn.execute(
        """INSERT INTO raptor_consent_ledger
           (prospect_id, consent_type, consent_date, revoked, deletion_requested, write_timestamp)
           VALUES (?, 'casl_express', date('now'), 0, 0, datetime('now'))""",
        (prospect_id,),
    )
    db.conn.commit()


def _add_touchpoint(db, prospect_id, *, days_ago=0, compliance_approved=1):
    tp_date = (date.today() - timedelta(days=days_ago)).isoformat()
    return db.conn.execute(
        """INSERT INTO raptor_touchpoints
           (prospect_id, date, channel, direction, compliance_approved, write_timestamp)
           VALUES (?, ?, 'phone', 'outbound', ?, datetime('now'))""",
        (prospect_id, tp_date, compliance_approved),
    ).lastrowid


def _activate_prospect(db, assets_band="1m_3m", source_type="cold_outreach") -> str:
    """Create a prospect and fast-track it to 'active' stage."""
    pid = _make_prospect(db, stage="identified",
                         assets_band=assets_band, source_type=source_type)
    _add_consent(db, pid)
    tp_id = _add_touchpoint(db, pid, compliance_approved=1)
    db.conn.commit()
    db.write_pipeline_transition(pid, "contacted",     transitioned_by="test")
    db.write_pipeline_transition(pid, "meeting_set",   transitioned_by="test")
    db.write_pipeline_transition(pid, "proposal_sent", transitioned_by="test",
                                 trigger_touchpoint_id=tp_id)
    db.write_pipeline_transition(pid, "onboarding",    transitioned_by="test")
    db.write_pipeline_transition(pid, "active",        transitioned_by="test")
    return pid


# ── calculate_client_lifetime_value ──────────────────────────────────────────

def test_clv_individual(db):
    pid = _activate_prospect(db, assets_band="1m_3m")
    result = RaptorAnalytics(db).calculate_client_lifetime_value(prospect_id=pid)
    expected_aum = _aum_mid("1m_3m")                                 # 2_000_000
    expected_clv = expected_aum * DEFAULT_FEE_RATE * DEFAULT_TENURE_YEARS * DEFAULT_REFERRAL_MULTIPLIER
    assert result["prospect_id"] == pid
    assert result["aum_estimate"] == expected_aum
    assert result["clv"] == round(expected_clv, 2)
    assert result["fee_rate"] == DEFAULT_FEE_RATE


def test_clv_individual_custom_params(db):
    pid = _activate_prospect(db, assets_band="500k_1m")
    result = RaptorAnalytics(db).calculate_client_lifetime_value(
        prospect_id=pid, fee_rate=0.015, avg_tenure_years=8.0, referral_multiplier=1.1
    )
    aum = _aum_mid("500k_1m")
    assert result["clv"] == round(aum * 0.015 * 8.0 * 1.1, 2)


def test_clv_unknown_prospect_raises(db):
    with pytest.raises(ValueError, match="Unknown prospect_id"):
        RaptorAnalytics(db).calculate_client_lifetime_value(prospect_id="bad-id")


def test_clv_portfolio_empty(db):
    result = RaptorAnalytics(db).calculate_client_lifetime_value()
    assert result["client_count"] == 0
    assert result["total_clv"] == 0.0


def test_clv_portfolio_aggregate(db):
    _activate_prospect(db, assets_band="1m_3m")
    _activate_prospect(db, assets_band="500k_1m")
    result = RaptorAnalytics(db).calculate_client_lifetime_value()
    assert result["client_count"] == 2
    assert result["total_clv"] > 0
    assert result["avg_clv"] > 0
    assert "by_band" in result
    assert "1m_3m" in result["by_band"] or "500k_1m" in result["by_band"]


def test_clv_portfolio_excludes_non_active(db):
    _activate_prospect(db)
    _make_prospect(db, stage="identified")   # identified — not active
    result = RaptorAnalytics(db).calculate_client_lifetime_value()
    assert result["client_count"] == 1


# ── calculate_payback_period ──────────────────────────────────────────────────

def test_payback_required_keys(db):
    pid = _activate_prospect(db)
    result = RaptorAnalytics(db).calculate_payback_period(pid)
    for key in ("prospect_id", "touchpoint_count", "acquisition_cost",
                "monthly_revenue", "payback_months", "aum_estimate"):
        assert key in result, f"Missing key: {key}"


def test_payback_calculation(db):
    pid = _make_prospect(db, assets_band="500k_1m")
    _add_touchpoint(db, pid)
    _add_touchpoint(db, pid)
    db.conn.commit()
    result = RaptorAnalytics(db).calculate_payback_period(
        pid, advisor_hourly_rate=200.0, hours_per_touchpoint=1.0, fee_rate=0.01
    )
    aum = _aum_mid("500k_1m")                 # 750_000
    expected_cost = result["touchpoint_count"] * 1.0 * 200.0
    expected_monthly = aum * 0.01 / 12.0      # 625
    assert result["acquisition_cost"] == expected_cost
    assert result["payback_months"] == round(expected_cost / expected_monthly, 1)


def test_payback_zero_touchpoints(db):
    pid = _make_prospect(db)
    result = RaptorAnalytics(db).calculate_payback_period(pid)
    assert result["touchpoint_count"] == 0
    assert result["acquisition_cost"] == 0.0
    assert result["payback_months"] == 0.0


def test_payback_unknown_prospect_raises(db):
    with pytest.raises(ValueError, match="Unknown prospect_id"):
        RaptorAnalytics(db).calculate_payback_period("bad-id")


# ── churn_risk_score ──────────────────────────────────────────────────────────

def test_churn_risk_high_no_contact(db):
    """Prospect with last contact 200 days ago + low AUM → MEDIUM or HIGH risk."""
    pid = _activate_prospect(db, assets_band="under_250k")
    # Back-date ALL touchpoints for this prospect to 200 days ago
    old_date = (date.today() - timedelta(days=200)).isoformat()
    db.conn.execute(
        "UPDATE raptor_touchpoints SET date=? WHERE prospect_id=?",
        (old_date, pid),
    )
    db.conn.commit()
    result = RaptorAnalytics(db).churn_risk_score(pid)
    assert result["risk_level"] in ("HIGH", "MEDIUM")
    assert result["risk_score"] >= CHURN_RISK_THRESHOLD


def test_churn_risk_low_recent_contact(db):
    """Prospect contacted today + high AUM → LOW risk."""
    pid = _activate_prospect(db, assets_band="over_3m")
    _add_touchpoint(db, pid, days_ago=0)
    db.conn.commit()
    result = RaptorAnalytics(db).churn_risk_score(pid)
    assert result["risk_level"] == "LOW"
    assert result["risk_score"] < CHURN_RISK_THRESHOLD


def test_churn_risk_required_keys(db):
    pid = _activate_prospect(db)
    result = RaptorAnalytics(db).churn_risk_score(pid)
    for key in ("prospect_id", "risk_score", "risk_level",
                "recommended_action", "days_since_contact", "factors"):
        assert key in result
    for factor in ("contact_frequency", "aum_band", "stage_velocity", "referral_history"):
        assert factor in result["factors"]


def test_churn_risk_unknown_raises(db):
    with pytest.raises(ValueError, match="Unknown prospect_id"):
        RaptorAnalytics(db).churn_risk_score("bad-id")


# ── get_at_risk_clients ───────────────────────────────────────────────────────

def test_at_risk_excludes_non_active(db):
    """Only active prospects can be at-risk."""
    _make_prospect(db, stage="identified")
    result = RaptorAnalytics(db).get_at_risk_clients()
    assert result == []


def test_at_risk_sorted_desc(db):
    """Result is sorted by risk_score descending."""
    pid1 = _activate_prospect(db, assets_band="under_250k")
    pid2 = _activate_prospect(db, assets_band="over_3m")
    # Give pid2 a very recent touchpoint (lower risk)
    _add_touchpoint(db, pid2, days_ago=1)
    db.conn.commit()
    result = RaptorAnalytics(db).get_at_risk_clients()
    if len(result) > 1:
        scores = [r["risk_score"] for r in result]
        assert scores == sorted(scores, reverse=True)


def test_at_risk_required_keys(db):
    pid = _activate_prospect(db, assets_band="under_250k")
    # Force high risk: old touchpoint
    old_date = (date.today() - timedelta(days=200)).isoformat()
    db.conn.execute(
        """INSERT INTO raptor_touchpoints
           (prospect_id, date, channel, direction, compliance_approved, write_timestamp)
           VALUES (?, ?, 'email', 'outbound', 1, datetime('now'))""",
        (pid, old_date),
    )
    db.conn.commit()
    result = RaptorAnalytics(db).get_at_risk_clients()
    if result:
        for key in ("prospect_id", "risk_score", "risk_level", "action", "days_since_contact"):
            assert key in result[0]


# ── retention_vs_acquisition_roi ──────────────────────────────────────────────

def test_retention_roi_no_clients(db):
    result = RaptorAnalytics(db).retention_vs_acquisition_roi()
    assert result["client_count"] == 0


def test_retention_roi_ratio_positive(db):
    _activate_prospect(db, assets_band="1m_3m")
    _add_touchpoint(db, _activate_prospect(db, assets_band="500k_1m"), days_ago=10)
    db.conn.commit()
    result = RaptorAnalytics(db).retention_vs_acquisition_roi()
    assert result["client_count"] >= 1
    assert result["retention_roi_ratio"] >= 1.0
    for key in ("avg_annual_retention_cost", "avg_replacement_cost",
                "avg_clv", "recommendation"):
        assert key in result


# ── growth_scenario_model ─────────────────────────────────────────────────────

def test_growth_three_scenarios(db):
    result = RaptorAnalytics(db).growth_scenario_model(months=60)
    assert "conservative" in result
    assert "base" in result
    assert "aggressive" in result
    assert "assumptions" in result


def test_growth_snapshots_at_correct_months(db):
    result = RaptorAnalytics(db).growth_scenario_model(months=60)
    months = [s["month"] for s in result["base"]]
    assert months == [12, 36, 60]


def test_growth_aggressive_exceeds_conservative(db):
    result = RaptorAnalytics(db).growth_scenario_model(months=60)
    agg_final = result["aggressive"][-1]["clients"]
    con_final = result["conservative"][-1]["clients"]
    assert agg_final > con_final


# ── channel_effectiveness ─────────────────────────────────────────────────────

def test_channel_effectiveness_empty(db):
    result = RaptorAnalytics(db).channel_effectiveness()
    assert isinstance(result, dict)


def test_channel_effectiveness_required_keys(db):
    _activate_prospect(db, source_type="coi_referral")
    result = RaptorAnalytics(db).channel_effectiveness()
    for ch, data in result.items():
        for key in ("total", "converted", "conversion_rate", "avg_aum"):
            assert key in data, f"Missing key '{key}' in channel '{ch}'"


def test_channel_effectiveness_conversion_rate(db):
    # 1 active from coi_referral → conversion_rate = 1.0
    _activate_prospect(db, source_type="coi_referral")
    # 1 non-active from cold_outreach → conversion_rate = 0.0
    _make_prospect(db, source_type="cold_outreach")
    result = RaptorAnalytics(db).channel_effectiveness()
    assert result["coi_referral"]["conversion_rate"] == 1.0
    assert result["cold_outreach"]["conversion_rate"] == 0.0


def test_channel_sorted_by_conversion_rate_desc(db):
    _activate_prospect(db, source_type="coi_referral")
    _make_prospect(db, source_type="cold_outreach")
    result = RaptorAnalytics(db).channel_effectiveness()
    rates = [v["conversion_rate"] for v in result.values()]
    assert rates == sorted(rates, reverse=True)
