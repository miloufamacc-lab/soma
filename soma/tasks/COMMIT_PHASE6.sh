#!/bin/bash
# SOMA-INTEL Phase 6 — Git commits (corrected paths)
# P6.5 already committed as b894a05.
# This script commits P6.2–P6.4 (untracked), P6.6, P6.7, then tags.
#
# Run from: ~/Desktop/DABEIBA/shared/
# Usage: bash soma/tasks/COMMIT_PHASE6.sh

set -e
cd "$(cd "$(dirname "$0")/../.." && pwd)"  # shared/

echo "Working in: $(pwd)"

echo ""
echo "=== Commit P6.2: novelty.py + IntelStore additions ==="
git add soma/intel/novelty.py \
        soma/intel/store.py \
        soma/tests/test_novelty_p62.py
git commit -m "P6.2: novelty.py + IntelStore.count_signals_by_ticker_type()

- novelty.py: novelty_score() = 1.0 - min(1.0, count_90d/10)
- store.py: count_signals_by_ticker_type(), get_cell_threshold(),
  append_threshold_adjustment()
- 14 tests all green"

echo ""
echo "=== Commit P6.3: exploration.py (P-X channel) ==="
git add soma/intel/exploration.py \
        soma/tests/test_exploration_p63.py
git commit -m "P6.3: exploration channel (1.5<=z<2.5, roulette-wheel, P-X tag)

- exploration.py: ExplorationChannel — get_candidates(), sample(n), weighted sampling
- Samples 1-2 low-z signals per day weighted by novelty_score
- Tags selected signals priority='P-X', appends 'exploration_channel' to notes
- 15 tests all green"

echo ""
echo "=== Commit P6.4: meta_learner.py + Migration 025 ==="
git add soma/intel/meta_learner.py \
        soma/migrations/025_soma_intel_threshold_history.sql \
        soma/migrations/025_soma_intel_threshold_history.down.sql \
        soma/tests/test_meta_learner_p64.py
git commit -m "P6.4: meta_learner.py + Migration 025 (soma_intel_threshold_history)

- meta_learner.py: weekly per-cell threshold adjustment via backtest outcomes
  Cell key: regime|sector|dominant_feature
  Rules: >=3 false_neg -> lower 0.1; >=3 false_pos -> raise 0.1; cap +-0.5
- Migration 025: soma_intel_threshold_history (append-only via triggers)
- 16 tests all green (incl. real DB integration)"

echo ""
echo "=== Commit P6.6: weekly_brief.py + first brief ==="
git add soma/intel/weekly_brief.py
# weekly_brief HTML lives in the cipher repo — handled separately if needed
git commit -m "P6.6: weekly_brief.py — Friday HTML intelligence brief

- 6 sections: regime, P1 carry-overs, new theses, convergence movers,
  regime posterior placeholder, structural watch
- Output: cipher/outputs/weekly_brief_YYYY-MM-DD.html (Friday-gated)
- Zero internal codenames (scrubbed), zero emojis
- First brief: weekly_brief_2026-05-09.html (next Friday)"

echo ""
echo "=== Commit P6.7: run_day.py wiring + backtest fixes + docs ==="
git add soma/run_day.py \
        soma/tasks/todo.md \
        soma/tasks/COMMIT_PHASE6.sh \
        soma/intel/backtest_report.py \
        soma/intel/backtest_prices.py \
        soma/intel/backtest_runner.py \
        soma/migrations/024_soma_intel_signal_backtest.sql \
        soma/tests/test_backtest_p53.py \
        soma/intelligence/brief_log.jsonl 2>/dev/null || true
git commit -m "P6.7: run_day.py wired + full regression green + docs

- run_day.py step_soma_intel: horizon tracks + boost added (1d extension)
- run_day.py step_meta_learner_weekly: Sunday-only (1e)
- run_day.py step_weekly_brief_friday: Friday-only (1f)
- backtest_report.py: calibration PNG z-score bucket fix (was [0,1])
- tasks/todo.md: Phase 6 build log + 8 lessons appended
- 229/229 tests green, 44,388 backtest rows unchanged, schema v25"

echo ""
echo "=== Tag v22-soma-intel-phase6-green ==="
git tag -a v22-soma-intel-phase6-green -m "SOMA-INTEL Phase 6 complete

P6.0  Backtest reports (IS, OOS, summary) + calibration PNGs fixed
P6.1  PHASE5_5_REBACKTEST_SCHEDULED.md + CLAUDE.md entry
P6.2  novelty.py + count_signals_by_ticker_type()
P6.3  exploration.py (1.5<=z<2.5, roulette-wheel, P-X tag)
P6.4  meta_learner.py + Migration 025 (soma_intel_threshold_history)
P6.5  horizon_tactical / thematic / structural + boost + migration [b894a05]
P6.6  weekly_brief.py (Friday HTML, 6 sections, codename-clean)
P6.7  run_day.py 1d/1e/1f wired — 229 tests green

Backtest baseline: 44,388 rows (IS=34,843 / OOS=9,545)
Schema version: 25"

echo ""
echo "=== Done ==="
git log --oneline -8
echo ""
git tag | grep phase
