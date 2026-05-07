-- Migration 031: Regime-Shift Bayesian Detector — schema foundation
-- Phase 7 D.3.A — SOMA-INTEL
--
-- Adds two tables:
--   soma_intel_regime_shift_likelihood  — daily likelihood inputs (audit trail)
--   soma_intel_regime_shift_posterior   — daily Bayesian posterior output
--
-- Capability: regime_shift_bayesian (status=disabled until D.3.B backtest passes)
-- Trigger wiring: D.3.C (posterior > 0.40 → P1 alerts). D.3.A only stores values.

-- ── Daily likelihood inputs ───────────────────────────────────────────────────
-- One row per day. All z-score fields are nullable — missing inputs are handled
-- as LLR=0 in bayesian.py (neutral evidence, not absent evidence).

CREATE TABLE IF NOT EXISTS soma_intel_regime_shift_likelihood (
  ts                    TEXT PRIMARY KEY,         -- ISO 8601 date YYYY-MM-DD
  macro_z               REAL,                     -- max(|yield_curve_z|, |vix_term_z|), nullable if no data
  sentiment_z           REAL,                     -- AAII bull-minus-bear z-score, nullable (D.3.A.2 follow-on)
  cross_asset_z         REAL,                     -- correlation breakdown z, nullable
  transcript_drift_z    REAL,                     -- PRISM topic drift z, nullable (D.3.A.2 follow-on)
  computed_ts           TEXT NOT NULL DEFAULT (datetime('now')),
  source_notes          TEXT                      -- JSON: {"macro": "soma_intel_regime.features", ...}
);

-- ── Daily posterior ───────────────────────────────────────────────────────────
-- The primary output. trigger_state is computed and stored here for D.3.B replay
-- (no external triggers fire from D.3.A — that is D.3.C's job).

CREATE TABLE IF NOT EXISTS soma_intel_regime_shift_posterior (
  ts                    TEXT PRIMARY KEY,
  prior                 REAL NOT NULL,            -- 0.024 (daily base rate, locked §D.3)
  log_posterior         REAL NOT NULL,            -- log-odds form (numerical stability)
  posterior             REAL NOT NULL,            -- sigmoid(log_posterior), in [0.0, 1.0]
  llr_macro             REAL NOT NULL DEFAULT 0,  -- log-likelihood-ratio for macro input
  llr_sentiment         REAL NOT NULL DEFAULT 0,  -- log-likelihood-ratio for AAII input
  llr_cross_asset       REAL NOT NULL DEFAULT 0,  -- log-likelihood-ratio for cross-asset input
  llr_transcript        REAL NOT NULL DEFAULT 0,  -- log-likelihood-ratio for transcript input
  trigger_state         TEXT NOT NULL CHECK(trigger_state IN ('none','watch','imminent')),
  missing_inputs        TEXT,                     -- JSON list of input names with no data
  computed_ts           TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (ts) REFERENCES soma_intel_regime_shift_likelihood(ts)
);

CREATE INDEX IF NOT EXISTS idx_rs_posterior_ts
  ON soma_intel_regime_shift_posterior(ts DESC);

CREATE INDEX IF NOT EXISTS idx_rs_posterior_trigger
  ON soma_intel_regime_shift_posterior(trigger_state, ts DESC)
  WHERE trigger_state != 'none';

-- ── Schema version bump ───────────────────────────────────────────────────────
INSERT OR IGNORE INTO schema_version(version, applied_at, description)
  VALUES (31, datetime('now'), 'Regime-shift Bayesian detector — likelihood + posterior tables');
