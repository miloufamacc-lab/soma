#!/bin/bash
# RAPTOR Phase 8 — Git commits across TWO repos
# Repo 1 (shared/soma): knowledge files + pipeline registry
# Repo 2 (raptor/):     RAPTOR_HANDOFF.md
# Architecture doc lives outside any git repo — edit tracked only.
#
# Run from: ~/Desktop/DABEIBA/shared/
# Usage: bash soma/tasks/COMMIT_RAPTOR_P8.sh

set -e
cd "$(cd "$(dirname "$0")/../.." && pwd)"   # shared/
echo "Working in: $(pwd)"

# ── Commit 1: shared/soma repo ────────────────────────────────────────
echo ""
echo "=== Commit 1/2: SOMA knowledge files + pipeline registry ==="
git add soma/knowledge/raptor_lead_scoring.md \
        soma/knowledge/raptor_prohibited_terms.md \
        soma/knowledge/raptor_coi_strategy.md \
        soma/knowledge/raptor_consent_policy.md \
        soma/knowledge/raptor_pipeline_gates.md \
        soma/knowledge/raptor_onboarding_rules.md \
        soma/pipeline_registry.py \
        soma/tasks/COMMIT_RAPTOR_P8.sh
git commit -m "RAPTOR P8: 6 SOMA knowledge files + 4 pipeline registry entries

- knowledge/raptor_lead_scoring.md: RAPTOR_LEAD_SCORING_V1
  Weights, score bands, recency decay, CASL 2yr decay, HOT/WARM/COLD thresholds

- knowledge/raptor_prohibited_terms.md: RAPTOR_PROHIBITED_TERMS_V1
  7 AMF/CIRO categories (BLOCK/WARN), EN+FR patterns

- knowledge/raptor_coi_strategy.md: RAPTOR_COI_STRATEGY_V1
  Network 5-10, priority professions, 60d cadence, 1:1 reciprocity, composite_score

- knowledge/raptor_consent_policy.md: RAPTOR_CONSENT_POLICY_V1
  Law 25 / CASL / CIRO 3804 lifecycle, right-to-erasure, breach CAI notification

- knowledge/raptor_pipeline_gates.md: RAPTOR_PIPELINE_GATES_V1
  Gate rules: consent (→contacted), COI agreement (→onboarding),
  compliance touchpoint + trigger_touchpoint_id (→proposal_sent)

- knowledge/raptor_onboarding_rules.md: RAPTOR_ONBOARDING_V1
  Day 7/30/60/90, document checklist, CIPHER handoff mechanics

- pipeline_registry.py: 4 RAPTOR sub-pipelines added (14 → 18 total)
  PREDATOR (lead scoring), ALLIANCE (COI), CHARTER (compliance), HERALD (CRM3)
  All aliases resolve via resolve()

- Full regression: 390/390 green"

echo ""
echo "=== Done: shared/soma commit ==="
git log --oneline -3

# ── Commit 2: raptor/ repo ────────────────────────────────────────────
echo ""
echo "=== Commit 2/2: raptor/ repo — RAPTOR_HANDOFF.md ==="
cd ../raptor
git add RAPTOR_HANDOFF.md
git commit -m "RAPTOR P8: RAPTOR_HANDOFF.md — full module state document

10 sections: module identity, purpose, file inventory (migrations + commit hashes),
test coverage (141 tests across 7 files), key design decisions, compliance
architecture (AMF/Law25/CASL/CIRO), SOMA events, knowledge files, remaining
phases P9-P12, usage examples for all 5 major workflows."

echo ""
echo "=== Done: raptor/ commit ==="
git log --oneline -3

echo ""
echo "=== RAPTOR P8 complete ==="
echo "NOTE: architecture/DABEIBA_ARCHITECTURE_V2.md updated (V2.1 → V2.2)"
echo "      No git repo at DABEIBA root — file is locally updated only."
