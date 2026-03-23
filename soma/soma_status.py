#!/usr/bin/env python3
"""
SOMA Status Dashboard — one-screen terminal view of the entire system.

Usage:
    python3 ~/Desktop/DABEIBA/shared/soma/soma_status.py
"""

import os
import sys

# Make shared package importable when run as a standalone script
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from shared.soma.soma_bridge import SomaBridge

# ── ANSI codes ────────────────────────────────────────────────────────
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
WHITE = "\033[97m"
RESET = "\033[0m"

W = 62  # dashboard width


def _bar(title):
    pad = W - len(title) - 4
    return f"{BOLD}{CYAN}── {title} {'─' * pad}{RESET}"


def _fresh_label(is_fresh, age_hours):
    if age_hours == float("inf"):
        return f"{RED}NO DATA{RESET}"
    age_str = f"{age_hours:.1f}h ago"
    if is_fresh:
        return f"{GREEN}FRESH{RESET} ({age_str})"
    return f"{RED}STALE{RESET} ({age_str})"


def print_status(db_path: str | None = None) -> None:
    """Print SOMA status dashboard to terminal.

    Uses pathlib for default path handling relative to __file__.
    """
    if db_path is None:
        from pathlib import Path
        db_path = str(Path(__file__).parent / "data" / "soma.db")

    if not os.path.exists(db_path):
        print(f"\n{RED}SOMA database not found at: {db_path}{RESET}")
        print("Run ORACLE first to populate SOMA.\n")
        return

    with SomaBridge(db_path) as db:
        regime = db.get_latest_regime()
        valuations = db.get_latest_valuations()
        portfolio = db.get_latest_portfolio_state()
        outlook = db.get_latest_outlook()
        history = db.get_regime_history(limit=2)
        trades = db.get_trade_log(limit=50)
        regime_fresh, regime_age = db.is_fresh("regime_history")
        portfolio_fresh, portfolio_age = db.is_fresh("portfolio_state")
        outlook_fresh, outlook_age = db.is_fresh("outlook_snapshots")
        schema_v = db.get_schema_version()

        # Record counts
        tables = ["regime_history", "valuations", "trade_log",
                   "outlook_snapshots", "portfolio_state"]
        counts = {}
        for t in tables:
            try:
                row = db.conn.execute(f"SELECT COUNT(*) AS c FROM [{t}]").fetchone()
                counts[t] = row["c"]
            except Exception as e:
                print(f"[SOMA] count query failed for table {t}: {e}", file=sys.stderr)
                counts[t] = 0

    # DB file size
    db_size = os.path.getsize(db_path)
    if db_size < 1024:
        size_str = f"{db_size} B"
    elif db_size < 1024 * 1024:
        size_str = f"{db_size / 1024:.1f} KB"
    else:
        size_str = f"{db_size / (1024 * 1024):.1f} MB"

    # Previous regime for comparison
    prev_regime = history[1] if len(history) >= 2 else None

    # ── Print ─────────────────────────────────────────────────────
    print(f"\n{BOLD}{'=' * W}{RESET}")
    print(f"{BOLD}  SOMA STATUS DASHBOARD{RESET}")
    print(f"{BOLD}{'=' * W}{RESET}")

    # ── MACRO ─────────────────────────────────────────────────────
    print(f"\n{_bar('MACRO')}")
    if regime:
        regime_str = regime["regime"] or "N/A"
        if prev_regime and prev_regime["regime"] != regime["regime"]:
            regime_str = f"{prev_regime['regime']} -> {YELLOW}{regime_str}{RESET}"

        gli_delta_str = ""
        if prev_regime and prev_regime["gli_value"] is not None:
            delta = regime["gli_value"] - prev_regime["gli_value"]
            sign = "+" if delta >= 0 else ""
            gli_delta_str = f"  ({sign}{delta:.2f})"

        mom = regime.get("momentum")
        if mom is not None:
            mom_color = GREEN if mom >= 0 else RED
            mom_str = f"{mom_color}{mom:+.2f}{RESET}"
        else:
            mom_str = "N/A"

        diff = regime.get("diffusion_index")
        diff_str = f"{diff:.1f}%" if diff is not None else "N/A"

        print(f"  Regime:      {regime_str}")
        print(f"  GLI:         {regime['gli_value']}{gli_delta_str}")
        print(f"  Diffusion:   {diff_str}")
        print(f"  Momentum:    {mom_str}")
        print(f"  Data Age:    {_fresh_label(regime_fresh, regime_age)}")

        # Surface GLI spot components if available
        if regime.get("gli_components_json"):
            try:
                import json
                comp = json.loads(regime["gli_components_json"])
                spot = comp.get("spot", {})
                if spot:
                    parts = []
                    if "vix" in spot:
                        parts.append(f"VIX={spot['vix']}")
                    if "ust_10y" in spot:
                        parts.append(f"10Y={spot['ust_10y']}%")
                    if "dxy" in spot:
                        parts.append(f"DXY={spot['dxy']}")
                    if "hy_spread" in spot:
                        parts.append(f"HY={spot['hy_spread']}")
                    if "stress_index" in spot:
                        parts.append(f"Stress={spot['stress_index']}")
                    if parts:
                        print(f"  Context:     {DIM}{', '.join(parts)}{RESET}")
            except Exception as e:
                print(f"[SOMA] could not parse gli_components_json: {e}", file=sys.stderr)
    else:
        print(f"  {DIM}No regime data yet (ORACLE not run){RESET}")

    # ── PORTFOLIO (MANTIS) ────────────────────────────────────────
    print(f"\n{_bar('PORTFOLIO (MANTIS)')}")
    if portfolio:
        cash = portfolio.get("cash_pct")
        total = portfolio.get("total_value")
        dd = portfolio.get("dd_from_hwm")
        exposure = f"{(1 - cash) * 100:.1f}%" if cash is not None else "N/A"
        cash_str = f"{cash * 100:.1f}%" if cash is not None else "N/A"
        total_str = f"${total:,.0f}" if total is not None else "N/A"
        dd_str = f"{dd:.2f}%" if dd is not None else "N/A"
        print(f"  Net Exposure: {exposure}")
        print(f"  Cash:         {cash_str}")
        print(f"  Total Value:  {total_str}")
        print(f"  DD from HWM:  {dd_str}")
        print(f"  Data Age:     {_fresh_label(portfolio_fresh, portfolio_age)}")
        if portfolio.get("module_version"):
            print(f"  Source:        {portfolio['module_version']}")

        # Trade activity summary
        if trades:
            rebalances = [t for t in trades if t.get("action") == "REBALANCE"]
            tier_changes = [t for t in trades if t.get("action") == "TIER_CHANGE"]
            total_trades = len(trades)
            last_trade = trades[0] if trades else None
            print(f"  Trades:       {total_trades} total "
                  f"({len(rebalances)} rebalances, {len(tier_changes)} tier changes)")
            if last_trade:
                print(f"  Last Trade:   {last_trade.get('date', '?')} "
                      f"— {last_trade.get('action', '?')} {last_trade.get('ticker', '?')}")
    else:
        print(f"  {DIM}No portfolio data yet (MANTIS not connected){RESET}")

    # ── VALUATIONS ────────────────────────────────────────────────
    print(f"\n{_bar('VALUATIONS')}")
    if valuations:
        header = f"  {'Ticker':<8} {'Fair Value':>10} {'Price':>10} {'Upside':>8} {'Score':>6}"
        print(f"{WHITE}{header}{RESET}")
        print(f"  {'─' * 46}")
        for v in valuations:
            ticker = v.get("ticker", "?")
            fv = v.get("fair_value")
            price = v.get("current_price")
            upside = v.get("implied_upside")
            score = v.get("execution_score")
            fv_str = f"${fv:,.2f}" if fv is not None else "—"
            price_str = f"${price:,.2f}" if price is not None else "—"
            if upside is not None:
                up_color = GREEN if upside >= 0 else RED
                upside_str = f"{up_color}{upside:+.1%}{RESET}"
            else:
                upside_str = "—"
            score_str = f"{score:.1f}" if score is not None else "—"
            print(f"  {ticker:<8} {fv_str:>10} {price_str:>10} {upside_str:>17} {score_str:>6}")
    else:
        print(f"  {DIM}No valuation data yet{RESET}")

    # ── COMMUNICATION (CIPHER) ─────────────────────────────────────
    print(f"\n{_bar('COMMUNICATION (CIPHER)')}")
    if outlook:
        print(f"  Last Outlook: {outlook.get('date', '?')} (v{outlook.get('version', '?')})")
        print(f"  Data Age:     {_fresh_label(outlook_fresh, outlook_age)}")
        if outlook.get("full_text_hash"):
            print(f"  Hash:         {outlook['full_text_hash'][:16]}")
        if outlook.get("module_version"):
            print(f"  Source:        {outlook['module_version']}")
        # Show key conclusions
        if outlook.get("key_conclusions_json"):
            try:
                import json
                conclusions = json.loads(outlook["key_conclusions_json"])
                if conclusions:
                    print(f"  Conclusions:")
                    for c in conclusions[:5]:
                        print(f"    - {c}")
            except Exception as e:
                print(f"[SOMA] could not parse key_conclusions_json: {e}", file=sys.stderr)
        # Recommend new outlook if regime data is much fresher than outlook
        if regime and outlook_age > regime_age + 24:
            print(f"  {YELLOW}Outlook may be stale — regime data is {outlook_age - regime_age:.0f}h newer{RESET}")
    else:
        print(f"  {DIM}No outlooks yet (CIPHER not connected){RESET}")

    # ── SYSTEM HEALTH ─────────────────────────────────────────────
    print(f"\n{_bar('SYSTEM HEALTH')}")
    # Last ORACLE write
    oracle_ts = regime.get("write_timestamp", "N/A") if regime else "N/A"
    print(f"  Last Write:   {oracle_ts}  {_fresh_label(regime_fresh, regime_age)}")
    print(f"  Schema:       v{schema_v}")
    print(f"  DB Size:      {size_str}")

    # Cloud backup health check
    try:
        _shared_dir = os.path.join(os.path.dirname(__file__), "..")
        if _shared_dir not in sys.path:
            sys.path.insert(0, _shared_dir)
        from cloud_config import cloud_available
        if cloud_available():
            print(f"  Cloud:        {GREEN}CONNECTED{RESET} (~/DABEIBA_Cloud)")
        else:
            print(f"  Cloud:        {YELLOW}UNAVAILABLE{RESET} — offsite backup disabled")
    except ImportError:
        print(f"  Cloud:        {RED}NOT CONFIGURED{RESET} — run setup_cloud.py")
    print(f"  Records:")
    for t in tables:
        label = t.replace("_", " ").title()
        print(f"    {label:<22} {counts[t]:>6}")

    # ── NARRATIVE ALIGNMENT ─────────────────────────────────────────
    print(f"\n{_bar('NARRATIVE ALIGNMENT')}")
    try:
        from shared.soma.narrative_alignment import NarrativeAlignment
        with NarrativeAlignment(db_path) as na:
            result = na.analyze()
            alignment = result.get("alignment", 0)
            n_issues = len(result.get("inconsistencies", []))

            if alignment >= 0.8:
                color = GREEN
                label = "ALIGNED"
            elif alignment >= 0.5:
                color = YELLOW
                label = "PARTIAL"
            else:
                color = RED
                label = "MISALIGNED"

            print(f"  Score: {color}{alignment:.0%} ({label}){RESET}  |  Issues: {n_issues}")

            for inc in result.get("inconsistencies", [])[:3]:
                sev_color = RED if inc["severity"] == "HIGH" else YELLOW
                print(f"  {sev_color}[{inc['severity']}]{RESET} {inc['description'][:60]}")

            missing = [k for k, v in result.get("data_available", {}).items() if not v]
            if missing:
                print(f"  {DIM}Missing: {', '.join(missing)}{RESET}")
    except Exception as e:
        print(f"  {DIM}Alignment unavailable: {e}{RESET}")

    # ── KB VIOLATIONS ────────────────────────────────────────────
    print(f"\n{_bar('KB VIOLATIONS')}")
    try:
        with SomaBridge(db_path) as db_v:
            db_v.initialize_db()
            try:
                rows = db_v.conn.execute(
                    """SELECT severity, COUNT(*) AS cnt
                       FROM kb_violations GROUP BY severity"""
                ).fetchall()
                counts_v = {r["severity"]: r["cnt"] for r in rows}
            except Exception:
                counts_v = {}

            total_v = sum(counts_v.values())
            if total_v == 0:
                print(f"  {GREEN}No violations — clean slate{RESET}")
            else:
                crit = counts_v.get("CRITICAL", 0)
                warn = counts_v.get("WARNING", 0)
                info = counts_v.get("INFO", 0)
                crit_color = RED if crit > 0 else DIM
                warn_color = YELLOW if warn > 0 else DIM
                print(f"  Total: {total_v}  |  "
                      f"{crit_color}CRITICAL: {crit}{RESET}  "
                      f"{warn_color}WARNING: {warn}{RESET}  "
                      f"{DIM}INFO: {info}{RESET}")
                # Show last violation
                try:
                    last = db_v.conn.execute(
                        """SELECT severity, rule_id, description, detected_at
                           FROM kb_violations ORDER BY id DESC LIMIT 1"""
                    ).fetchone()
                    if last:
                        sev_c = RED if last["severity"] == "CRITICAL" else YELLOW
                        print(f"  Last:  {sev_c}[{last['severity']}]{RESET} "
                              f"{last['description'][:50]} ({last['detected_at'][:16]})")
                except Exception:
                    pass
    except Exception as e:
        print(f"  {DIM}Violations unavailable: {e}{RESET}")

    # ── KB RULES ──────────────────────────────────────────────────
    print(f"\n{_bar('KB RULES')}")
    try:
        with SomaBridge(db_path) as db2:
            db2.initialize_db()
            kr = db2.get_kb_reader()
            rules = kr.get_all_rules()
            if not rules:
                print(f"  {DIM}No rules indexed. Run: python3 soma_query.py 'rebuild index'{RESET}")
            else:
                # Summary line
                stale = kr.is_index_stale()
                status_str = f"{YELLOW}STALE — rebuild needed{RESET}" if stale else f"{GREEN}current{RESET}"
                print(f"  Rules: {len(rules)}  |  Index: {status_str}")

                # Rules by source module
                by_module = {}
                for rid, rdata in rules.items():
                    modules = rdata.get("source_module", "UNKNOWN")
                    if isinstance(modules, list):
                        for m in modules:
                            by_module.setdefault(m, []).append(rid)
                    elif isinstance(modules, str):
                        for m in modules.split(","):
                            by_module.setdefault(m.strip(), []).append(rid)

                for module in sorted(by_module):
                    print(f"  {module}: {len(by_module[module])} rules")

                # Recent audit activity
                audits = kr.get_rule_audit(limit=3)
                if audits:
                    print(f"  Last read: {audits[0].get('read_at', '?')[:16]} by {audits[0].get('read_by_module', '?')}")
    except Exception as e:
        print(f"  {DIM}KB status unavailable: {e}{RESET}")

    print(f"\n{BOLD}{'=' * W}{RESET}\n")


if __name__ == "__main__":
    print_status()
