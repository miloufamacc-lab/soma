"""
SOMA-INTEL Phase 7 D.3.A.2.a — Tests: cross-asset price cache + cache-aware ingestor

6 tests covering:
  1. CSV format validation
  2. Strict mode uses cache, no live fetch
  3. Strict mode returns None on cache miss
  4. Live mode falls back to Yahoo on cache miss
  5. build_cache refuses overwrite without --overwrite
  6. No look-ahead in cache read (strict mode)
"""
from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

# ── Path setup ────────────────────────────────────────────────────────────────
_HERE         = Path(__file__).resolve().parent
_DABEIBA_ROOT = _HERE.parent.parent.parent
for _p in [str(_DABEIBA_ROOT), str(_DABEIBA_ROOT / "shared")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from soma.intel.regime_shift.ingestors import (
    ingest_cross_asset_z,
    _read_cross_asset_cache,
)
from soma.intel.regime_shift.build_cross_asset_cache import build_cache

_FIXTURE_CSV = _HERE / "fixtures" / "cross_asset_prices_fixture.csv"


def _mock_store():
    return MagicMock()


class TestCacheCSVFormat(unittest.TestCase):
    """Test 1: Cache CSV has correct format."""

    def test_cache_csv_format(self):
        self.assertTrue(
            _FIXTURE_CSV.exists(),
            f"Fixture not found: {_FIXTURE_CSV}"
        )
        with open(_FIXTURE_CSV, newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        # Header
        self.assertEqual(reader.fieldnames, ["date", "SPY", "TLT", "GLD", "DX-Y.NYB"])
        # Row count
        self.assertGreaterEqual(len(rows), 30, "Fixture should have >= 30 rows")
        # 5 columns per row
        for row in rows:
            self.assertEqual(len(row), 5)
        # Dates parseable
        for row in rows:
            d = date.fromisoformat(row["date"])
            self.assertIsInstance(d, date)
        # Prices positive
        for row in rows:
            for t in ["SPY", "TLT", "GLD", "DX-Y.NYB"]:
                self.assertGreater(float(row[t]), 0)


class TestIngestCrossAssetStrictModeUsesCache(unittest.TestCase):
    """Test 2: bt_strict_mode=True uses cache, makes ZERO live fetch calls."""

    @patch("soma.intel.regime_shift.ingestors._fetch_yahoo_closes")
    def test_strict_mode_uses_cache_no_live_fetch(self, mock_fetch):
        """In strict mode, ingestor must NOT call Yahoo Finance at all."""
        # Use a target_date within the fixture (2024-02-12 is last fixture date)
        # The function will return None (insufficient history) but must not fetch live
        result = ingest_cross_asset_z(
            target_date="2024-01-15",
            store=_mock_store(),
            bt_strict_mode=True,
            _cache_path=_FIXTURE_CSV,
        )
        # Regardless of result (likely None due to insufficient history in 30-row fixture),
        # the key assertion is: no live fetch
        mock_fetch.assert_not_called()

    @patch("soma.intel.regime_shift.ingestors._fetch_yahoo_closes")
    def test_strict_mode_returns_none_on_cache_miss(self, mock_fetch):
        """Test 3: Strict mode + date beyond cache coverage → None, no live fetch."""
        result = ingest_cross_asset_z(
            target_date="2026-06-01",     # well beyond fixture coverage
            store=_mock_store(),
            bt_strict_mode=True,
            _cache_path=_FIXTURE_CSV,
        )
        self.assertIsNone(result)
        mock_fetch.assert_not_called()


class TestIngestCrossAssetLiveModeFallback(unittest.TestCase):
    """Test 4: Live mode (bt_strict_mode=False) falls back to Yahoo on cache miss."""

    @patch("soma.intel.regime_shift.ingestors._fetch_yahoo_closes")
    def test_live_mode_falls_back_to_yahoo_on_cache_miss(self, mock_fetch):
        """Cache miss in live mode triggers Yahoo Finance fetch."""
        # Mock Yahoo to return empty dicts (triggers per-ticker None path)
        mock_fetch.return_value = {}

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=True) as tmp:
            # Empty file = no cache hit
            empty_cache = Path(tmp.name)
            empty_cache.write_text("")

            result = ingest_cross_asset_z(
                target_date="2024-08-15",
                store=_mock_store(),
                bt_strict_mode=False,
                _cache_path=empty_cache,
            )

        # Yahoo should have been called (live fallback triggered)
        self.assertTrue(mock_fetch.called, "Expected live fetch to be called on cache miss")
        # Result is None because mock returns empty (fetch fails)
        self.assertIsNone(result)


class TestBuildCacheIdempotentOverwriteRefuses(unittest.TestCase):
    """Test 5: Second run without --overwrite exits with FileExistsError."""

    @patch("soma.intel.regime_shift.build_cross_asset_cache._fetch_yahoo_closes")
    def test_overwrite_refuses_without_flag(self, mock_fetch):
        """build_cache raises FileExistsError if file exists and overwrite=False."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "cross_asset_prices.csv"
            # Create an existing file
            out.write_text("date,SPY,TLT,GLD,DX-Y.NYB\n2024-01-02,460.0,90.0,190.0,102.0\n")

            with self.assertRaises(FileExistsError):
                build_cache(
                    start_date="2024-01-01",
                    end_date="2024-01-31",
                    output_path=str(out),
                    overwrite=False,
                )
            # Mock should not have been called (refused before fetch)
            mock_fetch.assert_not_called()


class TestNoLookaheadInCacheRead(unittest.TestCase):
    """Test 6: _read_cross_asset_cache filters to dates <= cutoff_date."""

    def test_no_lookahead_in_cache_read(self):
        """
        Query for 2024-01-10. Cache contains dates up to 2024-02-12.
        Returned prices must only contain dates <= 2024-01-10.
        """
        cutoff = date(2024, 1, 10)
        prices = _read_cross_asset_cache(cutoff_date=cutoff, cache_path=_FIXTURE_CSV)

        self.assertIsNotNone(prices, "Cache read should succeed with fixture")
        for ticker, ticker_prices in prices.items():
            for d in ticker_prices:
                self.assertLessEqual(
                    d, cutoff,
                    f"Look-ahead violation: {d} > cutoff {cutoff} for ticker {ticker}"
                )

        # Sanity: fixture has rows after 2024-01-10 so filtered count < total
        prices_all = _read_cross_asset_cache(
            cutoff_date=date(2026, 12, 31),
            cache_path=_FIXTURE_CSV,
        )
        spy_count_filtered = len(prices.get("SPY", {}))
        spy_count_all      = len(prices_all.get("SPY", {}))
        self.assertLess(spy_count_filtered, spy_count_all,
                        "Filtered count should be less than unfiltered count")


if __name__ == "__main__":
    unittest.main(verbosity=2)
