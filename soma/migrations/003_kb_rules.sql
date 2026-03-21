-- Migration 003: KB rules index + audit log (Phase 2.3b)

CREATE TABLE IF NOT EXISTS kb_rules (
    rule_id         TEXT PRIMARY KEY,
    source_file     TEXT NOT NULL,
    source_module   TEXT,              -- comma-separated: "ORACLE,MANTIS"
    rule_data       TEXT NOT NULL,     -- JSON of the YAML rule block
    confidence      REAL DEFAULT 1.0,
    file_hash       TEXT,              -- MD5 of source file at parse time
    parsed_at       TEXT NOT NULL,     -- ISO-8601
    schema_version  INTEGER DEFAULT 3
);

CREATE TABLE IF NOT EXISTS kb_audit_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id         TEXT NOT NULL,
    read_by_module  TEXT NOT NULL,     -- ORACLE, CIPHER, MANTIS
    read_at         TEXT NOT NULL,     -- ISO-8601
    run_id          TEXT,              -- links to SOMA run_id
    decision_context TEXT,             -- JSON: what triggered the read
    write_timestamp TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_rule ON kb_audit_log(rule_id);
CREATE INDEX IF NOT EXISTS idx_audit_module ON kb_audit_log(read_by_module);

INSERT OR IGNORE INTO schema_version (version, applied_at, description)
VALUES (3, datetime('now'), 'KB rules index + audit log (Phase 2.3b)');
