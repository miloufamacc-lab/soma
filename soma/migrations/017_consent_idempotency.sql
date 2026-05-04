-- ============================================================
-- Migration 017: Consent Ledger Idempotency (Phase 5.2)
-- Adds UNIQUE constraint on (prospect_id, consent_type, consent_date)
-- so that write_consent() can safely UPSERT without creating duplicates.
-- ============================================================

-- SQLite cannot ALTER TABLE ADD CONSTRAINT. We add a UNIQUE INDEX instead —
-- functionally equivalent for ON CONFLICT targeting.
CREATE UNIQUE INDEX IF NOT EXISTS ux_raptor_consent_prospect_type_date
    ON raptor_consent_ledger(prospect_id, consent_type, consent_date);

INSERT INTO schema_version (version, applied_at) VALUES (17, datetime('now'));
