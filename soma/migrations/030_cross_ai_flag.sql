-- Migration 030 -- soma_intel_cross_ai_flag + cross_ai_corroboration capability
-- Phase 7.I1.2 -- Dedicated table for Grok / Gemini / Phi-4 corroboration flags.
-- Flags ingest into this table first (canonical record with decay + supersedure),
-- then project into soma_intel_edge (source_type = ai_source + '_insight') so the
-- existing count_corroborations() gate counts them via _CORROBORATION_SOURCES.
-- Created: 2026-05-05

CREATE TABLE IF NOT EXISTS soma_intel_cross_ai_flag (
  flag_id        INTEGER PRIMARY KEY AUTOINCREMENT,
  ai_source      TEXT    NOT NULL CHECK(ai_source IN ('grok','gemini','phi4')),
  ticker         TEXT    NOT NULL,
  signal_type    TEXT    NOT NULL,           -- maps to anomaly type / horizon, free-form v1
  direction      TEXT    NOT NULL CHECK(direction IN ('bullish','bearish','neutral')),
  confidence     REAL    NOT NULL CHECK(confidence BETWEEN 0 AND 1),
  ts             TEXT    NOT NULL,            -- ISO 8601 when AI produced the flag
  evidence_text  TEXT,                        -- <= 500 chars
  source_path    TEXT    NOT NULL,            -- file path or URI where AI output was sourced
  ingested_ts    TEXT    NOT NULL DEFAULT (datetime('now')),
  half_life_days INTEGER NOT NULL DEFAULT 14, -- short: AI flags age fast
  superseded_by  INTEGER,
  FOREIGN KEY (superseded_by) REFERENCES soma_intel_cross_ai_flag(flag_id)
);

CREATE INDEX IF NOT EXISTS idx_caf_ticker_ts
  ON soma_intel_cross_ai_flag(ticker, ts DESC);

CREATE INDEX IF NOT EXISTS idx_caf_source_ts
  ON soma_intel_cross_ai_flag(ai_source, ts DESC);

CREATE INDEX IF NOT EXISTS idx_caf_active
  ON soma_intel_cross_ai_flag(ticker, signal_type, superseded_by)
  WHERE superseded_by IS NULL;

-- ── Capability registration ────────────────────────────────────────────────────
-- Ships DISABLED by default. User enables manually after reviewing test results.
-- depends_on: confirm_gate + signal_engine must be enabled first.

INSERT OR IGNORE INTO soma_intel_capability
  (capability_id, status, enabled_ts, version, depends_on)
VALUES
  ('cross_ai_corroboration', 'disabled', NULL, '1.0',
   '["confirm_gate","signal_engine"]');

INSERT INTO schema_version (version, applied_at) VALUES (30, datetime('now'));
