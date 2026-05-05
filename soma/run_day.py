#!/usr/bin/env python3
"""
DABEIBA Daily Orchestrator — runs the full pipeline in one command.
Coordinates: TITAN → DELTA → DOCTRINE → SENTINEL → FORGE → BEACON → HORIZON
See pipeline_registry.py for codename reference.

Usage:
    python3 ~/Desktop/DABEIBA/shared/soma/run_day.py

Steps:
    [KB]  KB Index Check — rebuild if knowledge files changed
    [0/7] Backup soma.db
    [0.5] PRISM — process scraper inbox (if files present)
    [1/7] Run ORACLE → writes regime + valuations to SOMA
    [1b]  COBALT → on-chain intelligence (BTC/SOL metrics, composite signals)
    [1c]  SPECTRE → geopolitical risk scoring (RSS feeds, keyword triage, delta check)
    [1d]  SOMA-INTEL → graph enrichment + signal propagation + sweep + SOMA bridge
              + horizon tracks (tactical / thematic / structural) + multi-horizon boost
    [1e]  Meta-learner (Sunday only) — per-cell threshold adjustment via backtest outcomes
    [1f]  Weekly Brief (Friday only) — HTML brief to cipher/outputs/
    [2/7] What Changed → diffs against previous, flags material shifts
    [2b]  DOCTRINE → thesis engine: belief testing, conviction adjustments, alerts
    [2c]  Narrative Alignment → flags outlook ↔ portfolio contradictions
    [2d]  KB Violations → reports any new validation violations
    [3/7] SOMA Status → one-screen dashboard
    [4/7] MANTIS → shows portfolio state + trades
    [5/7] CIPHER → generates outlook IF material changes detected
    [5b]  RAPTOR → daily pulse (scores, actions, COI, consent snapshot)
    [6/7] HORIZON → tactical timing analysis (7-lens synthesis)
    [7/7] Action items + timing
"""

import os
import sys
import subprocess
import time
from datetime import datetime

# Make shared package importable
_PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, _PROJECT_ROOT)

# ── ANSI codes ────────────────────────────────────────────────────────
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RESET = "\033[0m"

W = 62
_ORACLE_MAIN = os.path.join(_PROJECT_ROOT, "oracle", "main.py")


def _header(step, title):
    print(f"\n{BOLD}{CYAN}{'=' * W}{RESET}")
    print(f"{BOLD}  [{step}] {title}{RESET}")
    print(f"{BOLD}{CYAN}{'=' * W}{RESET}\n")


def _step_ok(msg):
    print(f"  {GREEN}OK{RESET} {msg}")


def _step_fail(msg):
    print(f"  {RED}FAIL{RESET} {msg}")


# ── Step KB: Knowledge Base Index ─────────────────────────────────────

def step_kb_index():
    """Rebuild KB rule index if any knowledge files changed."""
    _header("KB", "Knowledge Base Index")
    try:
        from shared.soma.soma_bridge import SomaBridge
        with SomaBridge() as db:
            db.initialize_db()
            kr = db.get_kb_reader()
            if kr.is_index_stale():
                print(f"  {YELLOW}KB files changed — rebuilding index...{RESET}")
                kr.build_index()
                rules = kr.get_all_rules()
                _step_ok(f"{len(rules)} rules re-indexed")
            else:
                rules = kr.get_all_rules()
                _step_ok(f"{len(rules)} rules up to date (no changes)")
            return True
    except Exception as e:
        _step_fail(f"KB index check failed: {e}")
        print(f"  {DIM}Continuing without KB — modules will use fallback values{RESET}")
        return True  # non-fatal — don't abort the pipeline


# ── Step 0: Backup ────────────────────────────────────────────────────

def step_0_backup():
    """Back up soma.db before any new writes."""
    _header("0/6", "Backup soma.db")

    from shared.soma.backup_soma import run_backup

    try:
        result = run_backup()
        if result:
            _step_ok(f"Database backed up as {result}")
        else:
            _step_ok("No database to back up yet (first run)")
        return True
    except Exception as e:
        _step_fail(f"Backup error: {e}")
        return False


# ── Step 0b: Dispatch Staging Files ──────────────────────────────────

def step_0b_dispatch_staging():
    """Process any staging YAML files (PRISM, DOCTRINE, MODEL_FLAG, etc.)."""
    _header("0b", "Staging Dispatch")

    try:
        from shared.soma.staging_dispatcher import StagingDispatcher
        from shared.soma.soma_bridge import SomaBridge

        staging_dir = os.path.join(_PROJECT_ROOT, "shared", "soma", "staging")
        with SomaBridge() as db:
            dispatcher = StagingDispatcher(staging_dir=staging_dir, soma_bridge=db)
            results = dispatcher.process_all()

        if results.get("skipped"):
            _step_fail(f"Dispatcher skipped: {results.get('reason', 'unknown')}")
            return results

        processed = results.get("processed", 0)
        errors = results.get("errors", 0)
        skipped = results.get("skipped", 0)

        if processed > 0:
            _step_ok(f"{processed} staging files processed")
            if results.get("model_flags"):
                print(f"  {YELLOW}MODEL FLAGS:{RESET} {', '.join(results['model_flags'])}")
            if results.get("wiki_updates"):
                print(f"  {CYAN}WIKI UPDATES:{RESET} {', '.join(results['wiki_updates'])}")
            if results.get("doctrine_evidence"):
                print(f"  {DIM}DOCTRINE:{RESET} {', '.join(results['doctrine_evidence'])}")
            if results.get("by_type"):
                print(f"  {DIM}By type: {results['by_type']}{RESET}")
        else:
            _step_ok("No staging files to process")

        if errors > 0:
            print(f"  {RED}ERRORS: {errors} files moved to staging/errors/{RESET}")

        return results

    except ImportError as e:
        _step_fail(f"Staging dispatcher not available: {e}")
        return {}
    except Exception as e:
        _step_fail(f"Staging dispatch error: {e}")
        return {}


# ── Step 0.5: PRISM (Inbox Ingestion) ────────────────────────────────

def step_05_prism():
    """PRISM — process any files in the scraper inbox."""
    _header("0.5", "PRISM — Inbox Ingestion")

    try:
        from shared.soma.prism_engine import PrismEngine

        with PrismEngine() as prism:
            result = prism.process_inbox()

            n_scanned = result.get("files_scanned", 0)
            n_processed = result.get("files_processed", 0)
            n_errored = result.get("files_errored", 0)

            if n_scanned == 0:
                print(f"  {DIM}Inbox empty — nothing to ingest{RESET}")
            else:
                prism.print_terminal()
                prism.save_log()
                if n_errored:
                    _step_fail(f"{n_processed} ingested, {n_errored} errored")
                else:
                    _step_ok(f"{n_processed} file(s) ingested into SOMA")

    except ImportError as e:
        print(f"  {YELLOW}[SKIP] PRISM not importable: {e}{RESET}")
    except Exception as e:
        _step_fail(f"PRISM error: {e}")


# ── Step 1: ORACLE ────────────────────────────────────────────────────

def step_1_oracle():
    """Run ORACLE → writes regime + valuations to SOMA.

    Generates a stable run_id and passes it via $ORACLE_RUN_ID so the SOMA
    UPSERT keys (regime_history.run_id, valuations.run_id+ticker) remain
    idempotent across retries within the same run_day invocation.
    """
    _header("1/6", "Run ORACLE")

    if not os.path.exists(_ORACLE_MAIN):
        print(f"  {YELLOW}ORACLE not found at: {_ORACLE_MAIN}{RESET}")
        print(f"  Run ORACLE manually, then re-run this script.")
        return False

    # Stable run_id per run_day invocation — retries reuse the same UUID.
    import uuid as _uuid
    oracle_run_id = os.environ.setdefault("ORACLE_RUN_ID", str(_uuid.uuid4()))
    env = {**os.environ, "ORACLE_RUN_ID": oracle_run_id}

    print(f"  Running: python3 {_ORACLE_MAIN} --run-id {oracle_run_id}")
    print(f"  {DIM}(this may take a few minutes){RESET}\n")
    try:
        result = subprocess.run(
            [sys.executable, _ORACLE_MAIN, "--run-id", oracle_run_id],
            cwd=os.path.dirname(_ORACLE_MAIN),
            timeout=600,
            env=env,
        )
        if result.returncode == 0:
            _step_ok("ORACLE completed successfully")
            return True
        else:
            _step_fail(f"ORACLE exited with code {result.returncode}")
            return False
    except subprocess.TimeoutExpired:
        _step_fail("ORACLE timed out after 10 minutes")
        return False
    except Exception as e:
        _step_fail(f"ORACLE error: {e}")
        return False


# ── Step 1b: COBALT (Digital Assets) ────────────────────────────────

def step_1b_cobalt():
    """COBALT — Digital Assets: BTC/SOL metrics, composite signals."""
    _header("1b", "COBALT — Digital Assets")

    try:
        from oracle.cobalt_engine import CobaltEngine

        with CobaltEngine() as cobalt:
            result = cobalt.analyze()
            cobalt.print_terminal()
            log_path = cobalt.save_log()

            assets = result.get("assets", {})
            sources = result.get("sources", {})
            degraded = [s for s, st in sources.items() if st != "OK"]

            summary_parts = []
            for asset, data in assets.items():
                summary_parts.append(
                    f"{asset}: {data['direction']} ({data['composite']:.0%})"
                )

            _step_ok(" | ".join(summary_parts))

            if degraded:
                print(f"  {YELLOW}Degraded sources: {', '.join(degraded)}{RESET}")

            _step_ok(f"Log saved to {log_path}")

    except ImportError as e:
        print(f"  {YELLOW}[SKIP] COBALT not importable: {e}{RESET}")
    except Exception as e:
        _step_fail(f"COBALT error: {e}")


# ── Step 1c: SPECTRE (Geopolitical Intelligence) ────────────────────

def step_1c_spectre():
    """SPECTRE — geopolitical risk scoring: RSS feeds, keyword triage, delta check."""
    _header("1c", "SPECTRE — Geopolitical Intelligence")

    try:
        from oracle.spectre_engine import SpectreEngine

        with SpectreEngine() as spectre:
            result = spectre.analyze()
            spectre.print_terminal()
            log_path = spectre.save_log()

            n_events = result.get("relevant_events", 0)
            n_shifts = len(result.get("material_shifts", []))
            nlp_mode = result.get("nlp_mode", "triage-only")

            _step_ok(f"{n_events} events classified ({nlp_mode})")

            if n_shifts:
                print(f"  {YELLOW}{n_shifts} material geopolitical shift(s) detected{RESET}")

            _step_ok(f"Log saved to {log_path}")

    except ImportError as e:
        print(f"  {YELLOW}[SKIP] SPECTRE not importable: {e}{RESET}")
    except Exception as e:
        _step_fail(f"SPECTRE error: {e}")


# ── Step 1d: SOMA-INTEL (Graph + Signal layer) ────────────────────────

def step_soma_intel():
    """
    SOMA-INTEL — daily graph enrichment + signal propagation.

    Runs four sub-tools in sequence (all idempotent):
      1. convergence_engine  — detect platform convergences, refresh beliefs
      2. signal_propagator   — time-decayed aggregate score per universe ticker
      3. signal_sweep        — expire stale signals, prune superseded beliefs
      4. soma_intel_bridge   — write signals to raw_intelligence for MANTIS/CIPHER

    Non-fatal: a failure in any sub-tool is logged but does not stop the run.
    """
    _header("1d", "SOMA-INTEL — Graph & Signal Layer")

    from soma.intel.store import IntelStore
    import os
    from pathlib import Path

    _dabeiba = Path(__file__).resolve().parent.parent.parent
    db_path  = Path(os.environ.get("SOMA_DB_PATH",
                    str(_dabeiba / "shared" / "soma" / "data" / "soma.db")))

    # ── 1. Convergence engine ──────────────────────────────────────────
    try:
        from soma.intel.convergence_engine import run_pass_a, run_pass_b, run_pass_c
        with IntelStore(db_path=db_path) as store:
            a = run_pass_a(store, dry_run=False, verbose=False)
            b = run_pass_b(store, dry_run=False, verbose=False)
            c = run_pass_c(store, dry_run=False, verbose=False)
        print(
            f"  {GREEN}[convergence]{RESET}  "
            f"companies={a['companies_processed']}  "
            f"conv_edges={a['convergence_edges_written']}  "
            f"has_thesis={b['has_thesis_written']}  "
            f"beliefs={c['beliefs_refreshed']}"
        )
    except Exception as e:
        print(f"  {YELLOW}[WARN]{RESET} convergence_engine failed (non-fatal): {e}")

    # ── 2. Signal propagator ──────────────────────────────────────────
    try:
        from soma.intel.signal_propagator import run_propagator
        with IntelStore(db_path=db_path) as store:
            sp = run_propagator(store, tickers=None, dry_run=False,
                                verbose=False, top_n=0)
        print(
            f"  {GREEN}[propagator]{RESET}   "
            f"scored={sp['tickers_scored']}  "
            f"written={sp['signals_written']}  "
            f"reconfirmed={sp['reconfirmed']}  "
            f"skipped={sp['skipped_low']}"
        )
    except Exception as e:
        print(f"  {YELLOW}[WARN]{RESET} signal_propagator failed (non-fatal): {e}")

    # ── 3. Signal sweep ───────────────────────────────────────────────
    try:
        from soma.intel.signal_sweep import run_pass_1, run_pass_2, run_pass_3
        with IntelStore(db_path=db_path) as store:
            p1 = run_pass_1(store, tickers=None, dry_run=False, verbose=False)
            p2 = run_pass_2(store, dry_run=False, verbose=False)
            p3 = run_pass_3(store, tickers=None, dry_run=False, verbose=False)
        print(
            f"  {GREEN}[sweep]{RESET}        "
            f"expired={p1['expired']}  "
            f"pruned={p2['pruned']}  "
            f"reconfirmed={p3['reconfirmed']}  "
            f"expired_low={p3['expired_low']}"
        )
    except Exception as e:
        print(f"  {YELLOW}[WARN]{RESET} signal_sweep failed (non-fatal): {e}")

    # ── 4. SOMA bridge ────────────────────────────────────────────────
    try:
        from datetime import date
        from soma.intel.soma_intel_bridge import run_bridge
        br = run_bridge(target_date=date.today().isoformat(),
                        dry_run=False, verbose=False)
        mantis = "written" if br["mantis_written"] else "skipped"
        cipher = "written" if br["cipher_written"] else "skipped"
        print(
            f"  {GREEN}[bridge]{RESET}       "
            f"signals={br['signals_found']}  "
            f"convergence={br['convergence_hits']}  "
            f"mantis={mantis}  cipher={cipher}"
        )
    except Exception as e:
        print(f"  {YELLOW}[WARN]{RESET} soma_intel_bridge failed (non-fatal): {e}")

    # ── 5. Multi-horizon tracks (§J) ─────────────────────────────────
    _today = date.today().isoformat()
    try:
        from soma.intel.horizon_tactical  import TacticalTrack
        from soma.intel.horizon_thematic  import ThematicTrack
        from soma.intel.horizon_structural import StructuralTrack
        with IntelStore(db_path=db_path) as store:
            tac  = TacticalTrack(store,  _today).run()
            them = ThematicTrack(store,   _today).run()
            struc= StructuralTrack(store, _today).run()
        print(
            f"  {GREEN}[horizons]{RESET}     "
            f"tactical={len(tac)}  thematic={len(them)}  structural={len(struc)}"
        )
    except Exception as e:
        print(f"  {YELLOW}[WARN]{RESET} horizon tracks failed (non-fatal): {e}")

    # ── 6. Multi-horizon boost (§J boost) ────────────────────────────
    try:
        from soma.intel.confirm import apply_multi_horizon_boost
        with IntelStore(db_path=db_path) as store:
            boosted = apply_multi_horizon_boost(store, _today)
        if boosted:
            print(
                f"  {GREEN}[boost]{RESET}        "
                f"{len(boosted)} signal(s) boosted (multi_horizon 1.5x)"
            )
    except Exception as e:
        print(f"  {YELLOW}[WARN]{RESET} multi_horizon_boost failed (non-fatal): {e}")


# ── Step 1e: Meta-learner (Sunday only) ──────────────────────────────

def step_meta_learner_weekly():
    """
    Meta-learner — runs once per week on Sunday.
    Adjusts per-cell z-thresholds based on backtest outcome history.
    No-op on other days.
    """
    from datetime import date as _date
    today = _date.today()
    if today.weekday() != 6:   # 6 = Sunday
        return   # silent no-op — not Sunday

    _header("1e", "Meta-Learner — Weekly Threshold Adjustment (Sunday)")

    from pathlib import Path
    import os
    _dabeiba = Path(__file__).resolve().parent.parent.parent
    db_path  = Path(os.environ.get("SOMA_DB_PATH",
                    str(_dabeiba / "shared" / "soma" / "data" / "soma.db")))

    try:
        from soma.intel.store import IntelStore
        from soma.intel.meta_learner import MetaLearner
        with IntelStore(db_path=db_path) as store:
            report = MetaLearner(store, as_of_date=today.isoformat()).run()
        print(
            f"  {GREEN}[meta_learner]{RESET}  "
            f"cells_evaluated={report['cells_evaluated']}  "
            f"cells_adjusted={report['cells_adjusted']}  "
            f"down={report['adjustments_down']}  up={report['adjustments_up']}  "
            f"cap_hits={report['cap_hits']}  skipped={report['skipped_min_data']}"
        )
    except Exception as e:
        print(f"  {YELLOW}[WARN]{RESET} meta_learner failed (non-fatal): {e}")


# ── Step 1f: Weekly Brief (Friday only) ──────────────────────────────

def step_weekly_brief_friday():
    """
    Weekly intelligence brief — runs once per week on Friday.
    Generates cipher/outputs/weekly_brief_YYYY-MM-DD.html.
    No-op on other days.
    """
    from datetime import date as _date
    today = _date.today()
    if today.weekday() != 4:   # 4 = Friday
        return   # silent no-op — not Friday

    _header("1f", "Weekly Intelligence Brief (Friday)")

    try:
        from soma.intel.weekly_brief import run_weekly_brief
        result = run_weekly_brief(as_of_date=today.isoformat(), force=True)
        if result.get("skipped"):
            print(f"  {YELLOW}[SKIP]{RESET} {result.get('reason', '')}")
        else:
            print(f"  {GREEN}OK{RESET} Brief written: {result['output_path']}")
    except Exception as e:
        print(f"  {YELLOW}[WARN]{RESET} weekly_brief failed (non-fatal): {e}")


# ── Step 2: What Changed ─────────────────────────────────────────────

def step_2_what_changed():
    """What Changed → diffs against previous, flags material shifts."""
    _header("2/6", "What Changed")

    from shared.soma.what_changed import WhatChanged

    try:
        with WhatChanged() as wc:
            result = wc.analyze()
            wc.print_terminal()
            log_path = wc.save_log()
            _step_ok(f"Analysis saved to {log_path}")
            return result
    except Exception as e:
        _step_fail(f"What Changed error: {e}")
        return None


# ── Step 2b: DOCTRINE (Thesis & Convictions) ────────────────────────────

def step_2b_doctrine():
    """DOCTRINE — Thesis & Convictions: beliefs, evidence, conviction, alerts."""
    _header("2b", "DOCTRINE — Thesis & Convictions")

    try:
        from shared.soma.doctrine_engine import DoctrineEngine

        with DoctrineEngine() as doc:
            result = doc.analyze()
            doc.print_terminal()
            log_path = doc.save_log()

            n_beliefs = result.get("beliefs_analyzed", 0)
            n_alerts = result.get("alerts_raised", 0)
            n_changes = len(result.get("conviction_changes", []))

            _step_ok(f"{n_beliefs} beliefs analyzed, {n_changes} conviction change(s), "
                     f"{n_alerts} alert(s)")

            if n_alerts > 0:
                critical = [a for a in result.get("alerts", [])
                            if a["severity"] == "CRITICAL"]
                if critical:
                    print(f"\n  {RED}{BOLD}CRITICAL:{RESET} "
                          f"{len(critical)} belief(s) require mandatory review")

    except ImportError as e:
        print(f"  {YELLOW}[SKIP] DOCTRINE not importable: {e}{RESET}")
    except Exception as e:
        _step_fail(f"DOCTRINE error: {e}")


# ── Step 2c: Narrative Alignment ──────────────────────────────────────

def step_2c_alignment():
    """Portfolio-Narrative Alignment — flags contradictions."""
    _header("2c", "Portfolio-Narrative Alignment")

    try:
        from shared.soma.narrative_alignment import NarrativeAlignment

        with NarrativeAlignment() as na:
            result = na.analyze()
            na.print_terminal()
            log_path = na.save_log()

            n_issues = len(result.get("inconsistencies", []))
            alignment = result.get("alignment", 0)

            if n_issues == 0:
                _step_ok(f"Aligned ({alignment:.0%}) — no contradictions")
            else:
                print(f"  {YELLOW}{n_issues} inconsistency(ies) found — review above{RESET}")
            _step_ok(f"Log saved to {log_path}")
            return result

    except Exception as e:
        _step_fail(f"Alignment check failed: {e}")
        print(f"  {DIM}Continuing — alignment check is non-fatal{RESET}")
        return None


# ── Step 2d: KB Violations ───────────────────────────────────────────

def step_2d_violations():
    """Check for new KB violations since last run."""
    _header("2c", "KB Violations Check")

    try:
        from shared.soma.soma_bridge import SomaBridge

        with SomaBridge() as db:
            db.initialize_db()
            try:
                rows = db.conn.execute(
                    """SELECT severity, COUNT(*) AS cnt
                       FROM kb_violations GROUP BY severity"""
                ).fetchall()
                counts = {r["severity"]: r["cnt"] for r in rows}
            except Exception:
                print(f"  {DIM}No violations table yet (Schema v4 migration not applied){RESET}")
                return

            total = sum(counts.values())
            if total == 0:
                _step_ok("No violations — all writes consistent with KB rules")
                return

            crit = counts.get("CRITICAL", 0)
            warn = counts.get("WARNING", 0)
            info = counts.get("INFO", 0)

            if crit > 0:
                print(f"  {RED}{BOLD}CRITICAL: {crit}{RESET}  {YELLOW}WARNING: {warn}{RESET}  {DIM}INFO: {info}{RESET}")
            elif warn > 0:
                print(f"  {YELLOW}WARNING: {warn}{RESET}  {DIM}INFO: {info}{RESET}")
            else:
                print(f"  {DIM}INFO: {info}{RESET}")

            # Show most recent critical/warning violations
            try:
                recent = db.conn.execute(
                    """SELECT severity, rule_id, source_module, description, detected_at
                       FROM kb_violations
                       WHERE severity IN ('CRITICAL', 'WARNING')
                       ORDER BY id DESC LIMIT 5"""
                ).fetchall()
                if recent:
                    print()
                    for r in recent:
                        sev_c = RED if r["severity"] == "CRITICAL" else YELLOW
                        print(f"    {sev_c}[{r['severity']}]{RESET} {r['source_module']}: "
                              f"{r['description'][:55]}")
                    print(f"\n  {DIM}Full details: python3 soma_query.py 'violations'{RESET}")
            except Exception:
                pass

    except Exception as e:
        _step_fail(f"Violations check failed: {e}")
        print(f"  {DIM}Continuing — violations check is non-fatal{RESET}")


# ── Step 3: SOMA Status ──────────────────────────────────────────────

def step_3_status():
    """SOMA Status → one-screen dashboard."""
    _header("3/6", "SOMA Status")

    from shared.soma.soma_status import print_status

    try:
        print_status()
        return True
    except Exception as e:
        _step_fail(f"Status dashboard error: {e}")
        return False


# ── Step 4: MANTIS ────────────────────────────────────────────────────

def step_4_mantis():
    """MANTIS → shows portfolio state + trades from SOMA."""
    _header("4/6", "MANTIS Portfolio")

    from shared.soma.soma_bridge import SomaBridge

    try:
        with SomaBridge() as db:
            portfolio = db.get_latest_portfolio_state()
            trades = db.get_trade_log(limit=10)

        if not portfolio:
            print(f"  {DIM}No portfolio data in SOMA yet (MANTIS not connected){RESET}")
            return

        # Portfolio snapshot
        cash = portfolio.get("cash_pct")
        total = portfolio.get("total_value")
        dd = portfolio.get("dd_from_hwm")
        print(f"  {CYAN}Total Value:{RESET}  ${total:,.0f}" if total else "")
        if cash is not None:
            print(f"  {CYAN}Cash:{RESET}         {cash * 100:.1f}%")
            print(f"  {CYAN}Exposure:{RESET}     {(1 - cash) * 100:.1f}%")
        if dd is not None:
            print(f"  {CYAN}DD from HWM:{RESET}  {dd:.1f}%")
        if portfolio.get("module_version"):
            print(f"  {CYAN}Source:{RESET}       {portfolio['module_version']}")

        # Trade summary
        if trades:
            rebalances = [t for t in trades if t.get("action") == "REBALANCE"]
            tier_changes = [t for t in trades if t.get("action") == "TIER_CHANGE"]
            print(f"\n  {BOLD}Recent Trades:{RESET} {len(trades)} entries "
                  f"({len(rebalances)} rebalances, {len(tier_changes)} tier changes)")
            for t in trades[:5]:
                action = t.get("action", "?")
                ticker = t.get("ticker", "?")
                date = t.get("date", "?")
                color = RED if action == "TIER_CHANGE" else YELLOW if action == "REBALANCE" else GREEN
                reason = (t.get("reason") or "")[:50]
                print(f"    {date}  {color}{action:<18s}{RESET} {ticker:<10s} {DIM}{reason}{RESET}")
        else:
            print(f"\n  {DIM}No trades recorded yet{RESET}")

    except Exception as e:
        _step_fail(f"MANTIS read error: {e}")


# ── Step 5: CIPHER ────────────────────────────────────────────────────

def step_5_cipher(wc_result):
    """CIPHER → generates outlook IF material changes detected, writes it back."""
    _header("5/6", "CIPHER Outlook")

    if wc_result is None:
        print(f"  {DIM}Skipping — What Changed did not run{RESET}")
        return

    if not wc_result.get("has_material_change"):
        print(f"  {GREEN}No new outlook needed — no material changes detected.{RESET}")
        return

    try:
        # Add CIPHER to path
        _CIPHER_ROOT = os.path.join(_PROJECT_ROOT, "cipher")
        if _CIPHER_ROOT not in sys.path:
            sys.path.insert(0, _CIPHER_ROOT)

        from cipher.soma_integration import generate_soma_powered_outlook

        print(f"  {YELLOW}Material changes detected — generating outlook...{RESET}")
        result = generate_soma_powered_outlook()

        if result.get("generated"):
            n_conclusions = len(result.get("conclusions", []))
            _step_ok(f"Outlook generated with {n_conclusions} key conclusions")
            for c in result.get("conclusions", [])[:5]:
                print(f"    - {c}")
        else:
            reason = result.get("context", {}).get("reason", "unknown")
            print(f"  {YELLOW}SOMA data unavailable ({reason}) — skipped{RESET}")

    except ImportError as _ie:
        print(f"  {YELLOW}[SKIP] CIPHER soma_integration not importable — outlook skipped.{RESET}")
        print(f"  {DIM}Reason: {_ie}{RESET}")
        print(f"  {DIM}Fix: ensure cipher/ is on sys.path and soma_integration.py exists.{RESET}")
    except Exception as e:
        _step_fail(f"CIPHER error: {e}")


# ── Step 6: HORIZON Timing & Signals ────────────────────────────────

def step_6_horizon():
    """HORIZON → run timing & signals analysis with fresh Research data."""
    _header("6/7", "HORIZON — Timing & Signals")

    try:
        from shared.soma.horizon import run_horizon

        question = "Daily portfolio timing check — should I hold, reduce, or add to TSLA + MSTR?"
        analysis = run_horizon(question, verbose=False)

        if analysis.concordance is None:
            print(f"  {RED}HORIZON failed — no regime gate available{RESET}")
            return

        # Compact summary
        dir_val = analysis.composite_direction.value
        if "BUY" in dir_val:
            color = GREEN
        elif "SELL" in dir_val:
            color = RED
        else:
            color = YELLOW

        cc = analysis.concordance
        passed = f"{GREEN}PASS{RESET}" if cc.passed else f"{YELLOW}FAIL{RESET}"

        print(f"  {BOLD}Signal:{RESET}       {color}{analysis.composite_score:+.3f} ({dir_val}){RESET}")
        print(f"  {BOLD}Concordance:{RESET}  {cc.agreeing_count}/{cc.total_lenses} [{passed}]")
        print(f"  {BOLD}Confidence:{RESET}   {analysis.final_confidence:.0%} (raw={analysis.raw_confidence:.0%})")

        if analysis.regime_gate:
            g = analysis.regime_gate
            print(f"  {BOLD}Regime:{RESET}       {g.regime.value} (GLI={g.gli_value:.2f})")

        if analysis.bias_audit and analysis.bias_audit.any_detected:
            names = [b.bias_name for b in analysis.bias_audit.biases_detected]
            print(f"  {BOLD}Biases:{RESET}       {YELLOW}{', '.join(names)}{RESET}")

        if analysis.monte_carlo and analysis.monte_carlo.windows:
            # Show best window
            best = max(analysis.monte_carlo.windows, key=lambda w: w.p_optimal)
            print(f"  {BOLD}Best window:{RESET}  {best.label} (P={best.p_optimal:.0%}, E={best.expected_move_pct:+.1f}%)")

        if not cc.passed:
            print(f"\n  {YELLOW}No action recommended — concordance not met{RESET}")

        print(f"\n  {DIM}Full report: soma_query.py \"horizon last\"{RESET}")
        _step_ok(f"Analysis stored (run={analysis.run_id})")

    except ImportError as e:
        print(f"  {YELLOW}[SKIP] HORIZON not importable: {e}{RESET}")
    except Exception as e:
        _step_fail(f"HORIZON error: {e}")


# ── Step 5b: RAPTOR Daily Pulse ──────────────────────────────────────

def step_5b_raptor():
    """RAPTOR — Daily Pulse: prospect scores, actions, COI, consent snapshot."""
    _header("5b", "RAPTOR — Daily Pulse")

    try:
        from soma.soma_bridge import SomaBridge
        from soma.raptor_engine import RaptorEngine
        from soma.raptor_onboarding import RaptorOnboarding

        with SomaBridge() as db:
            engine     = RaptorEngine(db)
            onboarding = RaptorOnboarding(db)
            status     = engine.raptor_status()
            overdue_ms = onboarding.check_milestone_due()

            # ── Print banner ──────────────────────────────────────────
            W_R = 50
            print(f"  {BOLD}{'=' * W_R}{RESET}")

            # Pipeline
            pip = status["pipeline"]
            stages = ["identified", "researched", "contacted",
                      "meeting_set", "proposal_sent", "onboarding", "active"]
            pip_parts = " | ".join(
                f"{s.replace('_',' ')}: {pip.get(s, 0)}" for s in stages
            )
            print(f"  Pipeline  {pip_parts}")

            # Scores
            sc = status["scores"]
            print(
                f"  Scores    {sc['hot']} hot (>80) | "
                f"{sc['warm']} warm (50-80) | "
                f"{sc['cold']} cold (<50)"
            )

            # Actions
            ac = status["actions"]
            imm_color  = RED    if ac["immediate"]  > 0 else GREEN
            rc_color   = YELLOW if ac["re_consent"] > 0 else GREEN
            ov_color   = YELLOW if ac["overdue"]    > 0 else GREEN
            print(
                f"  Actions   "
                f"{imm_color}[!] {ac['immediate']} immediate{RESET} | "
                f"{rc_color}[R] {ac['re_consent']} re-consent{RESET} | "
                f"{ov_color}[O] {ac['overdue']} overdue{RESET}"
            )

            # COI
            co = status["coi"]
            coi_color = YELLOW if co["due_for_contact"] > 0 else GREEN
            print(
                f"  COIs      {co['total']} active | "
                f"{coi_color}{co['due_for_contact']} due for contact{RESET} | "
                f"{co['referrals_month']} referrals this month"
            )

            # Consent
            cs = status["consent"]
            cons_color = YELLOW if cs["expiring_30d"] > 0 or cs["deletion_pending"] > 0 else GREEN
            print(
                f"  Consent   {cs['valid']} valid | "
                f"{cons_color}{cs['expiring_30d']} expiring <30d | "
                f"{cs['deletion_pending']} deletion pending{RESET}"
            )

            # Onboarding milestones
            ob_count   = pip.get("onboarding", 0)
            ms_color   = RED if overdue_ms else GREEN
            print(
                f"  Onboarding {ob_count} in progress | "
                f"{ms_color}{len(overdue_ms)} milestone(s) overdue{RESET}"
            )
            for ms in overdue_ms[:3]:   # show top 3
                print(
                    f"    {RED}[OVERDUE +{ms['days_overdue']}d]{RESET} "
                    f"{ms['prospect_id'][:8]}… {ms['label']}"
                )

            print(f"  {BOLD}{'=' * W_R}{RESET}")

            # Log to SOMA events
            import json as _json
            db.publish_event(
                "raptor_daily_pulse",
                {
                    "pipeline":          status["pipeline"],
                    "scores":            status["scores"],
                    "actions":           status["actions"],
                    "coi":               status["coi"],
                    "consent":           status["consent"],
                    "overdue_milestones": len(overdue_ms),
                },
                source_module="RAPTOR",
            )
            _step_ok("Daily pulse logged to soma_events")

    except ImportError as e:
        print(f"  {YELLOW}[SKIP] RAPTOR not importable: {e}{RESET}")
    except Exception as e:
        _step_fail(f"RAPTOR error: {e}")


# ── Step 7b: Wiki Sync (VAULT → Wiki) ────────────────────────────────

def _alert_wiki_sync_failure(reason: str, detail: str = "") -> None:
    """Loud banner + events-table row on wiki sync failure (Phase 3.5).

    Non-fatal: never raises. If SOMA write itself fails, just prints.
    """
    banner = "#" * 72
    print(f"\n{RED}{banner}{RESET}")
    print(f"{RED}!! WIKI SYNC FAILED — wiki may be stale !!{RESET}")
    print(f"{RED}   reason: {reason}{RESET}")
    if detail:
        print(f"{RED}   detail: {detail[:240]}{RESET}")
    print(f"{RED}{banner}{RESET}\n")
    try:
        import json as _json
        from shared.soma.soma_bridge import SomaBridge
        today = datetime.now().strftime("%Y-%m-%d")
        with SomaBridge() as s:
            s.write_event(
                date=today,
                event_type="WIKI_SYNC_FAILED",
                source_module="run_day.step_7b_wiki_sync",
                details_json=_json.dumps({"reason": reason, "detail": detail[:500]}),
                module_version="phase-3.5",
            )
    except Exception as e:
        print(f"  {DIM}(could not log events row: {e}){RESET}")


def step_7b_wiki_sync():
    """Sync latest VAULT valuations to wiki company articles."""
    _header("7b", "Wiki Sync (VAULT → Wiki)")

    try:
        import subprocess
        wiki_seed = os.path.join(_PROJECT_ROOT, "wiki", "tools", "wiki_seed_vault.py")

        if not os.path.exists(wiki_seed):
            _step_ok("wiki_seed_vault.py not found — skipping (wiki tools not installed)")
            return True

        result = subprocess.run(
            [sys.executable, wiki_seed, "--write", "--top", "10"],
            capture_output=True, text=True, timeout=120,
            cwd=os.path.join(_PROJECT_ROOT, "wiki"),
        )

        if result.returncode == 0:
            _step_ok("Wiki articles refreshed (top 10 tickers)")
            if result.stdout.strip():
                for line in result.stdout.strip().split("\n")[:5]:
                    print(f"  {DIM}{line}{RESET}")
        else:
            _step_fail(f"wiki_seed_vault.py returned {result.returncode}")
            if result.stderr.strip():
                print(f"  {DIM}{result.stderr.strip()[:200]}{RESET}")
            _alert_wiki_sync_failure(
                reason=f"wiki_seed_vault.py exit={result.returncode}",
                detail=result.stderr.strip() or result.stdout.strip(),
            )

        return True

    except subprocess.TimeoutExpired:
        _step_fail("Wiki sync timed out (120s)")
        _alert_wiki_sync_failure(reason="timeout", detail="wiki_seed_vault.py exceeded 120s")
        return True  # non-fatal
    except Exception as e:
        _step_fail(f"Wiki sync error: {e}")
        _alert_wiki_sync_failure(reason="exception", detail=str(e))
        return True  # non-fatal


# ── Step 7: Action Items + Timing ─────────────────────────────────────

def step_7_actions(wc_result, start_time):
    """Action items + timing."""
    _header("7/7", "Action Items + Timing")

    elapsed = time.time() - start_time

    if wc_result is None:
        print(f"  {DIM}Could not determine actions (What Changed did not run){RESET}")
    elif not wc_result.get("has_material_change"):
        print(f"  {GREEN}No action required — no material changes detected.{RESET}")
    else:
        changes = wc_result.get("changes", [])
        high = [c for c in changes if c["severity"] == "HIGH"]

        print(f"  {YELLOW}{len(changes)} material change(s) detected:{RESET}\n")

        for c in changes:
            color = RED if c["severity"] == "HIGH" else YELLOW
            print(f"    {color}[{c['severity']}]{RESET} {c['description']}")

        print(f"\n  {BOLD}Checklist:{RESET}")
        print(f"    [ ] Review regime assessment — has the macro picture shifted?")
        if any(c["type"] == "valuation_shift" for c in changes):
            print(f"    [ ] Check valuation changes — are position sizes still appropriate?")
        print(f"    [ ] Check MANTIS — is portfolio exposure aligned with current regime?")
        if any(c["type"] in ("regime_transition", "outlook_drift") for c in changes):
            print(f"    [ ] Consider writing a new Outlook to reflect changed conditions")
        if high:
            print(f"\n  {RED}{BOLD}HIGH severity changes require immediate attention.{RESET}")

    # Timing
    print(f"\n  {DIM}Pipeline completed in {elapsed:.1f}s{RESET}")


# ── Main ──────────────────────────────────────────────────────────────

def main():
    start = time.time()

    print(f"\n{BOLD}{'#' * W}{RESET}")
    print(f"{BOLD}  SOMA DAILY RUN{RESET}")
    print(f"{BOLD}{'#' * W}{RESET}")

    # Step KB: Knowledge Base Index
    try:
        step_kb_index()
    except Exception as e:
        print(f"  {RED}ERROR{RESET} in KB Index step: {e}")

    # Step 0: Backup
    try:
        step_0_backup()
    except Exception as e:
        print(f"  {RED}ERROR{RESET} in Backup step: {e}")

    # Step 0b: Dispatch staging files
    staging_results = {}
    try:
        staging_results = step_0b_dispatch_staging()
    except Exception as e:
        print(f"  {RED}ERROR{RESET} in Staging Dispatch step: {e}")

    # Step 0.5: PRISM (Inbox Ingestion)
    try:
        step_05_prism()
    except Exception as e:
        print(f"  {RED}ERROR{RESET} in PRISM step: {e}")

    # Step 1: ORACLE
    try:
        step_1_oracle()
    except Exception as e:
        print(f"  {RED}ERROR{RESET} in ORACLE step: {e}")

    # Step 1b: COBALT (Digital Assets)
    try:
        step_1b_cobalt()
    except Exception as e:
        print(f"  {RED}ERROR{RESET} in COBALT step: {e}")

    # Step 1c: SPECTRE (Geopolitical Intelligence)
    try:
        step_1c_spectre()
    except Exception as e:
        print(f"  {RED}ERROR{RESET} in SPECTRE step: {e}")

    # Step 1d: SOMA-INTEL (Graph + Signal layer + horizon tracks + boost)
    try:
        step_soma_intel()
    except Exception as e:
        print(f"  {RED}ERROR{RESET} in SOMA-INTEL step: {e}")

    # Step 1e: Meta-learner (Sunday only — no-op other days)
    try:
        step_meta_learner_weekly()
    except Exception as e:
        print(f"  {RED}ERROR{RESET} in Meta-learner step: {e}")

    # Step 1f: Weekly Brief (Friday only — no-op other days)
    try:
        step_weekly_brief_friday()
    except Exception as e:
        print(f"  {RED}ERROR{RESET} in Weekly Brief step: {e}")

    # Step 2: What Changed
    wc_result = None
    try:
        wc_result = step_2_what_changed()
    except Exception as e:
        print(f"  {RED}ERROR{RESET} in What Changed step: {e}")

    # Step 2b: DOCTRINE
    try:
        step_2b_doctrine()
    except Exception as e:
        print(f"  {RED}ERROR{RESET} in DOCTRINE step: {e}")

    # Step 2c: Narrative Alignment
    try:
        step_2c_alignment()
    except Exception as e:
        print(f"  {RED}ERROR{RESET} in Alignment step: {e}")

    # Step 2d: KB Violations
    try:
        step_2d_violations()
    except Exception as e:
        print(f"  {RED}ERROR{RESET} in Violations step: {e}")

    # Step 3: SOMA Status
    try:
        step_3_status()
    except Exception as e:
        print(f"  {RED}ERROR{RESET} in Status step: {e}")

    # Step 6: HORIZON (moved BEFORE MANTIS — must produce same-day signal first)
    # After HORIZON runs, HorizonContract computes and persists the sizing multiplier
    # so MANTIS can consume it in the very next step.
    try:
        step_6_horizon()
    except Exception as e:
        print(f"  {RED}ERROR{RESET} in HORIZON step: {e}")

    # Persist HORIZON→MANTIS sizing contract (migration 020)
    # This writes the horizon_signal row that get_horizon_multiplier() will read.
    try:
        from soma.horizon_contract import HorizonContract
        _hc = HorizonContract()
        _hc_result = _hc.compute()
        _hc_rowid  = _hc.persist(_hc_result)
        print(f"  {GREEN}[CONTRACT]{RESET} horizon_signal persisted "
              f"(mult={_hc_result.horizon_multiplier:.4f}, "
              f"dir={_hc_result.composite_direction}, "
              f"rowid={_hc_rowid})")
    except Exception as e:
        print(f"  {YELLOW}[WARN]{RESET} HorizonContract persist failed (non-fatal): {e}")

    # Step 4: MANTIS (now consumes fresh same-day horizon_signal)
    try:
        step_4_mantis()
    except Exception as e:
        print(f"  {RED}ERROR{RESET} in MANTIS step: {e}")

    # Step 5: CIPHER
    try:
        step_5_cipher(wc_result)
    except Exception as e:
        print(f"  {RED}ERROR{RESET} in CIPHER step: {e}")

    # Step 5b: RAPTOR Daily Pulse
    try:
        step_5b_raptor()
    except Exception as e:
        print(f"  {RED}ERROR{RESET} in RAPTOR step: {e}")

    # Step 7b: Wiki Sync (VAULT → Wiki)
    try:
        step_7b_wiki_sync()
    except Exception as e:
        print(f"  {RED}ERROR{RESET} in Wiki Sync step: {e}")

    # Step 7: Action Items + Timing
    try:
        step_7_actions(wc_result, start)
    except Exception as e:
        print(f"  {RED}ERROR{RESET} in Action Items step: {e}")

    # Footer
    elapsed = time.time() - start
    print(f"\n{BOLD}{'#' * W}{RESET}")
    print(f"{BOLD}  Completed in {elapsed:.1f}s{RESET}")
    print(f"{BOLD}{'#' * W}{RESET}\n")


if __name__ == "__main__":
    main()
