#!/usr/bin/env python3
"""
Compile split KB files into a single SOMA_COMPILED.md
Reads manifest.yaml for file order, concatenates with section dividers.
"""

import yaml
from datetime import datetime
from pathlib import Path

KNOWLEDGE_DIR = Path(__file__).parent / "knowledge"
SOMA_DIR = Path(__file__).parent
MANIFEST_PATH = KNOWLEDGE_DIR / "manifest.yaml"
OUTPUT_PATH = SOMA_DIR / "SOMA_COMPILED.md"


def compile_kb() -> None:
    """Compile knowledge base files from manifest into a single markdown file."""
    # Load manifest
    try:
        with open(MANIFEST_PATH, "r") as f:
            manifest = yaml.safe_load(f)
    except Exception as e:
        print(f"Error: could not load manifest from {MANIFEST_PATH}: {e}")
        return

    parts = []
    parts.append(f"# SOMA — Compiled Knowledge Base")
    parts.append(f"**Compiled:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    parts.append(f"**Version:** {manifest.get('version', 'unknown')}")
    parts.append(f"**Files:** {len(manifest['files'])}")
    parts.append("")

    for entry in manifest["files"]:
        filepath = KNOWLEDGE_DIR / entry["path"]
        if not filepath.exists():
            parts.append(f"\n---\n## [MISSING] {entry['path']}\n")
            continue

        try:
            with open(filepath, "r") as f:
                content = f.read()

            parts.append(f"\n{'='*80}")
            parts.append(f"## {entry['path']}  (source: {entry['source_module']})")
            parts.append(f"{'='*80}\n")
            parts.append(content)
        except Exception as e:
            print(f"Warning: could not read {filepath}: {e}")
            parts.append(f"\n---\n## [ERROR READING] {entry['path']}\n")

    compiled = "\n".join(parts)

    try:
        with open(OUTPUT_PATH, "w") as f:
            f.write(compiled)

        print(f"Compiled {len(manifest['files'])} KB files → {OUTPUT_PATH}")
        print(f"Total size: {len(compiled):,} characters")
    except Exception as e:
        print(f"Error: could not write output to {OUTPUT_PATH}: {e}")


if __name__ == "__main__":
    compile_kb()
