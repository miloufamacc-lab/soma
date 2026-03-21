#!/usr/bin/env python3
"""
Compile split KB files into a single SOMA_COMPILED.md
Reads manifest.yaml for file order, concatenates with section dividers.
"""

import os
import yaml
from datetime import datetime

KNOWLEDGE_DIR = os.path.dirname(os.path.abspath(__file__))
SOMA_DIR = os.path.dirname(KNOWLEDGE_DIR)
MANIFEST_PATH = os.path.join(KNOWLEDGE_DIR, "manifest.yaml")
OUTPUT_PATH = os.path.join(SOMA_DIR, "SOMA_COMPILED.md")


def compile_kb():
    # Load manifest
    with open(MANIFEST_PATH, "r") as f:
        manifest = yaml.safe_load(f)

    parts = []
    parts.append(f"# SOMA — Compiled Knowledge Base")
    parts.append(f"**Compiled:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    parts.append(f"**Version:** {manifest.get('version', 'unknown')}")
    parts.append(f"**Files:** {len(manifest['files'])}")
    parts.append("")

    for entry in manifest["files"]:
        filepath = os.path.join(KNOWLEDGE_DIR, entry["path"])
        if not os.path.exists(filepath):
            parts.append(f"\n---\n## [MISSING] {entry['path']}\n")
            continue

        with open(filepath, "r") as f:
            content = f.read()

        parts.append(f"\n{'='*80}")
        parts.append(f"## {entry['path']}  (source: {entry['source_module']})")
        parts.append(f"{'='*80}\n")
        parts.append(content)

    compiled = "\n".join(parts)

    with open(OUTPUT_PATH, "w") as f:
        f.write(compiled)

    print(f"Compiled {len(manifest['files'])} KB files → {OUTPUT_PATH}")
    print(f"Total size: {len(compiled):,} characters")


if __name__ == "__main__":
    compile_kb()
