# Phase 2.6 + 2.5 — KB Wiring & Portfolio-Narrative Alignment

## Plan

### Scope
Two tasks closing out Phase 2:
1. **KB Wiring (Phase 2.6)** — Prompts C/D/E/F. Only **E** (CIPHER) and **F** (orchestration) are in scope for this session. C (ORACLE) and D (MANTIS) require modifying those modules which aren't the focus here.
2. **Portfolio-Narrative Alignment (Phase 2.5)** — Build the scorer that flags contradictions between outlook text and portfolio positions.

### Architecture Decision
- Prompt E creates `cipher/cipher/kb_integration.py` — 3 getters (ADViCE, PRACTICE, money scripts) with KB-first + fallback
- Prompt F adds KB index step to `run_day.py`, KB section to `soma_status.py`, KB health to `soma_query.py`
- Alignment scorer lives at `shared/soma/narrative_alignment.py` — follows `what_changed.py` pattern
- Scorer reads `outlook_snapshots` + `portfolio_state` + `regime_history` from SOMA
- Output: 0-5 inconsistencies with severity + contradiction_score, overall alignment 0-1

### Execution Order
- [x] **E1:** Create `cipher/cipher/kb_integration.py` (3 getters + fallbacks)
- [x] **E2:** Modify `advice_framework.py` to load from KB
- [x] **E3:** Modify `practice_framework.py` to load from KB
- [x] **E4:** Modify `wiift_framework.py` to load money scripts from KB
- [x] **F1:** Add Step 0 (KB index rebuild) to `run_day.py`
- [x] **F2:** Add KB Rules section to `soma_status.py`
- [x] **F3:** Add `kb health` command to `soma_query.py`
- [x] **A1:** Build `narrative_alignment.py` (scorer core)
- [x] **A2:** Wire into `run_day.py` as step after What Changed
- [x] **A3:** Add alignment section to `soma_status.py`
- [x] **V1:** Import test all modified files
- [x] **V2:** Run scorer against mock data, verify output format

### Safety
- All KB reads have try/except → fallback to hardcoded values
- All scoring is non-fatal — pipeline never aborts on alignment failure
- No behavioral change to existing code — same values flow, just KB-sourced

## Results (March 21, 2026)

### KB Wiring (Prompts E + F) — COMPLETE
- `cipher/cipher/kb_integration.py` — 3 getters with hardcoded fallbacks + SOMA KB reads + audit logging
- `advice_framework.py` — loads ADViCE elements from KB via `_kb_rules`, adds `get_element()` and `get_all_elements()`
- `practice_framework.py` — loads PRACTICE steps from KB, adds `get_checklist()` and `get_step()`
- `wiift_framework.py` — loads money scripts from KB, adds `get_script_profile()`, `get_communication_strategies()`, `get_blind_spots()`
- `run_day.py` — new Step KB before backup: auto-rebuilds index if knowledge files changed
- `soma_status.py` — new KB RULES section: rule count, staleness, module breakdown, last audit read
- `soma_query.py` — new `kb health` command: rules by file, audit summary, most-read rules

### Portfolio-Narrative Alignment — COMPLETE
- `shared/soma/narrative_alignment.py` — 5 contradiction checks:
  1. Sentiment vs Regime (outlook tone ↔ regime signal)
  2. Exposure vs Regime (portfolio positioning ↔ regime)
  3. Outlook vs Exposure (narrative ↔ portfolio)
  4. Drawdown vs Outlook (HWM drawdown ↔ optimism)
  5. Regime Stability vs Confidence (instability ↔ conviction)
- Output: 0-1 alignment score, contradiction score, up to 5 inconsistencies with severity
- Wired into `run_day.py` as Step 2b (after What Changed)
- Wired into `soma_status.py` as NARRATIVE ALIGNMENT section
- JSON logs saved to `shared/soma/logs/alignment_*.json`

### Verification
- 8/8 import tests passed
- Aligned scenario: 100% alignment, 0 issues ✓
- Contradictory scenario: 0% alignment, 2 HIGH issues detected ✓
- Empty SOMA: graceful degradation, no crashes ✓
- All existing CIPHER functionality preserved (apply, generate_meeting_prep, map_insight_to_client, email, script assessment) ✓
