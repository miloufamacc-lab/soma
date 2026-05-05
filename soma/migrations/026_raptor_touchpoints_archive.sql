-- ============================================================
-- Migration 026: RAPTOR Touchpoints Archive (CIRO Rule 3804)
-- 7-year immutable retention via SQLite triggers.
-- Every INSERT / UPDATE / DELETE on raptor_touchpoints is
-- shadow-copied here. The archive itself is locked — UPDATE
-- and DELETE are blocked by triggers.
-- ============================================================

CREATE TABLE IF NOT EXISTS raptor_touchpoints_archive (
    archive_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    operation           TEXT NOT NULL,      -- 'INSERT' | 'UPDATE' | 'DELETE'
    archived_at         TEXT NOT NULL,      -- ISO datetime (UTC)
    touchpoint_id       INTEGER,
    prospect_id         TEXT,
    date                TEXT,
    channel             TEXT,
    direction           TEXT,
    subject             TEXT,
    content_hash        TEXT,
    attachment_refs     TEXT,
    compliance_approved INTEGER,
    approval_timestamp  TEXT,
    approval_principal  TEXT,
    write_timestamp     TEXT
);

CREATE INDEX IF NOT EXISTS idx_raptor_archive_prospect
    ON raptor_touchpoints_archive(prospect_id, archived_at);

CREATE INDEX IF NOT EXISTS idx_raptor_archive_touchpoint
    ON raptor_touchpoints_archive(touchpoint_id);

-- ── Capture triggers ────────────────────────────────────────
CREATE TRIGGER IF NOT EXISTS trg_touchpoints_archive_insert
AFTER INSERT ON raptor_touchpoints
BEGIN
    INSERT INTO raptor_touchpoints_archive (
        operation, archived_at,
        touchpoint_id, prospect_id, date, channel, direction,
        subject, content_hash, attachment_refs,
        compliance_approved, approval_timestamp, approval_principal,
        write_timestamp
    ) VALUES (
        'INSERT', datetime('now'),
        NEW.touchpoint_id, NEW.prospect_id, NEW.date, NEW.channel, NEW.direction,
        NEW.subject, NEW.content_hash, NEW.attachment_refs,
        NEW.compliance_approved, NEW.approval_timestamp, NEW.approval_principal,
        NEW.write_timestamp
    );
END;

CREATE TRIGGER IF NOT EXISTS trg_touchpoints_archive_update
AFTER UPDATE ON raptor_touchpoints
BEGIN
    INSERT INTO raptor_touchpoints_archive (
        operation, archived_at,
        touchpoint_id, prospect_id, date, channel, direction,
        subject, content_hash, attachment_refs,
        compliance_approved, approval_timestamp, approval_principal,
        write_timestamp
    ) VALUES (
        'UPDATE', datetime('now'),
        NEW.touchpoint_id, NEW.prospect_id, NEW.date, NEW.channel, NEW.direction,
        NEW.subject, NEW.content_hash, NEW.attachment_refs,
        NEW.compliance_approved, NEW.approval_timestamp, NEW.approval_principal,
        NEW.write_timestamp
    );
END;

CREATE TRIGGER IF NOT EXISTS trg_touchpoints_archive_delete
AFTER DELETE ON raptor_touchpoints
BEGIN
    INSERT INTO raptor_touchpoints_archive (
        operation, archived_at,
        touchpoint_id, prospect_id, date, channel, direction,
        subject, content_hash, attachment_refs,
        compliance_approved, approval_timestamp, approval_principal,
        write_timestamp
    ) VALUES (
        'DELETE', datetime('now'),
        OLD.touchpoint_id, OLD.prospect_id, OLD.date, OLD.channel, OLD.direction,
        OLD.subject, OLD.content_hash, OLD.attachment_refs,
        OLD.compliance_approved, OLD.approval_timestamp, OLD.approval_principal,
        OLD.write_timestamp
    );
END;

-- ── Immutability guards (CIRO Rule 3804) ────────────────────
CREATE TRIGGER IF NOT EXISTS trg_archive_no_update
BEFORE UPDATE ON raptor_touchpoints_archive
BEGIN
    SELECT RAISE(ABORT, 'raptor_touchpoints_archive is immutable (CIRO Rule 3804 — 7-year retention)');
END;

CREATE TRIGGER IF NOT EXISTS trg_archive_no_delete
BEFORE DELETE ON raptor_touchpoints_archive
BEGIN
    SELECT RAISE(ABORT, 'raptor_touchpoints_archive is immutable (CIRO Rule 3804 — 7-year retention)');
END;

INSERT INTO schema_version (version, applied_at, description)
VALUES (26, datetime('now'), 'RAPTOR touchpoints archive + immutability triggers');
