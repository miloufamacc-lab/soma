"""
Unit tests — RAPTOR Phase 2: Compliance Layer
Tests: prohibited term scan, validate_outreach, compliant footer,
       referral compliance, shadow table triggers, rule seeding.
24 tests total.
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
from soma.raptor_compliance import RaptorCompliance, seed_compliance_rules

_MIG_DIR = _DABEIBA_ROOT / "shared" / "soma" / "migrations"


@pytest.fixture
def db(tmp_path):
    """Isolated test DB with full RAPTOR schema including shadow table."""
    db_file = str(tmp_path / "test_raptor_p2.db")
    os.environ["SOMA_DB_PATH"] = db_file

    conn = sqlite3.connect(db_file)
    for mig_name in [
        "001_initial_schema.sql",
        "003_kb_rules.sql",
        "012_raptor_core.sql",
        "017_consent_idempotency.sql",
        "018_pipeline_trigger_touchpoint.sql",
        "026_raptor_touchpoints_archive.sql",
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


def _prospect_with_consent(db, consent_type="casl_express") -> str:
    pid = _new_id()
    db.write_prospect(pid, first_name="Test")
    db.write_consent(pid, consent_type, _today())
    return pid


_CLEAN_MESSAGE = (
    "Hello, I wanted to introduce myself as your Investment Advisor at Example Firm. "
    "Our approach focuses on long-term wealth preservation with a diversified portfolio. "
    "Past performance does not guarantee future results. "
    "To unsubscribe, reply UNSUBSCRIBE or contact us at advisor@example.com. "
    "T: 514-555-0100 | E: advisor@example.com"
)


# ── Prohibited term scan ──────────────────────────────────────────────────────

def test_scan_guaranteed_returns(db):
    compliance = RaptorCompliance(db)
    hits = compliance.scan_prohibited_terms("We offer guaranteed returns of 8%.")
    assert any(h["category"] == "PERFORMANCE_GUARANTEE" for h in hits)


def test_scan_risk_free(db):
    compliance = RaptorCompliance(db)
    hits = compliance.scan_prohibited_terms("This is a risk-free investment.")
    assert any(h["category"] == "RISK_MISREPRESENTATION" for h in hits)


def test_scan_no1_claim(db):
    compliance = RaptorCompliance(db)
    hits = compliance.scan_prohibited_terms("We are the No. 1 advisor in Montreal.")
    assert any(h["category"] == "COMPARATIVE_CLAIM" for h in hits)


def test_scan_amf_approved(db):
    compliance = RaptorCompliance(db)
    hits = compliance.scan_prohibited_terms("This product is approved by AMF.")
    assert any(h["category"] == "MISLEADING_REGISTRATION" for h in hits)


def test_scan_forward_looking(db):
    compliance = RaptorCompliance(db)
    hits = compliance.scan_prohibited_terms("Your investment will definitely double in 3 years.")
    assert any(h["category"] == "FORWARD_LOOKING_CLAIM" for h in hits)


def test_scan_prohibited_title(db):
    compliance = RaptorCompliance(db)
    hits = compliance.scan_prohibited_terms("From: John Smith, Advisor Emeritus")
    assert any(h["category"] == "PROHIBITED_TITLE" for h in hits)


def test_scan_clean_text_no_hits(db):
    """A well-written message returns zero prohibited term hits."""
    compliance = RaptorCompliance(db)
    hits = compliance.scan_prohibited_terms(_CLEAN_MESSAGE)
    block_hits = [h for h in hits if h["category"] not in {"CAUTION_TITLE"}]
    assert len(block_hits) == 0


def test_scan_french_sans_risque(db):
    compliance = RaptorCompliance(db)
    hits = compliance.scan_prohibited_terms("Ce placement est sans risque et garanti.")
    categories = {h["category"] for h in hits}
    assert "RISK_MISREPRESENTATION" in categories
    assert "PERFORMANCE_GUARANTEE" in categories


# ── validate_outreach ─────────────────────────────────────────────────────────

def test_validate_no_consent_blocked(db):
    pid = _new_id()
    db.write_prospect(pid)
    result = RaptorCompliance(db).validate_outreach(pid, _CLEAN_MESSAGE)
    assert result["approved"] is False
    codes = [v["code"] for v in result["violations"]]
    assert "CASL_NO_CONSENT" in codes


def test_validate_prohibited_term_blocked(db):
    pid = _prospect_with_consent(db)
    msg = (
        "We offer guaranteed returns! "
        "To unsubscribe reply UNSUBSCRIBE. "
        "E: advisor@example.com"
    )
    result = RaptorCompliance(db).validate_outreach(pid, msg)
    assert result["approved"] is False
    codes = [v["code"] for v in result["violations"]]
    assert "PROHIBITED_TERM" in codes


def test_validate_missing_unsubscribe_blocked(db):
    pid = _prospect_with_consent(db)
    msg = "Hello, I'm your Investment Advisor. Call me at 514-555-0100."
    result = RaptorCompliance(db).validate_outreach(pid, msg)
    assert result["approved"] is False
    codes = [v["code"] for v in result["violations"]]
    assert "MISSING_UNSUBSCRIBE" in codes


def test_validate_clean_message_approved(db):
    pid = _prospect_with_consent(db)
    result = RaptorCompliance(db).validate_outreach(pid, _CLEAN_MESSAGE)
    block_violations = [v for v in result["violations"] if v["severity"] == "BLOCK"]
    assert len(block_violations) == 0
    assert result["approved"] is True


def test_validate_warn_does_not_block(db):
    """WARN-severity violations (e.g. CAUTION_TITLE) don't set approved=False."""
    pid = _prospect_with_consent(db)
    msg = (
        "I am your Financial Advisor at Example Firm. "  # CAUTION_TITLE = WARN
        "To unsubscribe reply UNSUBSCRIBE. "
        "E: advisor@example.com"
    )
    result = RaptorCompliance(db).validate_outreach(pid, msg)
    # May have WARN violations, but should still be approved
    block = [v for v in result["violations"] if v["severity"] == "BLOCK"]
    assert len(block) == 0
    assert result["approved"] is True


def test_validate_returns_suggestions(db):
    pid = _new_id()
    db.write_prospect(pid)
    result = RaptorCompliance(db).validate_outreach(pid, "Buy now!")
    assert len(result["suggestions"]) > 0


# ── Compliant footer ──────────────────────────────────────────────────────────

def test_footer_en_has_required_fields(db):
    compliance = RaptorCompliance(db)
    footer = compliance.generate_compliant_footer(
        language="EN",
        first_name="Marie", last_name="Tremblay",
        title="Investment Advisor", firm_name="Example Inc.",
        amf_number="12345678", phone="514-555-0100",
        email="m.tremblay@example.com", privacy_url="https://example.com/privacy",
        address="1000 De La Gauchetière, Montréal, QC",
    )
    assert "12345678" in footer               # AMF number
    assert "unsubscribe" in footer.lower()    # unsubscribe mechanism
    assert "Law 25" in footer                 # privacy notice
    assert "m.tremblay@example.com" in footer # email present


def test_footer_fr_has_required_fields(db):
    compliance = RaptorCompliance(db)
    footer = compliance.generate_compliant_footer(
        language="FR",
        first_name="Marie", last_name="Tremblay",
        title="Conseillère en investissement", firm_name="Exemple inc.",
        amf_number="12345678", phone="514-555-0100",
        email="m.tremblay@exemple.com", privacy_url="https://exemple.com/confidentialite",
        address="1000 De La Gauchetière, Montréal, QC",
    )
    assert "12345678" in footer
    assert "désabonn" in footer.lower()       # French unsubscribe
    assert "Loi 25" in footer                 # FR privacy notice


# ── Referral compliance ───────────────────────────────────────────────────────

def test_referral_compliance_no_referrals(db):
    pid = _new_id()
    db.write_prospect(pid)
    result = RaptorCompliance(db).check_referral_compliance(pid)
    assert result["compliant"] is True
    assert result["missing"] == []


def test_referral_compliance_unsigned_agreement(db):
    pid, coi_id = _new_id(), _new_id()
    db.write_prospect(pid)
    db.write_coi(coi_id, "Unsigned COI", referral_agreement_signed=False)
    db.write_referral(coi_id, pid, _today())
    result = RaptorCompliance(db).check_referral_compliance(pid)
    assert result["compliant"] is False
    checks = [m["check"] for m in result["missing"]]
    assert "REFERRAL_AGREEMENT_UNSIGNED" in checks


def test_referral_compliance_disclosure_not_delivered(db):
    pid, coi_id = _new_id(), _new_id()
    db.write_prospect(pid)
    db.write_coi(coi_id, "Signed COI", referral_agreement_signed=True)
    db.write_referral(coi_id, pid, _today(), disclosure_delivered=False)
    result = RaptorCompliance(db).check_referral_compliance(pid)
    assert result["compliant"] is False
    checks = [m["check"] for m in result["missing"]]
    assert "DISCLOSURE_NOT_DELIVERED" in checks


def test_referral_compliance_fully_compliant(db):
    pid, coi_id = _new_id(), _new_id()
    db.write_prospect(pid)
    db.write_coi(coi_id, "Good COI", referral_agreement_signed=True)
    db.write_referral(coi_id, pid, _today(), disclosure_delivered=True)
    result = RaptorCompliance(db).check_referral_compliance(pid)
    assert result["compliant"] is True
    assert result["missing"] == []


# ── Shadow table (CIRO 7-year retention) ─────────────────────────────────────

def test_shadow_insert_trigger(db):
    """Writing a touchpoint creates an archive entry with operation=INSERT."""
    pid = _new_id()
    db.write_prospect(pid)
    db.write_touchpoint(pid, _today(), "email", "outbound", subject="Hello")
    count = db.conn.execute(
        "SELECT COUNT(*) FROM raptor_touchpoints_archive WHERE operation = 'INSERT'"
    ).fetchone()[0]
    assert count == 1


def test_shadow_delete_trigger(db):
    """Deleting a touchpoint creates an archive entry with operation=DELETE."""
    pid = _new_id()
    db.write_prospect(pid)
    tp_id = db.write_touchpoint(pid, _today(), "phone", "outbound")
    db.conn.execute(
        "DELETE FROM raptor_touchpoints WHERE touchpoint_id = ?", (tp_id,)
    )
    db.conn.commit()
    count = db.conn.execute(
        "SELECT COUNT(*) FROM raptor_touchpoints_archive WHERE operation = 'DELETE'"
    ).fetchone()[0]
    assert count == 1


def test_shadow_table_update_blocked(db):
    """UPDATE on archive is rejected (CIRO immutability)."""
    pid = _new_id()
    db.write_prospect(pid)
    db.write_touchpoint(pid, _today(), "email", "outbound")
    with pytest.raises((sqlite3.OperationalError, Exception), match="immutable"):
        db.conn.execute(
            "UPDATE raptor_touchpoints_archive SET subject = 'tampered' WHERE archive_id = 1"
        )
        db.conn.commit()


def test_shadow_table_delete_blocked(db):
    """DELETE on archive is rejected (CIRO immutability)."""
    pid = _new_id()
    db.write_prospect(pid)
    db.write_touchpoint(pid, _today(), "email", "outbound")
    with pytest.raises((sqlite3.OperationalError, Exception), match="immutable"):
        db.conn.execute("DELETE FROM raptor_touchpoints_archive WHERE archive_id = 1")
        db.conn.commit()


# ── Rule seeding ──────────────────────────────────────────────────────────────

def test_seed_compliance_rules_inserts(db):
    inserted = seed_compliance_rules(db)
    assert inserted is True
    row = db.conn.execute(
        "SELECT rule_data FROM kb_rules WHERE rule_id = 'RAPTOR_PROHIBITED_TERMS_V1'"
    ).fetchone()
    assert row is not None
    data = json.loads(row["rule_data"])
    assert len(data["patterns"]) > 10     # non-trivial rule set


def test_seed_compliance_rules_idempotent(db):
    seed_compliance_rules(db)
    assert seed_compliance_rules(db) is False
