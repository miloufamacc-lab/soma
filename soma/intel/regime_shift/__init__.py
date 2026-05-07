"""
SOMA-INTEL Phase 7 §D.3 — Regime-Shift Bayesian Detector

Package structure:
  ingestors.py   — 4 ingest_<input>_z(date, store) -> Optional[float]
  bayesian.py    — pure Bayesian update math (no I/O)
  orchestrator.py — run_daily(date, store) — orchestrates ingest + update + persist

Capability: regime_shift_bayesian (default: disabled)
Live triggers: D.3.C (not this session).
"""

__all__ = ["ingestors", "bayesian", "orchestrator"]
