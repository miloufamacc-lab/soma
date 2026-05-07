"""Tests for voice_loader.py"""

import pytest
from pathlib import Path
import tempfile
import os

# Make shared/ importable regardless of cwd
import sys
_ROOT = Path(__file__).resolve().parents[3]  # DABEIBA/
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_ROOT / "shared") not in sys.path:
    sys.path.insert(0, str(_ROOT / "shared"))

from social_tools.voice_loader import load_rules


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_load_rules_missing_file_raises():
    """load_rules raises FileNotFoundError when RULES.md is absent."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with pytest.raises(FileNotFoundError, match="RULES.md not found"):
            load_rules(Path(tmpdir))


def test_load_rules_returns_content():
    """load_rules returns the full text of RULES.md."""
    sample_content = "# RULES\n\nDo not shout.\n" * 100  # > 1000 chars
    with tempfile.TemporaryDirectory() as tmpdir:
        rules_path = Path(tmpdir) / "RULES.md"
        rules_path.write_text(sample_content, encoding="utf-8")
        result = load_rules(Path(tmpdir))
    assert result == sample_content


def test_load_rules_returns_string_type():
    """load_rules always returns a str."""
    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "RULES.md").write_text("Hello", encoding="utf-8")
        result = load_rules(Path(tmpdir))
    assert isinstance(result, str)


def test_load_rules_preserves_unicode():
    """load_rules handles non-ASCII characters correctly."""
    content = "règles d'écriture: jamais de majuscules inutiles.\n"
    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "RULES.md").write_text(content, encoding="utf-8")
        result = load_rules(Path(tmpdir))
    assert result == content
