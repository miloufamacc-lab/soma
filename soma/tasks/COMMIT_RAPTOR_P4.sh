#!/bin/bash
# RAPTOR Phase 4 — Git commit (shared/soma repo)
# Run from: ~/Desktop/DABEIBA/shared/
# Usage: bash soma/tasks/COMMIT_RAPTOR_P4.sh

set -e
cd "$(cd "$(dirname "$0")/../.." && pwd)"   # shared/
echo "Working in: $(pwd)"

echo ""
echo "=== Commit RAPTOR P4: CRM3 Value Proposition Engine (24/24 green, 351/351 regression) ==="
git add soma/migrations/027_raptor_crm3.sql \
        soma/raptor_crm3_analyzer.py \
        soma/soma_bridge.py \
        soma/tests/test_raptor_p4.py \
        soma/tasks/COMMIT_RAPTOR_P4.sh
git commit -m "RAPTOR P4: CRM3 value proposition engine + 24 tests green

- migrations/027_raptor_crm3.sql
  raptor_fund_mers table: fund_id, ticker (UNIQUE), fund_name, mer, ter,
  fund_family, fund_type, currency, notes
  Full UNIQUE index on ticker (required for ON CONFLICT upsert; NULL = distinct)
  Schema version 27

- raptor_crm3_analyzer.py: CRM3Analyzer class
  _normalize_weights(): auto-detects % vs fraction input, scales to sum=1.0
  _compound_drag(): aum × ((1+r)^N − (1+r−f)^N), r=6% default assumption
  ingest_prospect_holdings(): weighted MER + drag_per_1M at 10/20/30yr
  compare_to_raptor_model(): side-by-side fee_savings_pct + dollar savings
  generate_crm3_report(): markdown report, bilingual EN/FR, AMF-safe disclaimers
  seed_fund_mers(): 19 Canadian funds seeded (RBC/TD/Fidelity mutual funds +
    iShares/BMO/Vanguard ETFs + segregated fund proxy)

- soma_bridge.py: 3 new fund MER methods
  write_fund_mer(): upsert on ticker (ON CONFLICT DO UPDATE) or plain insert if
    ticker=None (NULL tickers are each distinct in SQLite)
  get_fund_mer(ticker): lookup by ticker
  get_all_fund_mers(): all funds ordered by family, name

- Fix: migration renamed 013→027 to avoid collision with 013_pipeline_alias_views.sql

- Full regression: 351/351 green (229 SOMA-INTEL + 98 RAPTOR P0-P4 + 24 new)"

echo ""
echo "=== Done ==="
git log --oneline -5
