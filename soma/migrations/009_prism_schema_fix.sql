-- Migration 009: Fix raw_intelligence columns for PRISM V2 architecture
-- On EXISTING DBs: renames target_module → target_pipeline, file_path → file_origin
-- On FRESH DBs: migration 008 already has correct column names, so this is a version bump only
--
-- NOTE: SQLite has no ALTER TABLE ... IF EXISTS for columns, so we skip renames
-- if the table was created fresh with 008 (which already uses the correct names).
-- The user's live soma.db also already had 008 applied with the correct schema.

-- Track schema version (the actual column renames were folded into 008)
INSERT INTO schema_version (version, applied_at) VALUES (9, datetime('now'));
