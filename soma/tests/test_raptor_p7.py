"""
Unit tests — RAPTOR Phase 7: 90-Day Onboarding Automation
Tests: initiate_onboarding, get_onboarding_status, check_milestone_due,
       handoff_to_cipher, bridge milestone methods.
20 tests total.
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
from soma.raptor_onboarding import RaptorOnboarding, MILESTONES

_MIG_DIR = _DABEIBA_ROOT / "shared" / "soma" / "migrations"


@pytest.fixture
def db(tmp_path):
    """Isolated test DB with RAPTOR + onboarding schema."""
    db_file = str(tmp_path / "test_raptor_p7.db")
    os.environ["SOMA_DB_PATH"] = db_file

    conn = sqlite3.connect(db_file)
    for mig_name in [
        "001_initial_schema.sql",
        "003_kb_rules.sql",
        "012_raptor_core.sql",
        "017_consent_idempotency.sql",
        "018_pipeline_trigger_touchpoint.sql",
        "019_soma_events_pubsub.sql",
        "028_raptor_onboarding.sql",
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


def _prospect_at_proposal(db) -> str:
    """Create a prospect and fast-track it to proposal_sent via direct SQL."""
    pid = _new_id()
    db.write_prospect(pid, first_name="Test", last_name="Client")
    # Add consent so 'contacted' gate passes
    db.conn.execute(
        """INSERT INTO raptor_consent_ledger
           (prospect_id, consent_type, consent_date, revoked, deletion_requested, write_timestamp)
           VALUES (?, 'casl_express', date('now'), 0, 0, datetime('now'))""",
        (pid,),
    )
    # Add compliance-approved touchpoint so 'proposal_sent' gate passes
    tp_id = db.conn.execute(
        """INSERT INTO raptor_touchpoints
           (prospect_id, date, channel, direction, compliance_approved, write_timestamp)
           VALUES (?, date('now'), 'phone', 'outbound', 1, datetime('now'))""",
        (pid,),
    ).lastrowid
    db.conn.commit()
    # Transition through stages
    db.write_pipeline_transition(pid, "contacted",     transitioned_by="test")
    db.write_pipeline_transition(pid, "meeting_set",   transitioned_by="test")
    db.write_pipeline_transition(pid, "proposal_sent", transitioned_by="test",
                                 trigger_touchpoint_id=tp_id)
    return pid


def _prospect_at_onboarding(db) -> str:
    """Create a prospect already in onboarding (all 4 milestones created)."""
    pid = _prospect_at_proposal(db)
    ob  = RaptorOnboarding(db)
    ob.initiate_onboarding(pid)
    return pid


# ── Bridge milestone methods ──────────────────────────────────────────────────

def test_write_and_get_milestone(db):
    pid = _new_id()
    db.write_prospect(pid, first_name="A")
    db.conn.executescript(
        "INSERT INTO raptor_onboarding_milestones "
        "(prospect_id, milestone, due_date, write_timestamp) "
        f"VALUES ('{pid}', 'day_7', '2026-05-12', datetime('now'))"
    )
    rows = db.get_onboarding_milestones(pid)
    assert len(rows) == 1
    assert rows[0]["milestone"] == "day_7"


def test_write_onboarding_milestone_upserts(db):
    """Calling write_onboarding_milestone twice on same key updates row."""
    pid = _new_id()
    db.write_prospect(pid, first_name="B")
    db.write_onboarding_milestone(pid, "day_7", "2026-05-12")
    db.write_onboarding_milestone(pid, "day_7", "2026-05-12",
                                  completed_date="2026-05-13")
    rows = db.get_onboarding_milestones(pid)
    assert len(rows) == 1
    assert rows[0]["completed_date"] == "2026-05-13"


def test_get_all_onboarding_milestones(db):
    pid1 = _new_id()
    pid2 = _new_id()
    db.write_prospect(pid1, first_name="X")
    db.write_prospect(pid2, first_name="Y")
    db.write_onboarding_milestone(pid1, "day_7",  "2026-05-12")
    db.write_onboarding_milestone(pid2, "day_30", "2026-06-04")
    all_ms = db.get_all_onboarding_milestones()
    pids = {r["prospect_id"] for r in all_ms}
    assert pid1 in pids and pid2 in pids


# ── initiate_onboarding ───────────────────────────────────────────────────────

def test_initiate_creates_four_milestones(db):
    pid = _prospect_at_proposal(db)
    ob  = RaptorOnboarding(db)
    ob.initiate_onboarding(pid)
    rows = db.get_onboarding_milestones(pid)
    assert len(rows) == 4
    keys = {r["milestone"] for r in rows}
    assert keys == set(MILESTONES.keys())


def test_initiate_advances_stage(db):
    pid = _prospect_at_proposal(db)
    RaptorOnboarding(db).initiate_onboarding(pid)
    p = db.get_prospect(pid)
    assert p["pipeline_stage"] == "onboarding"


def test_initiate_receipt_keys(db):
    pid = _prospect_at_proposal(db)
    receipt = RaptorOnboarding(db).initiate_onboarding(pid)
    assert "onboarding_start" in receipt
    assert "milestones" in receipt
    assert len(receipt["milestones"]) == 4


def test_initiate_wrong_stage_raises(db):
    pid = _new_id()
    db.write_prospect(pid, first_name="Early", pipeline_stage="identified")
    with pytest.raises(ValueError, match="must be in"):
        RaptorOnboarding(db).initiate_onboarding(pid)


def test_initiate_unknown_prospect_raises(db):
    with pytest.raises(ValueError, match="Unknown prospect_id"):
        RaptorOnboarding(db).initiate_onboarding("bad-id-xyz")


def test_initiate_logs_event(db):
    pid = _prospect_at_proposal(db)
    RaptorOnboarding(db).initiate_onboarding(pid)
    row = db.conn.execute(
        "SELECT * FROM soma_events WHERE event_type='raptor_onboarding_initiated'"
    ).fetchone()
    assert row is not None


# ── get_onboarding_status ─────────────────────────────────────────────────────

def test_get_status_includes_onboarding_prospects(db):
    pid = _prospect_at_onboarding(db)
    status = RaptorOnboarding(db).get_onboarding_status()
    pids = [s["prospect_id"] for s in status]
    assert pid in pids


def test_get_status_milestone_count(db):
    _prospect_at_onboarding(db)
    status = RaptorOnboarding(db).get_onboarding_status()
    assert status[0]["total_count"] == 4
    assert status[0]["completed_count"] == 0


def test_get_status_excludes_non_onboarding(db):
    pid = _new_id()
    db.write_prospect(pid, first_name="Active", pipeline_stage="identified")
    status = RaptorOnboarding(db).get_onboarding_status()
    pids = [s["prospect_id"] for s in status]
    assert pid not in pids


# ── check_milestone_due ───────────────────────────────────────────────────────

def test_overdue_milestone_detected(db):
    pid = _prospect_at_onboarding(db)
    # Backdate day_7 milestone to 10 days ago
    past = (date.today() - timedelta(days=10)).isoformat()
    db.conn.execute(
        "UPDATE raptor_onboarding_milestones SET due_date=? "
        "WHERE prospect_id=? AND milestone='day_7'",
        (past, pid),
    )
    db.conn.commit()
    overdue = RaptorOnboarding(db).check_milestone_due()
    assert any(o["milestone"] == "day_7" and o["prospect_id"] == pid
               for o in overdue)


def test_completed_milestone_not_overdue(db):
    pid = _prospect_at_onboarding(db)
    past = (date.today() - timedelta(days=10)).isoformat()
    db.conn.execute(
        "UPDATE raptor_onboarding_milestones SET due_date=?, completed_date=? "
        "WHERE prospect_id=? AND milestone='day_7'",
        (past, date.today().isoformat(), pid),
    )
    db.conn.commit()
    overdue = RaptorOnboarding(db).check_milestone_due()
    day7_overdue = [o for o in overdue
                    if o["prospect_id"] == pid and o["milestone"] == "day_7"]
    assert len(day7_overdue) == 0


def test_future_milestone_not_overdue(db):
    pid = _prospect_at_onboarding(db)
    # All milestones are future (set on initiation) — none should be overdue
    overdue = RaptorOnboarding(db).check_milestone_due()
    pid_overdue = [o for o in overdue if o["prospect_id"] == pid]
    assert len(pid_overdue) == 0


# ── handoff_to_cipher ─────────────────────────────────────────────────────────

def test_handoff_creates_cipher_profile(db):
    pid = _prospect_at_onboarding(db)
    receipt = RaptorOnboarding(db).handoff_to_cipher(pid)
    assert receipt["cipher_profile_created"] is True
    assert "client_alias" in receipt


def test_handoff_advances_to_active(db):
    pid = _prospect_at_onboarding(db)
    RaptorOnboarding(db).handoff_to_cipher(pid)
    p = db.get_prospect(pid)
    assert p["pipeline_stage"] == "active"


def test_handoff_logs_event(db):
    pid = _prospect_at_onboarding(db)
    RaptorOnboarding(db).handoff_to_cipher(pid)
    row = db.conn.execute(
        "SELECT * FROM soma_events WHERE event_type='raptor_cipher_handoff'"
    ).fetchone()
    assert row is not None


def test_handoff_wrong_stage_raises(db):
    pid = _new_id()
    db.write_prospect(pid, first_name="Wrong")
    with pytest.raises(ValueError, match="must be 'onboarding'"):
        RaptorOnboarding(db).handoff_to_cipher(pid)


def test_handoff_incomplete_milestones_in_receipt(db):
    """Handoff succeeds even with incomplete milestones; warns in receipt."""
    pid = _prospect_at_onboarding(db)
    receipt = RaptorOnboarding(db).handoff_to_cipher(pid)
    # All 4 milestones are pending (never marked complete)
    assert len(receipt["incomplete_milestones"]) == 4
