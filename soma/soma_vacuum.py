#!/usr/bin/env python3
"""
SOMA Vacuum — Database pruning, maintenance & health check utility.

Keeps soma.db lean by enforcing retention policies on high-volume tables
while preserving all configuration, reference, and low-volume data.

Usage:
    python3 ~/Desktop/DABEIBA/shared/soma/soma_vacuum.py              # dry-run (shows what would be pruned)
    python3 ~/Desktop/DABEIBA/shared/soma/soma_vacuum.py --execute    # actually prune + vacuum
    python3 ~/Desktop/DABEIBA/shared/soma/soma_vacuum.py --stats      # show DB stats only

Retention Policies:
    ┌──────────────────────┬────────────┬──────────────────────────────────┐
    │ Table                │ Keep       │ Reason                           │
    ├──────────────────────┼────────────┼──────────────────────────────────┤
    │ regime_history       │ 365 days   │ Full year for trend analysis     │
    │ valuations           │ 365 days   │ Full year for valuation history  │
    │ geo_events           │ 90 days    │ High volume, recent = relevant   │
    │ geo_vectors          │ 180 days   │ Moderate volume, baseline needs  │
    │ geo_baselines        │ 180 days   │ Keep aligned with vectors        │
    │ onchain_metrics      │ 365 days   │ Annual cycle analysis            │
    │ onchain_signals      │ 365 days   │ Annual cycle analysis            │
    │ raw_intelligence     │ 90 days    │ High volume, consumed = done     │
    │ philosophy_evidence  │ 365 days   │ Thesis evidence trail            │
    │ philosophy_history   │ 365 days   │ Conviction change history        │
    │ horizon_analyses     │ 180 days   │ Tactical — recent = relevant     │
    │ events               │ 180 days   │ System events log                │
    │ kb_audit_log         │ 90 days    │ High volume audit trail          │
    │ kb_violations        │ 180 days   │ Compliance audit trail           │
    │ outlook_snapshots    │ 365 days   │ Full year of outlook history     │
    │ trade_log            │ forever    │ Never prune — audit trail        │
    │ portfolio_state      │ forever    │ Never prune — audit trail        │
    │ client_profiles      │ forever    │ Never prune — reference data     │
    │ client_interactions  │ forever    │ Never prune — relationship data  │
    │ philosophy_beliefs   │ forever    │ Never prune — active beliefs     │
    │ philosophy_alerts    │ forever    │ Never prune — review trail       │
    │ kb_rules             │ forever    │ Never prune — knowledge base     │
    │ schema_version       │ forever    │ Never prune — migration state    │
    └──────────────────────┴────────────┴──────────────────────────────────┘

After pruning:
    - Runs VACUUM to reclaim disk space
    - Runs PRAGMA integrity_check
    - Reports before/after sizes
"""

import os
import sys
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

_PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, _PROJECT_ROOT)

from shared.soma.soma_bridge import SomaBridge

# ── ANSI ─────────────────────────────────────────────────────────────
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RESET = "\033[0m"

# ── Retention policies (table → days to keep, None = forever) ────────
RETENTION_POLICIES = {
    "regime_history":       365,
    "valuations":           365,
    "geo_events":           90,
    "geo_vectors":          180,
    "geo_baselines":        180,
    "onchain_metrics":      365,
    "onchain_signals":      365,
    "raw_intelligence":     90,
    "philosophy_evidence":  365,
    "philosophy_history":   365,
    "horizon_analyses":     180,
    "events":               180,
    "kb_audit_log":         90,
    "kb_violations":        180,
    "outlook_snapshots":    365,
    # Never pruned (None = forever)
    "trade_log":            None,
    "portfolio_state":      None,
    "client_profiles":      None,
    "client_interactions":  None,
    "philosophy_beliefs":   None,
    "philosophy_alerts":    None,
    "kb_rules":             None,
    "schema_version":       None,
}


def _get_db_size(db_path):
    """Return database file size in bytes."""
    try:
        return os.path.getsize(db_path)
    except OSError:
        return 0


def _format_size(bytes_val):
    """Format bytes as human-readable string."""
    if bytes_val < 1024:
        return f"{bytes_val} B"
    elif bytes_val < 1024 * 1024:
        return f"{bytes_val / 1024:.1f} KB"
    else:
        return f"{bytes_val / (1024 * 1024):.2f} MB"


def _get_table_stats(conn):
    """Return row counts for all tables."""
    stats = {}
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    for t in tables:
        name = t[0]
        try:
            count = conn.execute(f"SELECT COUNT(*) FROM [{name}]").fetchone()[0]
            stats[name] = count
        except Exception:
            stats[name] = -1  # table exists but can't count
    return stats


def _detect_timestamp_column(conn, table):
    """Detect which column to use for age-based pruning.

    Priority: write_timestamp > date > detected_at > ingested_at > logged_at
    """
    try:
        info = conn.execute(f"PRAGMA table_info([{table}])").fetchall()
        columns = [row[1] for row in info]
    except Exception:
        return None

    for candidate in ["write_timestamp", "date", "detected_at", "ingested_at",
                      "logged_at", "change_date", "date_flagged", "applied_at"]:
        if candidate in columns:
            return candidate
    return None


def run_vacuum(db_path=None, execute=False, stats_only=False):
    """Run the vacuum cycle.

    Args:
        db_path: Override path (for testing).
        execute: If True, actually delete rows and vacuum. If False, dry-run.
        stats_only: If True, only show stats without pruning plan.

    Returns:
        dict with results.
    """
    with SomaBridge(db_path) as bridge:
        bridge.initialize_db()
        conn = bridge.conn
        actual_path = bridge.db_path

        size_before = _get_db_size(actual_path)
        table_stats = _get_table_stats(conn)

        print(f"\n{BOLD}{'=' * 60}{RESET}")
        print(f"{BOLD}  SOMA Vacuum — Database Maintenance{RESET}")
        print(f"{DIM}  {datetime.now(timezone.utc).isoformat()}{RESET}")
        print(f"{BOLD}{'=' * 60}{RESET}")

        print(f"\n{CYAN}Database:{RESET}  {actual_path}")
        print(f"{CYAN}Size:{RESET}      {_format_size(size_before)}")
        print(f"{CYAN}Tables:{RESET}    {len(table_stats)}")
        print(f"{CYAN}Mode:{RESET}      {'EXECUTE' if execute else 'STATS ONLY' if stats_only else 'DRY RUN'}")

        # ── Table stats ─────────────────────────────────────────────
        print(f"\n{BOLD}--- Table Row Counts ---{RESET}")
        total_rows = 0
        for table in sorted(table_stats.keys()):
            count = table_stats[table]
            total_rows += max(0, count)
            policy = RETENTION_POLICIES.get(table)
            policy_str = f"{policy}d" if policy else "∞"
            if count > 1000:
                color = YELLOW
            elif count == 0:
                color = DIM
            else:
                color = RESET
            print(f"  {color}{table:<25} {count:>8,} rows  (keep: {policy_str}){RESET}")

        print(f"\n  {BOLD}Total: {total_rows:,} rows{RESET}")

        if stats_only:
            # Integrity check
            print(f"\n{BOLD}--- Integrity Check ---{RESET}")
            result = conn.execute("PRAGMA integrity_check").fetchone()
            status = result[0] if result else "unknown"
            color = GREEN if status == "ok" else RED
            print(f"  {color}{status}{RESET}")

            # Schema version
            ver = bridge.get_schema_version()
            print(f"\n{CYAN}Schema version:{RESET} {ver}")

            print(f"\n{BOLD}{'=' * 60}{RESET}\n")
            return {"size": size_before, "tables": table_stats, "integrity": status}

        # ── Pruning plan ────────────────────────────────────────────
        print(f"\n{BOLD}--- Pruning Plan ---{RESET}")
        now = datetime.now(timezone.utc)
        prune_plan = {}
        total_to_prune = 0

        for table, retention_days in RETENTION_POLICIES.items():
            if retention_days is None:
                continue  # forever — skip
            if table not in table_stats or table_stats[table] == 0:
                continue  # empty — skip

            ts_col = _detect_timestamp_column(conn, table)
            if not ts_col:
                print(f"  {DIM}{table:<25} — no timestamp column found, skipping{RESET}")
                continue

            cutoff = (now - timedelta(days=retention_days)).strftime("%Y-%m-%d")

            # Count rows that would be pruned
            try:
                count = conn.execute(
                    f"SELECT COUNT(*) FROM [{table}] WHERE [{ts_col}] < ?",
                    (cutoff,),
                ).fetchone()[0]
            except Exception as e:
                print(f"  {RED}{table:<25} — count failed: {e}{RESET}")
                continue

            if count > 0:
                prune_plan[table] = {
                    "column": ts_col,
                    "cutoff": cutoff,
                    "retention_days": retention_days,
                    "rows_to_prune": count,
                    "rows_total": table_stats[table],
                }
                total_to_prune += count
                pct = count / table_stats[table] * 100
                print(f"  {YELLOW}{table:<25} {count:>6,} / {table_stats[table]:>6,} rows "
                      f"({pct:.0f}%) older than {retention_days}d{RESET}")
            else:
                print(f"  {GREEN}{table:<25} — all rows within {retention_days}d retention{RESET}")

        if total_to_prune == 0:
            print(f"\n  {GREEN}Nothing to prune — database is clean.{RESET}")
            print(f"\n{BOLD}{'=' * 60}{RESET}\n")
            return {
                "size_before": size_before,
                "size_after": size_before,
                "rows_pruned": 0,
                "tables_pruned": 0,
            }

        print(f"\n  {BOLD}Total to prune: {total_to_prune:,} rows across {len(prune_plan)} table(s){RESET}")

        if not execute:
            print(f"\n  {YELLOW}DRY RUN — no rows deleted. Run with --execute to apply.{RESET}")
            print(f"\n{BOLD}{'=' * 60}{RESET}\n")
            return {
                "size_before": size_before,
                "rows_to_prune": total_to_prune,
                "tables": prune_plan,
                "mode": "dry_run",
            }

        # ── Execute pruning ─────────────────────────────────────────
        print(f"\n{BOLD}--- Executing Prune ---{RESET}")
        rows_deleted = 0
        tables_pruned = 0

        for table, plan in prune_plan.items():
            try:
                conn.execute(
                    f"DELETE FROM [{table}] WHERE [{plan['column']}] < ?",
                    (plan["cutoff"],),
                )
                rows_deleted += plan["rows_to_prune"]
                tables_pruned += 1
                print(f"  {GREEN}✓{RESET} {table}: {plan['rows_to_prune']:,} rows deleted")
            except Exception as e:
                print(f"  {RED}✗{RESET} {table}: delete failed — {e}")

        conn.commit()

        # ── VACUUM ──────────────────────────────────────────────────
        print(f"\n{BOLD}--- VACUUM ---{RESET}")
        try:
            conn.execute("VACUUM")
            print(f"  {GREEN}VACUUM completed{RESET}")
        except Exception as e:
            print(f"  {RED}VACUUM failed: {e}{RESET}")

        size_after = _get_db_size(actual_path)
        saved = size_before - size_after

        # ── Integrity check ─────────────────────────────────────────
        print(f"\n{BOLD}--- Integrity Check ---{RESET}")
        result = conn.execute("PRAGMA integrity_check").fetchone()
        status = result[0] if result else "unknown"
        color = GREEN if status == "ok" else RED
        print(f"  {color}{status}{RESET}")

        # ── Summary ─────────────────────────────────────────────────
        print(f"\n{BOLD}--- Summary ---{RESET}")
        print(f"  {CYAN}Rows deleted:{RESET}   {rows_deleted:,}")
        print(f"  {CYAN}Tables pruned:{RESET}  {tables_pruned}")
        print(f"  {CYAN}Size before:{RESET}    {_format_size(size_before)}")
        print(f"  {CYAN}Size after:{RESET}     {_format_size(size_after)}")
        if saved > 0:
            print(f"  {GREEN}Space saved:{RESET}    {_format_size(saved)}")
        else:
            print(f"  {DIM}Space saved:    (none — WAL may need checkpoint){RESET}")

        print(f"\n{BOLD}{'=' * 60}{RESET}\n")

        return {
            "size_before": size_before,
            "size_after": size_after,
            "space_saved": saved,
            "rows_deleted": rows_deleted,
            "tables_pruned": tables_pruned,
            "integrity": status,
            "mode": "execute",
        }


# ── CLI entry point ──────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="SOMA Vacuum — database pruning & maintenance")
    parser.add_argument("--execute", action="store_true", help="Actually prune rows and vacuum (default: dry-run)")
    parser.add_argument("--stats", action="store_true", help="Show DB stats only, no pruning plan")
    parser.add_argument("--db", type=str, default=None, help="Override database path")
    args = parser.parse_args()

    run_vacuum(db_path=args.db, execute=args.execute, stats_only=args.stats)
