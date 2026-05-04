-- Migration 014: Staging log for the batch staging processor.
-- Tracks every file processed by staging_dispatcher.py for idempotency and audit.

CREATE TABLE IF NOT EXISTS staging_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    filename        TEXT NOT NULL,
    staging_type    TEXT NOT NULL,
    source          TEXT,
    source_hash     TEXT,
    status          TEXT NOT NULL DEFAULT 'processed',  -- processed | error | skipped
    error_detail    TEXT,
    processed_at    TEXT NOT NULL,
    write_timestamp TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    module_version  TEXT DEFAULT 'staging_dispatcher_v1'
);

CREATE INDEX IF NOT EXISTS idx_staging_log_hash ON staging_log(source_hash);
CREATE INDEX IF NOT EXISTS idx_staging_log_type ON staging_log(staging_type);
CREATE INDEX IF NOT EXISTS idx_staging_log_status ON staging_log(status);
