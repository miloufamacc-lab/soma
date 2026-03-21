#!/usr/bin/env python3
"""
DABEIBA Cloud Setup — one-time symlink creation + folder scaffolding.

Run once on any new machine:
    python3 ~/Desktop/DABEIBA/shared/setup_cloud.py

What it does:
    1. Detects Google Drive for Desktop mount point (jacobo.pae@gmail.com)
    2. Creates ~/DABEIBA_Cloud symlink → Google Drive/DABEIBA/
    3. Scaffolds subdirectories: soma/, oracle/, mantis/, cipher/, exports/
    4. Prints a confirmation with the resolved path

To switch cloud providers later:
    rm ~/DABEIBA_Cloud
    ln -s /new/cloud/path/DABEIBA ~/DABEIBA_Cloud
    # Zero code changes needed — all modules use ~/DABEIBA_Cloud/
"""

import sys
from pathlib import Path

# ── Google Drive detection ────────────────────────────────────────────────────
# Tried in order. First match wins.
_GDRIVE_CANDIDATES = [
    Path.home() / "Library" / "CloudStorage" / "GoogleDrive-jacobo.pae@gmail.com" / "My Drive",
    Path.home() / "Google Drive" / "My Drive",
    Path("/Volumes/GoogleDrive/My Drive"),
]

_SYMLINK = Path.home() / "DABEIBA_Cloud"
_SUBDIRS = ["soma", "oracle", "mantis", "cipher", "exports"]


def main():
    print()
    print("  DABEIBA Cloud Setup")
    print("  " + "─" * 40)

    # Step 1: Find Google Drive
    gdrive = next((p for p in _GDRIVE_CANDIDATES if p.exists()), None)
    if gdrive is None:
        print("  ERROR: Google Drive for Desktop not found.")
        print("  Checked:")
        for p in _GDRIVE_CANDIDATES:
            print(f"    {p}")
        print()
        print("  Install Google Drive for Desktop, sign in with jacobo.pae@gmail.com,")
        print("  then re-run this script.")
        sys.exit(1)

    print(f"  Found Google Drive: {gdrive}")

    # Step 2: Create DABEIBA folder in Google Drive
    target = gdrive / "DABEIBA"
    target.mkdir(exist_ok=True)
    print(f"  Cloud folder: {target}")

    # Step 3: Create or update symlink
    if _SYMLINK.is_symlink():
        current = _SYMLINK.resolve()
        if current == target.resolve():
            print(f"  Symlink OK: ~/DABEIBA_Cloud → {target}")
        else:
            _SYMLINK.unlink()
            _SYMLINK.symlink_to(target)
            print(f"  Symlink updated: ~/DABEIBA_Cloud → {target}")
    elif _SYMLINK.exists():
        print(f"  WARNING: ~/DABEIBA_Cloud exists but is not a symlink.")
        print(f"  Remove it manually, then re-run this script.")
        sys.exit(1)
    else:
        _SYMLINK.symlink_to(target)
        print(f"  Symlink created: ~/DABEIBA_Cloud → {target}")

    # Step 4: Scaffold subdirectories
    for sub in _SUBDIRS:
        (target / sub).mkdir(exist_ok=True)
    print(f"  Subdirectories: {', '.join(_SUBDIRS)}")

    # Done
    print()
    print(f"  All modules now write to ~/DABEIBA_Cloud/{{module}}/")
    print(f"  Google Drive syncs automatically to jacobo.pae@gmail.com.")
    print("  " + "─" * 40)
    print()


if __name__ == "__main__":
    main()
