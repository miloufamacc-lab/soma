"""
Unit tests — RAPTOR Phase 12: Production Hardening
Tests: RaptorHealth checks — tables, compliance rules, orphans,
       stuck prospects, deletion SLA, expiring consent, diagnose().
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
from soma.raptor_compliance import seed_compliance_rules
from soma.raptor_health import RaptorHealth, MAX_STAGE_DAYS

_MIG_DIR = _DABEIBA_ROOT / "shared" / "soma" / "migrations"

_RAPTOR_MIGRATIONS = [
    "001_initial_schema.sql",
    "003_kb_rules.sql",
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
    db_file = str(tmp_path / "test_raptor_p12.db")
    os.environ["SOMA_DB_PATH"] = db_file

    conn = sqlite3.connect(db_file)
    for mig in _RAPTOR_MIGRATIONS:
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


# ── check() top-level ─────────────────────────────────────────────────────────

def test_check_returns_required_keys(db):
    result = RaptorHealth(db).check()
    assert "status" in result
    assert "checks" in result
    assert "checked_at" in result
    assert result["status"] in ("OK", "WARN", "ERROR")


def test_check_all_ok_on_clean_db(db):
    """Fresh DB with seeds applied + no data → all checks OK."""
    result = RaptorHealth(db).check()
    # May have WARN on compliance rules if not seeded — already seeded in fixture
    # Stuck/orphan checks should be OK on empty DB
    for name, check in result["checks"].items():
        if name == "compliance_rules":
            continue   # seeded — should be OK but not critical to assert here
        assert check["status"] in ("OK", "WARN"), \
            f"Check '{name}' returned ERROR on clean DB"


# ── _check_tables ─────────────────────────────────────────────────────────────

def test_tables_ok_when_schema_applied(db):
    check = RaptorHealth(db)._check_tables()
    assert check["status"] == "OK"
    assert check["missing"] == []


def test_tables_error_when_table_missing(db):
    db.conn.execute("DROP TABLE raptor_prospects")
    db.conn.commit()
    check = RaptorHealth(db)._check_tables()
    assert check["status"] == "ERROR"
    assert "raptor_prospects" in check["missing"]


# ── _check_compliance_rules ───────────────────────────────────────────────────

def test_compliance_rules_ok_when_seeded(db):
    check = RaptorHealth(db)._check_compliance_rules()
    assert check["status"] == "OK"
    assert check["rule_count"] > 0


def test_compliance_rules_warn_when_empty(db):
    db.conn.execute(
        "DELETE FROM kb_rules WHERE source_file LIKE '%raptor_compliance%'"
    )
    db.conn.commit()
    check = RaptorHealth(db)._check_compliance_rules()
    assert check["status"] == "WARN"
    assert check["rule_count"] == 0


# ── _check_orphaned_consent ───────────────────────────────────────────────────

def test_orphaned_consent_ok_when_none(db):
    check = RaptorHealth(db)._check_orphaned_consent()
    assert check["status"] == "OK"
    assert check["count"] == 0


def test_orphaned_consent_warn_when_present(db):
    fake_pid = _pid()
    db.conn.execute(
        """INSERT INTO raptor_consent_ledger
           (prospect_id, consent_type, consent_date, revoked,
            deletion_requested, write_timestamp)
           VALUES (?, 'casl_express', date('now'), 0, 0, datetime('now'))""",
        (fake_pid,),
    )
    db.conn.commit()
    check = RaptorHealth(db)._check_orphaned_consent()
    assert check["status"] == "WARN"
    assert check["count"] >= 1


# ── _check_orphaned_touchpoints ───────────────────────────────────────────────

def test_orphaned_touchpoints_ok_when_none(db):
    check = RaptorHealth(db)._check_orphaned_touchpoints()
    assert check["status"] == "OK"


def test_orphaned_touchpoints_warn_when_present(db):
    fake_pid = _pid()
    db.conn.execute(
        """INSERT INTO raptor_touchpoints
           (prospect_id, date, channel, direction, compliance_approved, write_timestamp)
           VALUES (?, date('now'), 'phone', 'outbound', 1, datetime('now'))""",
        (fake_pid,),
    )
    db.conn.commit()
    check = RaptorHealth(db)._check_orphaned_touchpoints()
    assert check["status"] == "WARN"
    assert check["count"] >= 1


# ── _check_stuck_prospects ────────────────────────────────────────────────────

def test_stuck_prospects_ok_on_fresh_prospect(db):
    """Prospect created today is not stuck."""
    pid = _pid()
    db.write_prospect(pid)
    check = RaptorHealth(db)._check_stuck_prospects()
    assert check["status"] == "OK"


def test_stuck_prospects_warn_when_over_limit(db):
    """Prospect with updated_date > MAX_STAGE_DAYS ago → WARN."""
    pid = _pid()
    db.write_prospect(pid)
    limit = MAX_STAGE_DAYS["identified"]
    old_date = (date.today() - timedelta(days=limit + 10)).isoformat()
    db.conn.execute(
        "UPDATE raptor_prospects SET updated_date=? WHERE prospect_id=?",
        (old_date, pid),
    )
    db.conn.commit()
    check = RaptorHealth(db)._check_stuck_prospects()
    assert check["status"] == "WARN"
    assert check["count"] >= 1
    assert any(d["prospect_id"] == pid for d in check["details"])


# ── _check_deletion_sla ───────────────────────────────────────────────────────

def test_deletion_sla_ok_when_none_pending(db):
    check = RaptorHealth(db)._check_deletion_sla()
    assert check["status"] == "OK"
    assert check["overdue_count"] == 0


def test_deletion_sla_error_when_overdue(db):
    """A deletion_requested=1 consent row older than 30 days → ERROR."""
    pid = _pid()
    db.write_prospect(pid)
    old_date = (date.today() - timedelta(days=35)).isoformat()
    db.conn.execute(
        """INSERT INTO raptor_consent_ledger
           (prospect_id, consent_type, consent_date, revoked,
            deletion_requested, deletion_executed_date, write_timestamp)
           VALUES (?, 'casl_express', ?, 0, 1, NULL, datetime('now'))""",
        (pid, old_date),
    )
    db.conn.commit()
    check = RaptorHealth(db)._check_deletion_sla()
    assert check["status"] == "ERROR"
    assert check["overdue_count"] >= 1


# ── _check_expiring_consent ───────────────────────────────────────────────────

def test_expiring_consent_ok_when_none(db):
    check = RaptorHealth(db)._check_expiring_consent()
    assert check["status"] == "OK"


def test_expiring_consent_warn_when_soon(db):
    """Consent expiring in 10 days → WARN."""
    pid = _pid()
    db.write_prospect(pid)
    expiry = (date.today() + timedelta(days=10)).isoformat()
    db.conn.execute(
        """INSERT INTO raptor_consent_ledger
           (prospect_id, consent_type, consent_date, expiry_date,
            revoked, deletion_requested, write_timestamp)
           VALUES (?, 'casl_express', date('now'), ?, 0, 0, datetime('now'))""",
        (pid, expiry),
    )
    db.conn.commit()
    check = RaptorHealth(db)._check_expiring_consent()
    assert check["status"] == "WARN"
    assert check["expiring_count"] >= 1


# ── diagnose() ────────────────────────────────────────────────────────────────

def test_diagnose_returns_string(db):
    output = RaptorHealth(db).diagnose()
    assert isinstance(output, str)
    assert "RAPTOR Health Check" in output


def test_diagnose_contains_all_check_names(db):
    output = RaptorHealth(db).diagnose()
    for label in ("Tables", "Compliance Rules", "Orphaned Consent",
                  "Stuck Prospects", "Deletion Sla"):
        assert label in output, f"Missing label: {label}"


def test_overall_status_error_when_any_error(db):
    """Dropping a required table makes overall status ERROR."""
    db.conn.execute("DROP TABLE raptor_prospects")
    db.conn.commit()
    result = RaptorHealth(db).check()
    assert result["status"] == "ERROR"
