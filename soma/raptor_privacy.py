"""
RAPTOR — Privacy & Data Sanitization Engine (Phase 5)

Implements Law 25 (Quebec) right-to-be-forgotten, dormant prospect cleanup,
consent health reporting, and CAI breach notification templates.

Key compliance rules:
  Law 25 — right to erasure: PII scrubbed within 30 days of written request
  CIRO Rule 3804 — 7-year retention: anonymized records KEPT in archive
  CAI notification — breach must be reported to Commission d'accès à l'information
  CASL — implied consent expires after 2 years of inactivity

Usage:
    from soma.soma_bridge import SomaBridge
    from soma.raptor_privacy import RaptorPrivacy

    with SomaBridge() as bridge:
        privacy = RaptorPrivacy(bridge)
        receipt = privacy.process_deletion_request(prospect_id)
        report  = privacy.consent_health_report()
        cleanup = privacy.run_dormant_cleanup(inactive_months=24)
        breach  = privacy.run_breach_notification_check()
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta, timezone

_ANONYMIZE_FIRST_NAME = "DELETED"
_DORMANT_STAGES       = frozenset({"lost", "dormant"})


def _pii_suffix(prospect_id: str) -> str:
    """Short deterministic hash suffix for anonymized placeholders."""
    return hashlib.sha256(prospect_id.encode()).hexdigest()[:8].upper()


class RaptorPrivacy:
    """Privacy automation for RAPTOR — Law 25, CASL, CIRO compliance.

    All PII scrubbing preserves the prospect record structure (for CIRO 7-year
    archive compliance) but replaces identifying fields with DELETED placeholders.
    """

    def __init__(self, bridge):
        self.bridge = bridge

    # ── Right to be forgotten (Law 25) ───────────────────────────────────────

    def process_deletion_request(self, prospect_id: str) -> dict:
        """Scrub PII from a prospect record per Law 25 right to erasure.

        Steps:
          1. Validate prospect exists.
          2. Overwrite PII fields with anonymized placeholders.
          3. Mark consent ledger records as deletion executed.
          4. Return a confirmation receipt.

        The anonymized record is retained (not deleted) to satisfy CIRO
        Rule 3804 7-year record-keeping requirements.
        """
        p = self.bridge.get_prospect(prospect_id)
        if not p:
            raise ValueError(
                f"[RAPTOR Privacy] Unknown prospect_id: {prospect_id}. "
                "Cannot process deletion request."
            )

        suffix = _pii_suffix(prospect_id)
        scrubbed_fields = [
            "first_name", "last_name", "display_name",
            "email", "phone", "linkedin_url", "notes",
        ]
        self.bridge.update_prospect(
            prospect_id,
            first_name=_ANONYMIZE_FIRST_NAME,
            last_name=f"[{suffix}]",
            display_name=f"DELETED_{suffix}",
            email=None,
            phone=None,
            linkedin_url=None,
            notes=None,
        )

        records_updated = self.bridge.execute_data_deletion(prospect_id)

        return {
            "prospect_id":             prospect_id,
            "anonymized_as":           f"DELETED_{suffix}",
            "pii_scrubbed":            scrubbed_fields,
            "consent_records_updated": records_updated,
            "executed_at":             date.today().isoformat(),
            "ciro_archive_preserved":  True,
            "law25_compliant":         True,
        }

    # ── Dormant prospect cleanup ──────────────────────────────────────────────

    def run_dormant_cleanup(self, inactive_months: int = 24) -> dict:
        """Anonymize prospects that are dormant/lost and inactive for N months.

        Eligible criteria (ALL must be true):
          - pipeline_stage in ('lost', 'dormant')
          - Not already anonymized (first_name != 'DELETED')
          - No active non-expired consent
          - Last activity (max touchpoint date or created_date) < cutoff

        Does NOT permanently delete records — anonymizes in place for CIRO retention.
        """
        cutoff = (date.today() - timedelta(days=inactive_months * 30)).isoformat()
        affected: list[str] = []
        skipped_active_consent: int = 0

        for p in self.bridge.get_all_prospects():
            if p["pipeline_stage"] not in _DORMANT_STAGES:
                continue
            if p.get("first_name") == _ANONYMIZE_FIRST_NAME:
                continue   # already anonymized

            # Check active consent
            consent_status = self.bridge.get_consent_status(p["prospect_id"])
            if consent_status.get("has_active_consent"):
                skipped_active_consent += 1
                continue

            # Determine last activity date
            tps = self.bridge.get_touchpoints(p["prospect_id"])
            if tps:
                last_activity = max(t["date"][:10] for t in tps)
            else:
                last_activity = (p.get("created_date") or p.get("updated_date") or "")[:10]

            if last_activity and last_activity < cutoff:
                self.process_deletion_request(p["prospect_id"])
                affected.append(p["prospect_id"])

        return {
            "anonymized_count":          len(affected),
            "prospect_ids":              affected,
            "cutoff_date":               cutoff,
            "inactive_months":           inactive_months,
            "skipped_active_consent":    skipped_active_consent,
        }

    # ── Consent health report ─────────────────────────────────────────────────

    def consent_health_report(self) -> dict:
        """Snapshot of consent coverage across the RAPTOR pipeline.

        Returns:
            valid_consent_count      — distinct prospects with any active non-expired consent
            expiring_30d             — consents expiring within 30 days
            expiring_60d             — consents expiring within 60 days
            expiring_90d             — consents expiring within 90 days
            revoked_not_scrubbed     — prospects with revoked consent but PII still present
            deletion_pending         — deletion_requested=1 but deletion_executed_date IS NULL
            report_date              — ISO date of report
        """
        conn  = self.bridge.conn
        today = date.today()

        def _threshold(days: int) -> str:
            return (today + timedelta(days=days)).isoformat()

        today_str = today.isoformat()

        valid = conn.execute(
            """SELECT COUNT(DISTINCT prospect_id) FROM raptor_consent_ledger
               WHERE revoked = 0 AND deletion_requested = 0
                 AND (expiry_date IS NULL OR expiry_date > ?)""",
            (today_str,),
        ).fetchone()[0]

        def _expiring_count(days: int) -> int:
            thr = _threshold(days)
            return conn.execute(
                """SELECT COUNT(*) FROM raptor_consent_ledger
                   WHERE revoked = 0 AND deletion_requested = 0
                     AND expiry_date IS NOT NULL
                     AND expiry_date > ? AND expiry_date <= ?""",
                (today_str, thr),
            ).fetchone()[0]

        revoked_not_scrubbed = conn.execute(
            """SELECT COUNT(DISTINCT cl.prospect_id)
               FROM raptor_consent_ledger cl
               JOIN raptor_prospects p ON cl.prospect_id = p.prospect_id
               WHERE cl.revoked = 1
                 AND (p.first_name IS NULL OR p.first_name != ?)""",
            (_ANONYMIZE_FIRST_NAME,),
        ).fetchone()[0]

        deletion_pending = conn.execute(
            """SELECT COUNT(DISTINCT prospect_id) FROM raptor_consent_ledger
               WHERE deletion_requested = 1 AND deletion_executed_date IS NULL""",
        ).fetchone()[0]

        return {
            "valid_consent_count":  valid,
            "expiring_30d":         _expiring_count(30),
            "expiring_60d":         _expiring_count(60),
            "expiring_90d":         _expiring_count(90),
            "revoked_not_scrubbed": revoked_not_scrubbed,
            "deletion_pending":     deletion_pending,
            "report_date":          today_str,
        }

    # ── Breach notification ───────────────────────────────────────────────────

    def run_breach_notification_check(self) -> dict:
        """Check for unresolved breach declarations and generate notification templates.

        A breach is declared by publishing a soma_event with:
          event_type = 'raptor_breach_declared'

        If an unresolved declaration is found:
          1. Counts affected prospects (non-anonymized PII present)
          2. Generates EN/FR client notification templates
          3. Logs a 'raptor_breach_notification_generated' response event
          4. Returns {breach_detected=True, affected_count, templates}

        If no declaration found, or all are resolved:
          Returns {breach_detected=False, affected_count=0, templates={}}
        """
        conn = self.bridge.conn

        rows = conn.execute(
            "SELECT * FROM soma_events WHERE event_type = 'raptor_breach_declared' "
            "ORDER BY event_id DESC LIMIT 1"
        ).fetchall()

        if not rows:
            return {"breach_detected": False, "affected_count": 0, "templates": {}}

        breach_event = dict(rows[0])
        payload = json.loads(breach_event.get("payload_json") or "{}")

        if payload.get("resolved"):
            return {"breach_detected": False, "affected_count": 0, "templates": {}}

        # Count non-anonymized prospects
        affected = conn.execute(
            "SELECT COUNT(*) AS n FROM raptor_prospects WHERE first_name != ?",
            (_ANONYMIZE_FIRST_NAME,),
        ).fetchone()["n"]

        breach_date = date.today().isoformat()
        templates = {
            "EN": (
                f"NOTICE OF PRIVACY INCIDENT — {breach_date}\n\n"
                "We are writing to inform you that we have identified a privacy incident "
                "that may have involved your personal information. We take the security "
                "of your information seriously and have immediately taken steps to contain "
                "the incident.\n\n"
                "If you have questions, please contact us at [ADVISOR_EMAIL].\n\n"
                "We have reported this incident to the Commission d'accès à l'information "
                "du Québec (CAI) as required under Law 25 (Act respecting the protection "
                "of personal information in the private sector)."
            ),
            "FR": (
                f"AVIS D'INCIDENT DE CONFIDENTIALITÉ — {breach_date}\n\n"
                "Nous vous écrivons pour vous informer que nous avons identifié un incident "
                "de confidentialité qui pourrait avoir concerné vos renseignements personnels. "
                "Nous prenons la sécurité de vos renseignements très au sérieux et avons "
                "immédiatement pris des mesures pour contenir l'incident.\n\n"
                "Pour toute question, veuillez communiquer avec nous à [COURRIEL_CONSEILLER].\n\n"
                "Nous avons signalé cet incident à la Commission d'accès à l'information "
                "du Québec (CAI) conformément à la Loi 25 (Loi sur la protection des "
                "renseignements personnels dans le secteur privé)."
            ),
        }

        # Log the notification generation event
        self.bridge.publish_event(
            "raptor_breach_notification_generated",
            {
                "breach_event_id": breach_event["event_id"],
                "affected_count":  affected,
                "generated_at":    breach_date,
            },
            source_module="RAPTOR",
        )

        return {
            "breach_detected":  True,
            "affected_count":   affected,
            "templates":        templates,
            "breach_event_id":  breach_event["event_id"],
        }
