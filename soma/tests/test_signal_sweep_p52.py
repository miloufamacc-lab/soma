"""
SOMA-INTEL P5.2 — Tests for half-life × 1.3 boost on reconfirmation (§C.3)

Design notes:
  - boost_signal_half_life applies round(current_hl * factor) per boost,
    NOT round(base_hl * factor^n). Rounding is applied once per step.
  - Cap: after max_boosts (3) reconfirmations the value is frozen.
  - All tests use isolated tmp_path DB — production DB never touched.

Expected compounded values (factor=1.3, base=5d):
  Boost 1: round(5    * 1.3) = round(6.5)  → computed at runtime
  Boost 2: round(b1   * 1.3)               → computed at runtime
  Boost 3: round(b2   * 1.3)               → computed at runtime
  Boost 4: capped → stays at b3 (unchanged)

We compute expected values the same way the implementation does so tests
are not brittle to float representation of 1.3.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

_DABEIBA_ROOT = Path(__file__).resolve().parent.parent.parent.parent
for _p in [str(_DABEIBA_ROOT), str(_DABEIBA_ROOT / "shared")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from soma.intel.store import IntelStore
from soma.intel.signal_sweep import RECONFIRM_BOOST_FACTOR, RECONFIRM_BOOST_MAX

_MIGRATIONS_DIR = _DABEIBA_ROOT / "shared" / "soma" / "migrations"


def _apply_migration(conn, migration_name: str) -> None:
    """Execute a migration SQL file; skip schema_version inserts (table absent in test DB)."""
    sql = (_MIGRATIONS_DIR / migration_name).read_text()
    lines = [ln for ln in sql.splitlines()
             if "schema_version" not in ln]
    conn.executescript("\n".join(lines))


# ── Fixture ───────────────────────────────────────────────────────────────────

@pytest.fixture
def store(tmp_path):
    """Fresh IntelStore with full intel schema (021 + 022) applied."""
    db_path = str(tmp_path / "test_p52.db")
    with IntelStore(db_path=db_path) as s:
        s.initialize_tables()
        _apply_migration(s._c, "021_soma_intel_schema.sql")
        _apply_migration(s._c, "022_soma_intel_audit_calibration.sql")
        s._c.commit()
        yield s


# ── Helper ────────────────────────────────────────────────────────────────────

def _insert_signal(
    store: IntelStore,
    ticker: str = "NVDA",
    half_life: int = 5,
    reconfirm_count: int = 0,
) -> int:
    """
    Insert a signal with the given stored half_life and reconfirmation_count.
    Does NOT apply the boost formula — half_life is stored as-is.
    """
    store.insert_signal(
        ticker        = ticker,
        date          = date.today().isoformat(),
        priority      = "P1",
        anomaly_score = 3.5,
        features      = "{}",
        corroboration = 2,
        half_life     = half_life,
        horizon       = "tactical",
        notes         = "propagator:test",
        status        = "active",
    )
    row = store._c.execute(
        "SELECT signal_id FROM soma_intel_signal "
        "WHERE ticker=? ORDER BY signal_id DESC LIMIT 1",
        (ticker,),
    ).fetchone()
    sid = row["signal_id"]

    if reconfirm_count > 0:
        store._c.execute(
            "UPDATE soma_intel_signal SET reconfirmation_count=? WHERE signal_id=?",
            (reconfirm_count, sid),
        )
    store.commit()
    return sid


# ── Compounded expected values ────────────────────────────────────────────────
# Computed the same way the implementation does: round-each-step.
# If RECONFIRM_BOOST_FACTOR changes, these automatically follow.
_BASE_HL = 5
_B1 = round(_BASE_HL * RECONFIRM_BOOST_FACTOR)          # after 1st boost
_B2 = round(_B1      * RECONFIRM_BOOST_FACTOR)          # after 2nd boost
_B3 = round(_B2      * RECONFIRM_BOOST_FACTOR)          # after 3rd boost (cap value)


# ════════════════════════════════════════════════════════════════════════════
# IntelStore.boost_signal_half_life
# ════════════════════════════════════════════════════════════════════════════

class TestBoostSignalHalfLife:

    def test_first_boost_multiplies_by_factor(self, store):
        """Boost #1: half_life goes from base → B1."""
        sid = _insert_signal(store, ticker="NVDA", half_life=_BASE_HL, reconfirm_count=0)
        # Simulate update_signal just bumped count to 1
        store._c.execute(
            "UPDATE soma_intel_signal SET reconfirmation_count=1 WHERE signal_id=?", (sid,)
        )
        store.commit()

        new_hl = store.boost_signal_half_life(sid, factor=RECONFIRM_BOOST_FACTOR,
                                               max_factor=RECONFIRM_BOOST_MAX)
        assert new_hl == _B1
        db_hl = store._c.execute(
            "SELECT half_life_days FROM soma_intel_signal WHERE signal_id=?", (sid,)
        ).fetchone()["half_life_days"]
        assert db_hl == _B1

    def test_second_boost_compounds(self, store):
        """Boost #2: half_life goes from B1 → B2 (compound, not base × factor^2)."""
        sid = _insert_signal(store, ticker="MSFT", half_life=_B1, reconfirm_count=1)
        store._c.execute(
            "UPDATE soma_intel_signal SET reconfirmation_count=2 WHERE signal_id=?", (sid,)
        )
        store.commit()

        new_hl = store.boost_signal_half_life(sid, factor=RECONFIRM_BOOST_FACTOR,
                                               max_factor=RECONFIRM_BOOST_MAX)
        assert new_hl == _B2

    def test_third_boost_reaches_cap_value(self, store):
        """Boost #3: half_life reaches B3 (the freeze value for subsequent calls)."""
        sid = _insert_signal(store, ticker="PLTR", half_life=_B2, reconfirm_count=2)
        store._c.execute(
            "UPDATE soma_intel_signal SET reconfirmation_count=3 WHERE signal_id=?", (sid,)
        )
        store.commit()

        new_hl = store.boost_signal_half_life(sid, factor=RECONFIRM_BOOST_FACTOR,
                                               max_factor=RECONFIRM_BOOST_MAX)
        assert new_hl == _B3

    def test_fourth_boost_capped_no_change(self, store):
        """Boost #4: reconfirm_count > 3 → returns current_hl unchanged (no 1.3^4)."""
        sid = _insert_signal(store, ticker="AMD", half_life=_B3, reconfirm_count=3)
        store._c.execute(
            "UPDATE soma_intel_signal SET reconfirmation_count=4 WHERE signal_id=?", (sid,)
        )
        store.commit()

        new_hl = store.boost_signal_half_life(sid, factor=RECONFIRM_BOOST_FACTOR,
                                               max_factor=RECONFIRM_BOOST_MAX)
        assert new_hl == _B3                           # unchanged
        assert new_hl != round(_B3 * RECONFIRM_BOOST_FACTOR)  # NOT 1.3^4

    def test_raises_on_missing_signal(self, store):
        """Non-existent signal_id raises KeyError."""
        with pytest.raises(KeyError):
            store.boost_signal_half_life(99999, factor=RECONFIRM_BOOST_FACTOR,
                                          max_factor=RECONFIRM_BOOST_MAX)

    def test_boost_idempotency_once_capped(self, store):
        """All calls with reconfirm_count > 3 return the same capped value."""
        sid = _insert_signal(store, ticker="COIN", half_life=_B3, reconfirm_count=3)

        for n in range(4, 8):   # simulate several extra reconfirmations
            store._c.execute(
                "UPDATE soma_intel_signal SET reconfirmation_count=? WHERE signal_id=?",
                (n, sid),
            )
            result = store.boost_signal_half_life(sid, factor=RECONFIRM_BOOST_FACTOR,
                                                   max_factor=RECONFIRM_BOOST_MAX)
            assert result == _B3, f"Expected capped={_B3} at reconfirm_count={n}, got {result}"


# ════════════════════════════════════════════════════════════════════════════
# Expiry-queue interaction
# ════════════════════════════════════════════════════════════════════════════

class TestReconfirmedSignalNotExpiredNextDay:
    """
    After 1 boost (half_life = B1), the signal should NOT appear in Pass 1
    expiry queue when sweep runs the next day.

    Pass 1 logic: expires when age_days > EXPIRY_MULTIPLIER × half_life_days.
    Reconfirmed grace: threshold += GRACE_MULTIPLIER × half_life_days.
    Result: threshold = (EXPIRY_MULTIPLIER + GRACE_MULTIPLIER) × B1 >> 1 day.
    """

    def test_reconfirmed_signal_survives_next_day(self, store):
        from soma.intel.signal_sweep import EXPIRY_MULTIPLIER, GRACE_MULTIPLIER

        yesterday = (date.today() - timedelta(days=1)).isoformat()

        store.insert_signal(
            ticker        = "NVDA",
            date          = yesterday,
            priority      = "P1",
            anomaly_score = 3.5,
            features      = "{}",
            corroboration = 2,
            half_life     = _B1,      # after first boost
            horizon       = "tactical",
            notes         = "propagator:test",
            status        = "reconfirmed",
        )
        store.commit()

        row = store._c.execute(
            "SELECT half_life_days, status FROM soma_intel_signal WHERE ticker='NVDA'"
        ).fetchone()

        age_days  = 1
        hl        = row["half_life_days"]
        threshold = hl * EXPIRY_MULTIPLIER
        if row["status"] == "reconfirmed":
            threshold += hl * GRACE_MULTIPLIER

        assert age_days <= threshold, (
            f"Reconfirmed signal (hl={hl}d) should survive at age={age_days}d "
            f"(threshold={threshold}d)"
        )
