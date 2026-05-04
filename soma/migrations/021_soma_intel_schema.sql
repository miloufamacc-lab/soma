-- Migration 021: SOMA-INTEL — Signal-from-Noise Intelligence Memory Layer
-- Adds 9 tables for the graph, signal, and forecast layers.
-- All tables use the soma_intel_* namespace to keep the split mechanical.
-- No existing tables are touched. run_day.py steps 1–15 are unaffected.
--
-- Split trigger (future module DELPHI): graph > 50k edges OR code > 5k LOC.
-- Down migration: 021_soma_intel_schema.down.sql

-- ── 1. Nodes ─────────────────────────────────────────────────────────────────
-- Entity registry: company | sector | theme | platform | person |
--                  regime  | event  | etf   | concept
CREATE TABLE IF NOT EXISTS soma_intel_node (
    node_id      TEXT PRIMARY KEY,
    node_type    TEXT NOT NULL,
    name         TEXT NOT NULL,
    aliases      TEXT,           -- JSON array of alternate names / IDs
    metadata     TEXT,           -- JSON object (arbitrary per node_type)
    created_ts   TEXT NOT NULL,
    last_seen_ts TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_intel_node_type
    ON soma_intel_node(node_type);

-- FTS5 virtual table for full-text node search
CREATE VIRTUAL TABLE IF NOT EXISTS soma_intel_node_fts
    USING fts5(
        node_id UNINDEXED,
        name,
        node_type,
        content=soma_intel_node,
        content_rowid=rowid
    );

-- Sync triggers (keep FTS5 in step with node upserts)
CREATE TRIGGER IF NOT EXISTS soma_intel_node_fts_ai
AFTER INSERT ON soma_intel_node BEGIN
    INSERT INTO soma_intel_node_fts(rowid, node_id, name, node_type)
    VALUES (new.rowid, new.node_id, new.name, new.node_type);
END;

CREATE TRIGGER IF NOT EXISTS soma_intel_node_fts_au
AFTER UPDATE ON soma_intel_node BEGIN
    INSERT INTO soma_intel_node_fts(soma_intel_node_fts, rowid, node_id, name, node_type)
        VALUES ('delete', old.rowid, old.node_id, old.name, old.node_type);
    INSERT INTO soma_intel_node_fts(rowid, node_id, name, node_type)
        VALUES (new.rowid, new.node_id, new.name, new.node_type);
END;

-- ── 2. Edges (§A.3 — verbatim DDL, IF NOT EXISTS added for idempotency) ─────
CREATE TABLE IF NOT EXISTS soma_intel_edge (
    edge_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    src_node_id    TEXT NOT NULL,
    dst_node_id    TEXT NOT NULL,
    edge_type      TEXT NOT NULL,
    weight         REAL NOT NULL DEFAULT 1.0,
    confidence     REAL NOT NULL CHECK(confidence BETWEEN 0 AND 1),
    ts             TEXT NOT NULL,                     -- ISO 8601
    half_life_days INTEGER NOT NULL,
    source_id      TEXT NOT NULL,
    source_type    TEXT NOT NULL,                     -- wiki|transcript|oracle_titan|10k|news|manual|derived
    evidence_text  TEXT,                              -- exact supporting quote (<=500 chars)
    audit_status   TEXT DEFAULT 'unaudited',          -- unaudited|approved|rejected|corrected
    audit_ts       TEXT,
    audit_notes    TEXT,
    superseded_by  INTEGER,                           -- edge_id of newer contradicting edge
    FOREIGN KEY (src_node_id)   REFERENCES soma_intel_node(node_id),
    FOREIGN KEY (dst_node_id)   REFERENCES soma_intel_node(node_id),
    FOREIGN KEY (superseded_by) REFERENCES soma_intel_edge(edge_id)
);

CREATE INDEX IF NOT EXISTS idx_edge_src
    ON soma_intel_edge(src_node_id, edge_type, ts DESC);
CREATE INDEX IF NOT EXISTS idx_edge_dst
    ON soma_intel_edge(dst_node_id, edge_type, ts DESC);
CREATE INDEX IF NOT EXISTS idx_edge_ts
    ON soma_intel_edge(ts);
CREATE INDEX IF NOT EXISTS idx_edge_audit
    ON soma_intel_edge(audit_status)
    WHERE audit_status = 'unaudited';

-- ── 3. Beliefs — versioned claims with provenance ─────────────────────────────
CREATE TABLE IF NOT EXISTS soma_intel_belief (
    belief_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_node_id TEXT NOT NULL,
    predicate      TEXT NOT NULL,                     -- e.g. "valuation_thesis", "platform_position"
    value          TEXT NOT NULL,                     -- JSON
    confidence     REAL NOT NULL,
    ts             TEXT NOT NULL,
    source_id      TEXT NOT NULL,
    superseded_by  INTEGER,
    FOREIGN KEY (subject_node_id) REFERENCES soma_intel_node(node_id)
);

CREATE INDEX IF NOT EXISTS idx_belief_subject
    ON soma_intel_belief(subject_node_id, predicate, ts DESC);

-- ── 4. Regime — daily classification (bull/bear/transition × vol × macro) ────
CREATE TABLE IF NOT EXISTS soma_intel_regime (
    date            TEXT PRIMARY KEY,
    trend_state     TEXT NOT NULL,      -- bull|transition|bear
    vol_state       TEXT NOT NULL,      -- low|med|high
    macro_state     TEXT NOT NULL,      -- easing|neutral|tightening
    composite_label TEXT NOT NULL,      -- e.g. "bull_low_easing"
    confidence      REAL NOT NULL,      -- product of per-axis confidence
    features        TEXT NOT NULL       -- JSON of the 13 input series
);

-- ── 5. Signals — daily ranked anomalies ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS soma_intel_signal (
    signal_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker               TEXT NOT NULL,
    date                 TEXT NOT NULL,
    priority             TEXT NOT NULL,          -- P1|P2|P3|P-X
    anomaly_score        REAL NOT NULL,
    features             TEXT NOT NULL,          -- JSON of f1..f5
    corroboration_count  INTEGER NOT NULL,
    half_life_days       INTEGER NOT NULL,
    reconfirmation_count INTEGER DEFAULT 0,
    status               TEXT DEFAULT 'active',  -- active|expired|reconfirmed
    horizon              TEXT,                   -- tactical|thematic|structural (added v1.1)
    notes                TEXT
);

CREATE INDEX IF NOT EXISTS idx_signal_ticker_date
    ON soma_intel_signal(ticker, date DESC);
CREATE INDEX IF NOT EXISTS idx_signal_priority_date
    ON soma_intel_signal(priority, date DESC);
CREATE INDEX IF NOT EXISTS idx_signal_status
    ON soma_intel_signal(status)
    WHERE status = 'active';

-- ── 6. Platforms — ARK-style innovation platforms ────────────────────────────
CREATE TABLE IF NOT EXISTS soma_intel_platform (
    platform_id       TEXT PRIMARY KEY,           -- pl_ai, pl_robotics, etc.
    name              TEXT NOT NULL,
    adoption_metric   TEXT NOT NULL,              -- what metric the S-curve tracks
    curve_K           REAL,                       -- logistic saturation level
    curve_r           REAL,                       -- adoption rate
    curve_t0          TEXT,                       -- inflection date (ISO 8601)
    wrights_law_rate  REAL,                       -- % cost decline per doubling
    position          TEXT,                       -- pre-takeoff|acceleration|inflection|deceleration|saturation
    last_fit_ts       TEXT
);

-- ── 7. S-curve history — monthly data points per platform ────────────────────
CREATE TABLE IF NOT EXISTS soma_intel_scurve_history (
    history_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    platform_id     TEXT NOT NULL,
    date            TEXT NOT NULL,                -- YYYY-MM (monthly)
    metric_value    REAL NOT NULL,
    cumulative_units REAL,
    unit_cost        REAL,
    source          TEXT NOT NULL,
    FOREIGN KEY (platform_id) REFERENCES soma_intel_platform(platform_id)
);

CREATE INDEX IF NOT EXISTS idx_scurve_platform_date
    ON soma_intel_scurve_history(platform_id, date DESC);

-- ── 8. Universe — canonical ticker registry ───────────────────────────────────
CREATE TABLE IF NOT EXISTS soma_intel_universe (
    ticker         TEXT PRIMARY KEY,
    source         TEXT NOT NULL,                 -- security_master|arkk|arkg|xle|smh
    platform_tags  TEXT,                          -- JSON array of platform_ids
    added_ts       TEXT NOT NULL,
    active         INTEGER DEFAULT 1,             -- 1=active, 0=demoted
    tier           TEXT DEFAULT 'core',           -- core|watch|archived
    auto_added     INTEGER DEFAULT 0,             -- 1 if promoted by universe_manager
    promotion_score REAL,
    promotion_source TEXT
);

CREATE INDEX IF NOT EXISTS idx_universe_active
    ON soma_intel_universe(active)
    WHERE active = 1;

-- ── 9. Baselines — regime-conditional per-ticker feature statistics ───────────
CREATE TABLE IF NOT EXISTS soma_intel_baseline (
    ticker         TEXT NOT NULL,
    regime_label   TEXT NOT NULL,                 -- composite_label from soma_intel_regime
    feature        TEXT NOT NULL,                 -- f1..f5 feature name
    mean           REAL NOT NULL,
    stdev          REAL NOT NULL,
    n_days         INTEGER NOT NULL,
    is_provisional INTEGER DEFAULT 0,             -- 1 if n_days < 30 (nearest-regime fallback)
    last_updated   TEXT NOT NULL,
    PRIMARY KEY (ticker, regime_label, feature)
);

-- ── Update schema version ─────────────────────────────────────────────────────
INSERT INTO schema_version (version, applied_at)
VALUES (21, datetime('now'));
