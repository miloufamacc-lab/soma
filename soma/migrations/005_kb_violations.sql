-- Schema v4: KB Violations — inline validation audit trail
-- Every SOMA write is checked against KB rules. Violations are logged here.

CREATE TABLE IF NOT EXISTS kb_violations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    severity        TEXT NOT NULL,          -- INFO, WARNING, CRITICAL
    rule_id         TEXT NOT NULL,          -- KB rule that was violated
    source_module   TEXT NOT NULL,          -- ORACLE, MANTIS, CIPHER
    write_type      TEXT NOT NULL,          -- regime, valuation, portfolio, trade
    description     TEXT NOT NULL,          -- Human-readable violation description
    context_json    TEXT,                   -- JSON blob with violation details
    detected_at     TEXT NOT NULL,          -- UTC ISO timestamp
    resolved        INTEGER DEFAULT 0,     -- 0 = open, 1 = acknowledged
    resolved_at     TEXT,                   -- When it was resolved
    resolution_note TEXT                    -- How it was resolved
);

CREATE INDEX IF NOT EXISTS idx_kbv_severity ON kb_violations(severity);
CREATE INDEX IF NOT EXISTS idx_kbv_module ON kb_violations(source_module);
CREATE INDEX IF NOT EXISTS idx_kbv_detected ON kb_violations(detected_at);

INSERT OR IGNORE INTO schema_version (version, applied_at, description)
VALUES (5, datetime('now'), 'KB violations — inline validation audit trail');
