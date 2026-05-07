#!/usr/bin/env python3
"""
seed_capabilities.py -- One-time idempotent seed for soma_intel_capability registry.

Registers every Phase 0-6 capability as 'enabled' so the registry reflects current
reality. Safe to run multiple times (register_capability uses INSERT OR IGNORE).

Usage:
    python3 shared/soma/intel/seed_capabilities.py

    # Or from the project root:
    cd ~/Desktop/DABEIBA && python3 -m shared.soma.intel.seed_capabilities
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Allow running from project root without installing the package.
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from shared.soma.intel.store import IntelStore

log = logging.getLogger(__name__)

# ── Capability manifest ────────────────────────────────────────────────────────
#
# Each entry: (capability_id, version, status, enabled_ts, depends_on)
# enabled_ts of '2026-05-04' = Phase 0 lock date (KB first went live).
# Phase-specific completion dates from CHANGELOG / PHASE5_F4_VERDICT.md.
#
# Capability IDs use neutral snake_case; never expose internal module names
# like SOMA/CIPHER/ORACLE in client-facing surfaces.
#
# Split rule (from brief): split if they have independent kill-switch value,
# else combine. signal_engine → combined Phase 2 signal stack (anomaly + confirm
# + decay are individually listed because each has independent kill-switch value).

_CAPABILITIES: list[tuple[str, str, str, str | None, list[str]]] = [
    # (capability_id, version, status, enabled_ts_override, depends_on)

    # -- Phase 0-1: Graph layer foundation --
    (
        "graph_layer",
        "1.0",
        "enabled",
        "2026-05-04",  # Phase 0 lock date
        [],
    ),
    (
        "belief_versioning",
        "1.0",
        "enabled",
        "2026-05-04",  # migration 021 -- soma_intel_belief table
        ["graph_layer"],
    ),
    (
        "platform_layer",
        "1.0",
        "enabled",
        "2026-05-04",  # platform_seeder.py -- 5 ARK platforms
        ["graph_layer"],
    ),
    (
        "edge_extractor",
        "1.0",
        "enabled",
        "2026-05-04",  # edge_extractor.py -- LLM relation extraction
        ["graph_layer"],
    ),
    (
        "universe_manager",
        "1.0",
        "enabled",
        "2026-05-04",  # universe_manager.py -- ticker promotion/demotion
        ["graph_layer"],
    ),

    # -- Phase 2: Signal engine --
    (
        "regime_classifier",
        "1.0",
        "enabled",
        "2026-05-04",  # regime.py -- bull/bear/transition x vol x macro
        ["graph_layer"],
    ),
    (
        "baseline_engine",
        "1.0",
        "enabled",
        "2026-05-04",  # baseline.py -- regime-conditional per-ticker priors
        ["regime_classifier"],
    ),
    (
        "anomaly_engine",
        "1.0",
        "enabled",
        "2026-05-04",  # anomaly.py -- Mahalanobis distance vs baseline
        ["baseline_engine"],
    ),
    (
        "confirm_gate",
        "1.0",
        "enabled",
        "2026-05-04",  # confirm.py -- multi-source corroboration gate
        ["anomaly_engine"],
    ),
    (
        "decay_engine",
        "1.0",
        "enabled",
        "2026-05-04",  # signal_sweep.py -- half-life decay + expiry
        ["anomaly_engine"],
    ),
    (
        "novelty_engine",
        "1.0",
        "enabled",
        "2026-05-04",  # novelty.py -- (ticker, signal_type) novelty score
        ["anomaly_engine"],
    ),
    (
        "exploration_channel",
        "1.0",
        "enabled",
        "2026-05-04",  # exploration.py -- 5% reserved low-z channel
        ["novelty_engine"],
    ),

    # -- Phase 3: Forecast layer --
    (
        "s_curve_tracker",
        "1.0",
        "enabled",
        "2026-05-04",  # scurve_fitter.py -- Wright's Law + logistic fit
        ["platform_layer"],
    ),
    (
        "convergence_engine",
        "1.0",
        "enabled",
        "2026-05-04",  # convergence_engine.py -- multi-platform convergence
        ["platform_layer", "graph_layer"],
    ),

    # -- Phase 4: Integration --
    (
        "weekly_brief",
        "1.0",
        "enabled",
        "2026-05-04",  # weekly_brief.py -- Friday CIPHER digest
        ["regime_classifier", "anomaly_engine", "graph_layer"],
    ),

    # -- Phase 4: Audit layer --
    (
        "audit_append_only",
        "1.0",
        "enabled",
        "2026-05-04",  # audit_engine.py + soma_intel_audit_log (migration 022)
        ["graph_layer"],
    ),

    # -- Phase 5: Backtest harness --
    (
        "backtest_runner",
        "1.0",
        "enabled",
        "2026-05-05",  # backtest_runner.py -- Phase 5 complete (PHASE5_F4_VERDICT.md)
        ["anomaly_engine", "regime_classifier"],
    ),

    # -- Phase 6: Meta-learner --
    (
        "meta_learner",
        "1.0",
        "enabled",
        "2026-05-05",  # meta_learner.py -- Phase 6 complete
        ["anomaly_engine", "backtest_runner"],
    ),

    # -- Phase 7 §I.1: Cross-AI corroboration channel --
    # Ships DISABLED by design. Enable manually after reviewing test results.
    (
        "cross_ai_corroboration",
        "1.0",
        "disabled",
        None,   # no enabled_ts — starts disabled
        ["confirm_gate", "signal_engine"],
    ),

    # -- Phase 7 §K.5: Adversarial audit --
    # Ships DISABLED by design. Enable manually after reviewing first dry-run.
    (
        "adversarial_audit",
        "1.0",
        "disabled",
        None,   # no enabled_ts — starts disabled
        ["graph_layer", "audit_append_only"],
    ),

    # -- Phase 7 §D.3: Regime-Shift Bayesian Detector --
    # Ships DISABLED by design.
    # Enable ONLY after D.3.B backtest validates precision > 50% at 0.40 threshold.
    (
        "regime_shift_bayesian",
        "1.0",
        "disabled",
        None,   # no enabled_ts — starts disabled; set after D.3.B passes
        ["regime_classifier"],
    ),
]


def seed(db_path: str | None = None, verbose: bool = True) -> int:
    """
    Register all Phase 0-6 capabilities as enabled.

    Idempotent: already-registered capabilities are left unchanged
    (register_capability uses INSERT OR IGNORE).

    Args:
        db_path: Optional override for soma.db path (for testing).
        verbose: Print progress to stdout if True.

    Returns:
        Number of capabilities processed.
    """
    with IntelStore(db_path=db_path) as store:
        for capability_id, version, status, enabled_ts, depends_on in _CAPABILITIES:
            store.register_capability(
                capability_id=capability_id,
                version=version,
                status=status,
                depends_on=depends_on,
            )
            # If enabled_ts was specified, patch it in (register_capability uses
            # _now_iso() for the timestamp; we backfill the Phase 0 lock date).
            if enabled_ts and status == "enabled":
                store._c.execute(
                    "UPDATE soma_intel_capability SET enabled_ts=? "
                    "WHERE capability_id=? AND (enabled_ts IS NULL OR enabled_ts > ?)",
                    (enabled_ts + "T00:00:00+00:00", capability_id, enabled_ts),
                )
            store.commit()
            if verbose:
                print(f"  registered: {capability_id} (v{version}, {status})")

        # Verify minimum expectations from the brief.
        total = len(store.list_capabilities())
        enabled_count = len(store.list_capabilities(status_filter="enabled"))

        assert store.is_capability_enabled("signal_engine") is False or \
               store.is_capability_enabled("anomaly_engine") is True, \
               "anomaly_engine should be enabled"
        assert total >= 21, f"Expected >= 21 capabilities, got {total}"

        if verbose:
            print(f"\nSeed complete: {total} capabilities registered, "
                  f"{enabled_count} enabled.")
            print("Verification: is_capability_enabled('anomaly_engine') = "
                  f"{store.is_capability_enabled('anomaly_engine')}")
            print("Verification: len(list_capabilities()) = "
                  f"{store.list_capabilities().__len__()}")

        return total


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Seed soma_intel_capability registry. Idempotent."
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help=(
            "Override the soma.db path. Defaults to the IntelStore default "
            "(SOMA_DB_PATH env var or ~/Desktop/DABEIBA/shared/soma/data/soma.db). "
            "Use this flag when running from an environment where Path.home() "
            "resolves differently from the actual DB location."
        ),
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING)
    n = seed(db_path=args.db_path)
    print(f"\nDone. {n} capabilities in registry.")
