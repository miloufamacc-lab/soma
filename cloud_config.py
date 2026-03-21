"""
DABEIBA Cloud Config — single source of truth for the offsite sync path.

All modules import from here instead of hardcoding Google Drive paths.

The design:
    ~/DABEIBA_Cloud  →  symlink to Google Drive/DABEIBA/
    All modules write to ~/DABEIBA_Cloud/{module}/

If the symlink doesn't exist, cloud sync is silently skipped (fire-and-forget).
To set up:  python3 ~/Desktop/DABEIBA/shared/setup_cloud.py
To change providers: just repoint the symlink. Zero code changes.

Structure:
    ~/DABEIBA_Cloud/
        soma/           ← soma_latest.db + 7 daily snapshots
        oracle/         ← last_good_snapshot.json, api_tracker
        mantis/         ← backtest results, portfolio state
        cipher/         ← generated reports, outlooks
        exports/        ← on-demand exports (Excel, HTML, PDF)
"""

from pathlib import Path

# The ONE path every module uses. Symlink → Google Drive (or any cloud provider).
CLOUD_ROOT = Path.home() / "DABEIBA_Cloud"


def get_cloud_dir(module: str) -> Path | None:
    """Return the cloud sync directory for a module, or None if cloud not available.

    Usage:
        from cloud_config import get_cloud_dir
        cloud = get_cloud_dir("soma")
        if cloud:
            shutil.copy2(db_path, cloud / "soma_latest.db")
    """
    if not CLOUD_ROOT.exists():
        return None
    d = CLOUD_ROOT / module
    d.mkdir(parents=True, exist_ok=True)
    return d


def cloud_available() -> bool:
    """Check if the cloud symlink exists and is accessible."""
    return CLOUD_ROOT.exists() and CLOUD_ROOT.is_dir()
