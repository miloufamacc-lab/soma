-- ============================================================
-- Migration 028: RAPTOR 90-Day Onboarding Milestones
-- Tracks Day 7/30/60/90 touchpoints for onboarding prospects.
-- Completed Day 90 triggers handoff to CIPHER client_profiles.
-- ============================================================

CREATE TABLE IF NOT EXISTS raptor_onboarding_milestones (
    milestone_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    prospect_id     TEXT NOT NULL REFERENCES raptor_prospects(prospect_id),
    milestone       TEXT NOT NULL,  -- 'day_7' | 'day_30' | 'day_60' | 'day_90'
    due_date        TEXT NOT NULL,  -- ISO date (onboarding_start + N days)
    completed_date  TEXT,           -- ISO date when marked complete; NULL = pending
    notes           TEXT,
    write_timestamp TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_raptor_onboarding_prospect
    ON raptor_onboarding_milestones(prospect_id, milestone);

CREATE INDEX IF NOT EXISTS idx_raptor_onboarding_due
    ON raptor_onboarding_milestones(due_date, completed_date);

INSERT INTO schema_version (version, applied_at, description)
VALUES (28, datetime('now'), 'RAPTOR 90-day onboarding milestone table');
