"""Tests for draft_store.py"""

import pytest
import tempfile
from pathlib import Path
import sys

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_ROOT / "shared") not in sys.path:
    sys.path.insert(0, str(_ROOT / "shared"))

from social_tools.draft_store import DraftStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_db(tmp_path):
    """Return a DraftStore backed by a temp DB file."""
    store = DraftStore(tmp_path / "test.db")
    yield store
    store.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDraftStoreCRUD:

    def test_save_draft_returns_int(self, tmp_db):
        draft_id = tmp_db.save_draft(pipeline="darkframe", post_text="hello world")
        assert isinstance(draft_id, int)
        assert draft_id >= 1

    def test_save_draft_sets_status_draft(self, tmp_db):
        draft_id = tmp_db.save_draft(pipeline="darkframe", post_text="test post")
        draft = tmp_db.get_draft(draft_id)
        assert draft["status"] == "draft"

    def test_get_draft_returns_dict(self, tmp_db):
        draft_id = tmp_db.save_draft(pipeline="darkframe", post_text="test post")
        draft = tmp_db.get_draft(draft_id)
        assert isinstance(draft, dict)
        assert draft["post_text"] == "test post"
        assert draft["pipeline"] == "darkframe"

    def test_get_draft_nonexistent_returns_none(self, tmp_db):
        assert tmp_db.get_draft(9999) is None

    def test_list_drafts_empty(self, tmp_db):
        assert tmp_db.list_drafts() == []

    def test_list_drafts_returns_all(self, tmp_db):
        tmp_db.save_draft(pipeline="darkframe", post_text="post 1")
        tmp_db.save_draft(pipeline="darkframe", post_text="post 2")
        drafts = tmp_db.list_drafts()
        assert len(drafts) == 2

    def test_list_drafts_filter_by_pipeline(self, tmp_db):
        tmp_db.save_draft(pipeline="darkframe", post_text="dark post")
        tmp_db.save_draft(pipeline="drycapital", post_text="dry post")
        dark_drafts = tmp_db.list_drafts(pipeline="darkframe")
        assert len(dark_drafts) == 1
        assert dark_drafts[0]["post_text"] == "dark post"

    def test_list_drafts_filter_by_status(self, tmp_db):
        d1 = tmp_db.save_draft(pipeline="darkframe", post_text="post 1")
        d2 = tmp_db.save_draft(pipeline="darkframe", post_text="post 2")
        tmp_db.mark_approved(d1)
        approved = tmp_db.list_drafts(status="approved")
        assert len(approved) == 1
        assert approved[0]["id"] == d1

    def test_mark_approved(self, tmp_db):
        draft_id = tmp_db.save_draft(pipeline="darkframe", post_text="test")
        tmp_db.mark_approved(draft_id)
        draft = tmp_db.get_draft(draft_id)
        assert draft["status"] == "approved"

    def test_mark_posted(self, tmp_db):
        draft_id = tmp_db.save_draft(pipeline="darkframe", post_text="test")
        tmp_db.mark_posted(draft_id, post_url="https://x.com/test/123")
        draft = tmp_db.get_draft(draft_id)
        assert draft["status"] == "posted"
        assert draft["post_url"] == "https://x.com/test/123"
        assert draft["posted_at"] is not None

    def test_mark_killed(self, tmp_db):
        draft_id = tmp_db.save_draft(pipeline="darkframe", post_text="test")
        tmp_db.mark_killed(draft_id, reason="too weak")
        draft = tmp_db.get_draft(draft_id)
        assert draft["status"] == "killed"

    def test_save_draft_with_optional_fields(self, tmp_db):
        draft_id = tmp_db.save_draft(
            pipeline="darkframe",
            post_text="inference cost is the next oil price.",
            pillar="AI_COMPUTE",
            topic_domain="robotics",
            gate_results={"length_ok": {"result": "pass"}},
            notes="strong angle",
        )
        draft = tmp_db.get_draft(draft_id)
        assert draft["pillar"] == "AI_COMPUTE"
        assert draft["topic_domain"] == "robotics"
        assert draft["notes"] == "strong angle"
        assert draft["gate_results"] is not None  # stored as JSON string

    def test_multiple_drafts_get_unique_ids(self, tmp_db):
        ids = [tmp_db.save_draft(pipeline="darkframe", post_text=f"post {i}") for i in range(5)]
        assert len(set(ids)) == 5

    def test_list_drafts_newest_first(self, tmp_db):
        for i in range(3):
            tmp_db.save_draft(pipeline="darkframe", post_text=f"post {i}")
        drafts = tmp_db.list_drafts()
        # Newest (highest id) should be first
        assert drafts[0]["id"] > drafts[-1]["id"]


class TestDraftStoreSaturationLog:

    def test_log_saturation_writes_record(self, tmp_db):
        draft_id = tmp_db.save_draft(pipeline="darkframe", post_text="test")
        tmp_db.log_saturation(
            draft_id=draft_id,
            query="optimus economics last 3 days",
            results_summary="LOW saturation, 3 posts found",
            decision="proceed",
        )
        # Verify it landed in the DB
        rows = tmp_db._conn.execute(
            "SELECT * FROM saturation_logs WHERE draft_id = ?", (draft_id,)
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][4] == "proceed"  # decision column


class TestDraftStorePillarHistory:

    def test_pillar_history_empty(self, tmp_db):
        result = tmp_db.get_pillar_history(n_days=7)
        assert result == []

    def test_pillar_history_only_counts_approved_posted(self, tmp_db):
        d1 = tmp_db.save_draft(pipeline="darkframe", post_text="p1", pillar="AI_COMPUTE")
        tmp_db.mark_approved(d1)
        d2 = tmp_db.save_draft(pipeline="darkframe", post_text="p2", pillar="AI_COMPUTE")
        # d2 stays as draft — should not be counted
        result = tmp_db.get_pillar_history(n_days=30, pipeline="darkframe")
        assert len(result) == 1
        assert result[0]["pillar"] == "AI_COMPUTE"
        assert result[0]["count"] == 1


class TestDraftStoreContextManager:

    def test_context_manager(self, tmp_path):
        with DraftStore(tmp_path / "ctx.db") as store:
            draft_id = store.save_draft(pipeline="test", post_text="hello")
            assert draft_id >= 1
        # After __exit__, connection is closed — further queries would fail
