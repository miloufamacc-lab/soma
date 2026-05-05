-- Migration 029 -- soma_intel_capability registry
-- Phase 7.H3 -- Feature flag table for phased rollout control.
-- Every feature registers here. Phased rollout = flag flip.
-- Disabling a capability = one row update, no code change.
-- Created: 2026-05-05

CREATE TABLE IF NOT EXISTS soma_intel_capability (
  capability_id  TEXT PRIMARY KEY,
  status         TEXT NOT NULL CHECK(status IN ('enabled','disabled','experimental')),
  enabled_ts     TEXT,            -- ISO 8601 timestamp when capability was first enabled
  version        TEXT NOT NULL,   -- semver string, e.g. '1.0'
  depends_on     TEXT             -- JSON array of capability_ids this one depends on
);

CREATE TABLE IF NOT EXISTS soma_intel_capability_history (
  history_id     INTEGER PRIMARY KEY AUTOINCREMENT,
  capability_id  TEXT    NOT NULL,
  old_status     TEXT    NOT NULL,
  new_status     TEXT    NOT NULL,
  changed_ts     TEXT    NOT NULL,
  changed_by     TEXT    NOT NULL DEFAULT 'system',
  notes          TEXT,
  FOREIGN KEY (capability_id) REFERENCES soma_intel_capability(capability_id)
);

CREATE INDEX IF NOT EXISTS idx_capability_status
  ON soma_intel_capability(status);

CREATE INDEX IF NOT EXISTS idx_capability_history_cap
  ON soma_intel_capability_history(capability_id, changed_ts DESC);

-- Append-only guards on history table (same pattern as soma_intel_threshold_history).
-- Prevent any UPDATE or DELETE on the history log.
CREATE TRIGGER IF NOT EXISTS trg_capability_history_no_update
BEFORE UPDATE ON soma_intel_capability_history
BEGIN
  SELECT RAISE(ABORT, 'soma_intel_capability_history is append-only: UPDATE not allowed');
END;

CREATE TRIGGER IF NOT EXISTS trg_capability_history_no_delete
BEFORE DELETE ON soma_intel_capability_history
BEGIN
  SELECT RAISE(ABORT, 'soma_intel_capability_history is append-only: DELETE not allowed');
END;

INSERT INTO schema_version (version, applied_at) VALUES (29, datetime('now'));
