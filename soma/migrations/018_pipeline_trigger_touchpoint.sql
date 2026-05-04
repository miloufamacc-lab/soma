-- ============================================================
-- Migration 018: Pipeline transition — trigger_touchpoint_id (Phase 5.3)
-- Every pipeline transition can cite the touchpoint that justified it.
-- REQUIRED for any transition → proposal_sent (compliance audit trail).
-- ============================================================

ALTER TABLE raptor_pipeline_log
    ADD COLUMN trigger_touchpoint_id INTEGER REFERENCES raptor_touchpoints(touchpoint_id);

CREATE INDEX IF NOT EXISTS idx_raptor_pipeline_log_trigger
    ON raptor_pipeline_log(trigger_touchpoint_id);

INSERT INTO schema_version (version, applied_at) VALUES (18, datetime('now'));
