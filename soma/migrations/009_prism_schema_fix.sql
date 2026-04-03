-- Migration 009: Fix raw_intelligence columns for PRISM V2 architecture
-- Renames target_module → target_pipeline (Architecture V2: pipelines, not modules)
-- Renames file_path → file_origin (clearer semantics)
-- Adds consumed_by and consumed_at columns for pipeline consumption tracking

ALTER TABLE raw_intelligence RENAME COLUMN target_module TO target_pipeline;
ALTER TABLE raw_intelligence RENAME COLUMN file_path TO file_origin;

-- Add consumption tracking columns (nullable — only set when consumed)
ALTER TABLE raw_intelligence ADD COLUMN consumed_by TEXT;
ALTER TABLE raw_intelligence ADD COLUMN consumed_at TEXT;

-- Drop old processed_at (replaced by consumed_at)
-- SQLite can't drop columns before 3.35, so we leave it as deprecated
-- ALTER TABLE raw_intelligence DROP COLUMN processed_at;

-- Track schema version
INSERT INTO schema_version (version, applied_at) VALUES (9, datetime('now'));
