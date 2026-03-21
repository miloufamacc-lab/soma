-- SOMA Migration 002: Add events table
-- Tracks system-level events: universe changes, config updates, manual overrides

CREATE TABLE IF NOT EXISTS events (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    date              TEXT NOT NULL,              -- YYYY-MM-DD
    event_type        TEXT NOT NULL,              -- UNIVERSE_ADD, UNIVERSE_REMOVE, CONFIG_CHANGE, MANUAL_OVERRIDE
    source_module     TEXT NOT NULL,              -- oracle, mantis, cipher, add_ticker
    details_json      TEXT,                       -- JSON blob with event-specific data
    write_timestamp   TEXT NOT NULL,              -- ISO-8601
    module_version    TEXT
);

-- Bump schema version
INSERT OR IGNORE INTO schema_version (version, applied_at, description)
VALUES (2, datetime('now'), 'Add events table for universe changes and system events');
