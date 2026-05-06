-- Migration 030 DOWN -- rollback cross_ai_flag table + capability
-- Phase 7.I1.2

DELETE FROM soma_intel_capability WHERE capability_id = 'cross_ai_corroboration';

DROP INDEX IF EXISTS idx_caf_active;
DROP INDEX IF EXISTS idx_caf_source_ts;
DROP INDEX IF EXISTS idx_caf_ticker_ts;
DROP TABLE IF EXISTS soma_intel_cross_ai_flag;

DELETE FROM schema_version WHERE version = 30;
