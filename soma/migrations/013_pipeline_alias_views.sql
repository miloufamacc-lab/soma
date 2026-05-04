-- Migration 013: Pipeline Alias Views
-- Phase 3 of the alias layer consolidation (April 5, 2026)
--
-- Creates convenience views that expose pipeline names for human-readable querying.
-- NOTE: SQLite cannot call Python functions from SQL, so these views use the
-- internal_id as-is. The Python layer (soma_bridge.py) translates to display names.
-- These views exist primarily for:
--   1. Direct SQL querying (e.g., from CLI or debugging)
--   2. Standardizing column names across tables that reference pipelines
--   3. Future-proofing: if we add a pipeline_names table, views get updated not callers
--
-- IMPORTANT: The raw tables are NEVER renamed. Internal IDs (TITAN, COBALT, etc.)
-- remain stable in the database forever. Display names are a presentation concern
-- handled by pipeline_registry.py → soma_bridge.py.

-- View: raw intelligence with standardized pipeline column aliases
DROP VIEW IF EXISTS v_raw_intelligence;
CREATE VIEW v_raw_intelligence AS
SELECT
    id,
    source_type,
    source_url,
    title,
    content,
    category,
    target_pipeline AS pipeline_id,
    target_pipeline AS pipeline_name,  -- same for now; Python layer translates
    relevance_score,
    key_claims_json,
    tags_json,
    file_origin,
    ingested_at,
    processed,
    consumed_by AS consumed_by_id,
    consumed_by AS consumed_by_name,   -- same for now; Python layer translates
    consumed_at,
    write_timestamp,
    module_version
FROM raw_intelligence;

-- View: philosophy evidence with standardized source references
DROP VIEW IF EXISTS v_philosophy_evidence;
CREATE VIEW v_philosophy_evidence AS
SELECT
    id,
    belief_id,
    source_module AS source_id,
    source_module AS source_name,      -- same for now; Python layer translates
    source_detail,
    supports,
    weight,
    run_id,
    date_logged,
    write_timestamp,
    module_version
FROM philosophy_evidence;

-- View: KB violations with standardized module references
DROP VIEW IF EXISTS v_kb_violations;
CREATE VIEW v_kb_violations AS
SELECT
    id,
    severity,
    rule_id,
    source_module AS module_id,
    source_module AS module_name,      -- same for now; Python layer translates
    write_type,
    description,
    context_json,
    detected_at,
    resolved,
    resolved_at,
    resolution_note
FROM kb_violations;

-- Update schema version
INSERT INTO schema_version (version, applied_at, description)
VALUES (13, datetime('now'), 'Pipeline alias views for display name abstraction');
