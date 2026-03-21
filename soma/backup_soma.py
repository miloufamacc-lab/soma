#!/usr/bin/env python3
"""
SOMA Backup — multi-tier backup of soma.db before any pipeline run.

Usage (standalone):
    python3 ~/Desktop/DABEIBA/shared/soma/backup_soma.py

What it does:
    TIER 1 (local):   soma.db → backups/soma_backup_YYYYMMDD_HHMMSS.db (30 rolling)
    TIER 2 (offsite): soma.db → iCloud Drive/DABEIBA_Backups/soma_latest.db
                       Also keeps 7 daily snapshots in iCloud for weekly coverage.
    TIER 3 (git):     All code is pushed to GitHub (handled separately by run_git_backup.sh)

Both tiers are fire-and-forget — iCloud failure never blocks the pipeline.

Architecture reference (system-wide):
    ┌─────────────────────────────────────────────────────────────┐
    │  DABEIBA DATA RESILIENCE CHAIN                              │
    │                                                             │
    │  L1  API Cache      oracle/cache/           4h→744h TTL     │
    │  L2  Snapshot       oracle/output/          last-good data  │
    │  L3  SOMA DB        shared/soma/data/       WAL mode        │
    │  L4  Local Backups  shared/soma/backups/     30 rolling      │
    │  L5  iCloud Sync    ~/Library/.../DABEIBA_Backups/  7 daily  │
    │  L6  What Changed   shared/soma/logs/       JSON archive    │
    │  L7  Git History    GitHub repos             full history    │
    │                                                             │
    │  GuruFocus Protection:                                      │
    │    • Monthly refresh gate (_month_already_refreshed)        │
    │    • Hard call counter (500/month)                          │
    │    • Cache TTL = 744h (31 days — never expires in-month)    │
    │    • _quota_exhausted blocks _get() at HTTP layer           │
    └─────────────────────────────────────────────────────────────┘
"""

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
_SOMA_DIR = Path(__file__).parent
_DB_PATH = _SOMA_DIR / "data" / "soma.db"
_BACKUP_DIR = _SOMA_DIR / "backups"

# iCloud Drive (macOS standard path)
_ICLOUD_BASE = Path.home() / "Library" / "Mobile Documents" / "com~apple~CloudDocs"
_ICLOUD_BACKUP_DIR = _ICLOUD_BASE / "DABEIBA_Backups"

# Retention
MAX_LOCAL_BACKUPS = 30
MAX_ICLOUD_DAILY = 7


# ── Tier 1: Local backup ─────────────────────────────────────────────────────

def _tier1_local_backup(ts: str) -> str | None:
    """Copy soma.db to local backups/ with timestamp. Prune to 30."""
    _BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    backup_name = f"soma_backup_{ts}.db"
    dest = _BACKUP_DIR / backup_name
    shutil.copy2(str(_DB_PATH), str(dest))

    size_kb = dest.stat().st_size / 1024

    # Prune old backups
    backups = sorted(_BACKUP_DIR.glob("soma_backup_*.db"))
    while len(backups) > MAX_LOCAL_BACKUPS:
        oldest = backups.pop(0)
        oldest.unlink()

    retained = len(list(_BACKUP_DIR.glob("soma_backup_*.db")))
    print(f"  [T1 local]   {backup_name} ({size_kb:.1f} KB) — {retained} retained")
    return backup_name


# ── Tier 2: iCloud offsite backup ────────────────────────────────────────────

def _tier2_icloud_backup(ts: str):
    """Copy soma.db to iCloud Drive for offsite sync. Fire-and-forget.

    Writes two files:
      - soma_latest.db       (always overwritten — fastest restore path)
      - soma_daily_YYYYMMDD.db  (one per day, 7 kept — weekly coverage)
    """
    if not _ICLOUD_BASE.exists():
        print("  [T2 iCloud]  iCloud Drive not found — skipping offsite backup")
        return

    try:
        _ICLOUD_BACKUP_DIR.mkdir(parents=True, exist_ok=True)

        # Always-current copy (single file, easy to find)
        latest = _ICLOUD_BACKUP_DIR / "soma_latest.db"
        shutil.copy2(str(_DB_PATH), str(latest))

        # Daily snapshot (one per calendar day)
        day_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        daily = _ICLOUD_BACKUP_DIR / f"soma_daily_{day_str}.db"
        if not daily.exists():
            shutil.copy2(str(_DB_PATH), str(daily))

        # Prune daily snapshots beyond 7
        dailies = sorted(_ICLOUD_BACKUP_DIR.glob("soma_daily_*.db"))
        while len(dailies) > MAX_ICLOUD_DAILY:
            oldest = dailies.pop(0)
            oldest.unlink()

        size_kb = latest.stat().st_size / 1024
        daily_count = len(list(_ICLOUD_BACKUP_DIR.glob("soma_daily_*.db")))
        print(f"  [T2 iCloud]  soma_latest.db ({size_kb:.1f} KB) + {daily_count} daily snapshots → iCloud sync")

    except Exception as e:
        print(f"  [T2 iCloud]  offsite backup failed (non-fatal): {e}")


# ── Main ──────────────────────────────────────────────────────────────────────

def run_backup():
    """Run all backup tiers. Returns local backup filename or None."""

    if not _DB_PATH.exists():
        print(f"  [backup]     No database at {_DB_PATH} — skipping all tiers")
        return None

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    print("  SOMA Backup:")

    # Tier 1: Local timestamped copy
    backup_name = _tier1_local_backup(ts)

    # Tier 2: iCloud offsite (fire-and-forget)
    _tier2_icloud_backup(ts)

    return backup_name


if __name__ == "__main__":
    run_backup()
