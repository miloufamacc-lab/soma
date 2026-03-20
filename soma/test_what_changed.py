"""
Tests for WhatChanged engine.
Seeds a temp DB, runs all 6 materiality checks, verifies results.
"""

import json
import os
import sys
import tempfile

# Ensure the shared package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from shared.soma.soma_bridge import SomaBridge
from shared.soma.what_changed import WhatChanged


def seed_db(db_path):
    """Seed a temp DB with two entries for each table to trigger all 6 checks."""
    with SomaBridge(db_path) as db:
        db.initialize_db()

        # Two regime entries: different regime, GLI delta > 3.5, diffusion crosses 45,
        # momentum sign flip
        db.write_regime(
            date="2026-03-18", run_id="run-001",
            gli_value=52.0, regime="RISK_ON",
            diffusion_index=48.0, momentum=1.5,
        )
        db.write_regime(
            date="2026-03-20", run_id="run-002",
            gli_value=46.0, regime="TURBULENCE",
            diffusion_index=42.0, momentum=-0.8,
        )

        # Two valuation runs: avg upside shifts by > 8%
        for ticker, upside in [("BTC", 0.15), ("ETH", 0.20), ("SOL", 0.10)]:
            db.write_valuation(
                date="2026-03-18", run_id="val-001",
                ticker=ticker, fair_value=100.0, current_price=80.0,
                implied_upside=upside,
            )
        for ticker, upside in [("BTC", 0.02), ("ETH", 0.05), ("SOL", -0.01)]:
            db.write_valuation(
                date="2026-03-20", run_id="val-002",
                ticker=ticker, fair_value=100.0, current_price=95.0,
                implied_upside=upside,
            )

        # Two outlook entries: low Jaccard overlap
        db.write_outlook(
            date="2026-03-18", version="1",
            full_text_hash="aaa",
            key_conclusions_json=json.dumps([
                "Fed holds rates", "Crypto bullish", "DXY weakening", "Oil stable"
            ]),
        )
        db.write_outlook(
            date="2026-03-20", version="2",
            full_text_hash="bbb",
            key_conclusions_json=json.dumps([
                "Fed cuts 25bp", "Crypto cautious", "DXY strengthening",
                "Oil volatile", "Recession risk rising"
            ]),
        )


def seed_identical_db(db_path):
    """Seed a DB where current == previous (no changes should fire)."""
    with SomaBridge(db_path) as db:
        db.initialize_db()

        for run_id in ("run-001", "run-002"):
            db.write_regime(
                date="2026-03-20", run_id=run_id,
                gli_value=50.0, regime="RISK_ON",
                diffusion_index=50.0, momentum=1.0,
            )

        for run_id in ("val-001", "val-002"):
            for ticker, upside in [("BTC", 0.12), ("ETH", 0.15)]:
                db.write_valuation(
                    date="2026-03-20", run_id=run_id,
                    ticker=ticker, fair_value=100.0, current_price=85.0,
                    implied_upside=upside,
                )

        conclusions = json.dumps(["Fed holds", "Crypto neutral"])
        for version in ("1", "2"):
            db.write_outlook(
                date="2026-03-20", version=version,
                full_text_hash="same",
                key_conclusions_json=conclusions,
            )


def test_all_checks_fire():
    """All 6 materiality checks should trigger."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        seed_db(db_path)
        with WhatChanged(db_path) as wc:
            result = wc.analyze()

            assert result["has_material_change"] is True, "Expected material changes"
            types = {c["type"] for c in result["changes"]}
            expected = {
                "regime_transition", "gli_delta", "diffusion_cross",
                "momentum_flip", "valuation_shift", "outlook_drift",
            }
            missing = expected - types
            assert not missing, f"Missing change types: {missing}"

            # Verify severities
            for c in result["changes"]:
                if c["type"] == "regime_transition":
                    assert c["severity"] == "HIGH"
                else:
                    assert c["severity"] == "MEDIUM"

            # Verify regime summary
            rs = result["regime_summary"]
            assert rs["current_regime"] == "TURBULENCE"
            assert rs["previous_regime"] == "RISK_ON"
            assert rs["gli_delta"] == -6.0

            # Verify valuation summary
            vs = result["valuation_summary"]
            assert len(vs["tickers_changed"]) > 0

            # Verify outlook summary
            os_ = result["outlook_summary"]
            assert os_["jaccard_score"] < 0.75

            print("[PASS] All 6 checks fired correctly")
            print(f"       Changes: {[c['type'] for c in result['changes']]}")

            # Visual output
            wc.print_terminal()
    finally:
        os.unlink(db_path)


def test_no_changes():
    """Identical entries should produce zero changes."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        seed_identical_db(db_path)
        with WhatChanged(db_path) as wc:
            result = wc.analyze()

            assert result["has_material_change"] is False, "Expected no material changes"
            assert len(result["changes"]) == 0, f"Got unexpected changes: {result['changes']}"

            print("[PASS] No-changes case correct")
            wc.print_terminal()
    finally:
        os.unlink(db_path)


def test_insufficient_data():
    """Single entries (no previous) should return cleanly with no changes."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        with SomaBridge(db_path) as db:
            db.initialize_db()
            db.write_regime(
                date="2026-03-20", run_id="run-001",
                gli_value=50.0, regime="RISK_ON",
                diffusion_index=50.0, momentum=1.0,
            )
        with WhatChanged(db_path) as wc:
            result = wc.analyze()
            assert result["has_material_change"] is False
            assert result["regime_summary"]["previous_regime"] is None
            print("[PASS] Insufficient data handled gracefully")
    finally:
        os.unlink(db_path)


if __name__ == "__main__":
    test_all_checks_fire()
    test_no_changes()
    test_insufficient_data()
    print("\n[ALL TESTS PASSED]")
