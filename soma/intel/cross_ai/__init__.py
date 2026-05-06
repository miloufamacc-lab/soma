"""
SOMA-INTEL Phase 7.I1.4 — Cross-AI Corroboration Adapters

Exposes three ingest functions, one per registered AI source.
Each adapter reads AI output from a documented filesystem path,
normalizes it into flag records, and writes via IntelStore.insert_cross_ai_flag().

All adapters are:
- Idempotent: duplicate flags (same ai_source + ticker + signal_type + ts) are skipped.
- Dry-run capable: pass dry_run=True to log without writing.
- Gated: callers must check is_capability_enabled('cross_ai_corroboration') first.

Usage (from run_day.py or any orchestrator):
    from soma.intel.cross_ai import ingest_grok, ingest_gemini, ingest_phi4

    with IntelStore() as store:
        if store.is_capability_enabled('cross_ai_corroboration'):
            ingest_grok(store)
            ingest_gemini(store)
            ingest_phi4(store)
"""

from __future__ import annotations

from soma.intel.cross_ai.grok_adapter   import ingest_grok
from soma.intel.cross_ai.gemini_adapter import ingest_gemini
from soma.intel.cross_ai.phi4_adapter   import ingest_phi4

__all__ = ["ingest_grok", "ingest_gemini", "ingest_phi4"]
