-- Down migration 021: Remove all SOMA-INTEL tables
-- WARNING: destructive — drops all graph, signal, and forecast data.
-- Run only to roll back migration 021.

DROP TRIGGER IF EXISTS soma_intel_node_fts_au;
DROP TRIGGER IF EXISTS soma_intel_node_fts_ai;
DROP TABLE IF EXISTS soma_intel_node_fts;
DROP TABLE IF EXISTS soma_intel_baseline;
DROP TABLE IF EXISTS soma_intel_universe;
DROP TABLE IF EXISTS soma_intel_scurve_history;
DROP TABLE IF EXISTS soma_intel_platform;
DROP TABLE IF EXISTS soma_intel_signal;
DROP TABLE IF EXISTS soma_intel_regime;
DROP TABLE IF EXISTS soma_intel_belief;
DROP TABLE IF EXISTS soma_intel_edge;
DROP TABLE IF EXISTS soma_intel_node;

-- Revert schema version
DELETE FROM schema_version WHERE version = 21;
