#!/bin/bash
# RAPTOR Phase 0 — Git commits (shared/soma repo)
# Commits the test file that validates all Phase 0 SomaBridge methods.
# Schema (012/017/018) and SomaBridge methods were already committed in prior sessions.
#
# Run from: ~/Desktop/DABEIBA/shared/
# Usage: bash soma/tasks/COMMIT_RAPTOR_P0.sh

set -e
cd "$(cd "$(dirname "$0")/../.." && pwd)"   # shared/
echo "Working in: $(pwd)"

# Remove stale test file if present (force flag needed if file has local modifications)
if [ -f soma/test_raptor_phase0.py ]; then
    git rm -f soma/test_raptor_phase0.py
    echo "Removed stale test file."
fi

echo ""
echo "=== Commit RAPTOR P0 tests (26/26 green) ==="
git add soma/tests/test_raptor_p0.py \
        soma/tasks/COMMIT_RAPTOR_P0.sh
git commit -m "RAPTOR P0: 26 tests green (SomaBridge + stage gates)

- test_raptor_p0.py: prospects, pipeline transitions, stage gates,
  touchpoints, consent ledger, COI network, referrals, dashboard summary
- Stage gate tests: Law 25 consent gate, NI 31-103 COI agreement gate,
  trigger_touchpoint_id required for proposal_sent
- All 3 required migrations applied in fixture (012 + 017 + 018)
- Full regression: 255/255 green (229 SOMA-INTEL + 26 RAPTOR P0)"

echo ""
echo "=== Done (shared/soma) ==="
git log --oneline -5
