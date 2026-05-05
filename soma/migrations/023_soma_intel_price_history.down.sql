-- Migration 023 DOWN
DROP TABLE IF EXISTS soma_intel_price_history;

DELETE FROM schema_version WHERE version = 23;
