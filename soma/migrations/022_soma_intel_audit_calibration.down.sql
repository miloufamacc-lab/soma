-- ════════════════════════════════════════════════════════════════════════════
-- Migration 022 DOWN — remove audit log + source calibration tables
-- ════════════════════════════════════════════════════════════════════════════

DROP TRIGGER  IF EXISTS soma_intel_audit_log_no_update;
DROP TRIGGER  IF EXISTS soma_intel_audit_log_no_delete;
DROP INDEX    IF EXISTS idx_audit_edge;
DROP TABLE    IF EXISTS soma_intel_audit_log;
DROP TABLE    IF EXISTS soma_intel_source_calibration;

DELETE FROM schema_version WHERE version = 22;
