-- Migration 008: PRISM — Pipeline for Raw Intelligence Sorting & Materiality
-- Pipeline: SOMA/PRISM | Module: SOMA
-- Universal ingestion table for ALL external intelligence sources:
--   YouTube transcripts, X threads, RSS articles, PDFs, manual notes, GEM dumps

CREATE TABLE IF NOT EXISTS raw_intelligence (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type     TEXT NOT NULL,           -- 'youtube', 'x_thread', 'rss', 'pdf', 'manual', 'gem_dump'
    source_url      TEXT,                    -- original URL (nullable for manual)
    title           TEXT,
    content         TEXT NOT NULL,           -- full text content
    category        TEXT,                    -- 'macro', 'crypto', 'equities', 'geopolitical', 'philosophy', 'risk'
    target_pipeline TEXT,                    -- 'TITAN', 'COBALT', 'SPECTRE', 'DOCTRINE', 'BEACON', etc.
    relevance_score INTEGER DEFAULT 5,      -- 1-10 (10 = highest relevance)
    key_claims_json TEXT,                    -- JSON array of extracted claims
    tags_json       TEXT,                    -- JSON array of tags for search
    file_origin     TEXT,                    -- original filename from inbox (for traceability)
    ingested_at     TEXT DEFAULT (datetime('now')),
    processed       INTEGER DEFAULT 0,      -- 0=raw, 1=classified, 2=routed, 3=consumed
    consumed_by     TEXT,                    -- which pipeline consumed this: 'DOCTRINE', 'BEACON', etc.
    consumed_at     TEXT,
    write_timestamp TEXT DEFAULT (datetime('now')),
    module_version  TEXT
);

-- Indexes for fast queries by pipeline consumers
CREATE INDEX IF NOT EXISTS idx_ri_category ON raw_intelligence(category);
CREATE INDEX IF NOT EXISTS idx_ri_pipeline ON raw_intelligence(target_pipeline);
CREATE INDEX IF NOT EXISTS idx_ri_processed ON raw_intelligence(processed);
CREATE INDEX IF NOT EXISTS idx_ri_source ON raw_intelligence(source_type);
CREATE INDEX IF NOT EXISTS idx_ri_ingested ON raw_intelligence(ingested_at);

-- Track schema version
INSERT INTO schema_version (version, applied_at) VALUES (8, datetime('now'));
