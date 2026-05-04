-- 016_backtest_summary.sql — Phase 4.5
-- Dedicated summary table so backtest metrics stop being packed into trade_log.reason.

CREATE TABLE IF NOT EXISTS backtest_summary (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    date            TEXT NOT NULL,
    run_label       TEXT NOT NULL,
    total_return    REAL,
    sharpe_ratio    REAL,
    max_dd          REAL,
    years           REAL,
    final_equity    REAL,
    metrics_json    TEXT,
    config_json     TEXT,
    write_timestamp TEXT NOT NULL,
    module_version  TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_backtest_summary_date_label
    ON backtest_summary(date, run_label);

CREATE INDEX IF NOT EXISTS idx_backtest_summary_date
    ON backtest_summary(date);
