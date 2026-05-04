#!/usr/bin/env python3
"""
SOMA-INTEL Step 1.3 — Graph Query CLI

Read-only interrogation of the soma_intel_* graph.

Commands:
  node   <node_id>             — show node details + all edges
  search <text>                — FTS search across node names
  edges  <node_id>             — list edges (filterable by type/direction)
  platform <pl_id>             — list all nodes on a platform
  stats                        — DB-wide counts by type
  audit  [--limit N]           — show unaudited edge queue
  path   <src_id> <dst_id>     — find 1-hop paths between two nodes

Usage examples:
  python3 soma/intel/query.py stats
  python3 soma/intel/query.py node co_TSLA
  python3 soma/intel/query.py search "autonomous vehicles"
  python3 soma/intel/query.py edges co_NVDA --type is_a
  python3 soma/intel/query.py edges co_NVDA --direction out
  python3 soma/intel/query.py platform pl_ai
  python3 soma/intel/query.py path co_TSLA pl_robotics
  python3 soma/intel/query.py audit --limit 20
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional

# ── Path bootstrap ────────────────────────────────────────────────────────────
_HERE    = Path(__file__).resolve().parent
_DABEIBA = _HERE.parent.parent.parent
for _p in [str(_DABEIBA), str(_DABEIBA / "shared")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from soma.intel.store import IntelStore, Edge, Node

# ── DB path ───────────────────────────────────────────────────────────────────
DB_PATH = (
    Path(os.environ["SOMA_DB_PATH"])
    if "SOMA_DB_PATH" in os.environ
    else _DABEIBA / "shared" / "soma" / "data" / "soma.db"
)

# ── ANSI colour helpers (disabled if not a TTY) ───────────────────────────────
_USE_COLOR = sys.stdout.isatty()

def _c(code: str, text: str) -> str:
    if not _USE_COLOR:
        return text
    return f"\033[{code}m{text}\033[0m"

def _bold(t: str)  -> str: return _c("1", t)
def _dim(t: str)   -> str: return _c("2", t)
def _cyan(t: str)  -> str: return _c("36", t)
def _green(t: str) -> str: return _c("32", t)
def _yellow(t: str)-> str: return _c("33", t)
def _red(t: str)   -> str: return _c("31", t)
def _blue(t: str)  -> str: return _c("34", t)

# ── Edge type colour map ──────────────────────────────────────────────────────
_EDGE_COLORS = {
    "is_a":               _cyan,
    "competes_with":      _red,
    "supplies":           _green,
    "holds":              _yellow,
    "mentioned_in":       _dim,
    "causes":             _red,
    "has_thesis":         _blue,
    "has_target_price":   _green,
    "expresses_sentiment":_yellow,
    "belongs_to_platform":_cyan,
    "convergence_of":     _blue,
    "regime_was":         _yellow,
    "correlated_with":    _cyan,
    "disrupts":           _red,
    "succeeded_by":       _dim,
}

def _edge_color(et: str) -> str:
    fn = _EDGE_COLORS.get(et, lambda x: x)
    return fn(et)


# ════════════════════════════════════════════════════════════════════════════
# Formatters
# ════════════════════════════════════════════════════════════════════════════

def _fmt_node(n: Node, verbose: bool = False) -> str:
    lines = [
        f"{_bold(n.node_id)}  {_dim('|')}  {n.name}  {_dim('|')}  type={_cyan(n.node_type)}",
    ]
    if n.aliases:
        lines.append(f"  aliases: {', '.join(n.aliases[:6])}"
                     + (" ..." if len(n.aliases) > 6 else ""))
    if verbose and n.metadata:
        for k, v in sorted(n.metadata.items()):
            if v is not None:
                lines.append(f"  {_dim(k)}: {v}")
    lines.append(f"  created: {n.created_ts[:10]}  last_seen: {n.last_seen_ts[:10]}")
    return "\n".join(lines)


def _fmt_edge(e: Edge, relative_to: Optional[str] = None) -> str:
    """One-line edge display, direction-aware relative to a node."""
    if relative_to and e.src_node_id == relative_to:
        arrow = f"{_bold('→')} {_edge_color(e.edge_type)} {_bold('→')} {e.dst_node_id}"
    elif relative_to and e.dst_node_id == relative_to:
        arrow = f"{e.src_node_id} {_bold('→')} {_edge_color(e.edge_type)} {_bold('→')}"
    else:
        arrow = (f"{e.src_node_id} {_bold('→')} {_edge_color(e.edge_type)} "
                 f"{_bold('→')} {e.dst_node_id}")

    conf_s  = _green(f"{e.confidence:.2f}") if e.confidence >= 0.70 else \
              _yellow(f"{e.confidence:.2f}") if e.confidence >= 0.50 else \
              _red(f"{e.confidence:.2f}")
    audit_s = _green("✓") if e.audit_status == "approved" else \
              _red("✗") if e.audit_status == "rejected" else \
              _dim("?")

    return (f"  [{e.edge_id:>5}] {arrow}  "
            f"conf={conf_s}  {audit_s}  "
            f"{_dim(e.source_type)}  {e.ts[:10]}")


def _fmt_edge_verbose(e: Edge) -> list[str]:
    lines = [_fmt_edge(e)]
    if e.evidence_text:
        # wrap at ~80 chars
        ev = e.evidence_text
        if len(ev) > 120:
            ev = ev[:117] + "..."
        lines.append(f"         evidence: {_dim(ev)}")
    lines.append(f"         source:   {e.source_id}  half_life={e.half_life_days}d")
    return lines


# ════════════════════════════════════════════════════════════════════════════
# Subcommand handlers
# ════════════════════════════════════════════════════════════════════════════

def cmd_stats(store: IntelStore, _args: argparse.Namespace) -> None:
    """DB-wide statistics."""
    node_total = store._c.execute("SELECT COUNT(*) FROM soma_intel_node").fetchone()[0]
    edge_total = store._c.execute("SELECT COUNT(*) FROM soma_intel_edge").fetchone()[0]
    unaudited  = store._c.execute(
        "SELECT COUNT(*) FROM soma_intel_edge WHERE audit_status='unaudited'"
    ).fetchone()[0]

    node_rows = store._c.execute(
        "SELECT node_type, COUNT(*) c FROM soma_intel_node GROUP BY node_type ORDER BY c DESC"
    ).fetchall()
    edge_rows = store._c.execute(
        "SELECT source_type, COUNT(*) c FROM soma_intel_edge GROUP BY source_type ORDER BY c DESC"
    ).fetchall()
    etype_rows = store._c.execute(
        "SELECT edge_type, COUNT(*) c FROM soma_intel_edge GROUP BY edge_type ORDER BY c DESC"
    ).fetchall()

    print(f"\n{_bold('SOMA-INTEL Graph Statistics')}")
    print(f"  {_bold('Nodes:')}  {node_total}")
    for r in node_rows:
        print(f"    {r[0]:<14} {r[1]}")
    print(f"\n  {_bold('Edges:')}  {edge_total}  (unaudited: {_yellow(str(unaudited))})")
    print(f"  By source:")
    for r in edge_rows:
        print(f"    {r[0]:<25} {r[1]}")
    print(f"  By type:")
    for r in etype_rows:
        print(f"    {_edge_color(r[0]):<35} {r[1]}")


def cmd_node(store: IntelStore, args: argparse.Namespace) -> None:
    """Show node detail + all edges."""
    node_id = args.node_id
    n = store.get_node(node_id)
    if not n:
        # Try FTS fallback
        hits = store.query_fts(node_id)
        if hits:
            print(f"{_yellow('Node not found exactly — FTS matches:')}")
            for h in hits[:5]:
                print(f"  {_bold(h.node_id)}  {h.name}  [{h.node_type}]")
        else:
            print(_red(f"Node not found: {node_id}"))
        return

    print(f"\n{_fmt_node(n, verbose=args.verbose)}")

    edges = store.neighbors(node_id)
    if not edges:
        print(_dim("  (no edges)"))
        return

    print(f"\n  {_bold(str(len(edges)))} edge(s):")
    for e in edges:
        if args.verbose:
            for line in _fmt_edge_verbose(e):
                print(line)
        else:
            print(_fmt_edge(e, relative_to=node_id))


def cmd_search(store: IntelStore, args: argparse.Namespace) -> None:
    """FTS search across node names."""
    text = " ".join(args.query)
    node_types = args.type.split(",") if args.type else None
    hits = store.query_fts(text, node_types=node_types)

    if not hits:
        print(_dim(f"No results for: {text!r}"))
        return

    print(f"\n{_bold(str(len(hits)))} result(s) for {_cyan(repr(text))}:")
    for h in hits[:args.limit]:
        print(f"  {_bold(h.node_id):<30}  {h.name:<40}  [{h.node_type}]")
    if len(hits) > args.limit:
        print(_dim(f"  ... {len(hits) - args.limit} more (increase --limit)"))


def cmd_edges(store: IntelStore, args: argparse.Namespace) -> None:
    """List edges for a node, with optional type/direction filters."""
    node_id = args.node_id
    n = store.get_node(node_id)
    if not n:
        print(_red(f"Node not found: {node_id}"))
        return

    edge_types = args.type.split(",") if args.type else None
    edges = store.neighbors(node_id, edge_types=edge_types)

    # Direction filter
    direction = getattr(args, "direction", "both")
    if direction == "out":
        edges = [e for e in edges if e.src_node_id == node_id]
    elif direction == "in":
        edges = [e for e in edges if e.dst_node_id == node_id]

    print(f"\n{_bold(node_id)}  ({n.name})  —  {_bold(str(len(edges)))} edge(s):")
    if not edges:
        print(_dim("  (no edges match filter)"))
        return

    for e in edges[:args.limit]:
        if args.verbose:
            for line in _fmt_edge_verbose(e):
                print(line)
        else:
            print(_fmt_edge(e, relative_to=node_id))

    if len(edges) > args.limit:
        print(_dim(f"  ... {len(edges) - args.limit} more (increase --limit)"))


def cmd_platform(store: IntelStore, args: argparse.Namespace) -> None:
    """List all company/security nodes on a platform."""
    pl_id = args.platform_id
    if not pl_id.startswith("pl_"):
        pl_id = f"pl_{pl_id}"

    pl_node = store.get_node(pl_id)
    if not pl_node:
        # Show available platforms
        rows = store._c.execute(
            "SELECT node_id, name FROM soma_intel_node WHERE node_type='platform'"
        ).fetchall()
        print(_red(f"Platform not found: {pl_id}"))
        print("Available platforms:")
        for r in rows:
            print(f"  {r[0]:<25} {r[1]}")
        return

    edges = store.neighbors(pl_id, edge_types=["belongs_to_platform"])
    # Deduplicate — multiple edges per src can exist (versioned). Show unique members.
    seen_src: set[str] = set()
    members: list[Edge] = []
    for e in edges:
        if e.dst_node_id == pl_id and e.src_node_id not in seen_src:
            members.append(e)
            seen_src.add(e.src_node_id)

    print(f"\n{_bold(pl_id)}  {pl_node.name}  —  {_bold(str(len(members)))} member(s):")
    for e in sorted(members, key=lambda x: x.src_node_id):
        src_node = store.get_node(e.src_node_id)
        name = src_node.name if src_node else "?"
        print(f"  {_bold(e.src_node_id):<20} {name}")


def cmd_path(store: IntelStore, args: argparse.Namespace) -> None:
    """Find 1-hop paths between two nodes (direct edge or shared neighbour)."""
    src_id = args.src
    dst_id = args.dst

    # Direct edge check
    direct = [
        e for e in store.neighbors(src_id)
        if e.dst_node_id == dst_id or e.src_node_id == dst_id
    ]
    if direct:
        print(f"\n{_bold('Direct edge(s)')} between {_cyan(src_id)} and {_cyan(dst_id)}:")
        for e in direct:
            print(_fmt_edge(e))
        return

    # 1-hop shared neighbour
    src_edges = store.neighbors(src_id)
    dst_edges = store.neighbors(dst_id)

    src_neighbors = set(
        e.dst_node_id if e.src_node_id == src_id else e.src_node_id
        for e in src_edges
    )
    dst_neighbors = set(
        e.dst_node_id if e.src_node_id == dst_id else e.src_node_id
        for e in dst_edges
    )

    shared = src_neighbors & dst_neighbors
    if not shared:
        print(_dim(f"No path found (≤1 hop) between {src_id} and {dst_id}"))
        return

    print(f"\n{_bold(str(len(shared)))} shared neighbour(s) between "
          f"{_cyan(src_id)} and {_cyan(dst_id)}:")
    for mid in sorted(shared)[:args.limit]:
        mid_node = store.get_node(mid)
        mid_name = mid_node.name if mid_node else "?"
        # Find the two bridging edges
        e1_list = [e for e in src_edges
                   if e.dst_node_id == mid or e.src_node_id == mid]
        e2_list = [e for e in dst_edges
                   if e.dst_node_id == mid or e.src_node_id == mid]
        e1 = e1_list[0] if e1_list else None
        e2 = e2_list[0] if e2_list else None

        print(f"\n  via {_bold(mid)}  ({mid_name}):")
        if e1:
            print(f"    {_fmt_edge(e1, relative_to=mid)}")
        if e2:
            print(f"    {_fmt_edge(e2, relative_to=mid)}")


def cmd_audit(store: IntelStore, args: argparse.Namespace) -> None:
    """Show unaudited edges sorted by confidence (lowest first)."""
    stratify = getattr(args, "stratify", "confidence")
    edges = store.audit_pending(limit=args.limit, stratify_by=stratify)

    total_unaudited = store._c.execute(
        "SELECT COUNT(*) FROM soma_intel_edge WHERE audit_status='unaudited'"
    ).fetchone()[0]

    print(f"\n{_bold('Audit Queue')}  —  {total_unaudited} total unaudited  "
          f"(showing {len(edges)}, sort={stratify}):")
    if not edges:
        print(_green("  Queue empty — all edges audited."))
        return

    for e in edges:
        if args.verbose:
            for line in _fmt_edge_verbose(e):
                print(line)
        else:
            print(_fmt_edge(e))

    if total_unaudited > args.limit:
        print(_dim(f"\n  ... {total_unaudited - args.limit} more. Increase --limit or run audit loop."))


# ════════════════════════════════════════════════════════════════════════════
# CLI wiring
# ════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="SOMA-INTEL graph query CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # stats
    sub.add_parser("stats", help="DB-wide node/edge counts")

    # node
    p_node = sub.add_parser("node", help="Show node detail + edges")
    p_node.add_argument("node_id")
    p_node.add_argument("-v", "--verbose", action="store_true")

    # search
    p_search = sub.add_parser("search", help="FTS search across node names")
    p_search.add_argument("query", nargs="+")
    p_search.add_argument("--type", default="", help="Comma-separated node types to restrict to")
    p_search.add_argument("--limit", type=int, default=20)

    # edges
    p_edges = sub.add_parser("edges", help="List edges for a node")
    p_edges.add_argument("node_id")
    p_edges.add_argument("--type",      default="", help="Comma-separated edge types")
    p_edges.add_argument("--direction", choices=["in", "out", "both"], default="both")
    p_edges.add_argument("--limit",     type=int, default=50)
    p_edges.add_argument("-v", "--verbose", action="store_true")

    # platform
    p_plat = sub.add_parser("platform", help="List all nodes on a platform")
    p_plat.add_argument("platform_id", help="e.g. pl_ai or just 'ai'")

    # path
    p_path = sub.add_parser("path", help="Find 1-hop paths between two nodes")
    p_path.add_argument("src")
    p_path.add_argument("dst")
    p_path.add_argument("--limit", type=int, default=10)

    # audit
    p_audit = sub.add_parser("audit", help="Show unaudited edge queue")
    p_audit.add_argument("--limit",    type=int, default=25)
    p_audit.add_argument("--stratify", choices=["confidence", "edge_type", "source_type"],
                         default="confidence")
    p_audit.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args()

    HANDLERS = {
        "stats":    cmd_stats,
        "node":     cmd_node,
        "search":   cmd_search,
        "edges":    cmd_edges,
        "platform": cmd_platform,
        "path":     cmd_path,
        "audit":    cmd_audit,
    }

    with IntelStore(db_path=DB_PATH) as store:
        HANDLERS[args.cmd](store, args)

    print()  # trailing newline


if __name__ == "__main__":
    main()
