-- ============================================================
-- Migration 012: RAPTOR Core Tables
-- Module: RAPTOR — Revenue & Asset Prospecting Through
--         Outreach & Relationship-building
-- Stage: ACQUIRE (client acquisition & growth)
-- ============================================================

-- Prospect master record
CREATE TABLE IF NOT EXISTS raptor_prospects (
    prospect_id             TEXT PRIMARY KEY,   -- UUID
    created_date            TEXT NOT NULL,       -- ISO date
    updated_date            TEXT NOT NULL,       -- ISO date
    first_name              TEXT,
    last_name               TEXT,
    display_name            TEXT,
    email                   TEXT,
    phone                   TEXT,
    linkedin_url            TEXT,
    language_pref           TEXT DEFAULT 'FR',  -- FR | EN
    province                TEXT,
    city                    TEXT,
    estimated_assets_band   TEXT,               -- "500K-1M" | "1M-2M" | "2M-5M" | "5M+"
    current_custodian       TEXT,
    source_type             TEXT,               -- "referral"|"event"|"digital"|"coi"|"cold"|"inbound"
    source_detail           TEXT,               -- COI name, event name, etc.
    pipeline_stage          TEXT DEFAULT 'identified',
    lead_score              REAL DEFAULT 0,
    lead_score_updated      TEXT,
    notes                   TEXT,
    write_timestamp         TEXT NOT NULL,
    module_version          TEXT DEFAULT 'RAPTOR-1.0'
);

CREATE INDEX IF NOT EXISTS idx_raptor_prospects_stage
    ON raptor_prospects(pipeline_stage);

CREATE INDEX IF NOT EXISTS idx_raptor_prospects_source
    ON raptor_prospects(source_type);

-- Immutable pipeline transition log
CREATE TABLE IF NOT EXISTS raptor_pipeline_log (
    log_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    prospect_id         TEXT NOT NULL REFERENCES raptor_prospects(prospect_id),
    from_stage          TEXT NOT NULL,
    to_stage            TEXT NOT NULL,
    transition_date     TEXT NOT NULL,          -- ISO datetime
    reason              TEXT,
    transitioned_by     TEXT DEFAULT 'manual',  -- "manual" | "auto"
    write_timestamp     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_raptor_pipeline_log_prospect
    ON raptor_pipeline_log(prospect_id, transition_date);

-- Communication touchpoints
CREATE TABLE IF NOT EXISTS raptor_touchpoints (
    touchpoint_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    prospect_id         TEXT NOT NULL REFERENCES raptor_prospects(prospect_id),
    date                TEXT NOT NULL,          -- ISO datetime
    channel             TEXT NOT NULL,          -- "email"|"phone"|"meeting"|"linkedin"|"event"|"other"
    direction           TEXT NOT NULL,          -- "outbound" | "inbound"
    subject             TEXT,
    content_hash        TEXT,                   -- SHA-256 of content for dedup (NOT full content)
    attachment_refs     TEXT,                   -- JSON array of file paths
    compliance_approved INTEGER DEFAULT 0,      -- BOOLEAN
    approval_timestamp  TEXT,
    approval_principal  TEXT,
    write_timestamp     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_raptor_touchpoints_prospect
    ON raptor_touchpoints(prospect_id, date);

-- Consent ledger — immutable record of consent events
CREATE TABLE IF NOT EXISTS raptor_consent_ledger (
    consent_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    prospect_id             TEXT NOT NULL REFERENCES raptor_prospects(prospect_id),
    consent_type            TEXT NOT NULL,      -- "law25_explicit"|"casl_express"|"casl_implied"
    consent_date            TEXT NOT NULL,
    expiry_date             TEXT,               -- CASL implied = consent_date + 2 years
    consent_method          TEXT,               -- "web_form"|"verbal_recorded"|"email_reply"|"written"
    consent_text_hash       TEXT,               -- SHA-256 of the exact consent language shown
    revoked                 INTEGER DEFAULT 0,  -- BOOLEAN
    revoked_date            TEXT,
    deletion_requested      INTEGER DEFAULT 0,  -- BOOLEAN
    deletion_executed_date  TEXT,
    write_timestamp         TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_raptor_consent_prospect
    ON raptor_consent_ledger(prospect_id, consent_type);

CREATE INDEX IF NOT EXISTS idx_raptor_consent_expiry
    ON raptor_consent_ledger(expiry_date, revoked);

-- Centre of Influence (COI) network
CREATE TABLE IF NOT EXISTS raptor_coi_network (
    coi_id                      TEXT PRIMARY KEY,  -- UUID
    name                        TEXT NOT NULL,
    firm                        TEXT,
    profession                  TEXT,
    email                       TEXT,
    phone                       TEXT,
    linkedin_url                TEXT,
    relationship_start_date     TEXT,
    referral_agreement_signed   INTEGER DEFAULT 0,  -- BOOLEAN
    referral_agreement_date     TEXT,
    referral_agreement_path     TEXT,               -- file path to signed PDF
    reciprocity_given           INTEGER DEFAULT 0,
    reciprocity_received        INTEGER DEFAULT 0,
    notes                       TEXT,
    write_timestamp             TEXT NOT NULL
);

-- Referral linkage: COI → Prospect
CREATE TABLE IF NOT EXISTS raptor_referrals (
    referral_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    coi_id              TEXT NOT NULL REFERENCES raptor_coi_network(coi_id),
    prospect_id         TEXT NOT NULL REFERENCES raptor_prospects(prospect_id),
    referral_date       TEXT NOT NULL,
    disclosure_delivered    INTEGER DEFAULT 0,  -- BOOLEAN
    disclosure_date     TEXT,
    outcome             TEXT DEFAULT 'pending', -- "converted"|"lost"|"pending"
    write_timestamp     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_raptor_referrals_coi
    ON raptor_referrals(coi_id);

CREATE INDEX IF NOT EXISTS idx_raptor_referrals_prospect
    ON raptor_referrals(prospect_id);

-- Track schema version
INSERT INTO schema_version (version, applied_at) VALUES (12, datetime('now'));
