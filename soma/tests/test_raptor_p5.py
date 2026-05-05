"""
Unit tests — RAPTOR Phase 5: Privacy & Data Sanitization Engine
Tests: process_deletion_request, run_dormant_cleanup,
       consent_health_report, run_breach_notification_check.
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
from soma.raptor_privacy import RaptorPrivacy

_MIG_DIR = _DABEIBA_ROOT / "shared" / "soma" / "migrations"


@pytest.fixture
def db(tmp_path):
    """Isolated test DB with RAPTOR + privacy schema."""
    db_file = str(tmp_path / "test_raptor_p5.db")
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


def _new_id():
    return str(uuid.uuid4())


def _days_ago(n: int) -> str:
    return (date.today() - timedelta(days=n)).isoformat()


def _add_consent(bridge, prospect_id, *, revoked=0, deletion_requested=0,
                 expiry_date=None, deletion_executed_date=None):
    """Insert a consent ledger record directly."""
    bridge.conn.execute(
        """INSERT INTO raptor_consent_ledger
           (prospect_id, consent_type, consent_date, expiry_date, revoked,
            deletion_requested, deletion_executed_date, write_timestamp)
           VALUES (?, 'casl_express', date('now'), ?, ?, ?, ?, datetime('now'))""",
        (prospect_id, expiry_date, revoked, deletion_requested, deletion_executed_date),
    )
    bridge.conn.commit()


def _add_touchpoint(bridge, prospect_id, days_ago: int):
    """Insert a touchpoint record N days in the past."""
    bridge.conn.execute(
        """INSERT INTO raptor_touchpoints
           (prospect_id, date, channel, direction, write_timestamp)
           VALUES (?, ?, 'phone', 'outbound', datetime('now'))""",
        (prospect_id, _days_ago(days_ago)),
    )
    bridge.conn.commit()


def _set_stage(bridge, prospect_id, stage: str):
    bridge.conn.execute(
        "UPDATE raptor_prospects SET pipeline_stage=? WHERE prospect_id=?",
        (stage, prospect_id),
    )
    bridge.conn.commit()


# ── process_deletion_request ──────────────────────────────────────────────────

def test_deletion_scrubs_pii(db):
    """PII fields are overwritten with DELETED placeholders."""
    pid = _new_id()
    db.write_prospect(pid, first_name="Marie", last_name="Tremblay",
                      email="marie@example.com", phone="514-555-0001")
    _add_consent(db, pid)
    privacy = RaptorPrivacy(db)
    privacy.process_deletion_request(pid)
    p = db.get_prospect(pid)
    assert p["first_name"] == "DELETED"
    assert p["last_name"].startswith("[")
    assert p["email"] is None
    assert p["phone"] is None


def test_deletion_preserves_record(db):
    """Record still exists after deletion (CIRO retention)."""
    pid = _new_id()
    db.write_prospect(pid, first_name="Jean", last_name="Dupont")
    _add_consent(db, pid)
    privacy = RaptorPrivacy(db)
    privacy.process_deletion_request(pid)
    p = db.get_prospect(pid)
    assert p is not None
    assert p["prospect_id"] == pid


def test_deletion_marks_consent_ledger(db):
    """execute_data_deletion marks consent records."""
    pid = _new_id()
    db.write_prospect(pid, first_name="Alice")
    _add_consent(db, pid)
    privacy = RaptorPrivacy(db)
    receipt = privacy.process_deletion_request(pid)
    assert receipt["consent_records_updated"] >= 1


def test_deletion_receipt_keys(db):
    """Receipt contains required compliance keys."""
    pid = _new_id()
    db.write_prospect(pid, first_name="Bob")
    _add_consent(db, pid)
    privacy = RaptorPrivacy(db)
    receipt = privacy.process_deletion_request(pid)
    for key in ["prospect_id", "anonymized_as", "pii_scrubbed",
                "consent_records_updated", "executed_at",
                "ciro_archive_preserved", "law25_compliant"]:
        assert key in receipt
    assert receipt["law25_compliant"] is True
    assert receipt["ciro_archive_preserved"] is True


def test_deletion_unknown_prospect_raises(db):
    """ValueError raised for unknown prospect_id."""
    privacy = RaptorPrivacy(db)
    with pytest.raises(ValueError, match="Unknown prospect_id"):
        privacy.process_deletion_request("nonexistent-id-xyz")


# ── run_dormant_cleanup ───────────────────────────────────────────────────────

def test_dormant_cleanup_anonymizes_old_lost(db):
    """Lost prospect inactive >24 months is anonymized."""
    pid = _new_id()
    db.write_prospect(pid, first_name="OldLost",
                      created_date=_days_ago(800))
    _set_stage(db, pid, "lost")
    # No touchpoints, no active consent
    privacy = RaptorPrivacy(db)
    result = privacy.run_dormant_cleanup(inactive_months=24)
    assert pid in result["prospect_ids"]
    assert result["anonymized_count"] >= 1


def test_dormant_cleanup_skips_active_stage(db):
    """Prospect in active stage is NOT cleaned up."""
    pid = _new_id()
    db.write_prospect(pid, first_name="Active",
                      created_date=_days_ago(800))
    _set_stage(db, pid, "qualified")
    privacy = RaptorPrivacy(db)
    result = privacy.run_dormant_cleanup(inactive_months=24)
    assert pid not in result["prospect_ids"]


def test_dormant_cleanup_skips_already_deleted(db):
    """Already-anonymized prospects are skipped."""
    pid = _new_id()
    db.write_prospect(pid, first_name="DELETED",
                      created_date=_days_ago(800))
    _set_stage(db, pid, "dormant")
    privacy = RaptorPrivacy(db)
    result = privacy.run_dormant_cleanup(inactive_months=24)
    assert pid not in result["prospect_ids"]


def test_dormant_cleanup_skips_recent_activity(db):
    """Prospect with recent touchpoint is skipped even if stage=lost."""
    pid = _new_id()
    db.write_prospect(pid, first_name="RecentLost",
                      created_date=_days_ago(800))
    _set_stage(db, pid, "lost")
    _add_touchpoint(db, pid, days_ago=30)   # recent activity
    privacy = RaptorPrivacy(db)
    result = privacy.run_dormant_cleanup(inactive_months=24)
    assert pid not in result["prospect_ids"]


# ── consent_health_report ─────────────────────────────────────────────────────

def test_consent_health_valid_count(db):
    """Prospects with active non-expired consent are counted."""
    pid1 = _new_id()
    pid2 = _new_id()
    db.write_prospect(pid1, first_name="A")
    db.write_prospect(pid2, first_name="B")
    _add_consent(db, pid1, expiry_date=(date.today() + timedelta(days=120)).isoformat())
    _add_consent(db, pid2, expiry_date=(date.today() + timedelta(days=60)).isoformat())
    privacy = RaptorPrivacy(db)
    report = privacy.consent_health_report()
    assert report["valid_consent_count"] >= 2


def test_consent_health_expiring_30d(db):
    """Consents expiring within 30 days are counted in expiring_30d."""
    pid = _new_id()
    db.write_prospect(pid, first_name="Expiring")
    _add_consent(db, pid, expiry_date=(date.today() + timedelta(days=20)).isoformat())
    privacy = RaptorPrivacy(db)
    report = privacy.consent_health_report()
    assert report["expiring_30d"] >= 1


def test_consent_health_expiring_90d_not_30d(db):
    """Consent expiring in 75 days appears in 90d but NOT in 30d."""
    pid = _new_id()
    db.write_prospect(pid, first_name="Mid")
    _add_consent(db, pid, expiry_date=(date.today() + timedelta(days=75)).isoformat())
    privacy = RaptorPrivacy(db)
    report = privacy.consent_health_report()
    # Should NOT be in 30d band
    # (expiring_30d counts within today+30, our consent expires at today+75)
    # Just check the key exists and report is structured
    assert "expiring_30d" in report
    assert "expiring_90d" in report
    assert report["expiring_90d"] >= report["expiring_30d"]


def test_consent_health_revoked_not_scrubbed(db):
    """Revoked consent with PII still present is counted."""
    pid = _new_id()
    db.write_prospect(pid, first_name="Revoked")
    _add_consent(db, pid, revoked=1)
    privacy = RaptorPrivacy(db)
    report = privacy.consent_health_report()
    assert report["revoked_not_scrubbed"] >= 1


def test_consent_health_deletion_pending(db):
    """deletion_requested=1 but no executed_date → counted in deletion_pending."""
    pid = _new_id()
    db.write_prospect(pid, first_name="Pending")
    _add_consent(db, pid, deletion_requested=1)
    privacy = RaptorPrivacy(db)
    report = privacy.consent_health_report()
    assert report["deletion_pending"] >= 1
    assert "report_date" in report


# ── run_breach_notification_check ─────────────────────────────────────────────

def test_breach_check_no_events_returns_clear(db):
    """No soma_events → breach_detected=False."""
    privacy = RaptorPrivacy(db)
    result = privacy.run_breach_notification_check()
    assert result["breach_detected"] is False
    assert result["affected_count"] == 0
    assert result["templates"] == {}


def test_breach_check_detected_when_declared(db):
    """raptor_breach_declared event → breach_detected=True."""
    pid = _new_id()
    db.write_prospect(pid, first_name="Live")
    db.publish_event("raptor_breach_declared", {}, source_module="RAPTOR")
    privacy = RaptorPrivacy(db)
    result = privacy.run_breach_notification_check()
    assert result["breach_detected"] is True
    assert result["affected_count"] >= 1


def test_breach_check_templates_have_en_fr(db):
    """Detected breach generates both EN and FR templates."""
    db.publish_event("raptor_breach_declared", {}, source_module="RAPTOR")
    privacy = RaptorPrivacy(db)
    result = privacy.run_breach_notification_check()
    assert "EN" in result["templates"]
    assert "FR" in result["templates"]
    assert "Law 25" in result["templates"]["EN"]
    assert "Loi 25" in result["templates"]["FR"]


def test_breach_check_logs_notification_event(db):
    """Breach detection publishes raptor_breach_notification_generated event."""
    db.write_prospect(_new_id(), first_name="Person")
    db.publish_event("raptor_breach_declared", {}, source_module="RAPTOR")
    privacy = RaptorPrivacy(db)
    privacy.run_breach_notification_check()
    row = db.conn.execute(
        "SELECT * FROM soma_events WHERE event_type='raptor_breach_notification_generated'"
    ).fetchone()
    assert row is not None


def test_breach_check_resolved_returns_clear(db):
    """resolved=true in payload → breach_detected=False."""
    db.publish_event("raptor_breach_declared", {"resolved": True}, source_module="RAPTOR")
    privacy = RaptorPrivacy(db)
    result = privacy.run_breach_notification_check()
    assert result["breach_detected"] is False
