-- Migration 006: HORIZON tactical timing pipeline
-- Stores full analysis results from the HORIZON 7-lens synthesis engine.

CREATE TABLE IF NOT EXISTS horizon_analyses (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id                   TEXT NOT NULL,
    analysis_date            TEXT NOT NULL,
    question                 TEXT,
    composite_score          REAL,
    composite_direction      TEXT,
    concordance_passed       INTEGER,    -- 0 or 1
    concordance_count        INTEGER,    -- agreeing lenses (0-7)
    regime                   TEXT,
    gli_value                REAL,
    raw_confidence           REAL,
    bias_adjusted_confidence REAL,
    final_confidence         REAL,
    n_lenses                 INTEGER,
    n_biases_detected        INTEGER,
    freshness_factor         REAL,
    full_json                TEXT,       -- complete serialized HorizonAnalysis
    write_timestamp          TEXT
);

CREATE INDEX IF NOT EXISTS idx_horizon_run_id ON horizon_analyses(run_id);
CREATE INDEX IF NOT EXISTS idx_horizon_date   ON horizon_analyses(analysis_date);

-- Update schema version
INSERT INTO schema_version (version, applied_at) VALUES (6, datetime('now'));
