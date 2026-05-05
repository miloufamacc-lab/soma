-- ============================================================
-- Migration 027: RAPTOR CRM3 Fund MER Reference Table
-- Fee drag comparison engine for value proposition analysis.
-- Seeded with common Canadian fund families via seed_fund_mers().
-- ============================================================

CREATE TABLE IF NOT EXISTS raptor_fund_mers (
    fund_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker          TEXT,                   -- e.g. "XIC", "RBF556"
    fund_name       TEXT NOT NULL,
    mer             REAL NOT NULL,          -- % annual, e.g. 2.35 = 2.35%
    ter             REAL,                   -- Total expense ratio (if available)
    fund_family     TEXT,                   -- e.g. "RBC", "iShares", "TD"
    fund_type       TEXT DEFAULT 'mutual_fund',  -- 'mutual_fund' | 'etf' | 'segregated'
    currency        TEXT DEFAULT 'CAD',
    notes           TEXT,
    write_timestamp TEXT
);

-- Full UNIQUE index (no WHERE) required for ON CONFLICT(ticker) upsert.
-- SQLite treats each NULL as distinct so multiple NULL-ticker rows are allowed.
CREATE UNIQUE INDEX IF NOT EXISTS idx_fund_mers_ticker
    ON raptor_fund_mers(ticker);

CREATE INDEX IF NOT EXISTS idx_fund_mers_family
    ON raptor_fund_mers(fund_family);

INSERT INTO schema_version (version, applied_at, description)
VALUES (27, datetime('now'), 'RAPTOR CRM3 fund MER reference table');
