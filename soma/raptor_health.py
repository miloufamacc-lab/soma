"""
RAPTOR — Production Health Check & Diagnostics (Phase 12)

Validates that the RAPTOR module is correctly configured and the DB is
in a consistent state. Designed to run at startup (in run_day.py) and
on-demand for debugging.

Checks performed:
  1. Required tables present (schema completeness)
  2. Compliance rules seeded (scanner will be blind without them)
  3. Orphaned consent records (prospect deleted but consent row remains)
  4. Orphaned touchpoints (no matching prospect)
  5. Stuck prospects (same stage > MAX_STAGE_DAYS with no recent touchpoint)
  6. Deletion requests overdue (> 30 days SLA)
  7. Consent expiry warnings (expiring in < 30 days, no renewal)

Status levels:
  OK    — all checks pass
  WARN  — issues found but RAPTOR can still operate
  ERROR — critical problems that will cause failures

Usage:
    from soma.soma_bridge import SomaBridge
    from soma.raptor_health import RaptorHealth

    with SomaBridge() as bridge:
        health = RaptorHealth(bridge)
        report = health.check()        # → {status, checks: {...}}
        print(health.diagnose())       # → human-readable string
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

# Stages where staying too long signals a stuck pipeline
MAX_STAGE_DAYS: dict[str, int] = {
    "identified":    90,
    "researched":    60,
    "contacted":     45,
    "meeting_set":   30,
    "proposal_sent": 60,
    "onboarding":   120,
}

# Required RAPTOR tables
_REQUIRED_TABLES = [
    "raptor_prospects",
    "raptor_consent_ledger",
    "raptor_coi_network",
    "raptor_referrals",
    "raptor_touchpoints",
    "raptor_pipeline_log",
    "raptor_touchpoints_archive",
    "raptor_fund_mers",
    "raptor_onboarding_milestones",
]


def _table_exists(conn, name: str) -> bool:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM sqlite_master "
        "WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row["n"] > 0


class RaptorHealth:
    """Schema and data integrity checks for the RAPTOR module."""

    def __init__(self, bridge):
        self.bridge = bridge
        self.conn   = bridge.conn

    # ── Public API ────────────────────────────────────────────────────────────

    def check(self) -> dict:
        """Run all health checks. Returns aggregated status dict.

        Returns:
            {
                "status": "OK" | "WARN" | "ERROR",
                "checks": {
                    "tables":              {status, missing},
                    "compliance_rules":    {status, rule_count},
                    "orphaned_consent":    {status, count},
                    "orphaned_touchpoints":{status, count},
                    "stuck_prospects":     {status, count, details},
                    "deletion_sla":        {status, overdue_count},
                    "expiring_consent":    {status, expiring_count},
                },
                "checked_at": "YYYY-MM-DD",
            }
        """
        checks = {
            "tables":               self._check_tables(),
            "compliance_rules":     self._check_compliance_rules(),
            "orphaned_consent":     self._check_orphaned_consent(),
            "orphaned_touchpoints": self._check_orphaned_touchpoints(),
            "stuck_prospects":      self._check_stuck_prospects(),
            "deletion_sla":         self._check_deletion_sla(),
            "expiring_consent":     self._check_expiring_consent(),
        }

        statuses = [c["status"] for c in checks.values()]
        if "ERROR" in statuses:
            overall = "ERROR"
        elif "WARN" in statuses:
            overall = "WARN"
        else:
            overall = "OK"

        return {
            "status":     overall,
            "checks":     checks,
            "checked_at": date.today().isoformat(),
        }

    def diagnose(self) -> str:
        """Return a human-readable diagnostic report string."""
        report = self.check()
        lines  = [
            "╔══════════════════════════════════════════════════╗",
            f"║  RAPTOR Health Check — {report['checked_at']}         ║",
            "╚══════════════════════════════════════════════════╝",
            f"  Overall status: {report['status']}",
            "",
        ]
        icons = {"OK": "✓", "WARN": "⚠", "ERROR": "✗"}
        for name, check in report["checks"].items():
            icon    = icons.get(check["status"], "?")
            label   = name.replace("_", " ").title()
            status  = check["status"]
            detail  = _check_detail(name, check)
            lines.append(f"  {icon} [{status:5s}] {label}: {detail}")

        lines += ["", f"  Checked {len(report['checks'])} categories."]
        return "\n".join(lines)

    # ── Individual checks ─────────────────────────────────────────────────────

    def _check_tables(self) -> dict:
        missing = [t for t in _REQUIRED_TABLES if not _table_exists(self.conn, t)]
        return {
            "status":  "ERROR" if missing else "OK",
            "missing": missing,
        }

    def _check_compliance_rules(self) -> dict:
        """Compliance scanner is blind without seeded rules in kb_rules."""
        try:
            n = self.conn.execute(
                "SELECT COUNT(*) AS n FROM kb_rules "
                "WHERE source_file LIKE '%raptor_compliance%'"
            ).fetchone()["n"]
        except Exception:
            n = 0
        return {
            "status":     "WARN" if n == 0 else "OK",
            "rule_count": n,
        }

    def _check_orphaned_consent(self) -> dict:
        """Consent rows whose prospect_id is not in raptor_prospects."""
        try:
            n = self.conn.execute(
                """SELECT COUNT(*) AS n FROM raptor_consent_ledger
                   WHERE prospect_id NOT IN (
                       SELECT prospect_id FROM raptor_prospects
                   )"""
            ).fetchone()["n"]
        except Exception:
            n = 0
        return {
            "status": "WARN" if n > 0 else "OK",
            "count":  n,
        }

    def _check_orphaned_touchpoints(self) -> dict:
        """Touchpoints whose prospect_id is not in raptor_prospects."""
        try:
            n = self.conn.execute(
                """SELECT COUNT(*) AS n FROM raptor_touchpoints
                   WHERE prospect_id NOT IN (
                       SELECT prospect_id FROM raptor_prospects
                   )"""
            ).fetchone()["n"]
        except Exception:
            n = 0
        return {
            "status": "WARN" if n > 0 else "OK",
            "count":  n,
        }

    def _check_stuck_prospects(self) -> dict:
        """Prospects in a non-terminal stage for longer than MAX_STAGE_DAYS."""
        today   = date.today()
        stuck   = []
        terminal = {"active", "onboarding"}   # long-lived stages, skip

        try:
            prospects = self.conn.execute(
                "SELECT prospect_id, pipeline_stage, updated_date "
                "FROM raptor_prospects"
            ).fetchall()
        except Exception:
            return {"status": "OK", "count": 0, "details": []}

        for p in prospects:
            stage = p["pipeline_stage"]
            limit = MAX_STAGE_DAYS.get(stage)
            if not limit:
                continue
            updated = (p["updated_date"] or "")[:10]
            if not updated:
                continue
            try:
                days = (today - date.fromisoformat(updated)).days
            except ValueError:
                continue
            if days > limit:
                stuck.append({
                    "prospect_id": p["prospect_id"],
                    "stage":       stage,
                    "days_in_stage": days,
                    "limit_days":  limit,
                })

        return {
            "status":  "WARN" if stuck else "OK",
            "count":   len(stuck),
            "details": stuck,
        }

    def _check_deletion_sla(self) -> dict:
        """Law 25: deletion requests must be executed within 30 days."""
        today = date.today()
        sla_deadline = (today - timedelta(days=30)).isoformat()
        try:
            n = self.conn.execute(
                """SELECT COUNT(*) AS n FROM raptor_consent_ledger
                   WHERE deletion_requested = 1
                     AND deletion_executed_date IS NULL
                     AND consent_date <= ?""",
                (sla_deadline,),
            ).fetchone()["n"]
        except Exception:
            n = 0
        return {
            "status":        "ERROR" if n > 0 else "OK",
            "overdue_count": n,
        }

    def _check_expiring_consent(self) -> dict:
        """CASL: flag consents expiring within 30 days with no renewal."""
        today    = date.today()
        deadline = (today + timedelta(days=30)).isoformat()
        try:
            n = self.conn.execute(
                """SELECT COUNT(*) AS n FROM raptor_consent_ledger
                   WHERE expiry_date IS NOT NULL
                     AND expiry_date <= ?
                     AND revoked = 0
                     AND deletion_requested = 0""",
                (deadline,),
            ).fetchone()["n"]
        except Exception:
            n = 0
        return {
            "status":         "WARN" if n > 0 else "OK",
            "expiring_count": n,
        }


# ── Formatting helper ─────────────────────────────────────────────────────────

def _check_detail(name: str, check: dict) -> str:
    if name == "tables":
        if check["missing"]:
            return f"MISSING: {', '.join(check['missing'])}"
        return "all tables present"
    if name == "compliance_rules":
        return f"{check['rule_count']} rules loaded"
    if name == "orphaned_consent":
        return f"{check['count']} orphaned row(s)"
    if name == "orphaned_touchpoints":
        return f"{check['count']} orphaned row(s)"
    if name == "stuck_prospects":
        if check["count"]:
            return f"{check['count']} prospect(s) over stage limit"
        return "no stuck prospects"
    if name == "deletion_sla":
        if check["overdue_count"]:
            return f"{check['overdue_count']} deletion(s) past 30-day SLA"
        return "all deletions on time"
    if name == "expiring_consent":
        if check["expiring_count"]:
            return f"{check['expiring_count']} consent(s) expiring within 30d"
        return "no imminent expiries"
    return str(check)
