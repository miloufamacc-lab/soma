-- Migration 007: DOCTRINE — Directional Oversight of Conviction, Thesis & Risk-Informed Navigation Engine
-- Pipeline: SOMA/DOCTRINE | Module: SOMA
-- Creates 4 tables for the investment thesis engine:
--   philosophy_beliefs  — core conviction statements
--   philosophy_evidence — data points supporting/contradicting beliefs
--   philosophy_history  — conviction score changes over time
--   philosophy_alerts   — conflicts, regime mismatches, stale beliefs

CREATE TABLE IF NOT EXISTS philosophy_beliefs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    belief_id        TEXT NOT NULL UNIQUE,       -- e.g. 'MACRO_ENERGY_BULL', 'CRYPTO_SOL_STRUCTURAL'
    domain           TEXT NOT NULL,              -- 'macro', 'crypto', 'equities', 'risk', 'behavioral'
    statement        TEXT NOT NULL,              -- human-readable belief: "Energy is in a structural bull market"
    conviction       INTEGER NOT NULL DEFAULT 5, -- 1-10 internal score
    evidence_for     INTEGER NOT NULL DEFAULT 0, -- count of supporting evidence
    evidence_against INTEGER NOT NULL DEFAULT 0, -- count of contradicting evidence
    last_tested      TEXT,                        -- ISO date of last evidence check
    is_active        INTEGER NOT NULL DEFAULT 1,  -- 0 = retired/superseded
    created_date     TEXT NOT NULL,
    write_timestamp  TEXT DEFAULT (datetime('now')),
    module_version   TEXT
);

CREATE TABLE IF NOT EXISTS philosophy_evidence (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    belief_id        TEXT NOT NULL,               -- FK to philosophy_beliefs.belief_id
    source_module    TEXT NOT NULL,               -- 'ORACLE', 'MANTIS', 'CIPHER', 'DELTA', 'manual'
    source_detail    TEXT,                        -- e.g. "GLI dropped below 50", "BTC MVRV > 3.5"
    supports         INTEGER NOT NULL,            -- 1 = supports belief, 0 = contradicts
    weight           REAL NOT NULL DEFAULT 1.0,   -- 0.0-2.0 (how strongly this evidence moves conviction)
    run_id           TEXT,                        -- link to ORACLE/MANTIS run that generated this
    date_logged      TEXT NOT NULL,
    write_timestamp  TEXT DEFAULT (datetime('now')),
    module_version   TEXT
);

CREATE TABLE IF NOT EXISTS philosophy_history (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    belief_id        TEXT NOT NULL,               -- FK to philosophy_beliefs.belief_id
    old_conviction   INTEGER NOT NULL,
    new_conviction   INTEGER NOT NULL,
    trigger_type     TEXT NOT NULL,               -- 'new_evidence', 'regime_change', 'stale_decay', 'manual', 'stress_test'
    trigger_detail   TEXT,                        -- human-readable explanation
    run_id           TEXT,
    change_date      TEXT NOT NULL,
    write_timestamp  TEXT DEFAULT (datetime('now')),
    module_version   TEXT
);

CREATE TABLE IF NOT EXISTS philosophy_alerts (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_type       TEXT NOT NULL,               -- 'regime_mismatch', 'evidence_contradiction', 'stale_belief', 'conviction_shock'
    severity         TEXT NOT NULL DEFAULT 'INFO', -- 'INFO', 'WARNING', 'CRITICAL'
    belief_id        TEXT,                         -- which belief is affected (nullable for cross-belief alerts)
    description      TEXT NOT NULL,
    recommended_action TEXT,
    resolved         INTEGER NOT NULL DEFAULT 0,   -- 0 = open, 1 = resolved
    date_flagged     TEXT NOT NULL,
    date_resolved    TEXT,
    write_timestamp  TEXT DEFAULT (datetime('now')),
    module_version   TEXT
);

-- Index for fast lookups
CREATE INDEX IF NOT EXISTS idx_beliefs_domain ON philosophy_beliefs(domain);
CREATE INDEX IF NOT EXISTS idx_beliefs_active ON philosophy_beliefs(is_active);
CREATE INDEX IF NOT EXISTS idx_evidence_belief ON philosophy_evidence(belief_id);
CREATE INDEX IF NOT EXISTS idx_evidence_date ON philosophy_evidence(date_logged);
CREATE INDEX IF NOT EXISTS idx_history_belief ON philosophy_history(belief_id);
CREATE INDEX IF NOT EXISTS idx_alerts_open ON philosophy_alerts(resolved, severity);

-- Track schema version
INSERT INTO schema_version (version, applied_at) VALUES (7, datetime('now'));
