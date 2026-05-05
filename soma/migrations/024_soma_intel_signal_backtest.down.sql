-- Migration 024 DOWN
DROP TABLE IF EXISTS soma_intel_signal_backtest;

DELETE FROM schema_version WHERE version = 24;
