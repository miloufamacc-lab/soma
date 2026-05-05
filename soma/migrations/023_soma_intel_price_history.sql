-- Migration 023: soma_intel_price_history
-- Stores daily closing prices for universe tickers to support backtest harness (P5.3).
-- Source: loaded via backtest_prices.py (oracle/cache price series → or optional yfinance).
-- Primary key: (ticker, date) — idempotent upsert pattern.

CREATE TABLE IF NOT EXISTS soma_intel_price_history (
  ticker  TEXT    NOT NULL,
  date    TEXT    NOT NULL,     -- ISO 8601 (YYYY-MM-DD)
  close   REAL    NOT NULL,
  volume  REAL,                 -- NULL if unavailable
  PRIMARY KEY (ticker, date)
);

CREATE INDEX IF NOT EXISTS idx_price_ticker_date
  ON soma_intel_price_history(ticker, date DESC);

INSERT INTO schema_version (version, applied_at) VALUES (23, datetime('now'));
