"""
posting_log.py
Append-only posting log — records a post after the operator publishes it.

Two writes on every call:
  1. Updates the draft in <pipeline>.db (status='posted', posted_at, post_url)
  2. Writes a human-readable markdown file to <pipeline_dir>/archive/

Usage:
    from pathlib import Path
    from shared.social_tools.posting_log import log_post

    log_post(
        pipeline_db_path=Path("cipher/pipelines/darkframe/darkframe.db"),
        pipeline_dir=Path("cipher/pipelines/darkframe"),
        post_text="tesla's inference bill will exceed their cloud bill by 2026.",
        posted_at="2026-05-06T14:32:00+00:00",
        url="https://x.com/endthefed_btc/status/123456789",
        draft_id=3,   # optional — if you approved a draft first
    )
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .draft_store import DraftStore


def log_post(
    pipeline_db_path: Path,
    pipeline_dir: Path,
    post_text: str,
    posted_at: str,
    url: str,
    draft_id: int | None = None,
) -> int:
    """
    Record that a piece of content was posted.

    Args:
        pipeline_db_path: Absolute path to the pipeline's SQLite database.
        pipeline_dir:     Absolute path to the pipeline folder
                          (archive/ will be created inside it).
        post_text:        The exact text that was posted.
        posted_at:        ISO-8601 timestamp of when it was posted.
        url:              URL of the live post.
        draft_id:         If the post came from an approved draft, pass its id.
                          If None, a new record is created.

    Returns:
        The draft id (existing or newly created).
    """
    pipeline_db_path = Path(pipeline_db_path)
    pipeline_dir = Path(pipeline_dir)

    with DraftStore(pipeline_db_path) as store:
        if draft_id is not None:
            # Update the existing draft record
            store.mark_posted(draft_id, post_url=url)
            post_id = draft_id
        else:
            # Create a new record representing this post
            post_id = store.save_draft(
                pipeline=pipeline_dir.name,
                post_text=post_text,
                notes="Logged via posting_log (no draft_id — posted directly)",
            )
            store.mark_posted(post_id, post_url=url)

    # Write the human-readable archive file
    archive_dir = pipeline_dir / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)

    date_str = _date_from_iso(posted_at)
    archive_file = archive_dir / f"{date_str}_{post_id:04d}.md"

    archive_file.write_text(
        f"---\n"
        f"id: {post_id}\n"
        f"posted_at: {posted_at}\n"
        f"url: {url}\n"
        f"pipeline: {pipeline_dir.name}\n"
        f"---\n\n"
        f"{post_text}\n",
        encoding="utf-8",
    )

    return post_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _date_from_iso(iso_str: str) -> str:
    """Extract YYYY-MM-DD from an ISO-8601 string."""
    try:
        return iso_str[:10]
    except Exception:
        return datetime.now(timezone.utc).date().isoformat()
