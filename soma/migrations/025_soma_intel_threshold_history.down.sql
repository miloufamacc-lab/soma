-- Migration 025 DOWN — remove soma_intel_threshold_history
DROP TRIGGER IF EXISTS trg_threshold_history_no_delete;
DROP TRIGGER IF EXISTS trg_threshold_history_no_update;
DROP INDEX  IF EXISTS idx_threshold_cell;
DROP TABLE  IF EXISTS soma_intel_threshold_history;
DELETE FROM schema_version WHERE version = 25;
