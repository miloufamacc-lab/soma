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
import statistics
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

    def _get_regime_pair(self) -> tuple[dict | None, dict | None]:
        """Returns (current, previous) regime dicts, or (None, None)."""
        history = self._bridge.get_regime_history(limit=2)
        if len(history) < 2:
            return (history[0] if history else None), None
        return history[0], history[1]

    def _get_valuation_pair(self) -> tuple[list[dict], list[dict]]:
        """Returns (current_rows, previous_rows) for the two most recent run_ids."""
        conn = self._bridge.conn
        try:
            run_ids = conn.execute(
                "SELECT DISTINCT run_id FROM valuations ORDER BY id DESC LIMIT 2"
            ).fetchall()
        except Exception as e:
            print(f"[WhatChanged] _get_valuation_pair failed: {e}")
            return [], []

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

    def _get_outlook_pair(self) -> tuple[dict | None, dict | None]:
        """Returns (current, previous) outlook dicts."""
        conn = self._bridge.conn
        try:
            rows = conn.execute(
                "SELECT * FROM outlook_snapshots ORDER BY id DESC LIMIT 2"
            ).fetchall()
        except Exception as e:
            print(f"[WhatChanged] _get_outlook_pair failed: {e}")
            return None, None

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

    def _check_gli_adaptive(self, cur, prev):
        """Flag if |DELTA GLI| exceeds 1.5x the rolling 30-day standard deviation."""
        history = self._bridge.get_regime_history(limit=30)
        if len(history) < 10:
            return None  # not enough data points for a meaningful std dev
        gli_values = [h["gli_value"] for h in history]
        std = statistics.stdev(gli_values)
        if std == 0:
            return None  # all identical values, no volatility to compare against
        delta = abs(cur["gli_value"] - prev["gli_value"])
        threshold = 1.5 * std
        if delta > threshold:
            return {
                "type": "gli_adaptive",
                "description": (
                    f"GLI moved {delta:.2f} points, exceeding "
                    f"1.5x the 30-day volatility of {std:.2f}"
                ),
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
                          self._check_gli_adaptive,
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

    # ── Historical context ("Why" explanations) ─────────────────────────

    def explain_context(self):
        """Enrich each material change with historical precedent from SOMA data.

        Must be called after analyze(). Returns a list of context dicts,
        one per material change that has historical data to reference.
        """
        if self._result is None:
            self.analyze()

        changes = self._result.get("changes", [])
        if not changes:
            return []

        explanations = []
        history = self._bridge.get_regime_history(limit=999)

        for change in changes:
            ctype = change["type"]

            if ctype == "regime_transition":
                explanations.append(self._explain_regime_transition(change, history))

            elif ctype in ("gli_delta", "gli_adaptive"):
                explanations.append(self._explain_gli_breach(change, history))

            elif ctype == "valuation_shift":
                explanations.append(self._explain_valuation_shift(change))

        # Filter out None entries (checks with no context to add)
        self._explanations = [e for e in explanations if e]
        return self._explanations

    def _explain_regime_transition(self, change, history):
        """Context for regime transitions: precedent, frequency, duration."""
        from_regime = change["before"]
        to_regime = change["after"]

        # How many times has this exact transition occurred?
        transition_count = 0
        last_occurrence = None
        for i in range(len(history) - 1):
            cur_r, prev_r = history[i]["regime"], history[i + 1]["regime"]
            if prev_r == from_regime and cur_r == to_regime:
                transition_count += 1
                if last_occurrence is None and i > 0:
                    # Skip the first match (that's the current one)
                    pass
                elif last_occurrence is None:
                    last_occurrence = history[i]["date"]
                else:
                    pass
        # Find the *previous* occurrence (not the current one)
        occurrences = []
        for i in range(len(history) - 1):
            cur_r, prev_r = history[i]["regime"], history[i + 1]["regime"]
            if prev_r == from_regime and cur_r == to_regime:
                occurrences.append(history[i]["date"])
        previous_date = occurrences[1] if len(occurrences) >= 2 else None

        # How long did the previous regime last? Count consecutive entries
        prev_duration = 0
        for i in range(1, len(history)):
            if history[i]["regime"] == from_regime:
                prev_duration += 1
            else:
                break

        lines = []
        lines.append(f"{from_regime} -> {to_regime}")
        if previous_date:
            lines.append(f"This transition last occurred on {previous_date}")
        else:
            lines.append("This is the first time this transition has occurred")
        lines.append(f"Total occurrences in history: {transition_count}")
        lines.append(f"Previous regime ({from_regime}) lasted {prev_duration} entries")

        return {
            "change_type": "regime_transition",
            "context_lines": lines,
        }

    def _explain_gli_breach(self, change, history):
        """Context for GLI threshold breaches: similar levels, regime at that time."""
        current_gli = change["after"]
        tolerance = 2.0

        # Find last time GLI was at a similar level (skip the most recent entry)
        similar = None
        for h in history[1:]:
            if abs(h["gli_value"] - current_gli) <= tolerance:
                similar = h
                break

        lines = []
        if similar:
            lines.append(f"GLI was last near {current_gli:.1f} (+-{tolerance}) "
                         f"on {similar['date']} at {similar['gli_value']:.2f}")
            lines.append(f"Regime at that time: {similar['regime']}")

            # Check if valuation data exists around that time
            try:
                conn = self._bridge.conn
                vals = conn.execute(
                    "SELECT AVG(implied_upside) as avg_up FROM valuations "
                    "WHERE date = ?", (similar["date"],)
                ).fetchone()
                if vals and vals["avg_up"] is not None:
                    lines.append(f"Avg implied upside at that time: {vals['avg_up']:.1%}")
            except Exception:
                pass
        else:
            lines.append(f"No prior GLI reading near {current_gli:.1f} found in history")

        return {
            "change_type": change["type"],
            "context_lines": lines,
        }

    def _explain_valuation_shift(self, change):
        """Context for valuation shifts: which tickers moved most."""
        conn = self._bridge.conn

        # Get current and previous valuation runs
        run_ids = conn.execute(
            "SELECT DISTINCT run_id FROM valuations ORDER BY id DESC LIMIT 2"
        ).fetchall()
        if len(run_ids) < 2:
            return None

        cur_id, prev_id = run_ids[0]["run_id"], run_ids[1]["run_id"]
        cur_vals = {r["ticker"]: r["implied_upside"] for r in conn.execute(
            "SELECT ticker, implied_upside FROM valuations WHERE run_id = ?", (cur_id,)
        ).fetchall()}
        prev_vals = {r["ticker"]: r["implied_upside"] for r in conn.execute(
            "SELECT ticker, implied_upside FROM valuations WHERE run_id = ?", (prev_id,)
        ).fetchall()}

        # Top 3 movers by |delta upside|
        deltas = []
        for ticker in set(cur_vals) & set(prev_vals):
            d = cur_vals[ticker] - prev_vals[ticker]
            deltas.append((ticker, d))
        deltas.sort(key=lambda x: abs(x[1]), reverse=True)

        lines = []
        lines.append("Top movers by |delta upside|:")
        for ticker, d in deltas[:3]:
            sign = "+" if d >= 0 else ""
            lines.append(f"  {ticker}: {sign}{d:.1%}")

            # Trend: last 5 entries for this ticker
            trend_rows = conn.execute(
                "SELECT date, implied_upside FROM valuations "
                "WHERE ticker = ? ORDER BY id DESC LIMIT 5", (ticker,)
            ).fetchall()
            if len(trend_rows) > 1:
                trend = " -> ".join(
                    f"{r['implied_upside']:+.1%}" for r in reversed(trend_rows)
                )
                lines.append(f"    Trend: {trend}")

        return {
            "change_type": "valuation_shift",
            "context_lines": lines,
        }

    # ── Persistence ────────────────────────────────────────────────────

    def _build_event_study(self):
        """Build the structured event-study payload for the log.

        Returns a dict with trigger_type, before, after, delta,
        materiality_score, and context fields.
        """
        r = self._result
        changes = r.get("changes", [])

        # Which checks fired
        trigger_type = [c["type"] for c in changes]

        # Reconstruct before / after / delta from regime + valuation summaries
        rs = r.get("regime_summary") or {}
        vs = r.get("valuation_summary") or {}

        before = {
            "gli": rs.get("gli_value", 0) - rs.get("gli_delta", 0)
                   if rs.get("gli_delta") is not None else None,
            "regime": rs.get("previous_regime"),
            "diffusion": None,
            "momentum": None,
            "avg_upside": vs.get("avg_upside_previous"),
        }
        after = {
            "gli": rs.get("gli_value"),
            "regime": rs.get("current_regime"),
            "diffusion": None,
            "momentum": None,
            "avg_upside": vs.get("avg_upside_current"),
        }

        # Fill diffusion/momentum from individual change entries if they fired
        for c in changes:
            if c["type"] == "diffusion_cross":
                before["diffusion"] = c["before"]
                after["diffusion"] = c["after"]
            elif c["type"] == "momentum_flip":
                before["momentum"] = c["before"]
                after["momentum"] = c["after"]

        delta = {
            "gli": rs.get("gli_delta"),
            "diffusion": (after["diffusion"] - before["diffusion"])
                         if after["diffusion"] is not None and before["diffusion"] is not None
                         else None,
            "momentum": (after["momentum"] - before["momentum"])
                        if after["momentum"] is not None and before["momentum"] is not None
                        else None,
            "avg_upside": vs.get("delta"),
        }

        # Context: how much history we have
        try:
            all_regimes = self._bridge.get_regime_history(limit=999)
        except Exception:
            all_regimes = []
        data_points_available = len(all_regimes)

        # Regime streak: how many consecutive entries share the same regime
        regime_streak = 0
        if all_regimes:
            current = all_regimes[0].get("regime")
            for entry in all_regimes:
                if entry.get("regime") == current:
                    regime_streak += 1
                else:
                    break

        return {
            "trigger_type": trigger_type,
            "before": before,
            "after": after,
            "delta": delta,
            "materiality_score": len(changes),
            "context": {
                "data_points_available": data_points_available,
                "regime_streak": regime_streak,
            },
        }

    def save_log(self) -> str:
        """Write the enriched event-study analysis to a JSON file in shared/soma/logs/.

        Uses pathlib for better path handling relative to __file__.
        """
        if self._result is None:
            self.analyze()

        # Merge the event-study fields into the result
        event_study = self._build_event_study()
        explanations = self.explain_context()
        enriched = {**self._result, **event_study, "historical_context": explanations}

        from pathlib import Path
        logs_dir = Path(__file__).parent / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        path = logs_dir / f"what_changed_{ts}.json"
        with open(path, "w") as f:
            json.dump(enriched, f, indent=2, default=str)
        return str(path.resolve())

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

        # Historical context (the "Why" section)
        if r["changes"]:
            explanations = self.explain_context()
            if explanations:
                print(f"\n{BOLD}--- Historical Context ---{RESET}")
                for exp in explanations:
                    print(f"\n  {CYAN}[{exp['change_type']}]{RESET}")
                    for line in exp["context_lines"]:
                        print(f"    {line}")

        print(f"\n{BOLD}{'=' * 60}{RESET}\n")
