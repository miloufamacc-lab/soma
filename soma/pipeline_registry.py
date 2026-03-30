"""
DABEIBA Pipeline Registry — Single source of truth for all pipeline codenames.

This file is the machine-readable reference for the DABEIBA naming convention.
Any Claude session, script, or module can import this to understand the platform structure.

Architecture V2.0 (March 29, 2026):
  - 4 modules (ORACLE, SOMA, MANTIS, CIPHER) — permanent, function-based
  - 12 named pipelines — military/nuclear/intelligence codenames, expandable
  - Scaling rule: new data source → ORACLE pipeline, new processing → SOMA pipeline,
    new decision logic → MANTIS pipeline, new comms → CIPHER pipeline. Never a 5th module.

Full documentation: ~/Desktop/DABEIBA/DABEIBA_ARCHITECTURE_V2.md
"""

# ─── Module Definitions ──────────────────────────────────────────────────────

MODULES = {
    "ORACLE": {
        "full_name": "Outlook, Research & Analytics for Cross-asset Liquidity Evaluation",
        "stage": "COLLECT",
        "function": "Signal extraction from ALL data sources",
        "folder": "oracle/",
    },
    "SOMA": {
        "full_name": "Shared Ontology for Market Analysis",
        "stage": "PROCESS",
        "function": "Intelligence processing, storage, thesis testing, ingestion",
        "folder": "shared/soma/",
    },
    "MANTIS": {
        "full_name": "Mechanical Algorithmic Navigator for Tactical Investment Signals",
        "stage": "DECIDE",
        "function": "Portfolio decisions + trade execution",
        "folder": "mantis/",
    },
    "CIPHER": {
        "full_name": "Client Intelligence Platform for Holistic Equity Research",
        "stage": "COMMUNICATE",
        "function": "Client communication + relationship management",
        "folder": "cipher/",
    },
}

# ─── Pipeline Definitions ────────────────────────────────────────────────────
#
# Each pipeline has:
#   - codename: military/nuclear/intelligence themed
#   - acronym: what the codename stands for
#   - module: which of the 4 modules it belongs to
#   - function: what it does (one line)
#   - status: BUILT, PARTIAL, or PLANNED
#   - key_files: primary files that implement this pipeline
#   - soma_tables: SOMA tables this pipeline reads from or writes to

PIPELINES = {

    # ── ORACLE Pipelines (Signal Extraction) ─────────────────────────────────

    "TITAN": {
        "acronym": "Tactical Intelligence for Ticker Analysis & Navigation",
        "module": "ORACLE",
        "function": "Equity + macro data ingestion, GLI regime detection, 76-ticker valuations",
        "status": "BUILT",
        "key_files": [
            "oracle/main.py",
            "oracle/oracle/gli/gli_engine.py",
            "oracle/valuation_engine.py",
            "oracle/oracle/shared/data_bridge.py",
        ],
        "soma_tables": ["regime_history", "valuations"],
    },

    "COBALT": {
        "acronym": "Chain Observation & Blockchain Analytics for Tactical Leverage",
        "module": "ORACLE",
        "function": "BTC/SOL on-chain metrics: MVRV Z-Score, NUPL, SOPR, exchange flows",
        "status": "PLANNED",
        "key_files": [],
        "soma_tables": ["onchain_metrics", "onchain_signals"],
        "data_sources": ["CoinGecko", "Mempool.space", "DeFiLlama", "Blockchain.com", "Dune"],
        "notes": "Free tier only. 80% alpha coverage per Grok. Circuit breaker pattern.",
    },

    "SPECTRE": {
        "acronym": "Strategic Political Event Classification & Threat Response Engine",
        "module": "ORACLE",
        "function": "Geopolitical risk scoring via RSS feeds, keyword triage, phi4-mini NLP",
        "status": "PLANNED",
        "key_files": [],
        "soma_tables": ["geo_events", "geo_vectors", "geo_baselines"],
        "notes": "4-stage NLP funnel: ingest → regex triage → phi4-mini → delta check. "
                 "Feeds ORACLE regime model ONLY, not MANTIS directly.",
    },

    # ── SOMA Pipelines (Intelligence Processing) ─────────────────────────────

    "DELTA": {
        "acronym": "Differential Engine for Longitudinal Trend Analysis",
        "module": "SOMA",
        "function": "What Changed engine — 7 materiality thresholds across all data sources",
        "status": "BUILT",
        "key_files": [
            "shared/soma/what_changed.py",
        ],
        "soma_tables": ["regime_history", "valuations", "outlook_snapshots"],
        "thresholds": {
            "regime_transition": "binary flag",
            "gli_delta": "> 3.5% (or 1.5x 30-day std)",
            "diffusion_cross": "45/55 band",
            "momentum_flip": "sign change",
            "valuation_shift": "> 8% weighted",
            "max_dd_projection": "> 5%",
            "outlook_jaccard": "< 0.75",
        },
    },

    "DOCTRINE": {
        "acronym": "Directional Oversight of Conviction, Thesis & Risk-Informed Navigation Engine",
        "module": "SOMA",
        "function": "Investment philosophy — beliefs, evidence, conviction tracking, conflict detection",
        "status": "PLANNED",
        "key_files": [],
        "soma_tables": [
            "philosophy_beliefs", "philosophy_evidence",
            "philosophy_history", "philosophy_alerts",
        ],
        "notes": "Living thesis builder + decision framework. Conviction 1-10 (0-1 normalized for MANTIS). "
                 "Auto-update: regime mismatch deducts conviction, evidence correlation boosts. "
                 "Stress-test via 2008/2020/2022 scenario backtests.",
    },

    "SENTINEL": {
        "acronym": "Systematic Enforcement of Norms, Thresholds, Investments & Logic",
        "module": "SOMA",
        "function": "KB validation + narrative alignment + rule enforcement",
        "status": "BUILT",
        "key_files": [
            "shared/soma/kb_validator.py",
            "shared/soma/narrative_alignment.py",
        ],
        "soma_tables": ["kb_violations", "kb_rules", "kb_audit_log"],
    },

    "PRISM": {
        "acronym": "Pipeline for Raw Intelligence Sorting & Materiality",
        "module": "SOMA",
        "function": "Universal ingestion funnel — scraper inbox, classification, routing to SOMA",
        "status": "PLANNED",
        "key_files": [
            "shared/youtube_extractor.py",
        ],
        "soma_tables": ["raw_intelligence"],
        "notes": "Gemini GEM scrapes X/YouTube → dumps to shared/scrapers/inbox/ → "
                 "Claude processes interactively (no API costs) → writes to SOMA.",
    },

    # ── MANTIS Pipelines (Decision & Execution) ──────────────────────────────

    "FORGE": {
        "acronym": "Financial Optimization & Regime-Guided Execution",
        "module": "MANTIS",
        "function": "Portfolio construction — V2 engine, inverse-vol weighting, drawdown tiers",
        "status": "BUILT",
        "key_files": [
            "mantis/convergence-backtester/src/v2_engine.py",
        ],
        "soma_tables": ["portfolio_state", "trade_log"],
        "performance": {
            "return": "205.1%",
            "max_drawdown": "47.3%",
            "sharpe": 0.74,
            "calmar": 0.60,
        },
    },

    "VECTOR": {
        "acronym": "Validated Execution & Chain Transaction Orchestration Runtime",
        "module": "MANTIS",
        "function": "Trade execution — Solana RPC, Jupiter API, transaction construction",
        "status": "BUILT",
        "key_files": [
            "mantis/convergence-backtester/src/execution.py",
            "mantis/convergence-backtester/src/solana_rpc.py",
        ],
        "soma_tables": ["trade_log"],
        "blockers": ["xStocks legal opinion (Quebec securities lawyer, $500-1,500)"],
    },

    # ── CIPHER Pipelines (Communication) ─────────────────────────────────────

    "BEACON": {
        "acronym": "Briefing Engine for Advisory Communications & Outlook Narratives",
        "module": "CIPHER",
        "function": "Market outlook reports, narrative composition, 3-tier export (email/DOCX/PDF)",
        "status": "BUILT",
        "key_files": [
            "cipher/cipher/pipeline/compose.py",
        ],
        "soma_tables": ["outlook_snapshots"],
    },

    "DOSSIER": {
        "acronym": "Detailed Observation & Strategic Summary of Individual Equity Relations",
        "module": "CIPHER",
        "function": "UHNW client profiling, IPS alignment, interaction history, money scripts",
        "status": "PARTIAL",
        "key_files": [],
        "soma_tables": ["client_profiles", "client_interactions"],
    },

    "INTEL": {
        "acronym": "Intelligence Extraction & Notation Toolkit for Enriched Learning",
        "module": "CIPHER",
        "function": "Research sidebar — note ingestion, tagging, AI-powered analysis",
        "status": "BUILT",
        "key_files": [
            "cipher/cipher/pipeline/intake.py",
        ],
        "soma_tables": [],
    },
}

# ─── Convenience Functions ───────────────────────────────────────────────────

def get_pipeline(codename: str) -> dict:
    """Look up a pipeline by codename. Returns None if not found."""
    return PIPELINES.get(codename.upper())


def get_module_pipelines(module: str) -> dict:
    """Get all pipelines belonging to a module."""
    module = module.upper()
    return {k: v for k, v in PIPELINES.items() if v["module"] == module}


def get_built_pipelines() -> dict:
    """Get all pipelines with status BUILT."""
    return {k: v for k, v in PIPELINES.items() if v["status"] == "BUILT"}


def get_planned_pipelines() -> dict:
    """Get all pipelines with status PLANNED."""
    return {k: v for k, v in PIPELINES.items() if v["status"] == "PLANNED"}


def pipeline_summary() -> str:
    """Print a one-line summary of all pipelines, grouped by module."""
    lines = []
    for mod in ["ORACLE", "SOMA", "MANTIS", "CIPHER"]:
        pipes = get_module_pipelines(mod)
        entries = [f"{name} [{v['status']}]" for name, v in pipes.items()]
        lines.append(f"  {mod}: {', '.join(entries)}")
    return "DABEIBA Pipeline Registry\n" + "\n".join(lines)


# ─── Build Order (for new pipelines) ────────────────────────────────────────

BUILD_ORDER = [
    {"phase": "A", "pipeline": "DOCTRINE", "module": "SOMA",   "effort": "1-2 sessions", "model": "Sonnet",        "confidence": 0.85},
    {"phase": "B", "pipeline": "PRISM",    "module": "SOMA",   "effort": "1 session",    "model": "Sonnet",        "confidence": 0.85},
    {"phase": "C", "pipeline": "COBALT",   "module": "ORACLE", "effort": "2-3 sessions", "model": "Sonnet",        "confidence": 0.75},
    {"phase": "D", "pipeline": "SPECTRE",  "module": "ORACLE", "effort": "3-4 sessions", "model": "Opus + Sonnet", "confidence": 0.70},
    {"phase": "E", "pipeline": "run_day V2", "module": "SOMA", "effort": "1 session",    "model": "Sonnet",        "confidence": 0.85},
    {"phase": "F", "pipeline": "soma_vacuum", "module": "SOMA","effort": "1 session",    "model": "Haiku",         "confidence": 0.90},
]

# ─── Scaling Rule ────────────────────────────────────────────────────────────
SCALING_RULE = """
New data source?         → New ORACLE pipeline
New processing function? → New SOMA pipeline
New decision logic?      → New MANTIS pipeline (rare)
New communication channel? → New CIPHER pipeline
Never a 5th module.
"""


if __name__ == "__main__":
    print(pipeline_summary())
    print()
    print("Planned pipelines:")
    for name, p in get_planned_pipelines().items():
        print(f"  {name}: {p['acronym']}")
        print(f"    → {p['function']}")
