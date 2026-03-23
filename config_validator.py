"""
DABEIBA Config Validator
========================
Validates API keys and credentials at startup for all modules.

Usage (in any module's entry point or settings file):

    import sys
    sys.path.insert(0, "/path/to/DABEIBA")  # or set at project root
    from shared.config_validator import validate_keys, KeySpec, load_env_file

    load_env_file("/path/to/.env")          # optional: load .env first
    validate_keys("ORACLE", [
        KeySpec("GURUFOCUS_API_KEY",  "GuruFocus API key",
                hint="gurufocus.com → My Account → API key"),
        KeySpec("GMAIL_APP_PASSWORD", "Gmail App Password",
                hint="Google Account → Security → 2-Step → App Passwords"),
    ])
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path


# ── ANSI colours ──────────────────────────────────────────────────────
_RED    = "\033[91m"
_YELLOW = "\033[93m"
_GREEN  = "\033[92m"
_BOLD   = "\033[1m"
_DIM    = "\033[2m"
_RESET  = "\033[0m"
_W      = 62


@dataclass
class KeySpec:
    """Describes one environment-variable credential that a module needs."""
    name: str
    description: str
    required: bool = True
    hint: str = ""


def load_env_file(env_path: str | Path) -> None:
    """
    Load key=value pairs from a .env file into os.environ.
    Skips blank lines and comments (#).
    Uses setdefault so already-set env vars are never overwritten.
    """
    p = Path(env_path)
    if not p.exists():
        return
    try:
        with open(p) as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                os.environ.setdefault(key.strip(), val.strip())
    except Exception as e:
        print(f"Warning: could not load .env file {p}: {e}")


def validate_keys(
    module_name: str,
    keys: list[KeySpec],
    *,
    exit_on_failure: bool = True,
) -> bool:
    """
    Check that every required KeySpec is present and non-empty in os.environ.

    Prints a clear, formatted error block listing each missing key, where to
    find it, and how to fix it.

    Args:
        module_name:      Short module label shown in the error header (e.g. "ORACLE").
        keys:             List of KeySpec objects describing required credentials.
        exit_on_failure:  If True (default), calls sys.exit(1) when any key is
                          missing. Set to False to get a bool return instead.

    Returns:
        True  — all keys are present.
        False — one or more required keys are missing (only when exit_on_failure=False).
    """
    missing: list[KeySpec] = [
        spec for spec in keys
        if spec.required and not os.environ.get(spec.name, "").strip()
    ]

    if not missing:
        return True

    # ── Error block ───────────────────────────────────────────────────
    print(f"\n{_RED}{'═' * _W}{_RESET}")
    print(f"{_RED}{_BOLD}  {module_name} — STARTUP ERROR: Missing Credentials{_RESET}")
    print(f"{_RED}{'═' * _W}{_RESET}\n")
    print(f"  The following API key(s) are required but not set:\n")

    for spec in missing:
        print(f"  {_BOLD}✗  {spec.name}{_RESET}")
        print(f"     {spec.description}")
        if spec.hint:
            print(f"     {_YELLOW}→  {spec.hint}{_RESET}")
        print()

    env_file = _env_file_hint(module_name)
    print(f"  {_DIM}Add the missing key(s) to:{_RESET}")
    print(f"  {_YELLOW}{env_file}{_RESET}")
    print(f"\n  {_DIM}Example:{_RESET}")
    for spec in missing:
        print(f"  {_DIM}{spec.name}=your-value-here{_RESET}")
    print(f"\n{_RED}{'═' * _W}{_RESET}\n")

    if exit_on_failure:
        sys.exit(1)
    return False


# ── Internal helpers ──────────────────────────────────────────────────

def _env_file_hint(module_name: str) -> str:
    """Return the .env file path hint for a given module."""
    locations: dict[str, str] = {
        "ORACLE": "~/Desktop/DABEIBA/oracle/.env",
        "CIPHER": "~/Desktop/DABEIBA/cipher/.env",
        "MANTIS": "~/Desktop/DABEIBA/mantis/convergence-backtester/config/telegram.env",
    }
    return locations.get(module_name.upper(), "the module's .env file")
