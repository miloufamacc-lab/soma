-- Migration 010: COBALT — Chain Observation & Blockchain Analytics for Tactical Leverage
-- Pipeline: ORACLE/COBALT | Module: ORACLE
-- On-chain intelligence: BTC/SOL metrics, composite signals, exchange flows

-- Individual metric readings (MVRV, NUPL, SOPR, exchange flows, etc.)
CREATE TABLE IF NOT EXISTS onchain_metrics (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    date            TEXT NOT NULL,
    run_id          TEXT,                    -- links to ORACLE run if triggered by run_day
    asset           TEXT NOT NULL,           -- 'BTC', 'SOL', 'ETH'
    metric          TEXT NOT NULL,           -- 'mvrv_zscore', 'nupl', 'sopr', 'exchange_flow', 'lth_supply', 'price', 'market_cap', 'tvl'
    value           REAL,
    source          TEXT NOT NULL,           -- 'coingecko', 'mempool', 'defillama', 'blockchain_com', 'derived'
    freshness_hours REAL,                    -- how old this data point is (for staleness checks)
    write_timestamp TEXT DEFAULT (datetime('now')),
    module_version  TEXT
);

-- Composite signal per asset (aggregated from individual metrics)
CREATE TABLE IF NOT EXISTS onchain_signals (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    date              TEXT NOT NULL,
    run_id            TEXT,
    asset             TEXT NOT NULL,          -- 'BTC', 'SOL'
    signal_direction  TEXT NOT NULL,          -- 'BULL', 'BEAR', 'NEUTRAL'
    composite_score   REAL,                   -- 0.0-1.0 (0=max bear, 1=max bull)
    confidence        REAL,                   -- 0.0-1.0 (how many metrics available)
    components_json   TEXT,                   -- JSON: {"mvrv": 0.7, "nupl": 0.6, ...}
    regime_at_time    TEXT,                   -- SOMA regime when signal was generated
    write_timestamp   TEXT DEFAULT (datetime('now')),
    module_version    TEXT
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_om_asset_date ON onchain_metrics(asset, date);
CREATE INDEX IF NOT EXISTS idx_om_metric ON onchain_metrics(metric);
CREATE INDEX IF NOT EXISTS idx_om_run ON onchain_metrics(run_id);
CREATE INDEX IF NOT EXISTS idx_os_asset_date ON onchain_signals(asset, date);
CREATE INDEX IF NOT EXISTS idx_os_direction ON onchain_signals(signal_direction);

-- Track schema version
INSERT INTO schema_version (version, applied_at) VALUES (10, datetime('now'));
