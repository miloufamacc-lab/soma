-- Migration 029 -- down
-- Removes soma_intel_capability registry tables and triggers.

DROP TRIGGER IF EXISTS trg_capability_history_no_delete;
DROP TRIGGER IF EXISTS trg_capability_history_no_update;
DROP INDEX IF EXISTS idx_capability_history_cap;
DROP INDEX IF EXISTS idx_capability_status;
DROP TABLE IF EXISTS soma_intel_capability_history;
DROP TABLE IF EXISTS soma_intel_capability;
DELETE FROM schema_version WHERE version = 29;
