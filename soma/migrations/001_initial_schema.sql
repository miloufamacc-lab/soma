-- SOMA Initial Schema (v1)
-- Shared Ontology for Market Analysis
-- All tables use write_timestamp for freshness checks and module_version for traceability.

CREATE TABLE IF NOT EXISTS schema_version (
    version       INTEGER PRIMARY KEY,
    applied_at    TEXT NOT NULL,
    description   TEXT
);

CREATE TABLE IF NOT EXISTS regime_history (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    date                TEXT NOT NULL,              -- YYYY-MM-DD
    run_id              TEXT NOT NULL,              -- UUID grouping all writes from one ORACLE run
    gli_value           REAL,
    regime              TEXT,                       -- e.g. RISK_ON, TURBULENCE, CONTRACTION
    diffusion_index     REAL,
    momentum            REAL,
    gli_components_json TEXT,                       -- JSON blob of raw GLI inputs
    write_timestamp     TEXT NOT NULL,              -- ISO-8601
    module_version      TEXT
);

CREATE TABLE IF NOT EXISTS valuations (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    date              TEXT NOT NULL,
    run_id            TEXT NOT NULL,
    ticker            TEXT NOT NULL,
    fair_value        REAL,
    current_price     REAL,
    implied_upside    REAL,
    execution_score   REAL,
    write_timestamp   TEXT NOT NULL,
    module_version    TEXT
);

CREATE TABLE IF NOT EXISTS trade_log (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    date              TEXT NOT NULL,
    ticker            TEXT NOT NULL,
    action            TEXT NOT NULL,                -- BUY / SELL / REBALANCE
    price             REAL,
    weight            REAL,
    reason            TEXT,
    regime_at_time    TEXT,
    gli_value         REAL,
    diffusion_index   REAL,
    momentum          REAL,
    vol_reading       REAL,
    onchain_tx_id     TEXT,                         -- Solana tx hash (future)
    confirm_block     INTEGER,
    write_timestamp   TEXT NOT NULL,
    module_version    TEXT
);

CREATE TABLE IF NOT EXISTS outlook_snapshots (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    date                  TEXT NOT NULL,
    version               TEXT,
    full_text_hash        TEXT,
    key_conclusions_json  TEXT,
    write_timestamp       TEXT NOT NULL,
    module_version        TEXT
);

CREATE TABLE IF NOT EXISTS portfolio_state (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    date              TEXT NOT NULL,
    positions_json    TEXT,
    cash_pct          REAL,
    total_value       REAL,
    dd_from_hwm       REAL,
    write_timestamp   TEXT NOT NULL,
    module_version    TEXT
);

-- Seed the schema version
INSERT OR IGNORE INTO schema_version (version, applied_at, description)
VALUES (1, datetime('now'), 'Initial SOMA schema');
