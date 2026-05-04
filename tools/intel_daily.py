#!/usr/bin/env python3
"""
intel_daily.py — DABEIBA Intel Date Layer Manager

Usage:
  python3 intel_daily.py register <deck_path> [--domain DOMAIN] [--slug SLUG] [--slides N] [--insight TEXT] [--flags TEXT]
  python3 intel_daily.py show [YYYY-MM-DD]
  python3 intel_daily.py week [YYYY-MM-DD]
  python3 intel_daily.py open [YYYY-MM-DD]

Commands:
  register  — Register a new deck: create symlink in by-date/, append to DAILY_INDEX.md
  show      — Print the DAILY_INDEX.md for a given date (default: today)
  week      — Show all daily indices for the week containing the given date
  open      — Open the DAILY_INDEX.md in the default editor

Examples:
  python3 intel_daily.py register ~/Desktop/DABEIBA/intel/by-topic/macro/regime/INTEL_20260415_01_jm-ep113.pptx \\
      --domain "Macro / Regime" --slug "jm-ep113" --slides 25 \\
      --insight "Hormuz closed, Iran accepts BTC" --flags "PROMOTER, CONFLICT"

  python3 intel_daily.py show 2026-04-15
  python3 intel_daily.py week
"""

import argparse
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# DABEIBA_ROOT env var allows override for sandbox/testing
def _resolve_dabeiba_root() -> Path:
    """3-tier fallback: $DABEIBA_ROOT -> ~/Desktop/DABEIBA -> walk up from __file__."""
    env = os.environ.get("DABEIBA_ROOT")
    if env:
        return Path(env)
    default_home = Path.home() / "Desktop" / "DABEIBA"
    if default_home.exists():
        return default_home
    here = Path(__file__).resolve()
    for parent in here.parents:
        if parent.name == "DABEIBA":
            return parent
    return default_home


_DABEIBA = _resolve_dabeiba_root()
INTEL_ROOT = _DABEIBA / "intel"
BY_DATE = INTEL_ROOT / "by-date"
BY_TOPIC = INTEL_ROOT / "by-topic"

MONTH_NAMES = {
    1: "01-January", 2: "02-February", 3: "03-March", 4: "04-April",
    5: "05-May", 6: "06-June", 7: "07-July", 8: "08-August",
    9: "09-September", 10: "10-October", 11: "11-November", 12: "12-December",
}


def date_dir(dt: datetime) -> Path:
    """Return the by-date directory for a given date."""
    return BY_DATE / str(dt.year) / MONTH_NAMES[dt.month] / f"{dt.day:02d}"


def parse_date(date_str: str | None) -> datetime:
    """Parse YYYY-MM-DD or default to today."""
    if date_str:
        return datetime.strptime(date_str, "%Y-%m-%d")
    return datetime.now()


def extract_date_from_filename(filename: str) -> datetime | None:
    """Extract date from INTEL_YYYYMMDD_NN_slug.pptx naming convention."""
    parts = filename.split("_")
    if len(parts) >= 2 and parts[0] == "INTEL" and len(parts[1]) == 8:
        try:
            return datetime.strptime(parts[1], "%Y%m%d")
        except ValueError:
            pass
    return None


def compute_relative_symlink(link_location: Path, target: Path) -> str:
    """Compute a relative path from link_location's parent to target."""
    return os.path.relpath(target, link_location.parent)


def register(args):
    """Register a new deck in the date layer."""
    deck_path = Path(args.deck_path).resolve()

    if not deck_path.exists():
        print(f"ERROR: Deck not found: {deck_path}", file=sys.stderr)
        sys.exit(1)

    # Extract date from filename
    dt = extract_date_from_filename(deck_path.name)
    if not dt:
        print("ERROR: Cannot parse date from filename. Expected INTEL_YYYYMMDD_NN_slug.pptx", file=sys.stderr)
        sys.exit(1)

    # Determine slug
    slug = args.slug
    if not slug:
        # Auto-derive from filename: INTEL_20260415_01_jm-ep113.pptx → jm-ep113
        parts = deck_path.stem.split("_", 3)
        slug = parts[3] if len(parts) >= 4 else deck_path.stem

    # Determine domain from path (e.g., by-topic/macro/regime → "macro/regime")
    domain = args.domain
    if not domain:
        try:
            rel = deck_path.relative_to(BY_TOPIC)
            domain = "/".join(rel.parent.parts)
        except ValueError:
            domain = "uncategorized"

    # Create date directory
    day_dir = date_dir(dt)
    day_dir.mkdir(parents=True, exist_ok=True)

    # Create symlink (domain-slug.pptx)
    safe_domain = domain.lower().replace(" / ", "-").replace("/", "-").replace(" ", "-")
    link_name = f"{safe_domain}-{slug}.pptx"
    link_path = day_dir / link_name

    if link_path.exists() or link_path.is_symlink():
        print(f"Symlink already exists: {link_path}")
    else:
        rel_target = compute_relative_symlink(link_path, deck_path)
        link_path.symlink_to(rel_target)
        print(f"Created symlink: {link_name} → {rel_target}")

    # Append to DAILY_INDEX.md
    index_path = day_dir / "DAILY_INDEX.md"
    slides = args.slides or "?"
    insight = args.insight or "—"
    flags = args.flags or "—"

    # Build or update DAILY_INDEX.md
    index_path = day_dir / "DAILY_INDEX.md"
    entry_num = 1

    if index_path.exists():
        lines = index_path.read_text().split("\n")
        # Count existing table entries and find last table row position
        last_table_line = -1
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("| ") and len(stripped) > 2 and stripped[2:3].isdigit():
                entry_num += 1
                last_table_line = i

        # If we found table rows, insert after the last one
        # If no table rows found, look for the header separator |---|
        if last_table_line == -1:
            for i, line in enumerate(lines):
                if line.strip().startswith("|---"):
                    last_table_line = i
                    break

        entry = f"| {entry_num} | {domain} | [{slug}]({link_name}) | {slides} | {insight} | {flags} |"

        if last_table_line >= 0:
            lines.insert(last_table_line + 1, entry)
        else:
            # Fallback: append to end
            lines.append(entry)

        index_path.write_text("\n".join(lines))
    else:
        # Create new index file with header + first entry
        content = f"# {dt.strftime('%Y-%m-%d')} — Intelligence Digest\n\n"
        content += "## Artifacts Produced\n\n"
        content += "| # | Domain | Slug | Slides | Key Insight | Flags |\n"
        content += "|---|--------|------|--------|-------------|-------|\n"
        content += f"| {entry_num} | {domain} | [{slug}]({link_name}) | {slides} | {insight} | {flags} |\n"
        index_path.write_text(content)

    print(f"Added entry #{entry_num} to {index_path.name}")
    print(f"Date: {dt.strftime('%Y-%m-%d')} | Domain: {domain} | Slug: {slug}")


def show(args):
    """Show the daily index for a date."""
    dt = parse_date(args.date)
    index_path = date_dir(dt) / "DAILY_INDEX.md"

    if not index_path.exists():
        print(f"No intelligence logged for {dt.strftime('%Y-%m-%d')}")
        # Check nearby dates
        for delta in range(-3, 4):
            check_dt = dt + timedelta(days=delta)
            check_path = date_dir(check_dt) / "DAILY_INDEX.md"
            if check_path.exists() and delta != 0:
                print(f"  Nearest: {check_dt.strftime('%Y-%m-%d')}")
        sys.exit(0)

    print(index_path.read_text())


def week(args):
    """Show all daily indices for the week."""
    dt = parse_date(args.date)
    # Go to Monday of this week
    monday = dt - timedelta(days=dt.weekday())

    found = 0
    for i in range(7):
        day = monday + timedelta(days=i)
        index_path = date_dir(day) / "DAILY_INDEX.md"
        if index_path.exists():
            print(f"{'=' * 60}")
            print(index_path.read_text())
            found += 1

    if found == 0:
        print(f"No intelligence logged for week of {monday.strftime('%Y-%m-%d')}")


def open_index(args):
    """Open the daily index in default editor."""
    dt = parse_date(args.date)
    index_path = date_dir(dt) / "DAILY_INDEX.md"

    if not index_path.exists():
        print(f"No intelligence logged for {dt.strftime('%Y-%m-%d')}")
        sys.exit(1)

    os.system(f"open '{index_path}'")


def main():
    parser = argparse.ArgumentParser(description="DABEIBA Intel Date Layer Manager")
    sub = parser.add_subparsers(dest="command")

    # register
    reg = sub.add_parser("register", help="Register a new deck in the date layer")
    reg.add_argument("deck_path", help="Path to the .pptx file")
    reg.add_argument("--domain", help="Display domain (e.g., 'Macro / Regime')")
    reg.add_argument("--slug", help="Short slug (auto-derived from filename if omitted)")
    reg.add_argument("--slides", type=int, help="Number of content slides")
    reg.add_argument("--insight", help="One-line key insight")
    reg.add_argument("--flags", help="Red flags (e.g., 'PROMOTER, CONFLICT')")

    # show
    sh = sub.add_parser("show", help="Show daily index")
    sh.add_argument("date", nargs="?", help="Date (YYYY-MM-DD, default: today)")

    # week
    wk = sub.add_parser("week", help="Show weekly intelligence")
    wk.add_argument("date", nargs="?", help="Any date in the target week")

    # open
    op = sub.add_parser("open", help="Open daily index in editor")
    op.add_argument("date", nargs="?", help="Date (YYYY-MM-DD, default: today)")

    args = parser.parse_args()

    if args.command == "register":
        register(args)
    elif args.command == "show":
        show(args)
    elif args.command == "week":
        week(args)
    elif args.command == "open":
        open_index(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
