#!/usr/bin/env python3
"""
SOMA Daily Orchestrator — runs the full DABEIBA pipeline in one command.

Usage:
    python3 ~/Desktop/DABEIBA/shared/soma/run_day.py

Steps:
    [0/6] Back up SOMA database
    [1/6] Run ORACLE (macro + valuations)
    [2/6] Run What Changed (diff analysis)
    [3/6] Show SOMA Status (dashboard)
    [4/6] Action Items (if material changes detected)
    [5/6] CIPHER Outlook (if material changes detected)
"""

import os
import sys
import subprocess
import time

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


def step_0_backup():
    """Back up soma.db before any new writes."""
    _header("0/6", "Back Up SOMA Database")

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


def step_1_oracle():
    """Run ORACLE's main.py."""
    _header("1/6", "Run ORACLE")

    if not os.path.exists(_ORACLE_MAIN):
        print(f"  {YELLOW}ORACLE not found at: {_ORACLE_MAIN}{RESET}")
        print(f"  Run ORACLE manually, then re-run this script.")
        return False

    print(f"  Running: python3 {_ORACLE_MAIN}")
    print(f"  {DIM}(this may take a few minutes){RESET}\n")
    try:
        result = subprocess.run(
            [sys.executable, _ORACLE_MAIN],
            cwd=os.path.dirname(_ORACLE_MAIN),
            timeout=600,
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


def step_2_what_changed():
    """Run WhatChanged analysis."""
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


def step_3_status():
    """Show the SOMA status dashboard."""
    _header("3/6", "SOMA Status")

    from shared.soma.soma_status import print_status

    try:
        print_status()
        return True
    except Exception as e:
        _step_fail(f"Status dashboard error: {e}")
        return False


def step_4_actions(wc_result):
    """Print action items based on What Changed results."""
    _header("4/6", "Action Items")

    if wc_result is None:
        print(f"  {DIM}Could not determine actions (What Changed did not run){RESET}")
        return

    if not wc_result.get("has_material_change"):
        print(f"  {GREEN}No action required — no material changes detected.{RESET}")
        return

    changes = wc_result.get("changes", [])
    high = [c for c in changes if c["severity"] == "HIGH"]
    medium = [c for c in changes if c["severity"] == "MEDIUM"]

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


def step_5_cipher(wc_result):
    """Generate CIPHER outlook if material changes detected."""
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
            print(f"  {GREEN}OK{RESET} Outlook generated with {n_conclusions} key conclusions")
            for c in result.get("conclusions", [])[:5]:
                print(f"    - {c}")
        else:
            reason = result.get("context", {}).get("reason", "unknown")
            print(f"  {YELLOW}SOMA data unavailable ({reason}) — skipped{RESET}")

    except ImportError:
        print(f"  {DIM}CIPHER not connected to SOMA yet (import failed){RESET}")
    except Exception as e:
        _step_fail(f"CIPHER error: {e}")


def main():
    start = time.time()

    print(f"\n{BOLD}{'#' * W}{RESET}")
    print(f"{BOLD}  SOMA DAILY RUN{RESET}")
    print(f"{BOLD}{'#' * W}{RESET}")

    # Step 0: Back up database before anything writes
    try:
        step_0_backup()
    except Exception as e:
        _step_fail(f"Unexpected error in Backup step: {e}")

    # Step 1: ORACLE
    try:
        step_1_oracle()
    except Exception as e:
        _step_fail(f"Unexpected error in ORACLE step: {e}")

    # Step 2: What Changed (independent of step 1)
    wc_result = None
    try:
        wc_result = step_2_what_changed()
    except Exception as e:
        _step_fail(f"Unexpected error in What Changed step: {e}")

    # Step 3: Status (independent of step 2)
    try:
        step_3_status()
    except Exception as e:
        _step_fail(f"Unexpected error in Status step: {e}")

    # Step 4: Action Items (depends on step 2 result, but won't crash)
    try:
        step_4_actions(wc_result)
    except Exception as e:
        _step_fail(f"Unexpected error in Action Items step: {e}")

    # Step 5: CIPHER Outlook (depends on step 2 result)
    try:
        step_5_cipher(wc_result)
    except Exception as e:
        _step_fail(f"Unexpected error in CIPHER step: {e}")

    # Footer
    elapsed = time.time() - start
    print(f"\n{BOLD}{'#' * W}{RESET}")
    print(f"{BOLD}  Completed in {elapsed:.1f}s{RESET}")
    print(f"{BOLD}{'#' * W}{RESET}\n")


if __name__ == "__main__":
    main()
