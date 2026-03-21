#!/usr/bin/env python3
"""
SOMA Query CLI — ask structured questions about SOMA data from the terminal.

Usage:
    python3 ~/Desktop/DABEIBA/shared/soma/soma_query.py "last regime change"
    python3 ~/Desktop/DABEIBA/shared/soma/soma_query.py "gli < 40"
    python3 ~/Desktop/DABEIBA/shared/soma/soma_query.py "cheapest"
    python3 ~/Desktop/DABEIBA/shared/soma/soma_query.py "help"

How it works:
    Parses your question using simple keyword matching (no AI, no embeddings).
    Maps it to the right SomaBridge read method and prints a clean terminal table.
"""

import os
import re
import sys

# Make shared package importable when run standalone
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from shared.soma.soma_bridge import SomaBridge

# ── ANSI codes ────────────────────────────────────────────────────────
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RESET = "\033[0m"
W = 62


def _title(text):
    print(f"\n{BOLD}{CYAN}{'=' * W}{RESET}")
    print(f"{BOLD}  {text}{RESET}")
    print(f"{BOLD}{CYAN}{'=' * W}{RESET}")


def _no_data(msg="No data yet — run ORACLE first."):
    print(f"\n  {YELLOW}{msg}{RESET}\n")


# ── REGIME queries ────────────────────────────────────────────────────

def query_last_regime_change(db):
    """Find the most recent pair where regime changed."""
    history = db.get_regime_history(limit=500)
    if len(history) < 2:
        _no_data("Not enough regime history to find a transition.")
        return
    for i in range(len(history) - 1):
        cur, prev = history[i], history[i + 1]
        if cur["regime"] != prev["regime"]:
            _title("Last Regime Change")
            print(f"\n  {CYAN}Date:{RESET}        {cur['date']}")
            print(f"  {CYAN}From:{RESET}        {prev['regime']}")
            print(f"  {CYAN}To:{RESET}          {RED}{cur['regime']}{RESET}")
            print(f"  {CYAN}GLI before:{RESET}  {prev['gli_value']}")
            print(f"  {CYAN}GLI after:{RESET}   {cur['gli_value']}")
            print()
            return
    print(f"\n  {GREEN}No regime changes found in history — regime has been stable.{RESET}\n")


def query_regime_history(db):
    """Show last 10 regime entries."""
    history = db.get_regime_history(limit=10)
    if not history:
        _no_data()
        return
    _title("Regime History (last 10)")
    print(f"\n  {'Date':<12} {'Regime':<14} {'GLI':>7} {'Diff':>7} {'Mom':>7}")
    print(f"  {'─' * 50}")
    for h in history:
        print(f"  {h['date']:<12} {h['regime']:<14} {h['gli_value']:>7.2f} "
              f"{h['diffusion_index']:>7.1f} {h['momentum']:>7.2f}")
    print()


def query_regime_streak(db):
    """Count consecutive entries with current regime."""
    history = db.get_regime_history(limit=500)
    if not history:
        _no_data()
        return
    current = history[0]["regime"]
    streak = 0
    start_date = history[0]["date"]
    for h in history:
        if h["regime"] == current:
            streak += 1
            start_date = h["date"]
        else:
            break
    _title("Regime Streak")
    print(f"\n  {CYAN}Current regime:{RESET}  {current}")
    print(f"  {CYAN}Streak:{RESET}          {streak} consecutive entries")
    print(f"  {CYAN}Since:{RESET}           {start_date}")
    print()


# ── GLI queries ───────────────────────────────────────────────────────

def query_gli_below(db, threshold):
    """Find most recent entry where GLI < threshold."""
    history = db.get_regime_history(limit=500)
    if not history:
        _no_data()
        return
    for h in history:
        if h["gli_value"] < threshold:
            _title(f"Last Time GLI < {threshold}")
            print(f"\n  {CYAN}Date:{RESET}    {h['date']}")
            print(f"  {CYAN}GLI:{RESET}     {h['gli_value']:.2f}")
            print(f"  {CYAN}Regime:{RESET}  {h['regime']}")
            print()
            return
    print(f"\n  {GREEN}GLI has never been below {threshold} in recorded history.{RESET}\n")


def query_gli_above(db, threshold):
    """Find most recent entry where GLI > threshold."""
    history = db.get_regime_history(limit=500)
    if not history:
        _no_data()
        return
    for h in history:
        if h["gli_value"] > threshold:
            _title(f"Last Time GLI > {threshold}")
            print(f"\n  {CYAN}Date:{RESET}    {h['date']}")
            print(f"  {CYAN}GLI:{RESET}     {h['gli_value']:.2f}")
            print(f"  {CYAN}Regime:{RESET}  {h['regime']}")
            print()
            return
    print(f"\n  {GREEN}GLI has never been above {threshold} in recorded history.{RESET}\n")


def query_gli_trend(db):
    """Show last 10 GLI values with direction arrows."""
    history = db.get_regime_history(limit=10)
    if not history:
        _no_data()
        return
    _title("GLI Trend (last 10)")
    print(f"\n  {'Date':<12} {'GLI':>7}  Direction")
    print(f"  {'─' * 35}")
    for i, h in enumerate(history):
        if i < len(history) - 1:
            prev_gli = history[i + 1]["gli_value"]
            cur_gli = h["gli_value"]
            if cur_gli > prev_gli + 0.1:
                arrow = f"{GREEN}\u2191{RESET}"
            elif cur_gli < prev_gli - 0.1:
                arrow = f"{RED}\u2193{RESET}"
            else:
                arrow = f"{YELLOW}\u2192{RESET}"
        else:
            arrow = " "
        print(f"  {h['date']:<12} {h['gli_value']:>7.2f}  {arrow}")
    print()


# ── VALUATION queries ─────────────────────────────────────────────────

def query_current_valuations(db):
    """Show latest run's valuations table."""
    vals = db.get_latest_valuations()
    if not vals:
        _no_data("No valuation data yet.")
        return
    _title("Current Valuations")
    print(f"\n  {'Ticker':<8} {'Fair Value':>10} {'Price':>10} {'Upside':>8} {'Score':>6}")
    print(f"  {'─' * 46}")
    for v in vals:
        fv = f"${v['fair_value']:,.2f}" if v.get("fair_value") is not None else "—"
        price = f"${v['current_price']:,.2f}" if v.get("current_price") is not None else "—"
        upside = v.get("implied_upside")
        if upside is not None:
            color = GREEN if upside >= 0 else RED
            up_str = f"{color}{upside:+.1%}{RESET}"
        else:
            up_str = "—"
        score = f"{v['execution_score']:.1f}" if v.get("execution_score") is not None else "—"
        print(f"  {v['ticker']:<8} {fv:>10} {price:>10} {up_str:>17} {score:>6}")
    print()


def query_ticker_valuation(db, ticker):
    """Show a specific ticker's latest valuation + last 5 entries."""
    ticker = ticker.upper()
    vals = db.get_latest_valuations()
    current = None
    for v in vals:
        if v["ticker"] == ticker:
            current = v
            break
    if not current:
        _no_data(f"No valuation data for {ticker}.")
        return

    _title(f"{ticker} Valuation")
    print(f"\n  {CYAN}Fair Value:{RESET}  ${current['fair_value']:,.2f}")
    print(f"  {CYAN}Price:{RESET}       ${current['current_price']:,.2f}")
    upside = current["implied_upside"]
    color = GREEN if upside >= 0 else RED
    print(f"  {CYAN}Upside:{RESET}      {color}{upside:+.1%}{RESET}")
    if current.get("execution_score") is not None:
        print(f"  {CYAN}Score:{RESET}       {current['execution_score']:.1f}")

    # History: last 5 entries for this ticker
    conn = db.conn
    rows = conn.execute(
        "SELECT date, implied_upside, current_price FROM valuations "
        "WHERE ticker = ? ORDER BY id DESC LIMIT 5", (ticker,)
    ).fetchall()
    if len(rows) > 1:
        print(f"\n  {BOLD}History (last {len(rows)} entries):{RESET}")
        print(f"  {'Date':<12} {'Price':>10} {'Upside':>8}")
        print(f"  {'─' * 32}")
        for r in rows:
            p = f"${r['current_price']:,.2f}" if r["current_price"] is not None else "—"
            u = r["implied_upside"]
            c = GREEN if u >= 0 else RED
            print(f"  {r['date']:<12} {p:>10} {c}{u:+.1%}{RESET}")
    print()


def query_cheapest(db):
    """Sort by implied_upside descending, show top 5."""
    vals = db.get_latest_valuations()
    if not vals:
        _no_data("No valuation data yet.")
        return
    ranked = sorted(vals, key=lambda v: v.get("implied_upside") or 0, reverse=True)
    _title("Most Undervalued (Top 5)")
    print(f"\n  {'Ticker':<8} {'Upside':>8} {'Fair Value':>10} {'Price':>10}")
    print(f"  {'─' * 40}")
    for v in ranked[:5]:
        up = v.get("implied_upside")
        color = GREEN if up and up >= 0 else RED
        up_str = f"{color}{up:+.1%}{RESET}" if up is not None else "—"
        fv = f"${v['fair_value']:,.2f}" if v.get("fair_value") is not None else "—"
        price = f"${v['current_price']:,.2f}" if v.get("current_price") is not None else "—"
        print(f"  {v['ticker']:<8} {up_str:>17} {fv:>10} {price:>10}")
    print()


def query_most_expensive(db):
    """Sort by implied_upside ascending, show top 5."""
    vals = db.get_latest_valuations()
    if not vals:
        _no_data("No valuation data yet.")
        return
    ranked = sorted(vals, key=lambda v: v.get("implied_upside") or 0)
    _title("Most Overvalued (Top 5)")
    print(f"\n  {'Ticker':<8} {'Upside':>8} {'Fair Value':>10} {'Price':>10}")
    print(f"  {'─' * 40}")
    for v in ranked[:5]:
        up = v.get("implied_upside")
        color = GREEN if up and up >= 0 else RED
        up_str = f"{color}{up:+.1%}{RESET}" if up is not None else "—"
        fv = f"${v['fair_value']:,.2f}" if v.get("fair_value") is not None else "—"
        price = f"${v['current_price']:,.2f}" if v.get("current_price") is not None else "—"
        print(f"  {v['ticker']:<8} {up_str:>17} {fv:>10} {price:>10}")
    print()


# ── PORTFOLIO queries ─────────────────────────────────────────────────

def query_portfolio(db):
    """Show latest portfolio state."""
    p = db.get_latest_portfolio_state()
    if not p:
        _no_data("No portfolio data yet (MANTIS not connected).")
        return
    _title("Portfolio State")
    cash = p.get("cash_pct")
    print(f"\n  {CYAN}Total Value:{RESET}  ${p['total_value']:,.0f}" if p.get("total_value") else "")
    if cash is not None:
        print(f"  {CYAN}Cash:{RESET}         {cash * 100:.1f}%")
        print(f"  {CYAN}Exposure:{RESET}     {(1 - cash) * 100:.1f}%")
    if p.get("dd_from_hwm") is not None:
        print(f"  {CYAN}DD from HWM:{RESET}  {p['dd_from_hwm']:.2f}%")
    print()


def query_trades(db):
    """Show last 10 trades."""
    trades = db.get_trade_log(limit=10)
    if not trades:
        _no_data("No trades recorded yet.")
        return
    _title("Trade Log (last 10)")
    print(f"\n  {'Date':<12} {'Ticker':<8} {'Action':<10} {'Price':>10} {'Weight':>7}")
    print(f"  {'─' * 50}")
    for t in trades:
        price = f"${t['price']:,.2f}" if t.get("price") is not None else "—"
        weight = f"{t['weight']:.1%}" if t.get("weight") is not None else "—"
        print(f"  {t['date']:<12} {t['ticker']:<8} {t['action']:<10} {price:>10} {weight:>7}")
    print()


def query_last_trade_ticker(db, ticker):
    """Show most recent trade for a specific ticker."""
    ticker = ticker.upper()
    conn = db.conn
    row = conn.execute(
        "SELECT * FROM trade_log WHERE ticker = ? ORDER BY id DESC LIMIT 1",
        (ticker,)
    ).fetchone()
    if not row:
        _no_data(f"No trades found for {ticker}.")
        return
    t = dict(row)
    _title(f"Last Trade: {ticker}")
    print(f"\n  {CYAN}Date:{RESET}    {t['date']}")
    print(f"  {CYAN}Action:{RESET}  {t['action']}")
    price = f"${t['price']:,.2f}" if t.get("price") is not None else "—"
    print(f"  {CYAN}Price:{RESET}   {price}")
    weight = f"{t['weight']:.1%}" if t.get("weight") is not None else "—"
    print(f"  {CYAN}Weight:{RESET}  {weight}")
    if t.get("reason"):
        print(f"  {CYAN}Reason:{RESET}  {t['reason']}")
    print()


# ── OUTLOOK queries ───────────────────────────────────────────────────

def query_latest_outlook(db):
    """Show most recent outlook snapshot."""
    o = db.get_latest_outlook()
    if not o:
        _no_data("No outlooks written yet.")
        return
    _title("Latest Outlook")
    print(f"\n  {CYAN}Date:{RESET}     {o['date']}")
    print(f"  {CYAN}Version:{RESET}  {o.get('version', '?')}")
    if o.get("key_conclusions_json"):
        try:
            import json
            conclusions = json.loads(o["key_conclusions_json"])
            print(f"  {CYAN}Key Conclusions:{RESET}")
            for c in conclusions:
                print(f"    - {c}")
        except Exception:
            pass
    print()


def query_outlook_history(db):
    """Show last 5 outlook snapshots."""
    conn = db.conn
    rows = conn.execute(
        "SELECT * FROM outlook_snapshots ORDER BY id DESC LIMIT 5"
    ).fetchall()
    if not rows:
        _no_data("No outlooks written yet.")
        return
    _title("Outlook History (last 5)")
    print(f"\n  {'Date':<12} {'Version':<10} {'Hash':<20}")
    print(f"  {'─' * 42}")
    for r in rows:
        r = dict(r)
        h = (r.get("full_text_hash") or "—")[:16]
        print(f"  {r['date']:<12} {r.get('version', '?'):<10} {h:<20}")
    print()


# ── CLIENT PROFILE queries ───────────────────────────────────────────

def query_clients(db):
    """List all client profiles."""
    profiles = db.get_all_client_profiles()
    if not profiles:
        _no_data("No client profiles yet. Add one with CIPHER or SomaBridge.")
        return
    _title(f"Client Profiles ({len(profiles)})")
    print(f"\n  {'Alias':<14} {'Positioning':<14} {'Risk':<8} {'Horizon':<8} {'Style':<14} {'Last Contact':<12}")
    print(f"  {'─' * 72}")
    for p in profiles:
        name = p.get('display_name') or p['client_alias']
        pos = p.get('positioning', '—')
        risk = p.get('risk_tolerance', '—')
        horizon = p.get('time_horizon', '—')
        style = p.get('communication_style', '—')
        last = p.get('last_contact_date', '—') or '—'
        print(f"  {name:<14} {pos:<14} {risk:<8} {horizon:<8} {style:<14} {last:<12}")
    print()


def query_client_detail(db, alias):
    """Show full detail for a single client profile."""
    profile = db.get_client_profile(alias)
    if not profile:
        # Try case-insensitive search
        all_profiles = db.get_all_client_profiles()
        for p in all_profiles:
            if p['client_alias'].lower() == alias.lower():
                profile = p
                break
    if not profile:
        _no_data(f"No client profile found for '{alias}'. Try: clients")
        return

    name = profile.get('display_name') or profile['client_alias']
    _title(f"Client: {name}")

    print(f"\n  {BOLD}THESIS POSITIONING{RESET}")
    print(f"  {CYAN}Positioning:{RESET}      {profile.get('positioning', '—')}")
    print(f"  {CYAN}Risk Tolerance:{RESET}   {profile.get('risk_tolerance', '—')}")
    print(f"  {CYAN}Time Horizon:{RESET}     {profile.get('time_horizon', '—')}")
    print(f"  {CYAN}Wealth Level:{RESET}     {profile.get('wealth_level', '—')}")

    print(f"\n  {BOLD}MACRO BIAS{RESET}")
    print(f"  {CYAN}Macro Bias:{RESET}       {profile.get('macro_bias', '—')}")
    sens = profile.get('regime_sensitivity', '—')
    sens_color = RED if sens == 'high' else GREEN if sens == 'low' else YELLOW
    print(f"  {CYAN}Regime Sens.:{RESET}    {sens_color}{sens}{RESET}")

    if profile.get('sector_convictions_json'):
        try:
            import json
            sectors = json.loads(profile['sector_convictions_json'])
            print(f"\n  {BOLD}SECTOR CONVICTIONS{RESET}")
            for s in sectors:
                conv_color = GREEN if s.get('conviction') == 'high' else YELLOW if s.get('conviction') == 'medium' else DIM
                print(f"    {s.get('sector', '?'):<16} {conv_color}{s.get('conviction', '?')}{RESET}")
        except Exception:
            pass

    print(f"\n  {BOLD}COMMUNICATION{RESET}")
    print(f"  {CYAN}Style:{RESET}            {profile.get('communication_style', '—')}")
    print(f"  {CYAN}Frequency:{RESET}        {profile.get('preferred_frequency', '—')}")
    print(f"  {CYAN}Channel:{RESET}          {profile.get('preferred_channel', '—')}")

    print(f"\n  {BOLD}CFA FRAMEWORK{RESET}")
    print(f"  {CYAN}Money Script:{RESET}     {profile.get('money_script', '—')}")
    print(f"  {CYAN}Primary Goal:{RESET}     {profile.get('primary_goal', '—')}")
    if profile.get('known_biases_json'):
        try:
            import json
            biases = json.loads(profile['known_biases_json'])
            print(f"  {CYAN}Known Biases:{RESET}     {', '.join(biases)}")
        except Exception:
            pass

    print(f"\n  {BOLD}RELATIONSHIP{RESET}")
    last = profile.get('last_contact_date', '—') or '—'
    last_type = profile.get('last_contact_type', '—') or '—'
    next_rev = profile.get('next_review_date', '—') or '—'
    print(f"  {CYAN}Last Contact:{RESET}     {last} ({last_type})")
    print(f"  {CYAN}Next Review:{RESET}      {next_rev}")
    if profile.get('notes'):
        print(f"  {CYAN}Notes:{RESET}            {profile['notes']}")

    # Show recent interactions
    interactions = db.get_client_interactions(profile['client_alias'], limit=5)
    if interactions:
        print(f"\n  {BOLD}RECENT INTERACTIONS{RESET}")
        print(f"  {'Date':<12} {'Type':<14} {'Topic'}")
        print(f"  {'─' * 50}")
        for ix in interactions:
            topic = ix.get('topic', '—') or '—'
            print(f"  {ix['date']:<12} {ix['interaction_type']:<14} {topic}")
    print()


def query_clients_due(db):
    """Show clients due for contact."""
    due = db.get_clients_due_for_contact()
    if not due:
        _no_data("No clients due for contact right now.")
        return
    _title(f"Clients Due for Contact ({len(due)})")
    print(f"\n  {'Alias':<14} {'Review Date':<12} {'Last Contact':<12} {'Positioning'}")
    print(f"  {'─' * 54}")
    for p in due:
        name = p.get('display_name') or p['client_alias']
        review = p.get('next_review_date', '—')
        last = p.get('last_contact_date', '—') or 'never'
        pos = p.get('positioning', '—')
        print(f"  {name:<14} {review:<12} {last:<12} {pos}")
    print()


def query_clients_by_positioning(db, positioning):
    """Show clients filtered by positioning type."""
    clients = db.get_clients_by_positioning(positioning)
    if not clients:
        _no_data(f"No clients with '{positioning}' positioning.")
        return
    _title(f"{positioning.title()} Clients ({len(clients)})")
    print(f"\n  {'Alias':<14} {'Risk':<8} {'Macro Bias':<12} {'Goal'}")
    print(f"  {'─' * 50}")
    for p in clients:
        name = p.get('display_name') or p['client_alias']
        risk = p.get('risk_tolerance', '—')
        bias = p.get('macro_bias', '—')
        goal = p.get('primary_goal', '—') or '—'
        print(f"  {name:<14} {risk:<8} {bias:<12} {goal}")
    print()


# ── META queries ──────────────────────────────────────────────────────

def query_status(db):
    """Run the SOMA status dashboard."""
    from shared.soma.soma_status import print_status
    print_status()


def query_health(db):
    """Show table record counts, db size, freshness."""
    _title("SOMA Health")
    db_path = db.db_path
    db_size = os.path.getsize(db_path)
    if db_size < 1024:
        size_str = f"{db_size} B"
    elif db_size < 1024 * 1024:
        size_str = f"{db_size / 1024:.1f} KB"
    else:
        size_str = f"{db_size / (1024 * 1024):.1f} MB"

    print(f"\n  {CYAN}Database:{RESET}  {db_path}")
    print(f"  {CYAN}Size:{RESET}      {size_str}")
    print(f"  {CYAN}Schema:{RESET}    v{db.get_schema_version()}")

    tables = ["regime_history", "valuations", "trade_log",
              "outlook_snapshots", "portfolio_state",
              "client_profiles", "client_interactions"]
    print(f"\n  {'Table':<22} {'Records':>8}  Freshness")
    print(f"  {'─' * 52}")
    for t in tables:
        try:
            row = db.conn.execute(f"SELECT COUNT(*) AS c FROM [{t}]").fetchone()
            count = row["c"]
        except Exception:
            count = 0
        fresh, age = db.is_fresh(t)
        if age == float("inf"):
            fresh_str = f"{RED}NO DATA{RESET}"
        elif fresh:
            fresh_str = f"{GREEN}FRESH{RESET} ({age:.1f}h)"
        else:
            fresh_str = f"{RED}STALE{RESET} ({age:.1f}h)"
        label = t.replace("_", " ").title()
        print(f"  {label:<22} {count:>8}  {fresh_str}")
    print()


def query_help(_db=None):
    """Print all available queries."""
    _title("SOMA Query — Available Commands")
    sections = [
        ("REGIME", [
            ('"last regime change"', "When did the regime last shift?"),
            ('"regime history"', "Last 10 regime entries"),
            ('"regime streak"', "How long in current regime?"),
        ]),
        ("GLI", [
            ('"gli < 40"', "Last time GLI was below a number"),
            ('"gli > 60"', "Last time GLI was above a number"),
            ('"gli trend"', "Last 10 GLI values with direction"),
        ]),
        ("VALUATIONS", [
            ('"valuations"', "Current valuations table"),
            ('"NVDA valuation"', "Single ticker detail + history"),
            ('"cheapest"', "Top 5 most undervalued"),
            ('"most expensive"', "Top 5 most overvalued"),
        ]),
        ("PORTFOLIO", [
            ('"portfolio"', "Current portfolio state"),
            ('"trades"', "Last 10 trades"),
            ('"last trade AAPL"', "Most recent trade for a ticker"),
        ]),
        ("OUTLOOK", [
            ('"last outlook"', "Latest outlook snapshot"),
            ('"outlook history"', "Last 5 outlooks"),
        ]),
        ("KNOWLEDGE BASE", [
            ('"kb list"', "List all KB files with descriptions"),
            ('"kb [keywords]"', "Search KB for matching content"),
            ('"kb sections macro"', "Show section headings for a KB file"),
            ('"what is GLI"', "Search KB (alias for kb search)"),
            ('"explain drawdown"', "Search KB (alias for kb search)"),
        ]),
        ("CLIENTS", [
            ('"clients"', "List all client profiles"),
            ('"client JSmith"', "Full detail for one client"),
            ('"clients due"', "Clients due for contact/review"),
            ('"conservative clients"', "Filter by positioning"),
            ('"aggressive clients"', "Filter by positioning"),
        ]),
        ("META", [
            ('"status"', "Full SOMA status dashboard"),
            ('"health"', "Table counts, DB size, freshness"),
            ('"help"', "This help message"),
        ]),
    ]
    for section, commands in sections:
        print(f"\n  {BOLD}{section}{RESET}")
        for cmd, desc in commands:
            print(f"    {cmd:<26} {DIM}{desc}{RESET}")
    print()


# ── KNOWLEDGE BASE queries ────────────────────────────────────────────

_KB_DIR = os.path.join(os.path.dirname(__file__), "knowledge")

# Map short aliases to filenames for direct file access
_KB_FILES = {
    "macro": "macro_regimes.md",
    "regimes": "macro_regimes.md",
    "liquidity": "macro_regimes.md",
    "gli": "macro_regimes.md",
    "valuation": "valuation_models.md",
    "dcf": "valuation_models.md",
    "portfolio construction": "valuation_models.md",
    "fixed income": "valuation_models.md",
    "bonds": "valuation_models.md",
    "communication": "communication_compliance.md",
    "compliance": "communication_compliance.md",
    "ethics": "communication_compliance.md",
    "gips": "communication_compliance.md",
    "advice": "communication_compliance.md",
    "practice": "communication_compliance.md",
    "epic": "communication_compliance.md",
    "mantis": "mantis_mechanics.md",
    "execution": "mantis_mechanics.md",
    "position sizing": "mantis_mechanics.md",
    "rebalancing": "mantis_mechanics.md",
    "drawdown": "mantis_mechanics.md",
    "stop loss": "mantis_mechanics.md",
}


def _search_kb_files(keywords):
    """Search all KB markdown files for lines matching any keyword.

    Returns a list of (filename, section_heading, matching_lines) tuples.
    """
    if not os.path.isdir(_KB_DIR):
        return []

    results = []
    for fname in sorted(os.listdir(_KB_DIR)):
        if not fname.endswith(".md"):
            continue
        filepath = os.path.join(_KB_DIR, fname)
        try:
            with open(filepath, "r") as f:
                lines = f.readlines()
        except Exception:
            continue

        current_section = fname.replace(".md", "").replace("_", " ").title()
        section_matches = []
        in_frontmatter = False

        for line in lines:
            stripped = line.strip()
            # Skip YAML frontmatter
            if stripped == "---":
                in_frontmatter = not in_frontmatter
                continue
            if in_frontmatter:
                continue
            # Track current section heading
            if stripped.startswith("## "):
                current_section = stripped.lstrip("# ").strip()
            elif stripped.startswith("### "):
                current_section = stripped.lstrip("# ").strip()

            # Check if any keyword appears in this line (case-insensitive)
            line_lower = stripped.lower()
            if any(kw in line_lower for kw in keywords):
                section_matches.append((current_section, stripped))

        if section_matches:
            results.append((fname, section_matches))

    return results


def query_kb_search(_db, search_terms):
    """Search the knowledge base for matching content."""
    keywords = [t.strip().lower() for t in search_terms.split() if len(t.strip()) > 2]
    if not keywords:
        _no_data("Search terms too short. Try: kb position sizing")
        return

    if not os.path.isdir(_KB_DIR):
        _no_data("Knowledge base not found. Expected at: " + _KB_DIR)
        return

    results = _search_kb_files(keywords)

    if not results:
        _title(f"KB Search: \"{search_terms}\"")
        print(f"\n  {YELLOW}No matches found. Try different keywords.{RESET}")
        print(f"  {DIM}Available KB files:{RESET}")
        for f in sorted(os.listdir(_KB_DIR)):
            if f.endswith(".md"):
                print(f"    {f}")
        print()
        return

    _title(f"KB Search: \"{search_terms}\"")

    total_matches = sum(len(matches) for _, matches in results)
    print(f"\n  {GREEN}{total_matches} matches across {len(results)} file(s){RESET}\n")

    for fname, matches in results:
        file_label = fname.replace(".md", "").replace("_", " ").title()
        print(f"  {BOLD}{CYAN}[{file_label}]{RESET}")

        # Group by section, show up to 5 matches per file
        shown = 0
        last_section = None
        for section, line in matches:
            if shown >= 8:
                remaining = len(matches) - shown
                print(f"    {DIM}... and {remaining} more matches{RESET}")
                break
            if section != last_section:
                print(f"    {YELLOW}{section}{RESET}")
                last_section = section
            # Truncate long lines
            display = line[:100] + "..." if len(line) > 100 else line
            # Highlight keywords
            for kw in keywords:
                # Case-insensitive highlight
                idx = display.lower().find(kw)
                if idx >= 0:
                    original = display[idx:idx + len(kw)]
                    display = display[:idx] + f"{GREEN}{BOLD}{original}{RESET}" + display[idx + len(kw):]
                    break  # one highlight per line is enough
            print(f"      {display}")
            shown += 1
        print()


def query_kb_list(_db=None):
    """List all knowledge base files with their descriptions."""
    if not os.path.isdir(_KB_DIR):
        _no_data("Knowledge base not found.")
        return

    _title("Knowledge Base Files")
    files = sorted(f for f in os.listdir(_KB_DIR) if f.endswith(".md"))
    if not files:
        _no_data("No knowledge base files found.")
        return

    for fname in files:
        filepath = os.path.join(_KB_DIR, fname)
        # Read first few lines to get description from frontmatter
        desc = ""
        line_count = 0
        try:
            with open(filepath, "r") as f:
                in_fm = False
                for line in f:
                    line_count += 1
                    stripped = line.strip()
                    if stripped == "---":
                        in_fm = not in_fm
                        continue
                    if in_fm and stripped.startswith("description:"):
                        desc = stripped.split(":", 1)[1].strip()
        except Exception:
            pass

        label = fname.replace(".md", "").replace("_", " ").title()
        print(f"\n  {BOLD}{label}{RESET} ({fname})")
        print(f"    {DIM}{line_count} lines{RESET}")
        if desc:
            print(f"    {desc}")
    print()


def query_kb_section(_db, filename_key):
    """Show the table of contents (## headings) for a specific KB file."""
    # Resolve alias to filename
    target = _KB_FILES.get(filename_key.lower())
    if not target:
        # Try direct match
        for f in os.listdir(_KB_DIR) if os.path.isdir(_KB_DIR) else []:
            if filename_key.lower() in f.lower():
                target = f
                break
    if not target:
        _no_data(f"No KB file matching \"{filename_key}\". Try: kb list")
        return

    filepath = os.path.join(_KB_DIR, target)
    if not os.path.exists(filepath):
        _no_data(f"File not found: {target}")
        return

    label = target.replace(".md", "").replace("_", " ").title()
    _title(f"KB: {label} — Sections")

    try:
        with open(filepath, "r") as f:
            in_fm = False
            for line in f:
                stripped = line.strip()
                if stripped == "---":
                    in_fm = not in_fm
                    continue
                if in_fm:
                    continue
                if stripped.startswith("## "):
                    heading = stripped.lstrip("# ").strip()
                    print(f"\n  {BOLD}{heading}{RESET}")
                elif stripped.startswith("### "):
                    heading = stripped.lstrip("# ").strip()
                    print(f"    {heading}")
    except Exception as e:
        _no_data(f"Error reading {target}: {e}")
    print()


# ── Query router ──────────────────────────────────────────────────────

def route_query(query, db):
    """Parse a query string and dispatch to the right handler."""
    q = query.strip().lower()

    # ── Help ──
    if q in ("help", "?"):
        query_help(db)
        return

    # ── Status / health ──
    if q == "status":
        query_status(db)
        return
    if q == "health":
        query_health(db)
        return

    # ── Regime ──
    if q in ("last regime change", "last transition", "regime change"):
        query_last_regime_change(db)
        return
    if q in ("regime history", "regimes"):
        query_regime_history(db)
        return
    if "regime streak" in q or "how long in" in q:
        query_regime_streak(db)
        return

    # ── GLI with threshold ──
    m = re.search(r'gli\s*<\s*([\d.]+)', q) or re.search(r'gli\s+below\s+([\d.]+)', q)
    if m:
        query_gli_below(db, float(m.group(1)))
        return
    m = re.search(r'gli\s*>\s*([\d.]+)', q) or re.search(r'gli\s+above\s+([\d.]+)', q)
    if m:
        query_gli_above(db, float(m.group(1)))
        return
    if q in ("gli trend", "gli"):
        query_gli_trend(db)
        return

    # ── Valuations ──
    if q in ("valuations", "current valuations", "vals"):
        query_current_valuations(db)
        return
    if q in ("cheapest", "most undervalued", "undervalued"):
        query_cheapest(db)
        return
    if q in ("most expensive", "most overvalued", "overvalued", "expensive"):
        query_most_expensive(db)
        return

    # ── Single ticker valuation (e.g., "NVDA valuation" or "valuation NVDA") ──
    m = re.match(r'^([A-Za-z]{1,6})\s+valuation$', q)
    if m:
        query_ticker_valuation(db, m.group(1))
        return
    m = re.match(r'^valuation\s+([A-Za-z]{1,6})$', q)
    if m:
        query_ticker_valuation(db, m.group(1))
        return

    # ── Portfolio ──
    if q in ("portfolio", "positions"):
        query_portfolio(db)
        return
    if q in ("trades", "trade log", "trade history"):
        query_trades(db)
        return

    # ── Last trade for ticker ──
    m = re.match(r'^last\s+trade\s+([A-Za-z]{1,6})$', q)
    if m:
        query_last_trade_ticker(db, m.group(1))
        return

    # ── Outlook ──
    if q in ("last outlook", "latest outlook", "outlook"):
        query_latest_outlook(db)
        return
    if q in ("outlook history", "outlooks"):
        query_outlook_history(db)
        return

    # ── Clients ──
    if q in ("clients", "client list", "all clients", "profiles"):
        query_clients(db)
        return
    if q in ("clients due", "due for contact", "contact due", "reviews due"):
        query_clients_due(db)
        return
    for pos in ("conservative", "moderate", "aggressive", "opportunistic"):
        if q in (f"{pos} clients", f"clients {pos}", pos):
            query_clients_by_positioning(db, pos)
            return
    m = re.match(r'^client\s+(.+)$', q)
    if m:
        query_client_detail(db, m.group(1).strip())
        return

    # ── Knowledge Base ──
    if q in ("kb list", "knowledge base", "kb"):
        query_kb_list(db)
        return
    if q.startswith("kb sections ") or q.startswith("kb toc "):
        key = q.split(None, 2)[2] if len(q.split(None, 2)) > 2 else ""
        query_kb_section(db, key)
        return
    if q.startswith("kb "):
        search_terms = q[3:].strip()
        if search_terms:
            query_kb_search(db, search_terms)
            return
    if q.startswith("what is ") or q.startswith("explain ") or q.startswith("define "):
        # Treat conceptual questions as KB searches
        search_terms = re.sub(r'^(what is|explain|define)\s+', '', q).strip()
        if search_terms:
            query_kb_search(db, search_terms)
            return

    # ── Fallback ──
    print(f"\n  {YELLOW}I don't understand that query. Type 'help' to see what I can answer.{RESET}\n")


# ── Main ──────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        query_help()
        return

    query = " ".join(sys.argv[1:])

    with SomaBridge() as db:
        route_query(query, db)


if __name__ == "__main__":
    main()
