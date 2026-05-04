#!/usr/bin/env python3
"""check_fallback_drift.py — Phase 6.4.

Sync check: the hardcoded `_FALLBACK_*` dicts in each module's
`kb_integration.py` must stay close to whatever is live in SOMA `kb_rules`.
Drift means: (a) the fallback value diverges from the KB rule's `rules`
sub-dict, OR (b) the `_FALLBACK_VERSION` date is older than N days.

When drift is detected the tool prints a per-rule report and, if
`--emit-event` is set, publishes a `FALLBACK_DRIFT_DETECTED` event via
`SomaBridge.publish_event()` so subscribers can act on it.

Usage
-----
  python3 shared/soma/tools/check_fallback_drift.py
  python3 shared/soma/tools/check_fallback_drift.py --warn-days 30 --fail-days 60
  python3 shared/soma/tools/check_fallback_drift.py --emit-event
  python3 shared/soma/tools/check_fallback_drift.py --module ORACLE

Exit codes: 0 = clean, 1 = WARN drift, 2 = FAIL drift (past fail-days).
Designed for a weekly Monday cron run; failures should page ops.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from datetime import datetime, date, timezone
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
_SOMA_ROOT = _HERE.parent
_REPO_ROOT = _SOMA_ROOT.parent.parent  # shared/soma/tools → ..
# Ensure the canonical SOMA package is importable
for _p in (_REPO_ROOT, _REPO_ROOT / "shared", _REPO_ROOT / "shared" / "soma"):
    s = str(_p)
    if s not in sys.path:
        sys.path.insert(0, s)


# ── Registry of kb_integration modules to audit ──────────────────────────
# Each entry: module_label, absolute path to kb_integration.py, and the
# rule_id→fallback-var-name pairs to compare.
#
# Adding a new module? Append here and the weekly cron picks it up.

_MODULES: list[dict[str, Any]] = [
    {
        "label": "ORACLE",
        "path": _REPO_ROOT / "oracle" / "oracle" / "kb_integration.py",
        "rules": {
            "REGIME_ALLOCATIONS_V1": "_FALLBACK_REGIME_ALLOCATIONS",
            "YIELD_CURVE_SIGNALS_V1": "_FALLBACK_YIELD_CURVE",
            "INFLATION_ASSET_MAP_V1": "_FALLBACK_INFLATION_MAP",
            "CREDIT_SPREAD_THRESHOLDS_V1": "_FALLBACK_CREDIT_SPREADS",
            "VALUATION_METHOD_SELECTOR_V1": "_FALLBACK_VALUATION_SELECTOR",
        },
    },
    {
        "label": "MANTIS",
        "path": _REPO_ROOT / "mantis" / "convergence-backtester" / "src" / "kb_integration.py",
        "rules": {
            "POSITION_SIZING_V1": "_FALLBACK_POSITION_SIZING",
            "DRAWDOWN_CONTROLS_V1": "_FALLBACK_DRAWDOWN_CONTROLS",
            "REGIME_TRANSITION_RULES_V1": "_FALLBACK_REGIME_TRANSITIONS",
            "TRANSITION_SPEED_V1": "_FALLBACK_TRANSITION_SPEED",
            "REGIME_ALLOCATIONS_V1": "_FALLBACK_REGIME_ALLOCATIONS",
        },
    },
    {
        "label": "CIPHER",
        "path": _REPO_ROOT / "cipher" / "cipher" / "kb_integration.py",
        "rules": {
            "ADVICE_FRAMEWORK_V1": "_FALLBACK_ADVICE",
            "PRACTICE_FRAMEWORK_V1": "_FALLBACK_PRACTICE",
            "MONEY_SCRIPT_TYPES_V1": "_FALLBACK_MONEY_SCRIPTS",
            "COMMUNICATION_COMPLIANCE_V1": "_FALLBACK_COMMUNICATION_COMPLIANCE",
        },
    },
]


# ── Helpers ──────────────────────────────────────────────────────────────
def _load_module(label: str, path: Path):
    """Load a kb_integration.py by absolute path without polluting sys.modules names."""
    spec = importlib.util.spec_from_file_location(f"_kbi_{label.lower()}", str(path))
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot build spec for {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _parse_fallback_date(module_obj) -> date | None:
    ver = getattr(module_obj, "_FALLBACK_VERSION", None)
    if not ver:
        return None
    try:
        return datetime.strptime(ver.strip(), "%Y-%m-%d").date()
    except Exception:
        return None


def _fetch_kb_rule(rule_id: str) -> dict | None:
    """Read rule_data JSON straight from SOMA's kb_rules table (bypasses KBReader cache)."""
    try:
        from shared.soma.soma_bridge import SomaBridge
    except Exception:
        return None
    try:
        with SomaBridge() as db:
            row = db.conn.execute(
                "SELECT rule_data FROM kb_rules WHERE rule_id = ?",
                (rule_id,),
            ).fetchone()
            if row is None:
                return None
            # row may be sqlite3.Row or tuple
            payload = row[0] if isinstance(row, (tuple, list)) else row["rule_data"]
            return json.loads(payload)
    except Exception:
        return None


def _structural_keys(obj: Any) -> set[str]:
    """Return top-level keys if obj is dict, else an empty set."""
    if isinstance(obj, dict):
        return set(obj.keys())
    return set()


# ── Core check ───────────────────────────────────────────────────────────
def check_module(entry: dict[str, Any], warn_days: int, fail_days: int) -> dict[str, Any]:
    label = entry["label"]
    path = entry["path"]
    results: dict[str, Any] = {
        "label": label,
        "path": str(path),
        "fallback_version": None,
        "days_since_fallback": None,
        "rules": [],
        "worst_level": "OK",
    }

    if not path.exists():
        results["worst_level"] = "FAIL"
        results["rules"].append({"rule_id": "(module missing)", "level": "FAIL",
                                 "note": f"File not found: {path}"})
        return results

    try:
        mod = _load_module(label, path)
    except Exception as e:
        results["worst_level"] = "FAIL"
        results["rules"].append({"rule_id": "(import error)", "level": "FAIL",
                                 "note": f"Could not import {path}: {e}"})
        return results

    fb_date = _parse_fallback_date(mod)
    results["fallback_version"] = getattr(mod, "_FALLBACK_VERSION", None)
    today = datetime.now(timezone.utc).date()
    if fb_date:
        age_days = (today - fb_date).days
        results["days_since_fallback"] = age_days
    else:
        age_days = None

    worst = "OK"
    for rule_id, fb_varname in entry["rules"].items():
        row: dict[str, Any] = {"rule_id": rule_id, "level": "OK", "note": ""}

        fb_val = getattr(mod, fb_varname, None)
        kb_rule = _fetch_kb_rule(rule_id)

        if fb_val is None:
            row["level"] = "WARN"
            row["note"] = f"fallback var {fb_varname} missing in module"
        elif kb_rule is None:
            row["level"] = "WARN"
            row["note"] = "rule not present in SOMA kb_rules — cannot compare"
        else:
            # Prefer the nested 'rules' sub-dict when present (KB YAML convention)
            kb_body = kb_rule.get("rules", kb_rule) if isinstance(kb_rule, dict) else kb_rule
            fb_keys = _structural_keys(fb_val)
            kb_keys = _structural_keys(kb_body)
            if fb_keys and kb_keys:
                missing_in_fb = kb_keys - fb_keys
                extra_in_fb = fb_keys - kb_keys
                if missing_in_fb or extra_in_fb:
                    row["level"] = "WARN"
                    row["note"] = (
                        f"key drift — missing in fallback: {sorted(missing_in_fb) or 'none'}; "
                        f"extra in fallback: {sorted(extra_in_fb) or 'none'}"
                    )

        # Age overlay
        if age_days is not None:
            if age_days >= fail_days and row["level"] != "FAIL":
                row["level"] = "FAIL"
                if row["note"]:
                    row["note"] += f"; fallback age {age_days}d >= fail_days={fail_days}"
                else:
                    row["note"] = f"fallback age {age_days}d >= fail_days={fail_days}"
            elif age_days >= warn_days and row["level"] == "OK":
                row["level"] = "WARN"
                row["note"] = f"fallback age {age_days}d >= warn_days={warn_days}"

        # Track worst across the module
        if row["level"] == "FAIL":
            worst = "FAIL"
        elif row["level"] == "WARN" and worst != "FAIL":
            worst = "WARN"

        results["rules"].append(row)

    results["worst_level"] = worst
    return results


def _emit_event(report: list[dict], warn_days: int, fail_days: int) -> None:
    """Publish a FALLBACK_DRIFT_DETECTED event if any module is not OK."""
    any_drift = any(m.get("worst_level") != "OK" for m in report)
    if not any_drift:
        return
    try:
        from shared.soma.soma_bridge import SomaBridge
    except Exception:
        return
    try:
        with SomaBridge() as db:
            db.publish_event(
                event_type="FALLBACK_DRIFT_DETECTED",
                payload={
                    "summary": [
                        {"label": m["label"], "worst_level": m["worst_level"],
                         "fallback_version": m["fallback_version"],
                         "days_since_fallback": m["days_since_fallback"]}
                        for m in report
                    ],
                    "warn_days": warn_days,
                    "fail_days": fail_days,
                },
                source_module="soma_tools",
                correlation_key="phase_6_4_fallback_drift",
            )
    except Exception as e:
        print(f"[check_fallback_drift] event publish skipped: {e}", file=sys.stderr)


# ── CLI ──────────────────────────────────────────────────────────────────
def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--warn-days", type=int, default=30,
                   help="Age threshold in days for WARN (default 30)")
    p.add_argument("--fail-days", type=int, default=60,
                   help="Age threshold in days for FAIL (default 60)")
    p.add_argument("--module", default=None, help="Restrict to a single module label (ORACLE|MANTIS|CIPHER)")
    p.add_argument("--emit-event", action="store_true",
                   help="Publish a FALLBACK_DRIFT_DETECTED event on drift")
    p.add_argument("--json", action="store_true", help="Emit machine-readable JSON report")
    args = p.parse_args(argv)

    target = [m for m in _MODULES if args.module is None or m["label"] == args.module.upper()]
    if not target:
        print(f"No modules match --module={args.module}", file=sys.stderr)
        return 2

    report = [check_module(m, args.warn_days, args.fail_days) for m in target]

    if args.json:
        print(json.dumps(report, default=str, indent=2))
    else:
        for m in report:
            tag = m["worst_level"]
            age = m["days_since_fallback"]
            ver = m["fallback_version"]
            print(f"[{tag}] {m['label']:7} fallback={ver} age={age}d  path={m['path']}")
            for r in m["rules"]:
                if r["level"] != "OK":
                    print(f"    - {r['level']:4} {r['rule_id']:32} {r['note']}")
            if all(r["level"] == "OK" for r in m["rules"]):
                print("    - all rules match SOMA and within age window")

    if args.emit_event:
        _emit_event(report, args.warn_days, args.fail_days)

    # Exit code: worst across modules
    if any(m["worst_level"] == "FAIL" for m in report):
        return 2
    if any(m["worst_level"] == "WARN" for m in report):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
