-- Migration 015: Model flags for cross-skill intelligence routing.
-- Written by staging_dispatcher MODEL_FLAG handler.
-- Read by ORACLE run_day.py (ranking badges) and update-valuation (stale detection).

CREATE TABLE IF NOT EXISTS model_flags (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker              TEXT NOT NULL,
    flag_type           TEXT NOT NULL DEFAULT 'FRESH_INTEL',  -- FRESH_INTEL | STALE_TRIGGER
    source              TEXT NOT NULL,
    source_hash         TEXT,
    claims_summary      TEXT,           -- JSON array of key claims
    impact_on_valuation TEXT,
    suggested_action    TEXT,           -- refresh | deep_update | null
    is_consumed         INTEGER DEFAULT 0,  -- 0=pending, 1=consumed by ORACLE/update-valuation
    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    consumed_at         TEXT,
    consumed_by         TEXT,           -- run_day | update-valuation | manual
    write_timestamp     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    module_version      TEXT DEFAULT 'staging_dispatcher_v1'
);

CREATE INDEX IF NOT EXISTS idx_model_flags_ticker ON model_flags(ticker);
CREATE INDEX IF NOT EXISTS idx_model_flags_pending ON model_flags(is_consumed) WHERE is_consumed = 0;
