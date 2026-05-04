-- ============================================================
-- Migration 019: soma_events pub/sub (Phase 6.1)
-- Distinct from legacy `events` table (which is an audit log).
-- soma_events is a cursor-based fanout: publishers append,
-- subscribers advance their own cursor and replay from it.
-- ============================================================

CREATE TABLE IF NOT EXISTS soma_events (
    event_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type       TEXT NOT NULL,            -- REGIME_CHANGE, RULE_UPDATE, PROSPECT_ADDED, REPORT_EXPORTED, MODEL_FLAG_RAISED, BACKTEST_COMPLETE, …
    source_module    TEXT NOT NULL,            -- oracle, mantis, cipher, raptor, soma
    payload_json     TEXT NOT NULL,            -- arbitrary JSON blob
    published_at     TEXT NOT NULL,            -- ISO-8601 UTC
    correlation_key  TEXT                      -- optional (e.g. prospect_id, ticker, run_id)
);

CREATE INDEX IF NOT EXISTS idx_soma_events_type
    ON soma_events(event_type);

CREATE INDEX IF NOT EXISTS idx_soma_events_published_at
    ON soma_events(published_at);

CREATE INDEX IF NOT EXISTS idx_soma_events_correlation
    ON soma_events(correlation_key);


-- Per-subscriber cursor — pub/sub clients advance this as they consume.
CREATE TABLE IF NOT EXISTS soma_event_subscribers (
    subscriber_name      TEXT PRIMARY KEY,      -- e.g. "cipher_dashboard", "oracle_main", "raptor_ui"
    last_seen_event_id   INTEGER NOT NULL DEFAULT 0,
    type_filter          TEXT,                  -- optional CSV of event_types this subscriber cares about (NULL = all)
    first_registered_at  TEXT NOT NULL,
    updated_at           TEXT NOT NULL
);


INSERT INTO schema_version (version, applied_at) VALUES (19, datetime('now'));
