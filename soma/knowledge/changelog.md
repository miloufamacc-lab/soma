# SOMA — Changelog

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
