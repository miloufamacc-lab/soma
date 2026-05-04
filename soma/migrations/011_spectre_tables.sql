-- Migration 011: SPECTRE — Strategic Political Event Classification & Threat Response Engine
-- Pipeline: ORACLE/SPECTRE | Module: ORACLE
-- Geopolitical risk scoring: RSS feeds → keyword triage → NLP → delta check

-- Geopolitical events: every article/headline that passes triage
CREATE TABLE IF NOT EXISTS geo_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    date            TEXT NOT NULL,               -- YYYY-MM-DD
    run_id          TEXT,
    source          TEXT NOT NULL,               -- 'reuters', 'bbc', 'ap', 'aljazeera', 'manual'
    title           TEXT NOT NULL,
    url             TEXT,
    content_snippet TEXT,                        -- first ~500 chars for triage
    category        TEXT,                        -- 'conflict', 'sanctions', 'trade', 'election', 'energy', 'monetary', 'other'
    region          TEXT,                        -- 'US', 'EU', 'CN', 'RU', 'ME', 'GLOBAL', etc.
    severity        INTEGER DEFAULT 3,           -- 1-5 (5 = highest market impact)
    keywords_json   TEXT,                        -- JSON array of matched keywords
    nlp_score       REAL,                        -- phi4-mini confidence score (0-1), NULL if regex-only
    market_relevance TEXT DEFAULT 'LOW',         -- 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'
    write_timestamp TEXT DEFAULT (datetime('now')),
    module_version  TEXT
);

-- Geopolitical risk vectors: aggregated risk scores per region/category
CREATE TABLE IF NOT EXISTS geo_vectors (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    date            TEXT NOT NULL,
    run_id          TEXT,
    region          TEXT NOT NULL,
    category        TEXT NOT NULL,
    risk_score      REAL NOT NULL,               -- 0-1 normalized
    event_count     INTEGER DEFAULT 0,           -- how many events drove this score
    trend           TEXT,                        -- 'RISING', 'STABLE', 'FALLING'
    components_json TEXT,                        -- JSON breakdown of score drivers
    write_timestamp TEXT DEFAULT (datetime('now')),
    module_version  TEXT
);

-- Geopolitical baselines: rolling 30-day averages for delta detection
CREATE TABLE IF NOT EXISTS geo_baselines (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    date            TEXT NOT NULL,
    region          TEXT NOT NULL,
    category        TEXT NOT NULL,
    baseline_score  REAL NOT NULL,               -- 30-day rolling average risk score
    std_dev         REAL,                        -- standard deviation for sigma-based alerts
    sample_count    INTEGER DEFAULT 0,           -- how many days in the rolling window
    write_timestamp TEXT DEFAULT (datetime('now')),
    module_version  TEXT
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_geo_events_date ON geo_events(date);
CREATE INDEX IF NOT EXISTS idx_geo_events_category ON geo_events(category);
CREATE INDEX IF NOT EXISTS idx_geo_events_region ON geo_events(region);
CREATE INDEX IF NOT EXISTS idx_geo_events_severity ON geo_events(severity);
CREATE INDEX IF NOT EXISTS idx_geo_events_relevance ON geo_events(market_relevance);
CREATE INDEX IF NOT EXISTS idx_geo_vectors_date ON geo_vectors(date);
CREATE INDEX IF NOT EXISTS idx_geo_vectors_region ON geo_vectors(region, category);
CREATE INDEX IF NOT EXISTS idx_geo_baselines_region ON geo_baselines(region, category);

-- Track schema version
INSERT INTO schema_version (version, applied_at) VALUES (11, datetime('now'));
