"""
voice_loader.py
Loads the RULES.md for a given pipeline directory.
Every drafting session starts by calling load_rules() so the voice spec
is always the single source of truth.
"""

from pathlib import Path


def load_rules(pipeline_path: Path) -> str:
    """
    Read and return the full text of RULES.md from pipeline_path.

    Args:
        pipeline_path: Path to the pipeline folder
                       (e.g. cipher/pipelines/darkframe/)

    Returns:
        The full RULES.md text as a string.

    Raises:
        FileNotFoundError: if RULES.md does not exist at that path.
    """
    rules_file = Path(pipeline_path) / "RULES.md"
    if not rules_file.exists():
        raise FileNotFoundError(
            f"RULES.md not found at: {rules_file}\n"
            f"Create it before running a draft session."
        )
    return rules_file.read_text(encoding="utf-8")
