# WIRING Manifest — Promoter Blueprint (2026-04-17)

**Transcript:** Jonathan Courtney on Startup Ideas (Greg Eisenberg)
**Hash:** `cbb417e3`
**PRISM primary:** philosophy
**Deliverable status:** Deck complete, QA passed, 3 critical issues fixed.

## Artifact Inventory

| Artifact | Path | Status |
|---|---|---|
| PPTX deck | `intel/by-topic/philosophy/INTEL_20260417_01_promoter-blueprint.pptx` | Built, QA pass |
| Scratchpad (master) | `shared/soma/staging/SCRATCHPAD_20260417_promoter-blueprint.md` | Complete |
| PRISM routing | `shared/soma/staging/PRISM_20260417_promoter-blueprint.yaml` | Complete |
| Wiki article — framework | `wiki/raw/promoter-blueprint-framework.md` | Staged (needs `wiki_ingest`) |
| Wiki article — speaker | `wiki/raw/jonathan-courtney-speaker.md` | Staged (needs `wiki_ingest`) |
| Transcript source | `outputs/transcript_intel/transcript.txt` | Preserved |
| Scanner JSON | `outputs/transcript_intel/scanner_results.json` | Preserved |

## Cross-Module Routing

- **ORACLE:** No equity ticker context — skipped Phase 0.75.
- **SOMA:** PRISM routing staged; 2 wiki articles queued for `wiki_ingest` → wiki/compiled.
- **MANTIS:** Not routed — zero portfolio-action signal.
- **CIPHER:** Flagged for framework re-use. "Post-PMF vs. pre-PMF" caveat must be preserved in any client-facing quotation.
- **RAPTOR:** Not applicable.

## Speaker Index Entries (new first-appearance)

- Jonathan Courtney → `wiki/raw/jonathan-courtney-speaker.md`, tier T2
- Greg Eisenberg → flagged as interviewer-only, no stance captured, no wiki article.

## Prediction Ledger

| ID | Claim | Testable? | Window | Method |
|---|---|---|---|---|
| C5 | AJ&Smart ~$450K per weekly webinar | Yes | 12 mo | Third-party revenue attribution / disclosure |

## Next Actions (manual)

1. Run `wiki_ingest` on the 2 staged `.md` files to move to `compiled/`.
2. Register this transcript in `intel_daily.py` (by-date symlink under `intel/by-date/2026/04/17/`).
3. Email the PPTX to jacobo.pae@gmail.com.
