-- Migration 020: HORIZON→MANTIS Sizing Contract
-- Stores the daily distilled sizing contract (multiplier) produced by HorizonContract.compute().
-- This is a DERIVED table — it does not replace horizon_analyses (raw 7-lens output).
-- MANTIS reads from horizon_signal; it never touches horizon_analyses directly.

CREATE TABLE IF NOT EXISTS horizon_signal (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_date             TEXT NOT NULL,          -- YYYY-MM-DD (UTC)
    run_id                  TEXT NOT NULL,           -- matches horizon_analyses.run_id
    composite_direction     TEXT NOT NULL,           -- BUY | NEUTRAL | SELL | STRONG_BUY | STRONG_SELL
    final_confidence        REAL NOT NULL,           -- 0.0 – 1.0
    concordance_passed      INTEGER NOT NULL,        -- 0 or 1 (from horizon_analyses)
    regime                  TEXT,                    -- regime string from horizon_analyses (may be NULL)
    regime_gate_pass        INTEGER NOT NULL,        -- 0 if regime in block_list; 1 otherwise
    concordance_gate_pass   INTEGER NOT NULL,        -- 0 if concordance_passed==0; 1 otherwise
    horizon_multiplier      REAL NOT NULL,           -- the output: bounded [0.5, 1.5]; 1.0 on gate fail
    gate_failure_reason     TEXT,                    -- NULL if both gates pass; human-readable reason if not
    write_timestamp         TEXT NOT NULL            -- ISO-8601 UTC
);

-- One row per calendar date (UPSERT-safe via INSERT OR REPLACE).
CREATE UNIQUE INDEX IF NOT EXISTS ux_horizon_signal_date
    ON horizon_signal(signal_date);

-- Fast lookup by write time for staleness checks.
CREATE INDEX IF NOT EXISTS idx_horizon_signal_ts
    ON horizon_signal(write_timestamp);

-- Update schema version table.
INSERT INTO schema_version (version, applied_at) VALUES (20, datetime('now'));
