#!/usr/bin/env python3
"""
SOMA-INTEL Phase 2 Step 2.1 — Convergence Engine

Runs three passes on the graph and writes derived edges + signals:

  PASS A — Platform Convergence Detection
    Finds co_* nodes with ≥2 distinct belongs_to_platform edges.
    Creates pairwise convergence concept nodes: cn_conv_<pl1>_<pl2>
    Creates convergence_of edges: co_TICKER → convergence_of → cn_conv_*
    Writes anomaly signals to soma_intel_signal.
    Writes beliefs to soma_intel_belief.

  PASS B — has_thesis Edge Population
    Derives has_thesis edges from existing mentioned_in edges where:
      - src is a company node (co_*)
      - dst is a thesis node (th_*)
      - thesis is "non-structural": mentioned by < MAX_STRUCTURAL_MENTIONS companies
    Skips if has_thesis edge already exists for the pair.

  PASS C — Belief Refresh
    Writes or refreshes soma_intel_belief rows for:
      - platform_count per company
      - signal_score (from universe_manager promotion_score)

All writes are dry-run by default. Pass --apply to commit.

Usage:
  python3 soma/intel/convergence_engine.py          # dry run
  python3 soma/intel/convergence_engine.py --apply  # write to DB
  python3 soma/intel/convergence_engine.py --apply --pass A   # single pass
  python3 soma/intel/convergence_engine.py --verbose
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import Optional

# ── Path bootstrap ────────────────────────────────────────────────────────────
_HERE    = Path(__file__).resolve().parent
_DABEIBA = _HERE.parent.parent.parent
for _p in [str(_DABEIBA), str(_DABEIBA / "shared")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from soma.intel.store import IntelStore

# ── Config ────────────────────────────────────────────────────────────────────
DB_PATH = (
    Path(os.environ["SOMA_DB_PATH"])
    if "SOMA_DB_PATH" in os.environ
    else _DABEIBA / "shared" / "soma" / "data" / "soma.db"
)

TODAY      = date.today().isoformat()
NOW        = datetime.now(timezone.utc).isoformat()

# Pass B threshold: theses mentioned by MORE than this many companies are structural
MAX_STRUCTURAL_MENTIONS = 50

# Convergence signal parameters
CONV_HALF_LIFE_DAYS = 180    # per VALID_EDGE_TYPES §A.2
CONV_BASE_CONFIDENCE = 0.90  # platform membership is curated, high confidence
HAS_THESIS_CONFIDENCE = 0.70 # derived from mentioned_in — moderate confidence

SOURCE_TYPE_CONVERGENCE = "derived"
SOURCE_TYPE_HAS_THESIS  = "derived"


# ════════════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════════════

def _slugify(text: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "-", text.lower().strip()).strip("-")


def _pl_short(pl_id: str) -> str:
    """pl_ai → ai, pl_energy_storage → energy-storage"""
    return pl_id[3:]   # strip "pl_"


def _conv_node_id(pl_a: str, pl_b: str) -> str:
    """Stable pair ID regardless of argument order."""
    a, b = sorted([_pl_short(pl_a), _pl_short(pl_b)])
    return f"cn_conv_{a}_{b}"


def _conv_node_name(pl_a: str, pl_b: str, pl_names: dict[str, str]) -> str:
    a, b = sorted([pl_a, pl_b])
    return f"{pl_names.get(a, a)} × {pl_names.get(b, b)} Convergence"


def _priority_from_count(count: int) -> str:
    """Platform count → signal priority label."""
    if count >= 4:
        return "CRITICAL"
    if count == 3:
        return "HIGH"
    return "MEDIUM"


def _anomaly_from_count(count: int) -> float:
    """Platform count → anomaly score in (0, 1]."""
    return min(1.0, round(count * 0.28, 3))


# ════════════════════════════════════════════════════════════════════════════
# Pass A — Platform Convergence Detection
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class ConvergenceResult:
    ticker: str
    node_id: str
    platforms: list[str]                # pl_* ids, sorted
    platform_names: dict[str, str]      # pl_id → display name
    conv_nodes_created: list[str] = field(default_factory=list)
    conv_edges_written: int = 0
    signal_written: bool = False
    belief_written: bool = False


def _load_platform_names(store: IntelStore) -> dict[str, str]:
    rows = store._c.execute(
        "SELECT node_id, name FROM soma_intel_node WHERE node_type='platform'"
    ).fetchall()
    return {r["node_id"]: r["name"] for r in rows}


def _get_platform_members(store: IntelStore) -> dict[str, list[str]]:
    """Returns co_node_id → sorted list of pl_ids (≥2 only)."""
    rows = store._c.execute(
        """
        SELECT src_node_id, dst_node_id
        FROM soma_intel_edge
        WHERE edge_type = 'belongs_to_platform'
          AND src_node_id LIKE 'co_%'
          AND dst_node_id LIKE 'pl_%'
          AND superseded_by IS NULL
        """
    ).fetchall()

    membership: dict[str, set[str]] = {}
    for r in rows:
        membership.setdefault(r["src_node_id"], set()).add(r["dst_node_id"])

    return {
        nid: sorted(pls)
        for nid, pls in membership.items()
        if len(pls) >= 2
    }


def run_pass_a(
    store: IntelStore,
    dry_run: bool,
    verbose: bool,
) -> dict:
    """Detect platform convergences, write edges + signals."""
    stats = {
        "convergence_nodes_created": 0,
        "convergence_edges_written": 0,
        "signals_written":           0,
        "beliefs_written":           0,
        "companies_processed":       0,
    }

    pl_names = _load_platform_names(store)
    members  = _get_platform_members(store)

    if verbose:
        print(f"  [Pass A] {len(members)} multi-platform companies found")

    for node_id, platforms in members.items():
        ticker = node_id[3:]
        stats["companies_processed"] += 1

        result = ConvergenceResult(
            ticker         = ticker,
            node_id        = node_id,
            platforms      = platforms,
            platform_names = pl_names,
        )

        # ── Create pairwise convergence concept nodes ─────────────────────
        for pl_a, pl_b in combinations(platforms, 2):
            conv_id   = _conv_node_id(pl_a, pl_b)
            conv_name = _conv_node_name(pl_a, pl_b, pl_names)

            if verbose:
                print(f"  [A:node] {conv_id}  {conv_name}")

            if not dry_run:
                store.upsert_node(
                    conv_id, "concept", conv_name,
                    aliases=[conv_id, conv_name],
                    metadata={
                        "convergence_platforms": [pl_a, pl_b],
                        "oracle_source":         "convergence_engine",
                    },
                )
            result.conv_nodes_created.append(conv_id)
            stats["convergence_nodes_created"] += 1

            # ── convergence_of edge: co_TICKER → conv_node ────────────────
            evidence = (
                f"{ticker} operates across both {pl_names.get(pl_a, pl_a)} "
                f"and {pl_names.get(pl_b, pl_b)} platforms"
            )
            if verbose:
                print(f"  [A:edge] {node_id} → convergence_of → {conv_id}  conf={CONV_BASE_CONFIDENCE}")
            if not dry_run:
                store.upsert_edge(
                    src          = node_id,
                    dst          = conv_id,
                    edge_type    = "convergence_of",
                    confidence   = CONV_BASE_CONFIDENCE,
                    source_id    = f"convergence_engine:{TODAY}",
                    evidence     = evidence,
                    source_type  = SOURCE_TYPE_CONVERGENCE,
                    half_life_days = CONV_HALF_LIFE_DAYS,
                    audit_status = "approved",   # derived from curated platform tags → trusted
                )
            result.conv_edges_written += 1
            stats["convergence_edges_written"] += 1

        # ── Write soma_intel_signal ────────────────────────────────────────
        priority    = _priority_from_count(len(platforms))
        anomaly     = _anomaly_from_count(len(platforms))
        features    = json.dumps({
            "platforms":          platforms,
            "platform_count":     len(platforms),
            "convergence_pairs":  [
                _conv_node_id(a, b)
                for a, b in combinations(platforms, 2)
            ],
            "platform_names":     {pl: pl_names.get(pl, pl) for pl in platforms},
        })

        if verbose:
            print(f"  [A:signal] {ticker}  priority={priority}  anomaly={anomaly}")

        if not dry_run:
            store._c.execute(
                """
                INSERT INTO soma_intel_signal
                  (ticker, date, priority, anomaly_score, features,
                   corroboration_count, half_life_days, status, horizon, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'active', 'medium',
                        'Platform convergence detected by convergence_engine')
                """,
                (ticker, TODAY, priority, anomaly, features,
                 len(platforms), CONV_HALF_LIFE_DAYS),
            )
        result.signal_written = True
        stats["signals_written"] += 1

        # ── Write soma_intel_belief ───────────────────────────────────────
        if verbose:
            print(f"  [A:belief] {node_id}  platform_count={len(platforms)}")
        if not dry_run:
            # Supersede any prior platform_count belief for this node
            prior = store._c.execute(
                """SELECT belief_id FROM soma_intel_belief
                   WHERE subject_node_id=? AND predicate='platform_count'
                     AND superseded_by IS NULL""",
                (node_id,),
            ).fetchone()
            prior_id = prior["belief_id"] if prior else None

            cur = store._c.execute(
                """
                INSERT INTO soma_intel_belief
                  (subject_node_id, predicate, value, confidence, ts,
                   source_id, superseded_by)
                VALUES (?, 'platform_count', ?, ?, ?, 'convergence_engine', ?)
                """,
                (node_id, str(len(platforms)), CONV_BASE_CONFIDENCE, NOW, prior_id),
            )
            if prior_id:
                store._c.execute(
                    "UPDATE soma_intel_belief SET superseded_by=? WHERE belief_id=?",
                    (cur.lastrowid, prior_id),
                )
        result.belief_written = True
        stats["beliefs_written"] += 1

    if not dry_run:
        store._c.commit()

    return stats


# ════════════════════════════════════════════════════════════════════════════
# Pass B — has_thesis Edge Population
# ════════════════════════════════════════════════════════════════════════════

def _structural_theses(store: IntelStore) -> set[str]:
    """
    Return thesis node IDs that are structural (mentioned by too many companies).
    These are wiki framework/meta articles, not investable thesis signals.
    """
    rows = store._c.execute(
        """
        SELECT dst_node_id, COUNT(DISTINCT src_node_id) as c
        FROM soma_intel_edge
        WHERE edge_type = 'mentioned_in'
          AND src_node_id LIKE 'co_%'
          AND dst_node_id LIKE 'th_%'
        GROUP BY dst_node_id
        HAVING c > ?
        """,
        (MAX_STRUCTURAL_MENTIONS,),
    ).fetchall()
    return {r["dst_node_id"] for r in rows}


def _existing_has_thesis_pairs(store: IntelStore) -> set[tuple[str, str]]:
    """Already-written has_thesis edges — skip re-writing."""
    rows = store._c.execute(
        """
        SELECT src_node_id, dst_node_id FROM soma_intel_edge
        WHERE edge_type = 'has_thesis'
          AND src_node_id LIKE 'co_%'
          AND superseded_by IS NULL
        """
    ).fetchall()
    return {(r["src_node_id"], r["dst_node_id"]) for r in rows}


def run_pass_b(
    store: IntelStore,
    dry_run: bool,
    verbose: bool,
) -> dict:
    """Derive has_thesis edges from non-structural mentioned_in pairs."""
    stats = {"has_thesis_written": 0, "skipped_structural": 0, "skipped_existing": 0}

    structural   = _structural_theses(store)
    existing     = _existing_has_thesis_pairs(store)

    # All co_* → mentioned_in → th_* edges
    rows = store._c.execute(
        """
        SELECT DISTINCT src_node_id, dst_node_id, source_id
        FROM soma_intel_edge
        WHERE edge_type  = 'mentioned_in'
          AND src_node_id LIKE 'co_%'
          AND dst_node_id LIKE 'th_%'
          AND superseded_by IS NULL
        """
    ).fetchall()

    for r in rows:
        co  = r["src_node_id"]
        th  = r["dst_node_id"]
        sid = r["source_id"]

        if th in structural:
            stats["skipped_structural"] += 1
            continue
        if (co, th) in existing:
            stats["skipped_existing"] += 1
            continue

        ticker    = co[3:]
        th_name   = store._c.execute(
            "SELECT name FROM soma_intel_node WHERE node_id=?", (th,)
        ).fetchone()
        th_label  = th_name["name"] if th_name else th

        evidence = f"{ticker} wiki article cross-links to thesis: {th_label}"
        if verbose:
            print(f"  [B:edge] {co} → has_thesis → {th}  conf={HAS_THESIS_CONFIDENCE}")

        if not dry_run:
            store.upsert_edge(
                src         = co,
                dst         = th,
                edge_type   = "has_thesis",
                confidence  = HAS_THESIS_CONFIDENCE,
                source_id   = f"derived:{sid}",
                evidence    = evidence,
                source_type = SOURCE_TYPE_HAS_THESIS,
                audit_status = "unaudited",
            )
        existing.add((co, th))   # prevent duplicates within this run
        stats["has_thesis_written"] += 1

    if not dry_run:
        store._c.commit()

    return stats


# ════════════════════════════════════════════════════════════════════════════
# Pass C — Belief Refresh (signal_score from universe_manager)
# ════════════════════════════════════════════════════════════════════════════

def run_pass_c(
    store: IntelStore,
    dry_run: bool,
    verbose: bool,
) -> dict:
    """
    Refresh signal_score beliefs for all universe tickers that have a
    promotion_score set (by universe_manager).
    """
    stats = {"beliefs_refreshed": 0}

    rows = store._c.execute(
        """
        SELECT ticker, promotion_score, promotion_source
        FROM soma_intel_universe
        WHERE active=1 AND promotion_score IS NOT NULL
        ORDER BY promotion_score DESC
        """
    ).fetchall()

    for r in rows:
        ticker = r["ticker"]
        score  = r["promotion_score"]
        src    = r["promotion_source"] or ""
        nid    = f"co_{ticker}"

        if verbose and score > 5.0:
            print(f"  [C:belief] {nid}  signal_score={score:.3f}")

        if not dry_run:
            # Supersede prior signal_score belief
            prior = store._c.execute(
                """SELECT belief_id FROM soma_intel_belief
                   WHERE subject_node_id=? AND predicate='signal_score'
                     AND superseded_by IS NULL""",
                (nid,),
            ).fetchone()
            prior_id = prior["belief_id"] if prior else None

            cur = store._c.execute(
                """
                INSERT INTO soma_intel_belief
                  (subject_node_id, predicate, value, confidence, ts,
                   source_id, superseded_by)
                VALUES (?, 'signal_score', ?, ?, ?, 'universe_manager', ?)
                """,
                (nid, f"{score:.3f}", min(0.95, score / 30.0), NOW, prior_id),
            )
            if prior_id:
                store._c.execute(
                    "UPDATE soma_intel_belief SET superseded_by=? WHERE belief_id=?",
                    (cur.lastrowid, prior_id),
                )
        stats["beliefs_refreshed"] += 1

    if not dry_run:
        store._c.commit()

    return stats


# ════════════════════════════════════════════════════════════════════════════
# Main
# ════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="SOMA-INTEL convergence engine: convergence_of + has_thesis + beliefs"
    )
    parser.add_argument("--apply",   action="store_true",
                        help="Write to DB (default: dry run)")
    parser.add_argument("--pass",    dest="only_pass",
                        choices=["A", "B", "C", "all"], default="all",
                        help="Run only one pass (default: all)")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    dry_run  = not args.apply
    run_all  = args.only_pass == "all"
    if dry_run:
        print("DRY RUN — pass --apply to write to DB")

    all_stats: dict[str, dict] = {}

    with IntelStore(db_path=DB_PATH) as store:

        if run_all or args.only_pass == "A":
            print("\n[Pass A] Platform convergence detection...")
            a = run_pass_a(store, dry_run=dry_run, verbose=args.verbose)
            all_stats["A"] = a
            print(f"  Companies:   {a['companies_processed']}")
            print(f"  Conv nodes:  {a['convergence_nodes_created']}")
            print(f"  Conv edges:  {a['convergence_edges_written']}")
            print(f"  Signals:     {a['signals_written']}")
            print(f"  Beliefs:     {a['beliefs_written']}")

        if run_all or args.only_pass == "B":
            print("\n[Pass B] has_thesis edge population...")
            b = run_pass_b(store, dry_run=dry_run, verbose=args.verbose)
            all_stats["B"] = b
            print(f"  has_thesis written:    {b['has_thesis_written']}")
            print(f"  skipped (structural):  {b['skipped_structural']}")
            print(f"  skipped (existing):    {b['skipped_existing']}")

        if run_all or args.only_pass == "C":
            print("\n[Pass C] Belief refresh (signal_score)...")
            c = run_pass_c(store, dry_run=dry_run, verbose=args.verbose)
            all_stats["C"] = c
            print(f"  Beliefs refreshed: {c['beliefs_refreshed']}")

        # Final DB snapshot
        print("\nDB snapshot:")
        for table in ("soma_intel_edge", "soma_intel_node",
                      "soma_intel_signal", "soma_intel_belief"):
            cnt = store._c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"  {table:<30} {cnt}")

        # Edge type breakdown
        etype = store._c.execute(
            "SELECT edge_type, COUNT(*) c FROM soma_intel_edge GROUP BY edge_type ORDER BY c DESC"
        ).fetchall()
        print("\n  Edge types:")
        for r in etype:
            print(f"    {r[0]:<28} {r[1]}")

    if dry_run:
        print("\nDRY RUN complete — pass --apply to write.")
    else:
        print("\nconvergence_engine: OK")


if __name__ == "__main__":
    main()
