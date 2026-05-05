-- Migration 024: soma_intel_signal_backtest
-- Stores signal snapshots taken during the backtest replay (P5.3.b).
-- Each row mirrors one soma_intel_signal row as observed on sim_date,
-- tagged with the run that produced it.
--
-- Outcome columns (forward_return, direction_label, outcome, scored_ts) are
-- populated later by backtest_outcomes.py (P5.3.c) — initially NULL.
--
-- No-look-ahead guarantee: backtest_runner.py asserts that for every row
-- inserted, all regime/edge rows used have ts <= sim_date (bt_strict_mode).

CREATE TABLE IF NOT EXISTS soma_intel_signal_backtest (
  bt_id                INTEGER PRIMARY KEY AUTOINCREMENT,
  backtest_run_id      TEXT    NOT NULL,  -- e.g. "in_sample_20240506_20260305"
  sim_date             TEXT    NOT NULL,  -- YYYY-MM-DD — the day being replayed

  -- mirror of soma_intel_signal columns (snapshot at sim_date)
  signal_id            INTEGER,           -- original signal_id; NULL for v2 generated signals
  ticker               TEXT    NOT NULL,
  date                 TEXT    NOT NULL,  -- same as sim_date for day-of signals
  priority             TEXT    NOT NULL,
  anomaly_score        REAL    NOT NULL,
  features             TEXT    NOT NULL,  -- JSON, frozen at signal creation
  corroboration_count  INTEGER NOT NULL,
  half_life_days       INTEGER NOT NULL,
  reconfirmation_count INTEGER DEFAULT 0,
  status               TEXT,
  horizon              TEXT,
  notes                TEXT,
  regime_label         TEXT,              -- composite_label from soma_intel_regime on sim_date

  -- no-look-ahead audit
  lookahead_clean      INTEGER DEFAULT 1, -- 1=passed, 0=violation found

  -- outcome columns (populated by backtest_outcomes.py)
  forward_return       REAL,             -- 60-calendar-day fwd return (NULL = unavailable)
  direction_label      TEXT,             -- long|short|absolute
  outcome              TEXT,             -- hit|miss|data_unavailable
  scored_ts            TEXT              -- ISO 8601 when outcome was scored
);

CREATE INDEX IF NOT EXISTS idx_bt_run_date
  ON soma_intel_signal_backtest(backtest_run_id, sim_date);

CREATE INDEX IF NOT EXISTS idx_bt_ticker_date
  ON soma_intel_signal_backtest(ticker, sim_date);

CREATE INDEX IF NOT EXISTS idx_bt_priority_outcome
  ON soma_intel_signal_backtest(priority, outcome);

CREATE INDEX IF NOT EXISTS idx_bt_outcome
  ON soma_intel_signal_backtest(outcome)
  WHERE outcome IS NOT NULL;

INSERT INTO schema_version (version, applied_at) VALUES (24, datetime('now'));
