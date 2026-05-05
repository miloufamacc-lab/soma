"""
Unit tests — RAPTOR Phase 0: SomaBridge RAPTOR methods
Tests: prospects, pipeline transitions, stage gates, touchpoints,
       consent ledger, COI network, referrals, dashboard summary.
26 tests total.
"""
import sys, os, uuid, pytest
from pathlib import Path

_DABEIBA_ROOT = Path(__file__).resolve().parent.parent.parent.parent
for _p in [str(_DABEIBA_ROOT), str(_DABEIBA_ROOT / "shared")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from soma.soma_bridge import SomaBridge

_MIGRATIONS = _DABEIBA_ROOT / "shared" / "soma" / "migrations"
MIGRATION_12 = _MIGRATIONS / "012_raptor_core.sql"
MIGRATION_17 = _MIGRATIONS / "017_consent_idempotency.sql"       # UNIQUE index for write_consent UPSERT
MIGRATION_18 = _MIGRATIONS / "018_pipeline_trigger_touchpoint.sql"  # trigger_touchpoint_id column


@pytest.fixture
def db(tmp_path):
    """Isolated test DB with RAPTOR schema (migrations 012 + 017 + 018)."""
    db_file = str(tmp_path / "test_raptor.db")
    os.environ["SOMA_DB_PATH"] = db_file

    import sqlite3
    conn = sqlite3.connect(db_file)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version INTEGER NOT NULL,
            applied_at TEXT
        )
    """)
    conn.execute("INSERT INTO schema_version (version, applied_at) VALUES (11, datetime('now'))")
    conn.commit()
    conn.executescript(MIGRATION_12.read_text())
    conn.executescript(MIGRATION_17.read_text())
    conn.executescript(MIGRATION_18.read_text())
    conn.close()

    bridge = SomaBridge(db_path=db_file)
    bridge.__enter__()
    yield bridge
    bridge.__exit__(None, None, None)


def new_id():
    return str(uuid.uuid4())


# ── Prospects ──────────────────────────────────────────────────────────────

def test_write_and_get_prospect(db):
    pid = new_id()
    db.write_prospect(pid, first_name="Marie", last_name="Dubois",
                      email="marie@test.com", province="QC",
                      estimated_assets_band="2M-5M", source_type="referral")
    p = db.get_prospect(pid)
    assert p is not None
    assert p["first_name"] == "Marie"
    assert p["province"] == "QC"
    assert p["pipeline_stage"] == "identified"


def test_get_prospect_missing_returns_none(db):
    assert db.get_prospect("does-not-exist") is None


def test_update_prospect(db):
    pid = new_id()
    db.write_prospect(pid, first_name="Jean")
    db.update_prospect(pid, first_name="Jean-Paul", notes="Updated")
    p = db.get_prospect(pid)
    assert p["first_name"] == "Jean-Paul"
    assert p["notes"] == "Updated"


def test_get_all_prospects_filter(db):
    pid1, pid2 = new_id(), new_id()
    db.write_prospect(pid1, pipeline_stage="identified")
    db.write_prospect(pid2, pipeline_stage="researched")
    all_p = db.get_all_prospects()
    assert len(all_p) == 2
    identified = db.get_all_prospects(stage="identified")
    assert len(identified) == 1
    assert identified[0]["prospect_id"] == pid1


# ── Pipeline transitions ───────────────────────────────────────────────────

def test_simple_transition_no_gate(db):
    """identified → researched has no gate."""
    pid = new_id()
    db.write_prospect(pid)
    log_id = db.write_pipeline_transition(pid, "researched", reason="Done research")
    assert log_id > 0
    p = db.get_prospect(pid)
    assert p["pipeline_stage"] == "researched"


def test_pipeline_history_logged(db):
    pid = new_id()
    db.write_prospect(pid)
    db.write_pipeline_transition(pid, "researched")
    db.write_consent(pid, "casl_express", "2026-01-01")
    db.write_pipeline_transition(pid, "contacted", reason="Ready to contact")
    history = db.get_pipeline_history(pid)
    assert len(history) == 2
    assert history[0]["from_stage"] == "identified"
    assert history[0]["to_stage"] == "researched"
    assert history[1]["from_stage"] == "researched"
    assert history[1]["to_stage"] == "contacted"
    assert history[1]["reason"] == "Ready to contact"


def test_transition_unknown_prospect_raises(db):
    with pytest.raises(ValueError, match="Unknown prospect_id"):
        db.write_pipeline_transition("bad-id", "researched")


# ── Stage gate: contacted requires consent ─────────────────────────────────

def test_gate_contacted_blocked_without_consent(db):
    pid = new_id()
    db.write_prospect(pid)
    with pytest.raises(ValueError, match="no active consent"):
        db.write_pipeline_transition(pid, "contacted")


def test_gate_contacted_allowed_with_consent(db):
    pid = new_id()
    db.write_prospect(pid)
    db.write_consent(pid, "casl_express", "2026-01-01")
    log_id = db.write_pipeline_transition(pid, "contacted")
    assert log_id > 0
    assert db.get_prospect(pid)["pipeline_stage"] == "contacted"


# ── Stage gate: onboarding requires signed COI agreement ──────────────────

def test_gate_onboarding_blocked_without_signed_agreement(db):
    pid = new_id()
    coi_id = new_id()
    db.write_prospect(pid)
    db.write_coi(coi_id, "Bob Notaire", referral_agreement_signed=False)
    db.write_referral(coi_id, pid, "2026-01-15")
    db.write_consent(pid, "casl_express", "2026-01-01")
    db.write_pipeline_transition(pid, "contacted")
    with pytest.raises(ValueError, match="no signed referral agreement"):
        db.write_pipeline_transition(pid, "onboarding")


def test_gate_onboarding_allowed_with_signed_agreement(db):
    """Prospect with signed COI agreement can reach onboarding."""
    pid = new_id()
    coi_id = new_id()
    db.write_prospect(pid)
    db.write_coi(coi_id, "Bob Notaire", referral_agreement_signed=True)
    db.write_referral(coi_id, pid, "2026-01-15")
    db.write_consent(pid, "casl_express", "2026-01-01")
    tp_id = db.write_touchpoint(pid, "2026-02-01", "email", "outbound",
                                compliance_approved=True, approval_principal="Compliance")
    db.write_pipeline_transition(pid, "contacted")
    db.write_pipeline_transition(pid, "meeting_set")
    db.write_pipeline_transition(pid, "proposal_sent", trigger_touchpoint_id=tp_id)
    log_id = db.write_pipeline_transition(pid, "onboarding")
    assert log_id > 0
    assert db.get_prospect(pid)["pipeline_stage"] == "onboarding"


# ── Stage gate: proposal_sent requires approved touchpoint ────────────────

def test_gate_proposal_blocked_without_approved_touchpoint(db):
    pid = new_id()
    db.write_prospect(pid)
    db.write_consent(pid, "casl_express", "2026-01-01")
    db.write_pipeline_transition(pid, "contacted")
    db.write_pipeline_transition(pid, "meeting_set")
    with pytest.raises(ValueError, match="zero compliance-approved touchpoints"):
        db.write_pipeline_transition(pid, "proposal_sent")


def test_gate_proposal_allowed_with_approved_touchpoint(db):
    pid = new_id()
    db.write_prospect(pid)
    db.write_consent(pid, "casl_express", "2026-01-01")
    db.write_pipeline_transition(pid, "contacted")
    tp_id = db.write_touchpoint(pid, "2026-02-01", "email", "outbound",
                                subject="Initial deck", compliance_approved=True,
                                approval_principal="Compliance Officer")
    db.write_pipeline_transition(pid, "meeting_set")
    log_id = db.write_pipeline_transition(pid, "proposal_sent", trigger_touchpoint_id=tp_id)
    assert log_id > 0


# ── Touchpoints ────────────────────────────────────────────────────────────

def test_write_and_get_touchpoints(db):
    pid = new_id()
    db.write_prospect(pid)
    tp_id = db.write_touchpoint(pid, "2026-03-01", "phone", "outbound",
                                 subject="Intro call")
    assert tp_id > 0
    tps = db.get_touchpoints(pid)
    assert len(tps) == 1
    assert tps[0]["channel"] == "phone"


# ── Consent ledger ─────────────────────────────────────────────────────────

def test_casl_implied_auto_expiry(db):
    pid = new_id()
    db.write_prospect(pid)
    db.write_consent(pid, "casl_implied", "2025-01-01")
    rows = db.get_consent_status(pid)
    assert rows["consents"][0]["expiry_date"] == "2027-01-01"


def test_check_consent_active(db):
    pid = new_id()
    db.write_prospect(pid)
    db.write_consent(pid, "casl_express", "2026-01-01")
    assert db.check_consent(pid, "casl_express") is True


def test_check_consent_revoked(db):
    pid = new_id()
    db.write_prospect(pid)
    consent_id = db.write_consent(pid, "casl_express", "2026-01-01")
    db.revoke_consent(consent_id)
    assert db.check_consent(pid, "casl_express") is False


def test_get_consent_status_no_active(db):
    pid = new_id()
    db.write_prospect(pid)
    status = db.get_consent_status(pid)
    assert status["has_active_consent"] is False
    assert status["active_count"] == 0


def test_get_expiring_consents(db):
    pid = new_id()
    db.write_prospect(pid)
    from datetime import date, timedelta
    expiry = (date.today() + timedelta(days=10)).isoformat()
    db.write_consent(pid, "casl_implied", "2024-01-01", expiry_date=expiry)
    expiring = db.get_expiring_consents(days_ahead=30)
    assert any(e["prospect_id"] == pid for e in expiring)


def test_get_expiring_consents_excludes_far_future(db):
    pid = new_id()
    db.write_prospect(pid)
    from datetime import date, timedelta
    expiry = (date.today() + timedelta(days=90)).isoformat()
    db.write_consent(pid, "casl_implied", "2024-01-01", expiry_date=expiry)
    expiring = db.get_expiring_consents(days_ahead=30)
    assert not any(e["prospect_id"] == pid for e in expiring)


# ── COI network ────────────────────────────────────────────────────────────

def test_write_and_get_coi(db):
    coi_id = new_id()
    db.write_coi(coi_id, "Luc Martin", firm="Martin & Associés",
                 profession="Notaire", referral_agreement_signed=True)
    coi = db.get_coi(coi_id)
    assert coi["name"] == "Luc Martin"
    assert coi["referral_agreement_signed"] == 1


def test_get_coi_network(db):
    for name in ["Alice", "Bob", "Carol"]:
        db.write_coi(new_id(), name)
    network = db.get_coi_network()
    assert len(network) == 3


def test_get_coi_referral_stats(db):
    coi_id = new_id()
    db.write_coi(coi_id, "Test COI")
    pid1, pid2, pid3 = new_id(), new_id(), new_id()
    for pid in [pid1, pid2, pid3]:
        db.write_prospect(pid)
    db.write_referral(coi_id, pid1, "2026-01-01", outcome="converted")
    db.write_referral(coi_id, pid2, "2026-01-02", outcome="lost")
    db.write_referral(coi_id, pid3, "2026-01-03", outcome="pending")
    stats = db.get_coi_referral_stats(coi_id)
    assert stats["total"] == 3
    assert stats["converted"] == 1
    assert stats["conversion_rate"] == pytest.approx(1/3, rel=1e-3)


# ── Referrals ──────────────────────────────────────────────────────────────

def test_write_and_get_referrals(db):
    coi_id, pid = new_id(), new_id()
    db.write_coi(coi_id, "My COI")
    db.write_prospect(pid)
    ref_id = db.write_referral(coi_id, pid, "2026-03-15", disclosure_delivered=True)
    assert ref_id > 0
    by_coi = db.get_referrals_by_coi(coi_id)
    assert len(by_coi) == 1
    by_prospect = db.get_referrals_by_prospect(pid)
    assert len(by_prospect) == 1


# ── Dashboard summary ──────────────────────────────────────────────────────

def test_get_raptor_summary_empty(db):
    summary = db.get_raptor_summary()
    assert summary["total_prospects"] == 0
    assert summary["conversion_rate"] == 0.0
    assert summary["coi_count"] == 0


def test_get_raptor_summary_with_data(db):
    pid = new_id()
    db.write_prospect(pid, pipeline_stage="active")
    db.write_coi(new_id(), "Test COI")
    summary = db.get_raptor_summary()
    assert summary["total_prospects"] == 1
    assert summary["active_count"] == 1
    assert summary["conversion_rate"] == 1.0
    assert summary["coi_count"] == 1
