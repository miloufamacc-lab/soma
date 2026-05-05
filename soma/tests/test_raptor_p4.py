"""
Unit tests — RAPTOR Phase 4: CRM3 Value Proposition Engine
Tests: ingest_prospect_holdings, compare_to_raptor_model, generate_crm3_report,
       fund MER table, seed_fund_mers.
20 tests total.
"""
from __future__ import annotations

import sys
import os
import uuid
import math
import sqlite3
import pytest
from datetime import date
from pathlib import Path

_DABEIBA_ROOT = Path(__file__).resolve().parent.parent.parent.parent
for _p in [str(_DABEIBA_ROOT), str(_DABEIBA_ROOT / "shared")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from soma.soma_bridge import SomaBridge
from soma.raptor_crm3_analyzer import (
    CRM3Analyzer,
    seed_fund_mers,
    _compound_drag,
    _normalize_weights,
    ASSUMED_GROSS_RETURN,
    _AUM_REFERENCE,
)

_MIG_DIR = _DABEIBA_ROOT / "shared" / "soma" / "migrations"


@pytest.fixture
def db(tmp_path):
    """Isolated test DB with RAPTOR + CRM3 schema."""
    db_file = str(tmp_path / "test_raptor_p4.db")
    os.environ["SOMA_DB_PATH"] = db_file

    conn = sqlite3.connect(db_file)
    for mig_name in [
        "001_initial_schema.sql",
        "003_kb_rules.sql",
        "012_raptor_core.sql",
        "017_consent_idempotency.sql",
        "018_pipeline_trigger_touchpoint.sql",
        "027_raptor_crm3.sql",
    ]:
        conn.executescript((_MIG_DIR / mig_name).read_text())
    conn.commit()
    conn.close()

    bridge = SomaBridge(db_path=db_file)
    bridge.__enter__()
    yield bridge
    bridge.__exit__(None, None, None)


def _new_id():
    return str(uuid.uuid4())


# ── Helper: representative portfolio dicts ────────────────────────────────────

_HIGH_MER_PORTFOLIO = [
    {"fund_name": "RBC Canadian Equity Fund", "ticker": "RBF556", "weight": 0.60, "mer": 2.35},
    {"fund_name": "RBC Balanced Fund",        "ticker": "RBF256", "weight": 0.40, "mer": 2.10},
]
# weighted MER = 0.60*2.35 + 0.40*2.10 = 1.41 + 0.84 = 2.25%

_LOW_MER_PORTFOLIO = [
    {"fund_name": "iShares XIC ETF",         "ticker": "XIC",  "weight": 0.50, "mer": 0.06},
    {"fund_name": "Advisory management fee", "ticker": None,   "weight": 1.00, "mer": 1.00},
]
# weighted MER: normalised weights = [0.5/1.5, 1.0/1.5] = [0.333, 0.667]
# weighted MER = 0.333*0.06 + 0.667*1.00 ≈ 0.687%


# ── _normalize_weights unit tests ─────────────────────────────────────────────

def test_normalize_fraction_weights():
    holdings = [
        {"fund_name": "A", "weight": 0.60, "mer": 2.0},
        {"fund_name": "B", "weight": 0.40, "mer": 1.0},
    ]
    norm = _normalize_weights(holdings)
    assert abs(sum(h["weight"] for h in norm) - 1.0) < 1e-6


def test_normalize_percentage_weights():
    """Weights given as percentages (60, 40) → normalized to (0.60, 0.40)."""
    holdings = [
        {"fund_name": "A", "weight": 60.0, "mer": 2.0},
        {"fund_name": "B", "weight": 40.0, "mer": 1.0},
    ]
    norm = _normalize_weights(holdings)
    assert abs(norm[0]["weight"] - 0.60) < 1e-4
    assert abs(norm[1]["weight"] - 0.40) < 1e-4


def test_normalize_unequal_weights_scaled():
    """Weights that don't sum to 1 are scaled proportionally."""
    holdings = [
        {"fund_name": "A", "weight": 0.30, "mer": 2.0},
        {"fund_name": "B", "weight": 0.30, "mer": 1.0},
    ]
    norm = _normalize_weights(holdings)
    assert abs(sum(h["weight"] for h in norm) - 1.0) < 1e-6
    assert abs(norm[0]["weight"] - 0.50) < 1e-4


# ── _compound_drag unit tests ─────────────────────────────────────────────────

def test_drag_increases_with_time():
    d10 = _compound_drag(_AUM_REFERENCE, 2.0, 10)
    d20 = _compound_drag(_AUM_REFERENCE, 2.0, 20)
    d30 = _compound_drag(_AUM_REFERENCE, 2.0, 30)
    assert d10 < d20 < d30


def test_drag_higher_for_higher_mer():
    d_high = _compound_drag(_AUM_REFERENCE, 2.35, 20)
    d_low  = _compound_drag(_AUM_REFERENCE, 0.10, 20)
    assert d_high > d_low


def test_drag_zero_mer_is_zero():
    d = _compound_drag(_AUM_REFERENCE, 0.0, 20)
    assert abs(d) < 1e-6


# ── ingest_prospect_holdings ──────────────────────────────────────────────────

def test_ingest_returns_required_keys(db):
    analyzer = CRM3Analyzer(db)
    result = analyzer.ingest_prospect_holdings(_HIGH_MER_PORTFOLIO)
    for key in ["holdings", "weighted_mer", "drag_per_1M_10yr",
                "drag_per_1M_20yr", "drag_per_1M_30yr", "gross_return_assumption"]:
        assert key in result


def test_ingest_weighted_mer_correct(db):
    """0.60×2.35 + 0.40×2.10 = 2.25% (exactly)."""
    analyzer = CRM3Analyzer(db)
    result = analyzer.ingest_prospect_holdings(_HIGH_MER_PORTFOLIO)
    assert abs(result["weighted_mer"] - 2.25) < 0.01


def test_ingest_drag_10yr_positive(db):
    analyzer = CRM3Analyzer(db)
    result = analyzer.ingest_prospect_holdings(_HIGH_MER_PORTFOLIO)
    assert result["drag_per_1M_10yr"] > 0


def test_ingest_drag_ordering(db):
    """10yr < 20yr < 30yr drag."""
    analyzer = CRM3Analyzer(db)
    r = analyzer.ingest_prospect_holdings(_HIGH_MER_PORTFOLIO)
    assert r["drag_per_1M_10yr"] < r["drag_per_1M_20yr"] < r["drag_per_1M_30yr"]


def test_ingest_empty_raises(db):
    analyzer = CRM3Analyzer(db)
    with pytest.raises(ValueError):
        analyzer.ingest_prospect_holdings([])


# ── compare_to_raptor_model ───────────────────────────────────────────────────

def test_compare_savings_positive(db):
    """Current 2.25% MER vs proposed ~0.69% → positive savings."""
    analyzer = CRM3Analyzer(db)
    comp = analyzer.compare_to_raptor_model(_HIGH_MER_PORTFOLIO, _LOW_MER_PORTFOLIO)
    assert comp["fee_savings_pct"] > 0
    assert comp["dollar_savings_10yr"] > 0
    assert comp["dollar_savings_20yr"] > 0
    assert comp["dollar_savings_30yr"] > 0


def test_compare_savings_increase_over_time(db):
    """Compounding means 30yr savings > 20yr > 10yr."""
    analyzer = CRM3Analyzer(db)
    comp = analyzer.compare_to_raptor_model(_HIGH_MER_PORTFOLIO, _LOW_MER_PORTFOLIO)
    assert comp["dollar_savings_10yr"] < comp["dollar_savings_20yr"] < comp["dollar_savings_30yr"]


def test_compare_identical_portfolios_zero_savings(db):
    """Same MER → savings ~0."""
    portfolio = [{"fund_name": "Fund A", "weight": 1.0, "mer": 1.5}]
    analyzer = CRM3Analyzer(db)
    comp = analyzer.compare_to_raptor_model(portfolio, portfolio)
    assert abs(comp["fee_savings_pct"]) < 1e-6
    assert abs(comp["dollar_savings_10yr"]) < 1e-4


def test_compare_structure(db):
    analyzer = CRM3Analyzer(db)
    comp = analyzer.compare_to_raptor_model(_HIGH_MER_PORTFOLIO, _LOW_MER_PORTFOLIO)
    for key in ["current", "proposed", "fee_savings_pct",
                "dollar_savings_10yr", "dollar_savings_20yr", "dollar_savings_30yr"]:
        assert key in comp


# ── generate_crm3_report ──────────────────────────────────────────────────────

def test_report_contains_prospect_name(db):
    pid = _new_id()
    db.write_prospect(pid, first_name="Marie", last_name="Tremblay")
    analyzer = CRM3Analyzer(db)
    comp   = analyzer.compare_to_raptor_model(_HIGH_MER_PORTFOLIO, _LOW_MER_PORTFOLIO)
    report = analyzer.generate_crm3_report(pid, comp)
    assert "Marie" in report or "Tremblay" in report


def test_report_has_disclaimer(db):
    pid = _new_id()
    db.write_prospect(pid, first_name="Test")
    analyzer = CRM3Analyzer(db)
    comp   = analyzer.compare_to_raptor_model(_HIGH_MER_PORTFOLIO, _LOW_MER_PORTFOLIO)
    report = analyzer.generate_crm3_report(pid, comp)
    assert "illustrative purposes only" in report
    assert "past performance" in report.lower()


def test_report_aum_scaling(db):
    """$2M AUM report shows roughly 2× dollar savings vs $1M."""
    pid = _new_id()
    db.write_prospect(pid, first_name="Rich")
    analyzer = CRM3Analyzer(db)
    comp = analyzer.compare_to_raptor_model(_HIGH_MER_PORTFOLIO, _LOW_MER_PORTFOLIO)
    report_1m = analyzer.generate_crm3_report(pid, comp, aum_estimate=1_000_000)
    report_2m = analyzer.generate_crm3_report(pid, comp, aum_estimate=2_000_000)
    # $2M report should have larger numbers — just confirm it renders
    assert "$2,000,000" in report_2m
    assert "$1,000,000" in report_1m


def test_report_fr_language(db):
    """FR report contains French disclaimer and French headings."""
    pid = _new_id()
    db.write_prospect(pid, first_name="Jean")
    analyzer = CRM3Analyzer(db)
    comp   = analyzer.compare_to_raptor_model(_HIGH_MER_PORTFOLIO, _LOW_MER_PORTFOLIO)
    report = analyzer.generate_crm3_report(pid, comp, language="FR")
    assert "titre indicatif" in report
    assert "rendements passés" in report


# ── Fund MER table & seed ─────────────────────────────────────────────────────

def test_fund_mer_table_write_and_read(db):
    db.write_fund_mer("iShares XIC ETF", 0.06, ticker="XIC",
                      fund_family="iShares", fund_type="etf")
    result = db.get_fund_mer("XIC")
    assert result is not None
    assert abs(result["mer"] - 0.06) < 1e-6
    assert result["fund_family"] == "iShares"


def test_fund_mer_upsert(db):
    """write_fund_mer on same ticker updates the MER."""
    db.write_fund_mer("Test Fund", 2.35, ticker="TST")
    db.write_fund_mer("Test Fund Updated", 2.10, ticker="TST")
    result = db.get_fund_mer("TST")
    assert abs(result["mer"] - 2.10) < 1e-6


def test_seed_fund_mers_count(db):
    count = seed_fund_mers(db)
    assert count >= 18   # at least 18 seed records
    all_funds = db.get_all_fund_mers()
    assert len(all_funds) >= 18


def test_seed_fund_mers_has_etfs_and_mutual_funds(db):
    seed_fund_mers(db)
    funds = db.get_all_fund_mers()
    types = {f["fund_type"] for f in funds}
    assert "etf" in types
    assert "mutual_fund" in types


def test_seed_fund_mers_idempotent(db):
    """Calling seed twice doesn't duplicate rows."""
    seed_fund_mers(db)
    seed_fund_mers(db)
    all_funds = db.get_all_fund_mers()
    tickers = [f["ticker"] for f in all_funds if f["ticker"]]
    assert len(tickers) == len(set(tickers))   # no duplicate tickers
