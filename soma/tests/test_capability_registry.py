"""
Tests for soma_intel_capability registry — Phase 7.H3.2.

Covers:
  1. register_capability creates row
  2. set_capability_status writes history row (trigger-guarded append-only pattern)
  3. is_capability_enabled returns False for unknown capability
  4. is_capability_enabled returns True only for status='enabled'
  5. depends_on stores and retrieves as JSON list
  6. history table is append-only (UPDATE/DELETE blocked by trigger)
"""

import pytest
import sqlite3
import tempfile
import os
from pathlib import Path

from shared.soma.intel.store import IntelStore


# ── Fixture ───────────────────────────────────────────────────────────────────

@pytest.fixture
def store(tmp_path):
    """Fresh in-memory IntelStore with capability tables bootstrapped."""
    db_file = str(tmp_path / "test_cap.db")
    with IntelStore(db_path=db_file) as s:
        s.initialize_tables()
        yield s


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestRegisterCapability:

    def test_register_creates_row(self, store):
        """register_capability inserts a row with correct fields."""
        store.register_capability("signal_engine", version="1.0", status="enabled")
        cap = store.get_capability("signal_engine")
        assert cap is not None
        assert cap["capability_id"] == "signal_engine"
        assert cap["status"] == "enabled"
        assert cap["version"] == "1.0"

    def test_register_is_idempotent(self, store):
        """Calling register_capability twice does not raise and does not duplicate."""
        store.register_capability("regime_classifier", version="1.0", status="disabled")
        store.register_capability("regime_classifier", version="1.0", status="disabled")
        caps = store.list_capabilities()
        ids = [c["capability_id"] for c in caps]
        assert ids.count("regime_classifier") == 1

    def test_register_invalid_status_raises(self, store):
        """register_capability raises ValueError for unknown status."""
        with pytest.raises(ValueError, match="status must be one of"):
            store.register_capability("bad_cap", version="1.0", status="unknown")

    def test_enabled_ts_set_when_status_enabled(self, store):
        """enabled_ts is populated when status='enabled', None otherwise."""
        store.register_capability("weekly_brief", version="1.0", status="enabled")
        cap = store.get_capability("weekly_brief")
        assert cap["enabled_ts"] is not None

        store.register_capability("audit_append_only", version="1.0", status="disabled")
        cap2 = store.get_capability("audit_append_only")
        assert cap2["enabled_ts"] is None


class TestSetCapabilityStatus:

    def test_set_status_writes_history_row(self, store):
        """set_capability_status writes a history row for each change."""
        store.register_capability("anomaly_engine", version="1.0", status="disabled")
        store.set_capability_status("anomaly_engine", "enabled", notes="Phase 2 complete")

        rows = store._c.execute(
            "SELECT * FROM soma_intel_capability_history WHERE capability_id=?",
            ("anomaly_engine",),
        ).fetchall()
        assert len(rows) == 1
        row = rows[0]
        assert row["old_status"] == "disabled"
        assert row["new_status"] == "enabled"
        assert row["notes"] == "Phase 2 complete"

    def test_set_status_unknown_capability_raises(self, store):
        """set_capability_status raises ValueError for unregistered capability."""
        with pytest.raises(ValueError, match="not found"):
            store.set_capability_status("nonexistent_cap", "enabled")

    def test_set_status_invalid_status_raises(self, store):
        """set_capability_status raises ValueError for invalid status."""
        store.register_capability("confirm_gate", version="1.0", status="disabled")
        with pytest.raises(ValueError, match="status must be one of"):
            store.set_capability_status("confirm_gate", "active")

    def test_flip_flop_produces_two_history_rows(self, store):
        """Two status changes produce two separate history rows."""
        store.register_capability("weekly_brief", version="1.0", status="enabled")
        store.set_capability_status("weekly_brief", "disabled", notes="test disable")
        store.set_capability_status("weekly_brief", "enabled", notes="test re-enable")

        rows = store._c.execute(
            "SELECT old_status, new_status FROM soma_intel_capability_history "
            "WHERE capability_id='weekly_brief' ORDER BY history_id ASC"
        ).fetchall()
        assert len(rows) == 2
        assert rows[0]["old_status"] == "enabled" and rows[0]["new_status"] == "disabled"
        assert rows[1]["old_status"] == "disabled" and rows[1]["new_status"] == "enabled"


class TestIsCapabilityEnabled:

    def test_returns_false_for_unknown_capability(self, store):
        """is_capability_enabled returns False for a capability that does not exist."""
        result = store.is_capability_enabled("nonexistent_feature")
        assert result is False

    def test_returns_false_for_disabled_capability(self, store):
        """is_capability_enabled returns False when status='disabled'."""
        store.register_capability("meta_learner", version="1.0", status="disabled")
        assert store.is_capability_enabled("meta_learner") is False

    def test_returns_false_for_experimental_capability(self, store):
        """is_capability_enabled returns False when status='experimental'."""
        store.register_capability("experimental_feature", version="0.1", status="experimental")
        assert store.is_capability_enabled("experimental_feature") is False

    def test_returns_true_only_for_enabled(self, store):
        """is_capability_enabled returns True only when status='enabled'."""
        store.register_capability("graph_layer", version="1.0", status="enabled")
        assert store.is_capability_enabled("graph_layer") is True

    def test_enabled_after_status_change(self, store):
        """is_capability_enabled reflects status changes."""
        store.register_capability("backtest_runner", version="1.0", status="disabled")
        assert store.is_capability_enabled("backtest_runner") is False
        store.set_capability_status("backtest_runner", "enabled")
        assert store.is_capability_enabled("backtest_runner") is True


class TestDependsOn:

    def test_depends_on_stores_and_retrieves_as_list(self, store):
        """depends_on is stored as JSON and retrieved as a Python list."""
        store.register_capability(
            "s_curve_tracker",
            version="1.0",
            status="enabled",
            depends_on=["platform_layer", "graph_layer"],
        )
        cap = store.get_capability("s_curve_tracker")
        assert isinstance(cap["depends_on"], list)
        assert "platform_layer" in cap["depends_on"]
        assert "graph_layer" in cap["depends_on"]

    def test_depends_on_none_returns_empty_list(self, store):
        """depends_on=None stores an empty JSON array and returns []."""
        store.register_capability("belief_versioning", version="1.0", status="enabled")
        cap = store.get_capability("belief_versioning")
        assert cap["depends_on"] == []


class TestHistoryAppendOnly:

    def test_history_update_blocked_by_trigger(self, store):
        """Direct UPDATE on soma_intel_capability_history is blocked by trigger.

        SQLite RAISE(ABORT, ...) surfaces as IntegrityError in Python's sqlite3 module.
        """
        store.register_capability("decay_engine", version="1.0", status="disabled")
        store.set_capability_status("decay_engine", "enabled")

        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            store._c.execute(
                "UPDATE soma_intel_capability_history SET notes='hack' WHERE history_id=1"
            )

    def test_history_delete_blocked_by_trigger(self, store):
        """Direct DELETE on soma_intel_capability_history is blocked by trigger.

        SQLite RAISE(ABORT, ...) surfaces as IntegrityError in Python's sqlite3 module.
        """
        store.register_capability("confirm_gate", version="1.0", status="disabled")
        store.set_capability_status("confirm_gate", "enabled")

        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            store._c.execute(
                "DELETE FROM soma_intel_capability_history WHERE history_id=1"
            )


class TestListCapabilities:

    def test_list_all_capabilities(self, store):
        """list_capabilities returns all registered capabilities."""
        store.register_capability("graph_layer", version="1.0", status="enabled")
        store.register_capability("signal_engine", version="1.0", status="enabled")
        store.register_capability("regime_classifier", version="1.0", status="disabled")
        caps = store.list_capabilities()
        assert len(caps) == 3

    def test_list_with_status_filter(self, store):
        """list_capabilities with status_filter returns only matching rows."""
        store.register_capability("graph_layer", version="1.0", status="enabled")
        store.register_capability("signal_engine", version="1.0", status="enabled")
        store.register_capability("regime_classifier", version="1.0", status="disabled")
        enabled = store.list_capabilities(status_filter="enabled")
        assert len(enabled) == 2
        assert all(c["status"] == "enabled" for c in enabled)

    def test_list_ordered_by_capability_id(self, store):
        """list_capabilities returns rows in alphabetical order by capability_id."""
        store.register_capability("z_feature", version="1.0", status="enabled")
        store.register_capability("a_feature", version="1.0", status="enabled")
        caps = store.list_capabilities()
        ids = [c["capability_id"] for c in caps]
        assert ids == sorted(ids)
