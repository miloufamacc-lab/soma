-- SOMA Migration 004: Client Profiles (Phase 2.3 — Client Alpha Layer)
--
-- Per-client investment thesis profiles: NOT personal data.
-- Profiles the advisor's own thinking patterns per client:
--   - positioning bias (conservative vs. aggressive)
--   - macro sensitivity tendencies
--   - sector conviction patterns
--   - communication style preference
--   - CFA framework compatibility (money_script, behavioral biases)
--
-- Used by CIPHER's prompt engine to personalize outputs (ADViCE, WIIFT, PRACTICE).
-- Data flows freely — no compliance or consent workflows required.

CREATE TABLE IF NOT EXISTS client_profiles (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Identity (advisor's label, not PII)
    client_alias            TEXT NOT NULL UNIQUE,          -- e.g. "JSmith", "ClientA" — advisor's shorthand
    display_name            TEXT,                          -- e.g. "John S." — for report headers

    -- Investment Thesis Positioning
    positioning             TEXT DEFAULT 'moderate',       -- conservative / moderate / aggressive / opportunistic
    risk_tolerance          TEXT DEFAULT 'medium',         -- low / medium / high / very_high
    time_horizon            TEXT DEFAULT 'medium',         -- short (<2y) / medium (2-7y) / long (7y+)
    wealth_level            TEXT,                          -- hnw / uhnw / mass_affluent / retail

    -- Macro Bias Tendencies (how this client typically reacts)
    macro_bias              TEXT DEFAULT 'neutral',        -- bullish / neutral / cautious / contrarian
    regime_sensitivity      TEXT DEFAULT 'moderate',       -- low / moderate / high
    -- "high" = panics in CONTRACTION, needs proactive outreach
    -- "low"  = stays the course, minimal hand-holding needed

    -- Sector Conviction Patterns (JSON array of sectors + conviction level)
    sector_convictions_json TEXT,                          -- e.g. [{"sector":"tech","conviction":"high"},{"sector":"energy","conviction":"low"}]

    -- Communication Style
    communication_style     TEXT DEFAULT 'formal',         -- formal / conversational / data_heavy / brief
    preferred_frequency     TEXT DEFAULT 'quarterly',      -- weekly / biweekly / monthly / quarterly / ad_hoc
    preferred_channel       TEXT DEFAULT 'email',          -- email / call / in_person / video

    -- CFA Framework Compatibility (feeds directly into CIPHER)
    money_script            TEXT,                          -- vigilance / avoidance / worship / status (Klontz)
    primary_goal            TEXT,                          -- e.g. "retirement income", "wealth accumulation", "capital preservation"
    known_biases_json       TEXT,                          -- e.g. ["recency_bias", "loss_aversion", "home_bias"]

    -- Relationship Tracking
    last_contact_date       TEXT,                          -- YYYY-MM-DD
    last_contact_type       TEXT,                          -- email / call / meeting
    next_review_date        TEXT,                          -- YYYY-MM-DD
    notes                   TEXT,                          -- freeform advisor notes

    -- Metadata (standard SOMA pattern)
    created_at              TEXT NOT NULL,                 -- ISO-8601
    updated_at              TEXT NOT NULL,                 -- ISO-8601
    write_timestamp         TEXT NOT NULL,                 -- ISO-8601 (for is_fresh() compatibility)
    module_version          TEXT
);

-- Index for fast lookups
CREATE INDEX IF NOT EXISTS idx_client_alias ON client_profiles(client_alias);
CREATE INDEX IF NOT EXISTS idx_next_review ON client_profiles(next_review_date);

-- Interaction log: tracks every contact for pattern analysis
CREATE TABLE IF NOT EXISTS client_interactions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    client_alias        TEXT NOT NULL,                     -- FK to client_profiles.client_alias
    date                TEXT NOT NULL,                     -- YYYY-MM-DD
    interaction_type    TEXT NOT NULL,                     -- email / call / meeting / report_sent
    topic               TEXT,                              -- e.g. "quarterly review", "market volatility", "portfolio rebalance"
    regime_at_time      TEXT,                              -- regime snapshot at time of contact
    notes               TEXT,
    write_timestamp     TEXT NOT NULL,
    module_version      TEXT
);

CREATE INDEX IF NOT EXISTS idx_interaction_client ON client_interactions(client_alias);
CREATE INDEX IF NOT EXISTS idx_interaction_date ON client_interactions(date);

-- Update schema version
INSERT OR IGNORE INTO schema_version (version, applied_at, description)
VALUES (4, datetime('now'), 'Client profiles + interaction log (Phase 2.3)');
