"""
WhatChanged — SOMA's core diff engine.

Compares current vs. previous regime, valuation, and outlook data,
flags material changes using quantitative thresholds.

Usage:
    with WhatChanged() as wc:
        result = wc.analyze()
        wc.print_terminal()
"""

import json
import math
import os
from datetime import datetime, timezone

from .soma_bridge import SomaBridge


class WhatChanged:
    def __init__(self, db_path=None):
        self.db_path = db_path
        self._bridge = None
        self._result = None

    def __enter__(self):
        self._bridge = SomaBridge(self.db_path)
        self._bridge.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._bridge:
            self._bridge.__exit__(exc_type, exc_val, exc_tb)
            self._bridge = None
        return False

    # ── Data fetching ─────────────────────────────────────────────────

    def _get_regime_pair(self):
        """Returns (current, previous) regime dicts, or (None, None)."""
        history = self._bridge.get_regime_history(limit=2)
        if len(history) < 2:
            return (history[0] if history else None), None
        return history[0], history[1]

    def _get_valuation_pair(self):
        """Returns (current_rows, previous_rows) for the two most recent run_ids."""
        conn = self._bridge.conn
        run_ids = conn.execute(
            "SELECT DISTINCT run_id FROM valuations ORDER BY id DESC LIMIT 2"
        ).fetchall()
        if not run_ids:
            return [], []
        current_id = run_ids[0]["run_id"]
        current = [dict(r) for r in conn.execute(
            "SELECT * FROM valuations WHERE run_id = ? ORDER BY ticker", (current_id,)
        ).fetchall()]
        if len(run_ids) < 2:
            return current, []
        prev_id = run_ids[1]["run_id"]
        previous = [dict(r) for r in conn.execute(
            "SELECT * FROM valuations WHERE run_id = ? ORDER BY ticker", (prev_id,)
        ).fetchall()]
        return current, previous

    def _get_outlook_pair(self):
        """Returns (current, previous) outlook dicts."""
        conn = self._bridge.conn
        rows = conn.execute(
            "SELECT * FROM outlook_snapshots ORDER BY id DESC LIMIT 2"
        ).fetchall()
        rows = [dict(r) for r in rows]
        if len(rows) < 2:
            return (rows[0] if rows else None), None
        return rows[0], rows[1]

    # ── Materiality checks ────────────────────────────────────────────

    def _check_regime_transition(self, cur, prev):
        if cur["regime"] != prev["regime"]:
            return {
                "type": "regime_transition",
                "description": f"Regime changed from {prev['regime']} to {cur['regime']}",
                "severity": "HIGH",
                "before": prev["regime"],
                "after": cur["regime"],
            }
        return None

    def _check_gli_delta(self, cur, prev):
        delta = abs(cur["gli_value"] - prev["gli_value"])
        if delta > 3.5:
            return {
                "type": "gli_delta",
                "description": f"|DELTA GLI| = {delta:.2f} (threshold 3.5)",
                "severity": "MEDIUM",
                "before": prev["gli_value"],
                "after": cur["gli_value"],
            }
        return None

    def _check_diffusion_cross(self, cur, prev):
        cd, pd = cur["diffusion_index"], prev["diffusion_index"]
        crossed = False
        desc_parts = []
        if pd >= 45 and cd < 45:
            crossed = True
            desc_parts.append(f"crossed below 45 ({pd:.1f} -> {cd:.1f})")
        if pd <= 55 and cd > 55:
            crossed = True
            desc_parts.append(f"crossed above 55 ({pd:.1f} -> {cd:.1f})")
        if crossed:
            return {
                "type": "diffusion_cross",
                "description": f"Diffusion {'; '.join(desc_parts)}",
                "severity": "MEDIUM",
                "before": pd,
                "after": cd,
            }
        return None

    def _check_momentum_flip(self, cur, prev):
        def sign(x):
            if x > 0: return 1
            if x < 0: return -1
            return 0
        cm, pm = cur["momentum"], prev["momentum"]
        if sign(cm) != sign(pm) and sign(cm) != 0 and sign(pm) != 0:
            return {
                "type": "momentum_flip",
                "description": f"Momentum sign flipped ({pm:.2f} -> {cm:.2f})",
                "severity": "MEDIUM",
                "before": pm,
                "after": cm,
            }
        return None

    def _check_valuation_shift(self, cur_rows, prev_rows):
        if not cur_rows or not prev_rows:
            return None, {}
        cur_by_ticker = {r["ticker"]: r["implied_upside"] for r in cur_rows}
        prev_by_ticker = {r["ticker"]: r["implied_upside"] for r in prev_rows}
        avg_cur = sum(cur_by_ticker.values()) / len(cur_by_ticker)
        avg_prev = sum(prev_by_ticker.values()) / len(prev_by_ticker)
        delta = abs(avg_cur - avg_prev)
        tickers_changed = []
        all_tickers = set(cur_by_ticker) | set(prev_by_ticker)
        for t in sorted(all_tickers):
            c = cur_by_ticker.get(t)
            p = prev_by_ticker.get(t)
            if c is not None and p is not None and abs(c - p) > 0.05:
                tickers_changed.append(t)
            elif c is None or p is None:
                tickers_changed.append(t)
        summary = {
            "avg_upside_current": round(avg_cur, 4),
            "avg_upside_previous": round(avg_prev, 4),
            "delta": round(avg_cur - avg_prev, 4),
            "tickers_changed": tickers_changed,
        }
        change = None
        if delta > 0.08:
            change = {
                "type": "valuation_shift",
                "description": f"|DELTA avg implied upside| = {delta:.1%} (threshold 8%)",
                "severity": "MEDIUM",
                "before": round(avg_prev, 4),
                "after": round(avg_cur, 4),
            }
        return change, summary

    def _jaccard(self, set_a, set_b):
        if not set_a and not set_b:
            return 1.0
        union = set_a | set_b
        if not union:
            return 1.0
        return len(set_a & set_b) / len(union)

    def _check_outlook_drift(self, cur, prev):
        if not cur or not prev:
            return None, None
        try:
            cur_conclusions = set(json.loads(cur["key_conclusions_json"])) if cur.get("key_conclusions_json") else set()
            prev_conclusions = set(json.loads(prev["key_conclusions_json"])) if prev.get("key_conclusions_json") else set()
        except (json.JSONDecodeError, TypeError):
            return None, None
        score = self._jaccard(cur_conclusions, prev_conclusions)
        summary = {
            "current_version": cur.get("version"),
            "previous_version": prev.get("version"),
            "jaccard_score": round(score, 4),
        }
        change = None
        if score < 0.75:
            change = {
                "type": "outlook_drift",
                "description": f"Outlook Jaccard = {score:.2f} (threshold 0.75)",
                "severity": "MEDIUM",
                "before": sorted(prev_conclusions),
                "after": sorted(cur_conclusions),
            }
        return change, summary

    # ── Main analysis ─────────────────────────────────────────────────

    def analyze(self):
        cur_regime, prev_regime = self._get_regime_pair()
        cur_vals, prev_vals = self._get_valuation_pair()
        cur_outlook, prev_outlook = self._get_outlook_pair()

        changes = []
        regime_summary = None
        valuation_summary = {}
        outlook_summary = None

        # Regime checks (1-4)
        if cur_regime and prev_regime:
            regime_summary = {
                "current_regime": cur_regime["regime"],
                "previous_regime": prev_regime["regime"],
                "gli_value": cur_regime["gli_value"],
                "gli_delta": round(cur_regime["gli_value"] - prev_regime["gli_value"], 4),
            }
            for check in (self._check_regime_transition, self._check_gli_delta,
                          self._check_diffusion_cross, self._check_momentum_flip):
                result = check(cur_regime, prev_regime)
                if result:
                    changes.append(result)
        elif cur_regime:
            regime_summary = {
                "current_regime": cur_regime["regime"],
                "previous_regime": None,
                "gli_value": cur_regime["gli_value"],
                "gli_delta": None,
            }

        # Valuation check (5)
        val_change, valuation_summary = self._check_valuation_shift(cur_vals, prev_vals)
        if val_change:
            changes.append(val_change)

        # Outlook check (6)
        outlook_change, outlook_summary = self._check_outlook_drift(cur_outlook, prev_outlook)
        if outlook_change:
            changes.append(outlook_change)

        self._result = {
            "has_material_change": len(changes) > 0,
            "changes": changes,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "regime_summary": regime_summary,
            "valuation_summary": valuation_summary,
            "outlook_summary": outlook_summary,
        }
        return self._result

    # ── Persistence ────────────────────────────────────────────────────

    def save_log(self):
        """Write the analysis result to a JSON file in shared/soma/logs/."""
        if self._result is None:
            self.analyze()
        logs_dir = os.path.join(os.path.dirname(__file__), "logs")
        os.makedirs(logs_dir, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        path = os.path.join(logs_dir, f"what_changed_{ts}.json")
        with open(path, "w") as f:
            json.dump(self._result, f, indent=2, default=str)
        return os.path.realpath(path)

    # ── Terminal display ──────────────────────────────────────────────

    def print_terminal(self):
        if self._result is None:
            self.analyze()
        r = self._result

        BOLD = "\033[1m"
        RED = "\033[91m"
        YELLOW = "\033[93m"
        GREEN = "\033[92m"
        CYAN = "\033[96m"
        DIM = "\033[2m"
        RESET = "\033[0m"

        severity_color = {"HIGH": RED, "MEDIUM": YELLOW, "LOW": GREEN}

        print(f"\n{BOLD}{'=' * 60}{RESET}")
        print(f"{BOLD}  SOMA — What Changed{RESET}")
        print(f"{DIM}  {r['timestamp']}{RESET}")
        print(f"{BOLD}{'=' * 60}{RESET}")

        # Regime summary
        rs = r.get("regime_summary")
        if rs:
            regime_str = rs["current_regime"] or "N/A"
            if rs["previous_regime"] and rs["previous_regime"] != rs["current_regime"]:
                regime_str = f"{rs['previous_regime']} -> {RED}{regime_str}{RESET}"
            gli_delta_str = ""
            if rs["gli_delta"] is not None:
                sign = "+" if rs["gli_delta"] >= 0 else ""
                gli_delta_str = f" ({sign}{rs['gli_delta']:.2f})"
            print(f"\n{CYAN}Regime:{RESET}  {regime_str}")
            print(f"{CYAN}GLI:{RESET}     {rs['gli_value']}{gli_delta_str}")

        # Valuation summary
        vs = r.get("valuation_summary")
        if vs and vs.get("avg_upside_current") is not None:
            print(f"{CYAN}Upside:{RESET}  {vs['avg_upside_current']:.1%} avg "
                  f"(delta {vs['delta']:+.1%})")
            if vs.get("tickers_changed"):
                print(f"         Moved: {', '.join(vs['tickers_changed'])}")

        # Outlook summary
        os_ = r.get("outlook_summary")
        if os_:
            print(f"{CYAN}Outlook:{RESET} Jaccard={os_['jaccard_score']:.2f} "
                  f"(v{os_['current_version']} vs v{os_['previous_version']})")

        # Changes
        print(f"\n{BOLD}--- Material Changes ---{RESET}")
        if not r["changes"]:
            print(f"  {GREEN}No material changes detected.{RESET}")
        else:
            for c in r["changes"]:
                color = severity_color.get(c["severity"], RESET)
                print(f"  {color}[{c['severity']}]{RESET} {c['description']}")

        print(f"{BOLD}{'=' * 60}{RESET}\n")
