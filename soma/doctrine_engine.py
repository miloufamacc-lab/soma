"""
DOCTRINE — Directional Oversight of Conviction, Thesis & Risk-Informed Navigation Engine
Pipeline: SOMA/DOCTRINE | Module: SOMA | Status: BUILT

Investment thesis engine — tracks beliefs, gathers evidence from SOMA data,
adjusts conviction scores, and flags conflicts with the current regime.

Usage:
    with DoctrineEngine() as doc:
        result = doc.analyze()
        doc.print_terminal()
        doc.save_log()

Design:
    - Reads SOMA regime, valuations, and DELTA changes
    - Compares each active belief against current evidence
    - Adjusts conviction scores using Grok-validated rules:
        * Regime mismatch: deduct 0.2-0.3 from normalized conviction
        * Evidence correlation > 0.7: boost conviction
        * Belief untested > 90 days: flag as stale
        * Contradiction ratio > 60%: flag for mandatory review
    - Outputs terminal display + JSON log + alerts
    - Fire-and-forget: never crashes the caller
"""

import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

from .soma_bridge import SomaBridge


# ── Conviction adjustment rules (from Grok stress-test methodology) ──

# Regime mismatch deduction (normalized 0-1 scale, so 2-3 on 1-10 scale)
REGIME_MISMATCH_DEDUCTION = 2

# Days before a belief is flagged stale (Grok: 90 days)
STALE_THRESHOLD_DAYS = 90

# If contradiction ratio exceeds this, flag for mandatory review
CONTRADICTION_RATIO_THRESHOLD = 0.60

# Evidence weight thresholds
STRONG_EVIDENCE_WEIGHT = 1.5    # evidence with weight >= this gets extra impact
WEAK_EVIDENCE_WEIGHT = 0.5      # evidence with weight <= this gets reduced impact

# Conviction bounds
CONVICTION_MIN = 1
CONVICTION_MAX = 10

# ── Regime-to-belief alignment map ──────────────────────────────────
# Maps SOMA regime names to expected belief alignment
REGIME_ALIGNMENT = {
    "RISK_ON": {
        "bullish_domains": ["equities", "crypto"],
        "bearish_domains": ["risk"],
        "description": "Risk-on favours equity and crypto exposure",
    },
    "RISK_OFF": {
        "bullish_domains": ["risk"],
        "bearish_domains": ["equities", "crypto"],
        "description": "Risk-off favours defensive positioning",
    },
    "NORMAL": {
        "bullish_domains": [],
        "bearish_domains": [],
        "description": "Neutral regime — no strong directional bias",
    },
    "CRISIS": {
        "bullish_domains": ["risk"],
        "bearish_domains": ["equities", "crypto", "macro"],
        "description": "Crisis regime — maximum caution, cash preservation",
    },
}


class DoctrineEngine:
    """DOCTRINE — investment thesis engine for DABEIBA.

    Tracks beliefs, tests them against live SOMA data, adjusts conviction,
    and flags conflicts. Follows the same context-manager pattern as
    WhatChanged (DELTA) for clean resource handling.
    """

    MODULE_VERSION = "DOCTRINE-1.0.0"

    def __init__(self, db_path=None):
        self.db_path = db_path
        self._bridge = None
        self._result = None

    def __enter__(self):
        self._bridge = SomaBridge(self.db_path)
        self._bridge.__enter__()
        self._bridge.initialize_db()  # ensure migration 007 is applied
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._bridge:
            self._bridge.__exit__(exc_type, exc_val, exc_tb)
            self._bridge = None
        return False

    # ── Core analysis ────────────────────────────────────────────────

    def analyze(self):
        """Run the full DOCTRINE analysis cycle.

        Steps:
            1. Load all active beliefs
            2. Load current regime + DELTA changes
            3. Gather evidence from SOMA (regime, valuations, trade log)
            4. Score each belief: conviction adjustments
            5. Flag alerts: regime mismatch, stale, contradiction
            6. Persist changes to SOMA tables

        Returns a result dict with beliefs_analyzed, alerts, conviction_changes.
        """
        conn = self._bridge.conn
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # 1. Load active beliefs
        beliefs = self._get_active_beliefs()
        if not beliefs:
            self._result = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "beliefs_analyzed": 0,
                "alerts_raised": 0,
                "conviction_changes": [],
                "alerts": [],
                "regime": None,
                "summary": "No active beliefs found. Seed beliefs first.",
            }
            return self._result

        # 2. Load current regime + DELTA context
        regime = self._bridge.get_latest_regime()
        regime_name = regime["regime"] if regime else "UNKNOWN"

        # Load latest DELTA result if available
        delta_changes = self._load_latest_delta()

        # 3. Gather evidence from current SOMA state
        auto_evidence = self._gather_auto_evidence(regime, delta_changes)

        # 4-5. Process each belief
        conviction_changes = []
        alerts = []

        for belief in beliefs:
            bid = belief["belief_id"]

            # Get all evidence for this belief
            all_evidence = self._get_evidence(bid)

            # Check regime alignment
            regime_alert = self._check_regime_alignment(belief, regime_name)
            if regime_alert:
                alerts.append(regime_alert)

            # Check staleness
            stale_alert = self._check_staleness(belief, today)
            if stale_alert:
                alerts.append(stale_alert)

            # Check contradiction ratio
            contradiction_alert = self._check_contradiction_ratio(belief, all_evidence)
            if contradiction_alert:
                alerts.append(contradiction_alert)

            # Auto-add evidence from SOMA state (if relevant to this belief)
            new_evidence = self._match_auto_evidence(belief, auto_evidence)
            for ev in new_evidence:
                self._write_evidence(ev)

            # Recalculate conviction based on all evidence + regime
            old_conviction = belief["conviction"]
            new_conviction = self._calculate_conviction(
                belief, all_evidence + new_evidence, regime_name
            )

            if new_conviction != old_conviction:
                conviction_changes.append({
                    "belief_id": bid,
                    "domain": belief["domain"],
                    "statement": belief["statement"],
                    "old": old_conviction,
                    "new": new_conviction,
                    "delta": new_conviction - old_conviction,
                })
                # Persist the conviction change
                self._update_conviction(bid, old_conviction, new_conviction,
                                        "auto_analysis", today)

            # Update last_tested
            self._mark_tested(bid, today)

        # 6. Persist alerts
        for alert in alerts:
            self._write_alert(alert, today)

        self._result = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "beliefs_analyzed": len(beliefs),
            "alerts_raised": len(alerts),
            "conviction_changes": conviction_changes,
            "alerts": alerts,
            "regime": regime_name,
            "beliefs": [
                {
                    "belief_id": b["belief_id"],
                    "domain": b["domain"],
                    "statement": b["statement"],
                    "conviction": b["conviction"],
                    "evidence_for": b["evidence_for"],
                    "evidence_against": b["evidence_against"],
                }
                for b in beliefs
            ],
            "summary": self._build_summary(beliefs, conviction_changes, alerts, regime_name),
        }
        return self._result

    # ── Data access ──────────────────────────────────────────────────

    def _get_active_beliefs(self):
        """Load all active beliefs from SOMA."""
        try:
            rows = self._bridge.conn.execute(
                "SELECT * FROM philosophy_beliefs WHERE is_active = 1 ORDER BY domain, belief_id"
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            print(f"[DOCTRINE] Failed to load beliefs: {e}")
            return []

    def _get_evidence(self, belief_id):
        """Load all evidence for a specific belief."""
        try:
            rows = self._bridge.conn.execute(
                "SELECT * FROM philosophy_evidence WHERE belief_id = ? ORDER BY date_logged DESC",
                (belief_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            print(f"[DOCTRINE] Failed to load evidence for {belief_id}: {e}")
            return []

    def _load_latest_delta(self):
        """Load the most recent DELTA (WhatChanged) result from logs."""
        logs_dir = Path(__file__).parent / "logs"
        if not logs_dir.exists():
            return None
        log_files = sorted(logs_dir.glob("what_changed_*.json"), reverse=True)
        if not log_files:
            return None
        try:
            with open(log_files[0]) as f:
                return json.load(f)
        except Exception:
            return None

    # ── Evidence gathering ───────────────────────────────────────────

    def _gather_auto_evidence(self, regime, delta_changes):
        """Extract evidence from current SOMA state.

        Returns a list of candidate evidence dicts (not yet written).
        Each has: domain, source_module, source_detail, supports_direction, weight
        """
        evidence = []

        # Evidence from regime state
        if regime:
            gli = regime.get("gli_value", 0)
            regime_name = regime.get("regime", "UNKNOWN")

            # GLI level as evidence
            if gli > 60:
                evidence.append({
                    "domain": "macro",
                    "source_module": "ORACLE",
                    "source_detail": f"GLI at {gli:.1f} (expansionary territory)",
                    "direction": "bullish",
                    "weight": 1.0,
                })
            elif gli < 45:
                evidence.append({
                    "domain": "macro",
                    "source_module": "ORACLE",
                    "source_detail": f"GLI at {gli:.1f} (contractionary territory)",
                    "direction": "bearish",
                    "weight": 1.0,
                })

            # Regime itself as evidence
            if regime_name == "RISK_ON":
                evidence.append({
                    "domain": "macro",
                    "source_module": "ORACLE",
                    "source_detail": f"SOMA regime: {regime_name}",
                    "direction": "bullish",
                    "weight": 1.2,
                })
            elif regime_name in ("RISK_OFF", "CRISIS"):
                evidence.append({
                    "domain": "macro",
                    "source_module": "ORACLE",
                    "source_detail": f"SOMA regime: {regime_name}",
                    "direction": "bearish",
                    "weight": 1.2,
                })

        # Evidence from DELTA material changes
        if delta_changes and delta_changes.get("has_material_change"):
            for change in delta_changes.get("changes", []):
                if change["type"] == "regime_transition":
                    evidence.append({
                        "domain": "macro",
                        "source_module": "DELTA",
                        "source_detail": f"Regime transition: {change.get('description', '')}",
                        "direction": "neutral",  # direction depends on the belief
                        "weight": 1.5,
                    })
                elif change["type"] == "valuation_shift":
                    evidence.append({
                        "domain": "equities",
                        "source_module": "DELTA",
                        "source_detail": f"Valuation shift: {change.get('description', '')}",
                        "direction": "neutral",
                        "weight": 1.0,
                    })

        # Evidence from latest valuations (average upside)
        try:
            vals = self._bridge.get_latest_valuations()
            if vals:
                avg_upside = sum(v["implied_upside"] for v in vals) / len(vals)
                if avg_upside > 0.15:
                    evidence.append({
                        "domain": "equities",
                        "source_module": "ORACLE",
                        "source_detail": f"Average implied upside: {avg_upside:.1%} (attractive)",
                        "direction": "bullish",
                        "weight": 0.8,
                    })
                elif avg_upside < -0.05:
                    evidence.append({
                        "domain": "equities",
                        "source_module": "ORACLE",
                        "source_detail": f"Average implied upside: {avg_upside:.1%} (overvalued)",
                        "direction": "bearish",
                        "weight": 0.8,
                    })
        except Exception:
            pass

        return evidence

    def _match_auto_evidence(self, belief, auto_evidence):
        """Match auto-gathered evidence to a specific belief based on domain.

        Returns evidence entries formatted for writing.
        """
        matched = []
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        for ev in auto_evidence:
            if ev["domain"] != belief["domain"]:
                continue

            # Determine if this evidence supports or contradicts the belief
            # A bullish belief is supported by bullish evidence and contradicted by bearish
            belief_direction = self._infer_belief_direction(belief)
            if ev["direction"] == "neutral":
                # Regime transitions are ambiguous — skip auto-assignment
                continue

            supports = 1 if ev["direction"] == belief_direction else 0

            matched.append({
                "belief_id": belief["belief_id"],
                "source_module": ev["source_module"],
                "source_detail": ev["source_detail"],
                "supports": supports,
                "weight": ev["weight"],
                "date_logged": today,
            })

        return matched

    def _infer_belief_direction(self, belief):
        """Infer whether a belief is bullish or bearish from its statement."""
        statement = belief["statement"].lower()
        bullish_keywords = ["bull", "growth", "expansion", "upside", "structural",
                            "accelerat", "outperform", "strong", "recovery"]
        bearish_keywords = ["bear", "contraction", "downside", "recession",
                            "risk", "decline", "weak", "defensive"]
        bull_score = sum(1 for kw in bullish_keywords if kw in statement)
        bear_score = sum(1 for kw in bearish_keywords if kw in statement)
        if bull_score > bear_score:
            return "bullish"
        elif bear_score > bull_score:
            return "bearish"
        return "neutral"

    # ── Conviction calculation ───────────────────────────────────────

    def _calculate_conviction(self, belief, evidence_list, regime_name):
        """Recalculate conviction based on evidence + regime alignment.

        Algorithm:
            1. Start from current conviction
            2. For each recent evidence entry (last 30 days), nudge +/- based on weight
            3. Apply regime mismatch penalty if applicable
            4. Clamp to [1, 10]
        """
        conviction = belief["conviction"]

        # Count recent evidence (last 30 days)
        cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
        recent = [e for e in evidence_list if e.get("date_logged", "") >= cutoff]

        if recent:
            for_count = sum(1 for e in recent if e["supports"] == 1)
            against_count = sum(1 for e in recent if e["supports"] == 0)

            # Weighted net signal
            weighted_for = sum(e.get("weight", 1.0) for e in recent if e["supports"] == 1)
            weighted_against = sum(e.get("weight", 1.0) for e in recent if e["supports"] == 0)

            net_signal = weighted_for - weighted_against
            # Scale: each net unit of weighted evidence moves conviction by ~0.5
            conviction_delta = round(net_signal * 0.5)
            conviction += conviction_delta

        # Regime mismatch penalty
        alignment = REGIME_ALIGNMENT.get(regime_name, {})
        belief_direction = self._infer_belief_direction(belief)
        domain = belief["domain"]

        if belief_direction == "bullish" and domain in alignment.get("bearish_domains", []):
            conviction -= REGIME_MISMATCH_DEDUCTION
        elif belief_direction == "bearish" and domain in alignment.get("bullish_domains", []):
            conviction -= REGIME_MISMATCH_DEDUCTION

        # Clamp
        conviction = max(CONVICTION_MIN, min(CONVICTION_MAX, conviction))
        return conviction

    # ── Alert checks ─────────────────────────────────────────────────

    def _check_regime_alignment(self, belief, regime_name):
        """Check if belief direction conflicts with current regime."""
        alignment = REGIME_ALIGNMENT.get(regime_name, {})
        direction = self._infer_belief_direction(belief)
        domain = belief["domain"]

        mismatch = False
        if direction == "bullish" and domain in alignment.get("bearish_domains", []):
            mismatch = True
        elif direction == "bearish" and domain in alignment.get("bullish_domains", []):
            mismatch = True

        if mismatch:
            return {
                "alert_type": "regime_mismatch",
                "severity": "WARNING",
                "belief_id": belief["belief_id"],
                "description": (
                    f"Belief '{belief['belief_id']}' ({direction} {domain}) "
                    f"conflicts with {regime_name} regime"
                ),
                "recommended_action": (
                    f"Review {belief['belief_id']} — conviction may need adjustment. "
                    f"Current regime ({regime_name}) {alignment.get('description', '')}"
                ),
            }
        return None

    def _check_staleness(self, belief, today):
        """Flag beliefs not tested in > 90 days."""
        last_tested = belief.get("last_tested")
        if not last_tested:
            # Never tested — flag if created > 90 days ago
            last_tested = belief.get("created_date", today)

        try:
            last_dt = datetime.strptime(last_tested, "%Y-%m-%d")
            today_dt = datetime.strptime(today, "%Y-%m-%d")
            days_stale = (today_dt - last_dt).days
        except (ValueError, TypeError):
            return None

        if days_stale > STALE_THRESHOLD_DAYS:
            return {
                "alert_type": "stale_belief",
                "severity": "INFO",
                "belief_id": belief["belief_id"],
                "description": (
                    f"Belief '{belief['belief_id']}' untested for {days_stale} days "
                    f"(threshold: {STALE_THRESHOLD_DAYS})"
                ),
                "recommended_action": (
                    f"Gather fresh evidence for {belief['belief_id']} or retire it"
                ),
            }
        return None

    def _check_contradiction_ratio(self, belief, evidence_list):
        """Flag beliefs where > 60% of evidence contradicts."""
        total = belief["evidence_for"] + belief["evidence_against"]
        if total < 3:  # need minimum evidence to judge
            return None

        contradiction_ratio = belief["evidence_against"] / total
        if contradiction_ratio > CONTRADICTION_RATIO_THRESHOLD:
            return {
                "alert_type": "evidence_contradiction",
                "severity": "CRITICAL",
                "belief_id": belief["belief_id"],
                "description": (
                    f"Belief '{belief['belief_id']}' has {contradiction_ratio:.0%} "
                    f"contradicting evidence ({belief['evidence_against']}/{total})"
                ),
                "recommended_action": (
                    f"MANDATORY REVIEW: {belief['belief_id']} — evidence no longer supports "
                    f"this thesis. Consider retiring or reversing."
                ),
            }
        return None

    # ── Write helpers ────────────────────────────────────────────────

    def _write_evidence(self, ev):
        """Write a single evidence entry to SOMA."""
        try:
            self._bridge.conn.execute(
                """INSERT INTO philosophy_evidence
                   (belief_id, source_module, source_detail, supports, weight,
                    run_id, date_logged, write_timestamp, module_version)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (ev["belief_id"], ev["source_module"], ev["source_detail"],
                 ev["supports"], ev.get("weight", 1.0), ev.get("run_id"),
                 ev["date_logged"],
                 datetime.now(timezone.utc).isoformat(), self.MODULE_VERSION),
            )
            self._bridge.conn.commit()

            # Update evidence counts on the belief
            col = "evidence_for" if ev["supports"] == 1 else "evidence_against"
            self._bridge.conn.execute(
                f"UPDATE philosophy_beliefs SET {col} = {col} + 1 WHERE belief_id = ?",
                (ev["belief_id"],),
            )
            self._bridge.conn.commit()
        except Exception as e:
            print(f"[DOCTRINE] write_evidence failed: {e}")

    def _update_conviction(self, belief_id, old_conviction, new_conviction,
                           trigger_type, date):
        """Update belief conviction and log the change."""
        try:
            # Update the belief
            self._bridge.conn.execute(
                "UPDATE philosophy_beliefs SET conviction = ?, write_timestamp = ? WHERE belief_id = ?",
                (new_conviction, datetime.now(timezone.utc).isoformat(), belief_id),
            )
            # Log the history
            self._bridge.conn.execute(
                """INSERT INTO philosophy_history
                   (belief_id, old_conviction, new_conviction, trigger_type,
                    trigger_detail, change_date, write_timestamp, module_version)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (belief_id, old_conviction, new_conviction, trigger_type,
                 f"Auto-analysis: {old_conviction} -> {new_conviction}",
                 date, datetime.now(timezone.utc).isoformat(), self.MODULE_VERSION),
            )
            self._bridge.conn.commit()
        except Exception as e:
            print(f"[DOCTRINE] update_conviction failed for {belief_id}: {e}")

    def _mark_tested(self, belief_id, date):
        """Update last_tested date on a belief."""
        try:
            self._bridge.conn.execute(
                "UPDATE philosophy_beliefs SET last_tested = ? WHERE belief_id = ?",
                (date, belief_id),
            )
            self._bridge.conn.commit()
        except Exception as e:
            print(f"[DOCTRINE] mark_tested failed for {belief_id}: {e}")

    def _write_alert(self, alert, date):
        """Write an alert to SOMA."""
        try:
            self._bridge.conn.execute(
                """INSERT INTO philosophy_alerts
                   (alert_type, severity, belief_id, description,
                    recommended_action, date_flagged, write_timestamp, module_version)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (alert["alert_type"], alert["severity"], alert.get("belief_id"),
                 alert["description"], alert.get("recommended_action"),
                 date, datetime.now(timezone.utc).isoformat(), self.MODULE_VERSION),
            )
            self._bridge.conn.commit()
        except Exception as e:
            print(f"[DOCTRINE] write_alert failed: {e}")

    # ── Belief management (for seeding and manual updates) ───────────

    def add_belief(self, belief_id, domain, statement, conviction=5):
        """Add a new belief to the system."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        try:
            self._bridge.conn.execute(
                """INSERT OR IGNORE INTO philosophy_beliefs
                   (belief_id, domain, statement, conviction, created_date,
                    write_timestamp, module_version)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (belief_id, domain, statement, conviction, today,
                 datetime.now(timezone.utc).isoformat(), self.MODULE_VERSION),
            )
            self._bridge.conn.commit()
            return True
        except Exception as e:
            print(f"[DOCTRINE] add_belief failed for {belief_id}: {e}")
            return False

    def retire_belief(self, belief_id):
        """Retire a belief (set is_active = 0)."""
        try:
            self._bridge.conn.execute(
                "UPDATE philosophy_beliefs SET is_active = 0, write_timestamp = ? WHERE belief_id = ?",
                (datetime.now(timezone.utc).isoformat(), belief_id),
            )
            self._bridge.conn.commit()
            return True
        except Exception as e:
            print(f"[DOCTRINE] retire_belief failed: {e}")
            return False

    def add_manual_evidence(self, belief_id, source_detail, supports=True, weight=1.0):
        """Add manual evidence for a belief."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self._write_evidence({
            "belief_id": belief_id,
            "source_module": "manual",
            "source_detail": source_detail,
            "supports": 1 if supports else 0,
            "weight": weight,
            "date_logged": today,
        })

    # ── Summary builder ──────────────────────────────────────────────

    def _build_summary(self, beliefs, conviction_changes, alerts, regime_name):
        """Build a 2-3 sentence executive summary."""
        parts = []
        parts.append(f"DOCTRINE analyzed {len(beliefs)} active beliefs under {regime_name} regime.")

        if conviction_changes:
            ups = [c for c in conviction_changes if c["delta"] > 0]
            downs = [c for c in conviction_changes if c["delta"] < 0]
            if ups and downs:
                parts.append(f"{len(ups)} conviction(s) increased, {len(downs)} decreased.")
            elif ups:
                parts.append(f"{len(ups)} conviction(s) increased.")
            elif downs:
                parts.append(f"{len(downs)} conviction(s) decreased.")
        else:
            parts.append("No conviction changes.")

        critical = [a for a in alerts if a["severity"] == "CRITICAL"]
        if critical:
            parts.append(f"CRITICAL: {len(critical)} belief(s) require mandatory review.")
        elif alerts:
            parts.append(f"{len(alerts)} alert(s) raised — review recommended.")

        return " ".join(parts)

    # ── Persistence (log file) ───────────────────────────────────────

    def save_log(self) -> str:
        """Write DOCTRINE analysis to JSON log file."""
        if self._result is None:
            self.analyze()

        logs_dir = Path(__file__).parent / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        path = logs_dir / f"doctrine_{ts}.json"
        with open(path, "w") as f:
            json.dump(self._result, f, indent=2, default=str)
        return str(path.resolve())

    # ── Terminal display ─────────────────────────────────────────────

    def print_terminal(self):
        """Pretty-print DOCTRINE analysis to terminal with ANSI colours."""
        if self._result is None:
            self.analyze()
        r = self._result

        BOLD = "\033[1m"
        RED = "\033[91m"
        YELLOW = "\033[93m"
        GREEN = "\033[92m"
        CYAN = "\033[96m"
        DIM = "\033[2m"
        MAGENTA = "\033[95m"
        RESET = "\033[0m"

        severity_color = {"CRITICAL": RED, "WARNING": YELLOW, "INFO": DIM}

        print(f"\n{BOLD}{'=' * 60}{RESET}")
        print(f"{BOLD}  DOCTRINE — Investment Thesis Engine{RESET}")
        print(f"{DIM}  {r['timestamp']}{RESET}")
        print(f"{BOLD}{'=' * 60}{RESET}")

        # Regime context
        print(f"\n{CYAN}Regime:{RESET}  {r.get('regime', 'UNKNOWN')}")
        print(f"{CYAN}Beliefs:{RESET} {r['beliefs_analyzed']} active")

        # Beliefs table
        if r.get("beliefs"):
            print(f"\n{BOLD}--- Active Beliefs ---{RESET}")
            for b in r["beliefs"]:
                conv = b["conviction"]
                # Color code conviction: green >= 7, yellow 4-6, red <= 3
                if conv >= 7:
                    conv_color = GREEN
                elif conv >= 4:
                    conv_color = YELLOW
                else:
                    conv_color = RED

                direction = "N/A"
                ev_ratio = ""
                total_ev = b["evidence_for"] + b["evidence_against"]
                if total_ev > 0:
                    ev_ratio = f" ({b['evidence_for']}F/{b['evidence_against']}A)"

                print(f"  {MAGENTA}[{b['domain'].upper():>8}]{RESET} "
                      f"{conv_color}C={conv:>2}{RESET}{ev_ratio} "
                      f"{b['statement'][:55]}")

        # Conviction changes
        if r["conviction_changes"]:
            print(f"\n{BOLD}--- Conviction Changes ---{RESET}")
            for c in r["conviction_changes"]:
                arrow = f"{c['old']} -> {c['new']}"
                delta_str = f"{c['delta']:+d}"
                color = GREEN if c["delta"] > 0 else RED
                print(f"  {color}{delta_str}{RESET} {c['belief_id']}: {arrow}")
        else:
            print(f"\n{DIM}  No conviction changes this cycle.{RESET}")

        # Alerts
        if r["alerts"]:
            print(f"\n{BOLD}--- Alerts ---{RESET}")
            for a in r["alerts"]:
                color = severity_color.get(a["severity"], RESET)
                print(f"  {color}[{a['severity']}]{RESET} {a['description']}")
                if a.get("recommended_action"):
                    print(f"    {DIM}Action: {a['recommended_action'][:70]}{RESET}")
        else:
            print(f"\n  {GREEN}No alerts.{RESET}")

        # Summary
        print(f"\n{DIM}{r.get('summary', '')}{RESET}")
        print(f"{BOLD}{'=' * 60}{RESET}\n")


# ── Seed function (for initial belief loading) ───────────────────────

def seed_initial_beliefs(db_path=None):
    """Seed DOCTRINE with a starter set of investment beliefs.

    These reflect DABEIBA's current philosophy as of the build date.
    Conviction scores are initial estimates — DOCTRINE will adjust them
    based on evidence over time.

    Run once:  python3 -c "from soma.doctrine_engine import seed_initial_beliefs; seed_initial_beliefs()"
    """
    beliefs = [
        # Macro
        ("MACRO_GLI_REGIME", "macro",
         "Global Liquidity Index is the primary driver of broad market direction", 8),
        ("MACRO_RATE_CYCLE", "macro",
         "Central bank rate cycles create predictable regime transitions with 6-12 month lags", 6),
        ("MACRO_ENERGY_STRUCTURAL", "macro",
         "Energy sector is in a multi-year structural bull market driven by underinvestment", 5),
        ("MACRO_FISCAL_DOMINANCE", "macro",
         "Fiscal policy has overtaken monetary policy as the primary market driver", 6),

        # Crypto
        ("CRYPTO_SOL_ECOSYSTEM", "crypto",
         "Solana is the strongest smart-contract ecosystem for DeFi execution speed and cost", 7),
        ("CRYPTO_BTC_STORE_OF_VALUE", "crypto",
         "Bitcoin is a legitimate institutional store of value and inflation hedge", 7),
        ("CRYPTO_DEFI_SELF_CUSTODY", "crypto",
         "Self-custody DeFi on Solana offers superior risk-adjusted returns vs centralized platforms", 6),
        ("CRYPTO_ONCHAIN_SIGNALS", "crypto",
         "On-chain metrics (MVRV, NUPL, SOPR) have predictive power for cycle tops and bottoms", 7),

        # Equities
        ("EQ_CONCENTRATION_ALPHA", "equities",
         "Concentrated portfolios (10-15 positions) outperform diversified portfolios when conviction is high", 8),
        ("EQ_VALUATION_MEAN_REVERT", "equities",
         "Implied upside from fundamental valuation mean-reverts over 12-24 month horizons", 7),
        ("EQ_AI_SECULAR_THEME", "equities",
         "AI infrastructure spending is a decade-long secular theme with sustainable growth", 7),

        # Risk
        ("RISK_DRAWDOWN_ASYMMETRY", "risk",
         "Avoiding large drawdowns matters more than capturing all upside for long-term compounding", 9),
        ("RISK_REGIME_TIMING", "risk",
         "Regime-based position sizing reduces max drawdown without proportionally reducing returns", 8),

        # Behavioral
        ("BEH_RECENCY_BIAS", "behavioral",
         "Recency bias is the biggest risk to conviction — recent data gets overweighted vs base rates", 7),
        ("BEH_THESIS_DISCIPLINE", "behavioral",
         "Sticking to pre-committed thesis rules outperforms reactive decision-making in volatile markets", 8),
    ]

    with DoctrineEngine(db_path) as doc:
        added = 0
        for belief_id, domain, statement, conviction in beliefs:
            if doc.add_belief(belief_id, domain, statement, conviction):
                added += 1
        print(f"[DOCTRINE] Seeded {added} beliefs ({len(beliefs)} total, duplicates skipped)")
