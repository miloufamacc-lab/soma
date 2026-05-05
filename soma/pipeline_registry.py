"""
DABEIBA Pipeline Registry — Single source of truth for all pipeline codenames.

This file is the machine-readable reference for the DABEIBA naming convention.
Any Claude session, script, or module can import this to understand the platform structure.

Architecture V2.1 (April 15, 2026):
  - 5 modules (ORACLE, SOMA, MANTIS, CIPHER, RAPTOR) — permanent, function-based
  - 14 named pipelines — military/nuclear/intelligence codenames, expandable
  - Scaling rule: new data source → ORACLE pipeline, new processing → SOMA pipeline,
    new decision logic → MANTIS pipeline, new comms → CIPHER pipeline, new clients → RAPTOR.
  - Display names updated to generic, function-first labels (no module prefixes).

ALIAS LAYER (Phase 1 — April 5, 2026):
  Each pipeline now carries:
    - display_name:  human-readable label (change freely without touching any other file)
    - aliases:       list of alternative names that resolve to this pipeline's internal_id
    - categories:    routing categories (used by PRISM instead of hardcoded dicts)
  Use resolve() to look up a pipeline by ANY name (codename, display_name, or alias).
  Use get_category_routing() to generate category→pipeline mappings dynamically.

Full documentation: ~/Desktop/DABEIBA/DABEIBA_ARCHITECTURE_V2.md
"""

# ─── Module Definitions ──────────────────────────────────────────────────────

MODULES = {
    "ORACLE": {
        "full_name": "Outlook, Research & Analytics for Cross-asset Liquidity Evaluation",
        "display_name": "Market Intelligence",
        "aliases": ["oracle", "research", "market-intelligence", "equity-ranking", "Research"],
        "stage": "COLLECT & ANALYZE",
        "function": "Single-source intelligence: collect raw data, analyze within domain, render internal views",
        "boundary": "Owns everything about ONE data vertical end-to-end. Does NOT cross domains.",
        "folder": "oracle/",
    },
    "SOMA": {
        "full_name": "Shared Ontology for Market Analysis",
        "display_name": "SOMA",
        "aliases": ["soma", "synthesis", "cross-domain", "Synthesis"],
        "stage": "SYNTHESIZE",
        "function": "Cross-domain synthesis: combine ORACLE outputs, test theses, detect changes, orchestrate",
        "boundary": "Activates when 2+ ORACLE domains need to be combined. Single-source analysis stays in ORACLE.",
        "folder": "shared/soma/",
    },
    "MANTIS": {
        "full_name": "Mechanical Algorithmic Navigator for Tactical Investment Signals",
        "display_name": "Execution & Risk",
        "aliases": ["mantis", "decisions", "execution", "execution-and-risk", "Decisions"],
        "stage": "DECIDE & EXECUTE",
        "function": "Portfolio construction, position sizing, trade execution, risk management",
        "boundary": "Takes SOMA synthesis, outputs portfolio actions. No analysis, no communication.",
        "folder": "mantis/",
    },
    "CIPHER": {
        "full_name": "Client Intelligence Platform for Holistic Equity Research",
        "display_name": "Wealth Experience",
        "aliases": ["cipher", "advisory", "wealth-experience", "client-advisory", "Advisory"],
        "stage": "COMMUNICATE",
        "function": "Client-facing output: reports, emails, profiles, compliance",
        "boundary": "Anything that leaves the system and reaches a client. Internal views stay in ORACLE/SOMA.",
        "folder": "cipher/",
    },
    "RAPTOR": {
        "full_name": "Revenue & Asset Prospecting Through Outreach & Relationship-building",
        "display_name": "Asset Conquest",
        "aliases": ["raptor", "acquisition", "asset-conquest", "net-new-assets", "Acquisition"],
        "stage": "ACQUIRE",
        "function": "Net new client acquisition, prospect intelligence, referral network",
        "boundary": "New relationships only. Existing client management stays in CIPHER.",
        "folder": "raptor/",
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
        "display_name": "Equity & Macro Research",
        "aliases": ["titan", "equities", "equity-collector", "macro-collector", "equity-ranking", "equities-and-macro", "Equities & Macro", "ORACLE: Equities & Macro"],
        "categories": ["macro", "equities"],
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
        "function": "BTC/SOL on-chain metrics: MVRV proxy, NUPL proxy, network health, DeFi TVL, composite signals",
        "status": "BUILT",
        "display_name": "Digital Assets",
        "aliases": ["cobalt", "onchain", "crypto-collector", "chain-analytics", "ORACLE: On-Chain & Crypto"],
        "categories": ["crypto"],
        "key_files": [
            "oracle/cobalt_engine.py",
        ],
        "soma_tables": ["onchain_metrics", "onchain_signals"],
        "data_sources": ["CoinGecko", "Mempool.space", "DeFiLlama", "Blockchain.com"],
        "notes": "Free tier only. Proxy MVRV/NUPL via 200d MA + 365d avg mcap. Circuit breaker pattern. 24h cache TTL.",
    },

    "SPECTRE": {
        "acronym": "Strategic Political Event Classification & Threat Response Engine",
        "module": "ORACLE",
        "function": "Geopolitical risk scoring via RSS feeds, keyword triage, optional phi4-mini NLP, delta check",
        "status": "BUILT",
        "display_name": "Geopolitical & Event Risk",
        "aliases": ["spectre", "geopolitical", "geo-collector", "geopolitics", "ORACLE: Geopolitical"],
        "categories": ["geopolitical"],
        "key_files": [
            "oracle/spectre_engine.py",
        ],
        "soma_tables": ["geo_events", "geo_vectors", "geo_baselines"],
        "data_sources": ["Reuters RSS", "BBC World RSS", "Al Jazeera RSS"],
        "notes": "4-stage funnel: ingest → regex triage → phi4-mini (optional) → delta check. "
                 "6h cache TTL. Circuit breaker. Sigma-based material shift detection. "
                 "Feeds ORACLE regime model ONLY, not MANTIS directly.",
    },

    "MUSKONOMY": {
        "acronym": "MUSK-focused Observatory for Navigating Optimized Market Yields",
        "module": "ORACLE",
        "function": "Daily TSLA intelligence — 6-segment SITREP, S-curve tracking, Grok DeepSearch",
        "status": "BUILT",
        "display_name": "X Corp Intelligence",
        "aliases": ["muskonomy", "tsla-intel", "tesla-daily", "tsla-sitrep", "x-corp", "x-corporation", "everything-corp", "Musk Ecosystem", "ORACLE: TSLA Intelligence"],
        "categories": [],
        "key_files": [
            "MUSKONOMY_ARCHITECTURE.md",
        ],
        "soma_tables": ["brief_log"],
        "notes": "Scheduled task (7AM ET daily). Sources: robotaxitracker.com, "
                 "Grok DeepSearch, web, ORACLE-TITAN. 6 segments: Auto, Energy, "
                 "Robotaxi, FSD, Optimus, Services. Output: SITREP email.",
    },

    # ── SOMA Pipelines (Intelligence Processing) ─────────────────────────────

    "DELTA": {
        "acronym": "Differential Engine for Longitudinal Trend Analysis",
        "module": "SOMA",
        "function": "What Changed engine — 7 materiality thresholds across all data sources",
        "status": "BUILT",
        "display_name": "Regime & Change Detection",
        "aliases": ["delta", "what-changed", "diff-engine", "change-detection", "regime-change", "Change Detection", "SOMA: Change Detection"],
        "categories": [],
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
        "status": "BUILT",
        "display_name": "Investment Thesis Engine",
        "aliases": ["doctrine", "thesis-engine", "beliefs", "philosophy", "investment-thesis", "Thesis & Convictions", "SOMA: Thesis Engine"],
        "categories": ["philosophy"],
        "key_files": [
            "shared/soma/doctrine_engine.py",
            "shared/soma/migrations/007_doctrine_tables.sql",
        ],
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
        "display_name": "Compliance & Rule Validation",
        "aliases": ["sentinel", "kb-validator", "rule-enforcer", "validation", "compliance", "Compliance & Validation", "SOMA: Validation"],
        "categories": [],
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
        "status": "BUILT",
        "display_name": "Research Intake & Routing",
        "aliases": ["prism", "ingestion", "inbox-processor", "ingest", "research-intake", "Intelligence Intake", "SOMA: Ingestion"],
        "categories": [],
        "key_files": [
            "shared/soma/prism_engine.py",
            "shared/soma/migrations/008_raw_intelligence.sql",
            "shared/youtube_extractor.py",
            "shared/scrapers/inbox/",
        ],
        "soma_tables": ["raw_intelligence"],
        "notes": "Gemini GEM scrapes X/YouTube → dumps to shared/scrapers/inbox/ → "
                 "Claude processes interactively (no API costs) → writes to SOMA.",
    },

    "HORIZON": {
        "acronym": "Holistic Observation & Risk-Informed Zone of Optimal Navigation",
        "module": "SOMA",
        "function": "Tactical timing engine — 7-lens synthesis with Monte Carlo probability distributions",
        "status": "OPERATIONAL",
        "display_name": "Tactical Timing & Signal Synthesis",
        "aliases": ["horizon", "timing-engine", "tactical-timing", "7-lens", "signal-synthesis", "Timing & Signals", "SOMA: Tactical Timing"],
        "categories": [],
        "key_files": [
            "shared/soma/horizon.py",
            "shared/soma/horizon_dataclasses.py",
            "shared/soma/horizon_synthesis.py",
            "shared/soma/horizon_monte_carlo.py",
            "shared/soma/horizon_bias_audit.py",
            "shared/soma/horizon_output.py",
            "shared/soma/horizon_lenses/__init__.py",
            "shared/soma/horizon_lenses/macro_lens.py",
            "shared/soma/horizon_lenses/fundamental_lens.py",
            "shared/soma/horizon_lenses/technical_lens.py",
            "shared/soma/horizon_lenses/btc_onchain_lens.py",
            "shared/soma/horizon_lenses/credit_liquidity_lens.py",
            "shared/soma/horizon_lenses/sentiment_lens.py",
            "shared/soma/horizon_lenses/event_lens.py",
        ],
        "soma_tables": [
            "regime_history", "valuations", "portfolio_state",
            "trade_log", "outlook_snapshots", "raw_intelligence",
            "horizon_analyses",
        ],
        "lenses": {
            "MACRO": {"weight": 0.35, "role": "regime_gate"},
            "BTC_ONCHAIN": {"weight": 0.12, "role": "crypto_specific"},
            "CREDIT_LIQUIDITY": {"weight": 0.10, "role": "macro_leading"},
            "FUNDAMENTAL": {"weight": 0.15, "role": "valuation"},
            "TECHNICAL": {"weight": 0.12, "role": "price_action"},
            "SENTIMENT": {"weight": 0.09, "role": "behavioral"},
            "GEOPOLITICAL": {"weight": 0.07, "role": "calendar_risk"},
        },
        "synthesis": "hierarchical",  # regime_gate → concordance(4/7) → weighted
        "monte_carlo_paths": 10000,
        "notes": "Cross-AI reviewed (Grok Expert + Gemini Thinking + Claude CFA KB). "
                 "Macro-domain total 45% (35% MACRO + 10% Credit). "
                 "Hierarchical synthesis reduces false positives ~35-45% vs flat avg. "
                 "Behavioral bias audit as meta-layer (12 CFA biases). "
                 "Built April 2026.",
    },

    # ── MANTIS Pipelines (Decision & Execution) ──────────────────────────────

    "FORGE": {
        "acronym": "Financial Optimization & Regime-Guided Execution",
        "module": "MANTIS",
        "function": "Portfolio construction — V2 engine, inverse-vol weighting, drawdown tiers",
        "status": "BUILT",
        "display_name": "Portfolio Construction",
        "aliases": ["forge", "portfolio-builder", "portfolio-construction", "position-sizing", "Position Sizing & Risk", "MANTIS: Portfolio Construction"],
        "categories": ["risk"],
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
        "display_name": "Trade Execution",
        "aliases": ["vector", "trade-executor", "execution", "MANTIS: Execution"],
        "categories": [],
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
        "display_name": "Market Outlook",
        "aliases": ["beacon", "report-generator", "outlook-reports", "reports", "CIPHER: Reports"],
        "categories": [],
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
        "display_name": "Client Profiles & IPS",
        "aliases": ["dossier", "client-profiles", "client-intel", "ips", "investment-policy-statement", "Client Intelligence", "CIPHER: Client Profiles"],
        "categories": [],
        "key_files": [],
        "soma_tables": ["client_profiles", "client_interactions"],
    },

    "INTEL": {
        "acronym": "Intelligence Extraction & Notation Toolkit for Enriched Learning",
        "module": "CIPHER",
        "function": "Research sidebar — note ingestion, tagging, AI-powered analysis",
        "status": "BUILT",
        "display_name": "Source Intake & Annotation",
        "aliases": ["intel", "research-sidebar", "note-ingestion", "source-annotation", "Source Processing", "CIPHER: Research Intake"],
        "categories": [],
        "key_files": [
            "cipher/cipher/pipeline/intake.py",
        ],
        "soma_tables": [],
    },

    # ─── RAPTOR Pipelines ─────────────────────────────────────────────────────

    "PREDATOR": {
        "acronym": "Prospect Ranking Engine & Dynamic Asset-Tier Outreach Router",
        "module": "RAPTOR",
        "function": "Lead scoring, pipeline stage management, action queue generation",
        "status": "BUILT",
        "display_name": "Lead Scoring & Pipeline",
        "aliases": ["predator", "lead-scoring", "prospect-scoring", "pipeline-engine",
                    "RAPTOR: Lead Scoring", "raptor-lead"],
        "categories": [],
        "key_files": [
            "shared/soma/raptor_engine.py",
        ],
        "soma_tables": ["raptor_prospects", "raptor_pipeline_log", "raptor_touchpoints"],
    },

    "ALLIANCE": {
        "acronym": "Advisor Link & Liaison Intelligence for Acquisition Network & Client Engagement",
        "module": "RAPTOR",
        "function": "COI network management, referral tracking, reciprocity reporting",
        "status": "BUILT",
        "display_name": "COI Network & Referrals",
        "aliases": ["alliance", "coi-network", "referral-engine", "coi-intelligence",
                    "RAPTOR: COI", "raptor-coi", "referrals"],
        "categories": [],
        "key_files": [
            "shared/soma/raptor_engine.py",
        ],
        "soma_tables": ["raptor_coi_network", "raptor_referrals"],
    },

    "CHARTER": {
        "acronym": "Compliance Handling & Audit-Ready Tracking for Ethical Relationship-building",
        "module": "RAPTOR",
        "function": "AMF/CIRO compliance scanning, Law 25 privacy, CASL consent management",
        "status": "BUILT",
        "display_name": "Compliance & Privacy",
        "aliases": ["charter", "compliance-engine", "raptor-compliance", "privacy-engine",
                    "law25", "casl-compliance", "RAPTOR: Compliance"],
        "categories": [],
        "key_files": [
            "shared/soma/raptor_compliance.py",
            "shared/soma/raptor_privacy.py",
        ],
        "soma_tables": ["raptor_consent_ledger", "raptor_compliance_shadow"],
    },

    "HERALD": {
        "acronym": "High-value Engagement & Revenue Analysis for Lead-driven Decisions",
        "module": "RAPTOR",
        "function": "CRM3 fee drag analysis, value proposition engine, prospect-facing reports",
        "status": "BUILT",
        "display_name": "CRM3 Value Proposition",
        "aliases": ["herald", "crm3", "fee-analysis", "value-proposition", "fee-drag",
                    "RAPTOR: CRM3", "raptor-crm3"],
        "categories": [],
        "key_files": [
            "shared/soma/raptor_crm3_analyzer.py",
        ],
        "soma_tables": ["raptor_fund_mers"],
    },
}

# ─── Alias Index (built at import time) ──────────────────────────────────────
# Maps every known name (codename, display_name, alias, lowercase variants) → internal_id
# This is rebuilt automatically whenever this module is imported.

def _build_alias_index():
    """Build a flat lookup: any name → internal ID.
    Includes BOTH modules and pipelines (V4, April 16 2026).
    """
    index = {}
    # Modules first (so pipeline codenames win if there is any collision)
    for internal_id, meta in MODULES.items():
        index[internal_id] = internal_id
        index[internal_id.lower()] = internal_id
        dn = meta.get("display_name", internal_id)
        index[dn] = internal_id
        index[dn.lower()] = internal_id
        for alias in meta.get("aliases", []):
            index[alias] = internal_id
            index[alias.lower()] = internal_id
    # Pipelines
    for internal_id, meta in PIPELINES.items():
        # The codename itself (always uppercase in PIPELINES keys)
        index[internal_id] = internal_id
        index[internal_id.lower()] = internal_id
        # The display_name (may differ from codename after Phase 4 rename)
        dn = meta.get("display_name", internal_id)
        index[dn] = internal_id
        index[dn.lower()] = internal_id
        # All aliases
        for alias in meta.get("aliases", []):
            index[alias] = internal_id
            index[alias.lower()] = internal_id
    return index

_ALIAS_INDEX = _build_alias_index()


def _build_category_routing():
    """Build category → internal_id mapping from pipeline metadata.
    This replaces the hardcoded CATEGORY_TO_PIPELINE dict in prism_engine.py.
    If multiple pipelines claim the same category, the first one wins."""
    routing = {}
    for internal_id, meta in PIPELINES.items():
        for cat in meta.get("categories", []):
            if cat not in routing:
                routing[cat] = internal_id
    return routing

_CATEGORY_ROUTING = _build_category_routing()


# ─── Convenience Functions ───────────────────────────────────────────────────

def resolve(name: str) -> str:
    """Resolve ANY name (codename, display_name, alias) → internal ID (module or pipeline).
    Returns None if no match. Case-insensitive and space/hyphen-tolerant.

    Examples:
        resolve("TITAN")            → "TITAN"
        resolve("equities")         → "TITAN"
        resolve("equity ranking")   → "TITAN"    (space → hyphen normalization)
        resolve("Market Intelligence") → "ORACLE"
        resolve("Wealth Experience") → "CIPHER"
    """
    if not name:
        return None
    # Try literal, lowercase, space→hyphen, and lowercase space→hyphen
    normalized = name.strip().replace(" ", "-")
    return (
        _ALIAS_INDEX.get(name)
        or _ALIAS_INDEX.get(name.lower())
        or _ALIAS_INDEX.get(normalized)
        or _ALIAS_INDEX.get(normalized.lower())
    )


def get_display_name(codename: str) -> str:
    """Get the human-readable display name for a module OR pipeline.
    Checks MODULES first, then PIPELINES. Falls back to the codename if neither matches."""
    if not codename:
        return codename
    key = codename.upper()
    mod = MODULES.get(key)
    if mod:
        return mod.get("display_name", codename)
    pipe = PIPELINES.get(key)
    if pipe:
        return pipe.get("display_name", codename)
    return codename


def get_category_routing() -> dict:
    """Get the category → pipeline mapping for PRISM routing.
    Returns dict like {"crypto": "COBALT", "macro": "TITAN", ...}
    This is the SINGLE SOURCE OF TRUTH for ingestion routing."""
    return dict(_CATEGORY_ROUTING)


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
    for mod in ["ORACLE", "SOMA", "MANTIS", "CIPHER", "RAPTOR"]:
        pipes = get_module_pipelines(mod)
        entries = [f"{get_display_name(name)} [{v['status']}]" for name, v in pipes.items()]
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
BOUNDARY TEST — Where does a new capability belong?

1. Does it need data from only ONE source?     → ORACLE (collect + analyze within that domain)
2. Does it combine 2+ ORACLE domains?          → SOMA (cross-domain synthesis)
3. Does it produce portfolio actions?           → MANTIS (decide + execute)
4. Does it go to an EXISTING client?            → CIPHER (communicate)
5. Does it go to a PROSPECTIVE client?          → RAPTOR (acquire)

Never a 6th module. New data verticals = new ORACLE pipeline. New synthesis = new SOMA step.
"""


if __name__ == "__main__":
    print(pipeline_summary())
    print()

    # ── Alias Layer Demo ──
    print("=" * 60)
    print("ALIAS LAYER — Resolve any name to internal pipeline ID:")
    print("=" * 60)
    test_names = [
        "TITAN", "equities", "crypto-collector", "thesis-engine",
        "geopolitics", "portfolio-builder", "report-generator",
        "COBALT", "onchain", "SPECTRE", "geo-collector",
    ]
    for name in test_names:
        resolved = resolve(name)
        display = get_display_name(resolved) if resolved else "NOT FOUND"
        print(f"  resolve('{name}') → {resolved} (display: {display})")

    print()
    print("CATEGORY ROUTING (for PRISM):")
    for cat, pipe in get_category_routing().items():
        print(f"  {cat} → {pipe}")

    print()
    print("Planned pipelines:")
    for name, p in get_planned_pipelines().items():
        print(f"  {name}: {p['acronym']}")
        print(f"    → {p['function']}")
