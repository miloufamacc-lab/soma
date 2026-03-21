#!/usr/bin/env python3
"""
SOMA Backup — creates a timestamped copy of soma.db before any pipeline run.

Usage (standalone):
    python3 ~/Desktop/DABEIBA/shared/soma/backup_soma.py

What it does:
    1. Copies soma.db → backups/soma_backup_YYYYMMDD_HHMMSS.db
    2. Keeps only the 30 most recent backups (auto-deletes older ones)
    3. Prints a confirmation with file size and backup count
"""

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

# Paths
_SOMA_DIR = Path(__file__).parent
_DB_PATH = _SOMA_DIR / "data" / "soma.db"
_BACKUP_DIR = _SOMA_DIR / "backups"

# How many backups to keep
MAX_BACKUPS = 30


def run_backup():
    """Create a timestamped backup of soma.db and prune old backups.

    Returns the backup filename on success, or None if the database doesn't exist.
    """
    # ── Guard: nothing to back up if the database doesn't exist yet ──
    if not _DB_PATH.exists():
        print(f"⚠️  No database found at {_DB_PATH} — skipping backup.")
        return None

    # ── Create backups folder if needed ──
    _BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    # ── Copy the database with a timestamp in the filename ──
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_name = f"soma_backup_{ts}.db"
    dest = _BACKUP_DIR / backup_name
    shutil.copy2(str(_DB_PATH), str(dest))

    # ── Measure the backup size ──
    size_kb = dest.stat().st_size / 1024

    # ── Prune: keep only the newest MAX_BACKUPS files ──
    backups = sorted(_BACKUP_DIR.glob("soma_backup_*.db"))
    removed = 0
    while len(backups) > MAX_BACKUPS:
        oldest = backups.pop(0)
        oldest.unlink()
        removed += 1

    retained = len(list(_BACKUP_DIR.glob("soma_backup_*.db")))

    print(f"✅ Backup saved: {backup_name} ({size_kb:.1f} KB) — {retained} backups retained")

    return backup_name


if __name__ == "__main__":
    run_backup()
