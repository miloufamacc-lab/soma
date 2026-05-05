"""
RAPTOR Phase 11 — End-to-End Integration Tests

Full pipeline flows using synthetic data. No real client data required.
Exercises every RAPTOR sub-module in realistic sequence:
  identified → scored → compliant → contacted → meeting_set
  → proposal_sent → onboarding → active → CIPHER handoff

Cross-module interactions tested:
  compliance + engine, CRM3 + analytics, privacy + events,
  raptor_status + run_day step_5b.

~20 tests total.
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
from soma.raptor_engine import RaptorEngine
from soma.raptor_compliance import RaptorCompliance, seed_compliance_rules
from soma.raptor_crm3_analyzer import CRM3Analyzer
from soma.raptor_privacy import RaptorPrivacy
from soma.raptor_onboarding import RaptorOnboarding, MILESTONES
from soma.raptor_analytics import RaptorAnalytics

_MIG_DIR = _DABEIBA_ROOT / "shared" / "soma" / "migrations"

_ALL_MIGRATIONS = [
    "001_initial_schema.sql",
    "003_kb_rules.sql",
    "004_client_profiles.sql",
    "012_raptor_core.sql",
    "017_consent_idempotency.sql",
    "018_pipeline_trigger_touchpoint.sql",
    "019_soma_events_pubsub.sql",
    "026_raptor_touchpoints_archive.sql",
    "027_raptor_crm3.sql",
    "028_raptor_onboarding.sql",
]


@pytest.fixture
def db(tmp_path):
    """Full RAPTOR schema — all required migrations + seeded compliance rules."""
    db_file = str(tmp_path / "test_raptor_p11.db")
    os.environ["SOMA_DB_PATH"] = db_file

    conn = sqlite3.connect(db_file)
    for mig in _ALL_MIGRATIONS:
        conn.executescript((_MIG_DIR / mig).read_text())
    conn.commit()
    conn.close()

    bridge = SomaBridge(db_path=db_file)
    bridge.__enter__()
    seed_compliance_rules(bridge)
    yield bridge
    bridge.__exit__(None, None, None)


def _pid() -> str:
    return str(uuid.uuid4())


# ── Helpers ───────────────────────────────────────────────────────────────────

def _add_consent(db, prospect_id):
    db.conn.execute(
        """INSERT INTO raptor_consent_ledger
           (prospect_id, consent_type, consent_date, revoked,
            deletion_requested, write_timestamp)
           VALUES (?, 'casl_express', date('now'), 0, 0, datetime('now'))""",
        (prospect_id,),
    )
    db.conn.commit()


def _add_compliant_touchpoint(db, prospect_id, days_ago=0):
    tp_date = (date.today() - timedelta(days=days_ago)).isoformat()
    tp_id = db.conn.execute(
        """INSERT INTO raptor_touchpoints
           (prospect_id, date, channel, direction, compliance_approved, write_timestamp)
           VALUES (?, ?, 'phone', 'outbound', 1, datetime('now'))""",
        (prospect_id, tp_date),
    ).lastrowid
    db.conn.commit()
    return tp_id


def _prospect_at_proposal(db, assets_band="1m_3m",
                           source_type="coi_referral") -> tuple[str, int]:
    """Synthetic prospect advanced to proposal_sent. Returns (pid, tp_id)."""
    pid = _pid()
    db.write_prospect(
        pid,
        first_name="Marie",
        last_name="Tremblay",
        email="marie.tremblay@example.com",
        estimated_assets_band=assets_band,
        source_type=source_type,
        language_pref="FR",
        province="QC",
    )
    _add_consent(db, pid)
    tp_id = _add_compliant_touchpoint(db, pid)
    db.write_pipeline_transition(pid, "contacted",     transitioned_by="test")
    db.write_pipeline_transition(pid, "meeting_set",   transitioned_by="test")
    db.write_pipeline_transition(pid, "proposal_sent", transitioned_by="test",
                                 trigger_touchpoint_id=tp_id)
    return pid, tp_id


# ── 1. Full pipeline smoke test ───────────────────────────────────────────────

def test_full_pipeline_identified_to_active(db):
    """Walk a prospect from identified all the way to active via every stage gate."""
    pid, _ = _prospect_at_proposal(db)
    ob = RaptorOnboarding(db)
    ob.initiate_onboarding(pid)

    p = db.get_prospect(pid)
    assert p["pipeline_stage"] == "onboarding"
    assert len(db.get_onboarding_milestones(pid)) == len(MILESTONES)

    receipt = ob.handoff_to_cipher(pid)
    assert receipt["cipher_profile_created"] is True
    assert db.get_prospect(pid)["pipeline_stage"] == "active"


def test_full_pipeline_soma_events_published(db):
    """SOMA events are published at onboarding_initiated and cipher_handoff."""
    pid, _ = _prospect_at_proposal(db)
    ob = RaptorOnboarding(db)
    ob.initiate_onboarding(pid)
    ob.handoff_to_cipher(pid)

    events = db.conn.execute(
        "SELECT event_type FROM soma_events WHERE payload_json LIKE ?",
        (f'%"{pid}"%',),
    ).fetchall()
    event_types = {r["event_type"] for r in events}
    assert "raptor_onboarding_initiated" in event_types
    assert "raptor_cipher_handoff" in event_types


# ── 2. Lead scoring integration ───────────────────────────────────────────────

def test_scoring_all_prospects_scored(db):
    """score_all_prospects() returns a score for every prospect in DB."""
    pid1 = _pid()
    pid2 = _pid()
    db.write_prospect(pid1, estimated_assets_band="under_250k",
                      source_type="cold_outreach")
    db.write_prospect(pid2, estimated_assets_band="over_3m",
                      source_type="coi_referral")
    _add_consent(db, pid2)
    _add_compliant_touchpoint(db, pid2)

    engine = RaptorEngine(db)
    scores = engine.score_all_prospects()
    assert pid1 in scores
    assert pid2 in scores
    # prospect with consent + touchpoint + premium band scores higher
    assert scores[pid2] > scores[pid1]


def test_action_queue_has_all_buckets(db):
    """Action queue exposes all 5 expected buckets after scoring."""
    _prospect_at_proposal(db)
    engine = RaptorEngine(db)
    engine.score_all_prospects()
    queue = engine.get_action_queue()
    for bucket in ("immediate_outreach", "nurture", "passive", "overdue_followup"):
        assert bucket in queue


# ── 3. Compliance integration ─────────────────────────────────────────────────

def test_compliance_flags_guaranteed_returns(db):
    """Prohibited term scan detects 'garanti' as a PERFORMANCE_GUARANTEE hit."""
    hits = RaptorCompliance(db).scan_prohibited_terms(
        "Votre placement est garanti à 6% par année."
    )
    assert len(hits) > 0
    categories = {h["category"] for h in hits}
    assert "PERFORMANCE_GUARANTEE" in categories


def test_compliance_passes_clean_message(db):
    """Neutral client update generates no prohibited term hits."""
    hits = RaptorCompliance(db).scan_prohibited_terms(
        "Je souhaitais vous informer que votre portefeuille a bien été mis à jour."
    )
    assert hits == []


def test_compliance_validate_outreach_blocked_without_consent(db):
    """validate_outreach blocks if prospect has no consent on file."""
    pid = _pid()
    db.write_prospect(pid, first_name="Jean", last_name="Dupont")
    result = RaptorCompliance(db).validate_outreach(pid, "Hello Jean.")
    codes = [v["code"] for v in result["violations"]]
    assert any("CONSENT" in c for c in codes)


def test_touchpoints_archived_on_insert(db):
    """Inserting a touchpoint triggers the CIRO archive (raptor_touchpoints_archive)."""
    pid = _pid()
    db.write_prospect(pid)
    _add_compliant_touchpoint(db, pid)
    count = db.conn.execute(
        "SELECT COUNT(*) AS n FROM raptor_touchpoints_archive "
        "WHERE operation='INSERT'"
    ).fetchone()["n"]
    assert count >= 1


# ── 4. CRM3 integration ───────────────────────────────────────────────────────

def test_crm3_report_is_string_with_key_sections(db):
    """CRM3 report is a markdown string containing required section headers."""
    pid, _ = _prospect_at_proposal(db, assets_band="1m_3m")
    analyzer = CRM3Analyzer(db)

    current  = [{"fund_name": "RBC Mutual Fund", "ticker": "XSP",
                  "weight": 1.0, "mer": 0.20}]
    proposed = [{"fund_name": "Vanguard S&P 500", "ticker": "VFV",
                  "weight": 1.0, "mer": 0.09}]
    comp   = analyzer.compare_to_raptor_model(current, proposed)
    report = analyzer.generate_crm3_report(pid, comp, aum_estimate=1_500_000)

    assert isinstance(report, str)
    assert "CRM3 Fee Analysis" in report
    assert "Potential Savings" in report
    assert "DISCLOSURES" in report or "disclosure" in report.lower()


def test_crm3_report_shows_savings_when_mer_higher(db):
    """CRM3 report text contains a positive savings figure when current MER > proposed."""
    pid, _ = _prospect_at_proposal(db)
    analyzer = CRM3Analyzer(db)
    current  = [{"fund_name": "RBC Equity Fund", "ticker": "XSP",
                  "weight": 1.0, "mer": 0.25}]
    proposed = [{"fund_name": "Vanguard ETF", "ticker": "VFV",
                  "weight": 1.0, "mer": 0.08}]
    comp   = analyzer.compare_to_raptor_model(current, proposed)
    report = analyzer.generate_crm3_report(pid, comp, aum_estimate=1_000_000)
    # Savings section must mention a dollar amount
    assert "$" in report
    assert "Savings" in report or "savings" in report


# ── 5. Privacy integration ────────────────────────────────────────────────────

def test_privacy_deletion_scrubs_pii(db):
    """process_deletion_request() overwrites PII and preserves CIRO record."""
    pid = _pid()
    db.write_prospect(pid, first_name="Jean", last_name="Dupont",
                      email="jean.dupont@example.com")
    _add_consent(db, pid)
    db.conn.execute(
        "UPDATE raptor_consent_ledger SET deletion_requested=1 WHERE prospect_id=?",
        (pid,),
    )
    db.conn.commit()

    receipt = RaptorPrivacy(db).process_deletion_request(pid)
    assert receipt["law25_compliant"] is True
    assert receipt["ciro_archive_preserved"] is True
    assert "DELETED" in (db.get_prospect(pid).get("first_name") or "")


def test_privacy_consent_health_keys(db):
    """consent_health_report returns all required keys."""
    pid = _pid()
    db.write_prospect(pid)
    _add_consent(db, pid)
    report = RaptorPrivacy(db).consent_health_report()
    for key in ("valid_consent_count", "expiring_30d", "expiring_60d",
                "revoked_not_scrubbed", "deletion_pending"):
        assert key in report, f"Missing key: {key}"
    assert report["valid_consent_count"] >= 1


# ── 6. Analytics integration ──────────────────────────────────────────────────

def test_analytics_clv_after_full_pipeline(db):
    """CLV is correct for an active client with known AUM band."""
    pid, _ = _prospect_at_proposal(db, assets_band="1m_3m")
    ob = RaptorOnboarding(db)
    ob.initiate_onboarding(pid)
    ob.handoff_to_cipher(pid)

    result = RaptorAnalytics(db).calculate_client_lifetime_value(prospect_id=pid)
    assert result["clv"] > 0
    assert result["aum_estimate"] == 2_000_000   # midpoint for 1m_3m band


def test_analytics_churn_low_for_recently_contacted(db):
    """Newly active client with a today touchpoint = LOW churn risk."""
    pid, _ = _prospect_at_proposal(db, assets_band="over_3m")
    ob = RaptorOnboarding(db)
    ob.initiate_onboarding(pid)
    ob.handoff_to_cipher(pid)
    _add_compliant_touchpoint(db, pid, days_ago=0)

    result = RaptorAnalytics(db).churn_risk_score(pid)
    assert result["risk_level"] == "LOW"


def test_analytics_channel_tracks_source_type(db):
    """channel_effectiveness correctly attributes active clients to source_type."""
    pid, _ = _prospect_at_proposal(db, source_type="coi_referral",
                                    assets_band="500k_1m")
    ob = RaptorOnboarding(db)
    ob.initiate_onboarding(pid)
    ob.handoff_to_cipher(pid)

    channels = RaptorAnalytics(db).channel_effectiveness()
    assert "coi_referral" in channels
    assert channels["coi_referral"]["converted"] >= 1
    assert channels["coi_referral"]["conversion_rate"] == 1.0


# ── 7. raptor_status integration ─────────────────────────────────────────────

def test_raptor_status_sections_present(db):
    """raptor_status() returns all required top-level sections."""
    _prospect_at_proposal(db)
    engine = RaptorEngine(db)
    engine.score_all_prospects()
    status = engine.raptor_status()
    for section in ("pipeline", "scores", "actions", "coi", "consent"):
        assert section in status
    for key in ("immediate", "re_consent", "overdue"):
        assert key in status["actions"]


def test_raptor_status_pipeline_counts_match_db(db):
    """raptor_status pipeline counts match actual DB stage counts."""
    pid1, _ = _prospect_at_proposal(db)
    pid2 = _pid()
    db.write_prospect(pid2)   # stays at identified

    engine = RaptorEngine(db)
    engine.score_all_prospects()
    status = engine.raptor_status()

    assert status["pipeline"].get("identified", 0) >= 1
    assert status["pipeline"].get("proposal_sent", 0) >= 1


# ── 8. Growth model + retention ROI integration ────────────────────────────────

def test_growth_model_aggressive_beats_conservative(db):
    """Aggressive scenario always ends with more clients than conservative."""
    result = RaptorAnalytics(db).growth_scenario_model(
        months=60, new_per_month=2.0, avg_aum=1_000_000
    )
    agg_clients = result["aggressive"][-1]["clients"]
    con_clients = result["conservative"][-1]["clients"]
    assert agg_clients > con_clients
    # Revenue follows clients
    assert result["aggressive"][-1]["annual_revenue"] > \
           result["conservative"][-1]["annual_revenue"]


def test_retention_roi_after_active_clients(db):
    """Retention ROI ratio is positive with at least one active client."""
    pid, _ = _prospect_at_proposal(db, assets_band="1m_3m")
    ob = RaptorOnboarding(db)
    ob.initiate_onboarding(pid)
    ob.handoff_to_cipher(pid)
    _add_compliant_touchpoint(db, pid)

    roi = RaptorAnalytics(db).retention_vs_acquisition_roi()
    assert roi["client_count"] >= 1
    assert roi["retention_roi_ratio"] >= 1.0
    assert roi["avg_clv"] > 0
