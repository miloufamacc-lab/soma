-- ════════════════════════════════════════════════════════════════════════════
-- Migration 022 — SOMA-INTEL: Audit Log + Source Calibration
-- Spec: OPUS_DELIVERABLES.md §K.2 + §K.3
-- Additive-only. Does NOT modify any existing table.
-- ════════════════════════════════════════════════════════════════════════════

-- ── 1. Append-only audit log (§K.2) ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS soma_intel_audit_log (
    audit_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    edge_id       INTEGER NOT NULL,
    auditor       TEXT    NOT NULL,              -- 'user' | 'claude_adversarial' | 'meta_learner'
    decision      TEXT    NOT NULL,              -- 'approved' | 'rejected' | 'corrected' | 're_audited'
    rationale     TEXT,
    ts            TEXT    NOT NULL,
    prior_audit_id INTEGER,
    FOREIGN KEY (edge_id)        REFERENCES soma_intel_edge(edge_id),
    FOREIGN KEY (prior_audit_id) REFERENCES soma_intel_audit_log(audit_id)
);

CREATE INDEX IF NOT EXISTS idx_audit_edge
    ON soma_intel_audit_log(edge_id, ts DESC);

-- Immutability triggers: any UPDATE or DELETE raises immediately.
CREATE TRIGGER IF NOT EXISTS soma_intel_audit_log_no_update
    BEFORE UPDATE ON soma_intel_audit_log
    BEGIN
        SELECT RAISE(ABORT, 'soma_intel_audit_log is append-only');
    END;

CREATE TRIGGER IF NOT EXISTS soma_intel_audit_log_no_delete
    BEFORE DELETE ON soma_intel_audit_log
    BEGIN
        SELECT RAISE(ABORT, 'soma_intel_audit_log is append-only');
    END;

-- ── 2. Source calibration table (§K.3) ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS soma_intel_source_calibration (
    source_id      TEXT PRIMARY KEY,
    multiplier     REAL    NOT NULL DEFAULT 1.0 CHECK(multiplier > 0),
    brier_score    REAL,
    n_observations INTEGER NOT NULL DEFAULT 0,
    last_updated   TEXT    NOT NULL
);

-- ── 3. Schema version ────────────────────────────────────────────────────────
INSERT INTO schema_version (version, applied_at)
VALUES (22, datetime('now'));
