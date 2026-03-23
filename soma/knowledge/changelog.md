# SOMA — Changelog

## Schema v4 — 2026-03-22
- **Active Intelligence Layer (Phase 2.4):** `kb_violations` table + KBValidator engine
- KBValidator: validates every SOMA write against KB rules (fire-and-forget, never blocks)
  - `validate_regime_write()` — GLI vs regime consistency
  - `validate_valuation_write()` — extreme upside, negative fair value, no-new-positions
  - `validate_portfolio_write()` — cash floor, exposure vs target, drawdown tiers, concentration
  - `validate_trade_write()` — weight vs hard cap, buying in CONTRACTION
- KB Coordinator: modules consult SOMA before changes
  - `recommend_valuation_method()` — wired into `oracle/add_ticker.py` (replaces hardcoded sector→method)
  - `recommend_position_sizing()` — available for MANTIS integration
- soma_bridge.py: `_validate_write()` hooked into all 4 write methods (regime, valuation, trade, portfolio)
- soma_query.py: "violations", "violations [module]", "violations [severity]", "violations summary"
- soma_status.py: KB VIOLATIONS section showing counts + last violation
- run_day.py: Step 2c — violations check after Narrative Alignment
- SOMA event log in add_ticker.py enriched with `kb_valuation_method` and `kb_coordinated` flag

## Schema v3 — 2026-03-21
- **KB Runtime Reader (Phase 2.3b):** `kb_rules` + `kb_audit_log` tables
- KBReader: parses YAML rule blocks from KB markdown, caches in SQLite
- 12 rule blocks across 4 KB files (REGIME_ALLOCATIONS, POSITION_SIZING, DRAWDOWN_CONTROLS, ADVICE_FRAMEWORK, etc.)
- Every rule read logged to kb_audit_log for full traceability
- soma_query.py: "rules", "rule [ID]", "rule audit", "rebuild index", "kb health"
- run_day.py: auto-rebuilds KB index if knowledge files changed (Step KB)
- soma_status.py: KB Rules section showing rule count, staleness, audit activity
- ORACLE wired via `oracle/oracle/kb_integration.py` — 5 rules with fallbacks
- MANTIS wired via `mantis/convergence-backtester/src/kb_integration.py` — 5 rules with fallbacks
- CIPHER wired via `cipher/cipher/kb_integration.py` — 3 rules with fallbacks
- All modules: fire-and-forget pattern, never crash on SOMA failure

## Schema v2 — 2026-03-21
- **Client Profiles (Phase 2.3):** `client_profiles` + `client_interactions` tables
- Per-client investment thesis patterns: positioning, macro bias, sector convictions, CFA framework fields
- SomaBridge: `write_client_profile()` (upsert), `write_client_interaction()`, 6 read methods
- `get_client_context_for_cipher()` — bridges SOMA profiles to CIPHER's framework dict shape
- soma_query.py: "clients", "client [alias]", "clients due", "[positioning] clients"
- Interaction logging auto-updates `last_contact_date` on the profile

## v1.0 — 2026-03-20
- **Initial merge**: Split ORACLE + CIPHER monolithic KBs into 4 domain files
- `macro_regimes.md` — extracted from ORACLE V14.0 KB (GLI, regime framework)
- `valuation_models.md` — extracted from ORACLE V14.0 KB (fair value, DCF, sectors)
- `communication_compliance.md` — extracted from CIPHER KB (ADViCE, PRACTICE, compliance)
- `mantis_mechanics.md` — NEW content (always-in logic, sizing, circuit breaker, cross-AI rules)
- Added YAML `section_meta` frontmatter to each section (id, confidence_score, source_module, valid_condition)
- KB search integrated into `soma_query.py` ("kb [keyword]", "kb list", "kb stale")
