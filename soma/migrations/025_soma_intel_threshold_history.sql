-- Migration 025 — soma_intel_threshold_history
-- Meta-learner per-cell threshold adjustment log (append-only).
-- Created: 2026-05-05 (SOMA-INTEL Phase 6)

CREATE TABLE IF NOT EXISTS soma_intel_threshold_history (
  history_id     INTEGER PRIMARY KEY AUTOINCREMENT,
  cell_key       TEXT    NOT NULL,     -- "<regime>|<sector>|<feature>"
  prior_threshold REAL   NOT NULL,
  new_threshold  REAL    NOT NULL,
  adjustment     REAL    NOT NULL,     -- +0.1 or -0.1
  reason         TEXT    NOT NULL,     -- "false_negatives:5" | "false_positives:7" | etc.
  applied_ts     TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_threshold_cell
    ON soma_intel_threshold_history(cell_key, applied_ts DESC);

-- Append-only triggers: prevent UPDATE and DELETE on this table.
CREATE TRIGGER IF NOT EXISTS trg_threshold_history_no_update
BEFORE UPDATE ON soma_intel_threshold_history
BEGIN
  SELECT RAISE(ABORT, 'soma_intel_threshold_history is append-only: UPDATE not allowed');
END;

CREATE TRIGGER IF NOT EXISTS trg_threshold_history_no_delete
BEFORE DELETE ON soma_intel_threshold_history
BEGIN
  SELECT RAISE(ABORT, 'soma_intel_threshold_history is append-only: DELETE not allowed');
END;

INSERT INTO schema_version (version, applied_at) VALUES (25, datetime('now'));
