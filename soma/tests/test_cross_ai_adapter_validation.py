"""
SOMA-INTEL Phase 7.I1V — Cross-AI Adapter Validation Tests

Tests validate_grok / validate_gemini / validate_phi4 against synthetic fixtures,
and test ingest_grok / ingest_gemini / ingest_phi4 against in-memory DBs.

No live DB writes. No external API calls. All fixtures under:
    shared/soma/tests/fixtures/cross_ai/

Acceptance criteria (I1V.5):
  1. test_validate_grok_fixture          — parses fixture, returns valid=True, 3 flags
  2. test_validate_gemini_fixture        — parses fixture, returns valid=True, 2 flags
  3. test_validate_phi4_fixture          — parses fixture, returns valid=True, 2 flags, calibration applied
  4. test_validate_grok_missing_field    — missing 'source' → valid=False, error reported
  5. test_validate_gemini_bad_direction  — invalid direction → flag skipped, valid=False
  6. test_validate_phi4_low_confidence   — conf * 0.85 < 0.40 → skipped
  7. test_ingest_grok_fixture_dry_run    — ingest with dry_run=True → 0 DB writes
  8. test_ingest_idempotency             — second ingest on same file → flags_inserted=0
  9. test_ingest_capability_gate         — capability disabled → 0 DB writes
 10. test_validate_grok_empty_flags      — flags:[] → valid=True, 0 flags (empty is not an error)
 11. test_validate_phi4_bad_json_line    — one malformed JSONL line → errors reported, partial result
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

# ── Path bootstrap ─────────────────────────────────────────────────────────────
_HERE         = Path(__file__).resolve().parent
_DABEIBA_ROOT = _HERE.parent.parent.parent
for _p in [str(_DABEIBA_ROOT), str(_DABEIBA_ROOT / "shared")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from soma.intel.store import IntelStore
from soma.intel.cross_ai.grok_adapter   import validate_grok,   ingest_grok
from soma.intel.cross_ai.gemini_adapter import validate_gemini, ingest_gemini
from soma.intel.cross_ai.phi4_adapter   import validate_phi4,   ingest_phi4

import soma.intel.cross_ai.gemini_adapter as _gem_mod
import soma.intel.cross_ai.phi4_adapter   as _phi4_mod

# ── Fixture paths ──────────────────────────────────────────────────────────────
_FIXTURES = _HERE / "fixtures" / "cross_ai"
_GROK_FIXTURE    = _FIXTURES / "grok_flags_2026-05-03.json"
_GEMINI_FIXTURE  = _FIXTURES / "gemini_flags_2026-05-03.json"
_PHI4_FIXTURE    = _FIXTURES / "phi4_flags_2026-05-03.jsonl"

# ── DB DDL for in-memory test stores ──────────────────────────────────────────
_CROSS_AI_DDL = """
CREATE TABLE IF NOT EXISTS soma_intel_cross_ai_flag (
  flag_id        INTEGER PRIMARY KEY AUTOINCREMENT,
  ai_source      TEXT    NOT NULL CHECK(ai_source IN ('grok','gemini','phi4')),
  ticker         TEXT    NOT NULL,
  signal_type    TEXT    NOT NULL,
  direction      TEXT    NOT NULL CHECK(direction IN ('bullish','bearish','neutral')),
  confidence     REAL    NOT NULL CHECK(confidence BETWEEN 0 AND 1),
  ts             TEXT    NOT NULL,
  evidence_text  TEXT,
  source_path    TEXT    NOT NULL,
  ingested_ts    TEXT    NOT NULL DEFAULT (datetime('now')),
  half_life_days INTEGER NOT NULL DEFAULT 14,
  superseded_by  INTEGER,
  FOREIGN KEY (superseded_by) REFERENCES soma_intel_cross_ai_flag(flag_id)
);
CREATE INDEX IF NOT EXISTS idx_caf_ticker_ts   ON soma_intel_cross_ai_flag(ticker, ts DESC);
CREATE INDEX IF NOT EXISTS idx_caf_source_ts   ON soma_intel_cross_ai_flag(ai_source, ts DESC);
CREATE INDEX IF NOT EXISTS idx_caf_active      ON soma_intel_cross_ai_flag(ticker, signal_type, superseded_by)
  WHERE superseded_by IS NULL;
"""

_EXTRA_DDL = """
CREATE TABLE IF NOT EXISTS soma_intel_source_calibration (
  source_id TEXT PRIMARY KEY, multiplier REAL NOT NULL,
  brier_score REAL, n_observations INTEGER NOT NULL DEFAULT 0, last_updated TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS soma_intel_threshold_history (
  history_id INTEGER PRIMARY KEY AUTOINCREMENT,
  cell_key TEXT NOT NULL, prior_threshold REAL NOT NULL, new_threshold REAL NOT NULL,
  adjustment REAL NOT NULL, reason TEXT NOT NULL, applied_ts TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS soma_intel_signal_backtest (
  bt_id INTEGER PRIMARY KEY AUTOINCREMENT, backtest_run_id TEXT NOT NULL,
  sim_date TEXT NOT NULL, signal_id INTEGER, ticker TEXT NOT NULL, date TEXT NOT NULL,
  priority TEXT NOT NULL, anomaly_score REAL NOT NULL, features TEXT,
  corroboration_count INTEGER, half_life_days INTEGER,
  reconfirmation_count INTEGER DEFAULT 0, status TEXT DEFAULT 'active',
  horizon TEXT, notes TEXT, regime_label TEXT, lookahead_clean INTEGER DEFAULT 1,
  forward_return REAL, direction_label TEXT,
  outcome TEXT CHECK(outcome IN ('hit','miss','data_unavailable')), scored_ts TEXT
);
CREATE TABLE IF NOT EXISTS soma_intel_regime (
  date TEXT PRIMARY KEY, trend_state TEXT, vol_state TEXT,
  macro_state TEXT, composite_label TEXT, confidence REAL, features TEXT
);
CREATE TABLE IF NOT EXISTS soma_intel_signal (
  signal_id INTEGER PRIMARY KEY AUTOINCREMENT, ticker TEXT NOT NULL, date TEXT NOT NULL,
  priority TEXT NOT NULL, anomaly_score REAL NOT NULL, features TEXT NOT NULL,
  corroboration_count INTEGER NOT NULL, half_life_days INTEGER NOT NULL,
  reconfirmation_count INTEGER DEFAULT 0, status TEXT DEFAULT 'active', horizon TEXT, notes TEXT
);
CREATE TABLE IF NOT EXISTS soma_intel_universe (
  ticker TEXT PRIMARY KEY, active INTEGER DEFAULT 1, source TEXT, platform_tags TEXT,
  added_ts TEXT, tier TEXT, auto_added INTEGER DEFAULT 1, promotion_score REAL, promotion_source TEXT
);
"""


def _make_store(tmp_path: Path) -> IntelStore:
    db = tmp_path / "test_i1v.db"
    store = IntelStore(db_path=str(db))
    store.__enter__()
    store.initialize_tables()
    for ddl in (_CROSS_AI_DDL, _EXTRA_DDL):
        store._c.executescript(ddl)
    store._c.commit()
    return store


def _enable_cap(store: IntelStore) -> None:
    store.register_capability(
        capability_id="cross_ai_corroboration",
        version="1.0",
        status="enabled",
        depends_on=["confirm_gate", "signal_engine"],
    )
    store.commit()


def _disable_cap(store: IntelStore) -> None:
    try:
        store.set_capability_status(
            "cross_ai_corroboration", "disabled", notes="test teardown"
        )
    except ValueError:
        store.register_capability(
            capability_id="cross_ai_corroboration",
            version="1.0",
            status="disabled",
            depends_on=["confirm_gate", "signal_engine"],
        )
    store.commit()


# ── 1. validate_grok — happy path ─────────────────────────────────────────────

def test_validate_grok_fixture():
    """validate_grok parses fixture correctly: valid=True, 3 flags."""
    r = validate_grok(str(_GROK_FIXTURE))
    assert r["valid"] is True
    assert r["flags_found"] == 3
    assert r["flags_valid"] == 3
    assert r["flags_skipped"] == 0
    assert r["errors"] == []
    tickers = [f["ticker"] for f in r["flags"]]
    assert all(t == "TSLA" for t in tickers)
    directions = {f["direction"] for f in r["flags"]}
    assert "bullish" in directions
    assert "bearish" in directions


# ── 2. validate_gemini — happy path ───────────────────────────────────────────

def test_validate_gemini_fixture():
    """validate_gemini parses fixture correctly: valid=True, 2 flags."""
    r = validate_gemini(str(_GEMINI_FIXTURE))
    assert r["valid"] is True
    assert r["flags_found"] == 2
    assert r["flags_valid"] == 2
    assert r["flags_skipped"] == 0
    assert r["errors"] == []
    tickers = {f["ticker"] for f in r["flags"]}
    assert "PLTR" in tickers
    assert "NVDA" in tickers


# ── 3. validate_phi4 — happy path + calibration ───────────────────────────────

def test_validate_phi4_fixture():
    """validate_phi4 parses JSONL fixture: valid=True, calibration applied."""
    r = validate_phi4(str(_PHI4_FIXTURE))
    assert r["valid"] is True
    assert r["flags_found"] == 2
    assert r["flags_valid"] == 2
    assert r["flags_skipped"] == 0
    assert r["errors"] == []
    for flag in r["flags"]:
        # Calibrated confidence must be lower than raw
        assert flag["confidence"] < flag["confidence_raw"]
        # Calibrated = raw * 0.85
        assert abs(flag["confidence"] - flag["confidence_raw"] * 0.85) < 1e-6


# ── 4. validate_grok — missing top-level field ────────────────────────────────

def test_validate_grok_missing_field(tmp_path):
    """Missing 'source' field → valid=False, error list populated."""
    bad = {
        "generated_at": "2026-05-03T07:00:00Z",
        # "source" intentionally omitted
        "flags": [],
    }
    p = tmp_path / "grok_bad.json"
    p.write_text(json.dumps(bad))
    r = validate_grok(str(p))
    assert r["valid"] is False
    assert any("source" in e for e in r["errors"])


# ── 5. validate_gemini — invalid direction ────────────────────────────────────

def test_validate_gemini_bad_direction(tmp_path):
    """Invalid direction value → flag skipped, valid=False."""
    bad = {
        "generated_at": "2026-05-03T08:00:00Z",
        "source": "gemini_deep_research",
        "flags": [
            {
                "ticker": "PLTR",
                "signal_type": "thematic",
                "direction": "sideways",     # invalid
                "confidence": 0.80,
                "ts": "2026-05-03T08:00:00Z",
            }
        ],
    }
    p = tmp_path / "gemini_bad.json"
    p.write_text(json.dumps(bad))
    r = validate_gemini(str(p))
    assert r["valid"] is False
    assert r["flags_skipped"] == 1
    assert r["flags_valid"] == 0
    assert any("direction" in e for e in r["errors"])


# ── 6. validate_phi4 — low confidence after calibration ──────────────────────

def test_validate_phi4_low_confidence(tmp_path):
    """conf=0.40 * 0.85 = 0.34 < 0.40 minimum → flag skipped."""
    p = tmp_path / "phi4_low.jsonl"
    p.write_text(json.dumps({
        "ticker": "TSLA",
        "signal_type": "tactical",
        "direction": "bullish",
        "confidence": 0.40,    # calibrated: 0.34 — below 0.40 threshold
        "ts": "2026-05-03T06:00:00Z",
    }) + "\n")
    r = validate_phi4(str(p))
    assert r["valid"] is True   # no schema errors — just skipped on calibrated conf
    assert r["flags_found"] == 1
    assert r["flags_skipped"] == 1
    assert r["flags_valid"] == 0


# ── 7. ingest_grok — dry_run=True → 0 DB writes ──────────────────────────────

def test_ingest_grok_fixture_dry_run(tmp_path, monkeypatch):
    """ingest_grok with dry_run=True reads fixture, reports flags, writes nothing to DB."""
    store = _make_store(tmp_path)
    _enable_cap(store)

    # Point GROK_OUTPUT_DIR at fixtures dir via monkeypatch
    import soma.intel.cross_ai.grok_adapter as ga
    monkeypatch.setattr(ga, "GROK_OUTPUT_DIR",  _FIXTURES)
    monkeypatch.setattr(ga, "GROK_OUTPUT_GLOB", "grok_flags_2026-05-03.json")
    monkeypatch.setattr(ga, "_LOOKBACK_DAYS", 9999)  # don't skip on date filter

    result = ingest_grok(store, dry_run=True)

    assert result["flags_inserted"] == 3   # dry_run counts as inserted
    assert result["errors"] == 0
    # DB must be untouched
    count = store._c.execute(
        "SELECT COUNT(*) FROM soma_intel_cross_ai_flag"
    ).fetchone()[0]
    assert count == 0


# ── 8. ingest idempotency — second run skips duplicates ───────────────────────

def test_ingest_idempotency(tmp_path, monkeypatch):
    """Second ingest on same file → flags_inserted=0, flags_skipped=3."""
    store = _make_store(tmp_path)
    _enable_cap(store)

    import soma.intel.cross_ai.grok_adapter as ga
    monkeypatch.setattr(ga, "GROK_OUTPUT_DIR",  _FIXTURES)
    monkeypatch.setattr(ga, "GROK_OUTPUT_GLOB", "grok_flags_2026-05-03.json")
    monkeypatch.setattr(ga, "_LOOKBACK_DAYS", 9999)

    r1 = ingest_grok(store, dry_run=False)
    assert r1["flags_inserted"] == 3

    r2 = ingest_grok(store, dry_run=False)
    assert r2["flags_inserted"] == 0
    assert r2["flags_skipped"] == 3   # all duplicates


# ── 9. capability gate — disabled → 0 writes ─────────────────────────────────

def test_ingest_capability_gate(tmp_path, monkeypatch):
    """cross_ai_corroboration capability disabled → ingest_grok returns immediately."""
    store = _make_store(tmp_path)
    _disable_cap(store)

    import soma.intel.cross_ai.grok_adapter as ga
    monkeypatch.setattr(ga, "GROK_OUTPUT_DIR",  _FIXTURES)
    monkeypatch.setattr(ga, "GROK_OUTPUT_GLOB", "grok_flags_2026-05-03.json")
    monkeypatch.setattr(ga, "_LOOKBACK_DAYS", 9999)

    result = ingest_grok(store, dry_run=False)

    # Adapter exits early — no files scanned, no flags inserted
    assert result["files_scanned"] == 0
    assert result["flags_inserted"] == 0
    count = store._c.execute(
        "SELECT COUNT(*) FROM soma_intel_cross_ai_flag"
    ).fetchone()[0]
    assert count == 0


# ── 10. validate_grok — empty flags array ─────────────────────────────────────

def test_validate_grok_empty_flags(tmp_path):
    """flags:[] is valid schema — returns valid=True with 0 flags."""
    payload = {
        "generated_at": "2026-05-03T07:00:00Z",
        "source": "grok_deepsearch",
        "flags": [],
    }
    p = tmp_path / "grok_empty.json"
    p.write_text(json.dumps(payload))
    r = validate_grok(str(p))
    assert r["valid"] is True
    assert r["flags_found"] == 0
    assert r["flags_valid"] == 0
    assert r["errors"] == []


# ── 11. validate_phi4 — malformed JSONL line ──────────────────────────────────

def test_validate_phi4_bad_json_line(tmp_path):
    """One bad JSONL line → error reported for that line; other valid lines still parsed."""
    good_line = json.dumps({
        "ticker": "TSLA", "signal_type": "tactical", "direction": "bullish",
        "confidence": 0.65, "ts": "2026-05-03T06:00:00Z",
    })
    p = tmp_path / "phi4_mixed.jsonl"
    p.write_text(good_line + "\n" + "NOT VALID JSON {\n")
    r = validate_phi4(str(p))
    assert r["valid"] is False           # errors present
    assert len(r["errors"]) >= 1
    assert r["flags_found"] == 1         # only the good line counted
    assert r["flags_valid"] == 1


# ── 12. ingest_gemini — capability gate ───────────────────────────────────────

def test_gemini_ingest_skips_when_disabled(tmp_path, monkeypatch):
    """cross_ai_corroboration disabled → ingest_gemini returns immediately, 0 DB rows."""
    store = _make_store(tmp_path)
    _disable_cap(store)

    monkeypatch.setattr(_gem_mod, "GEMINI_OUTPUT_DIR",  _FIXTURES)
    monkeypatch.setattr(_gem_mod, "GEMINI_OUTPUT_GLOB", "gemini_flags_2026-05-03.json")
    monkeypatch.setattr(_gem_mod, "_LOOKBACK_DAYS", 9999)

    result = ingest_gemini(store, dry_run=False)

    assert result["files_scanned"] == 0
    assert result["flags_inserted"] == 0
    count = store._c.execute(
        "SELECT COUNT(*) FROM soma_intel_cross_ai_flag"
    ).fetchone()[0]
    assert count == 0


# ── 13. ingest_phi4 — capability gate ─────────────────────────────────────────

def test_phi4_ingest_skips_when_disabled(tmp_path, monkeypatch):
    """cross_ai_corroboration disabled → ingest_phi4 returns immediately, 0 DB rows."""
    store = _make_store(tmp_path)
    _disable_cap(store)

    monkeypatch.setattr(_phi4_mod, "PHI4_OUTPUT_DIR",  _FIXTURES)
    monkeypatch.setattr(_phi4_mod, "PHI4_OUTPUT_GLOB", "phi4_flags_2026-05-03.jsonl")
    monkeypatch.setattr(_phi4_mod, "_LOOKBACK_DAYS", 9999)

    result = ingest_phi4(store, dry_run=False)

    assert result["files_scanned"] == 0
    assert result["flags_inserted"] == 0
    count = store._c.execute(
        "SELECT COUNT(*) FROM soma_intel_cross_ai_flag"
    ).fetchone()[0]
    assert count == 0
