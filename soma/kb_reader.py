"""
KBReader — deterministic rule retrieval from KB markdown files.

Parses YAML rule blocks embedded in KB markdown (between
<!-- RULE_BLOCK: ID --> and <!-- END_RULE_BLOCK --> markers).
Caches parsed rules in SQLite (kb_rules table).
Provides get_rule(rule_id) for modules to read at runtime.
Logs every read to kb_audit_log for full traceability.
"""

import yaml
import json
import hashlib
import os
import re
from datetime import datetime, timezone
from pathlib import Path

_KB_DIR = Path(__file__).parent / "knowledge"

# Regex to match RULE_BLOCK markers
_BLOCK_START = re.compile(r'<!--\s*RULE_BLOCK:\s*(\S+)\s*-->')
_BLOCK_END = re.compile(r'<!--\s*END_RULE_BLOCK\s*-->')
_YAML_FENCE_OPEN = re.compile(r'^```ya?ml\s*$')
_YAML_FENCE_CLOSE = re.compile(r'^```\s*$')


class KBReader:
    """Deterministic rule retrieval from KB markdown files."""

    def __init__(self, soma_bridge):
        self.bridge = soma_bridge
        self._cache = {}  # rule_id -> parsed dict
        self._load_cache()

    def _now(self):
        return datetime.now(timezone.utc).isoformat()

    def _file_md5(self, filepath):
        """Return MD5 hex digest of a file's contents."""
        h = hashlib.md5()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def _load_cache(self) -> None:
        """Load all rules from SQLite into the in-memory cache."""
        try:
            rows = self.bridge.conn.execute(
                "SELECT rule_id, rule_data FROM kb_rules"
            ).fetchall()
            for row in rows:
                self._cache[row["rule_id"]] = json.loads(row["rule_data"])
        except Exception as e:
            print(f"[SOMA] _load_cache failed: {e}")
            self._cache = {}

    def _parse_rule_blocks(self, filepath: str) -> list[dict]:
        """Extract YAML rule blocks from a single markdown file.

        Returns a list of parsed dicts, one per RULE_BLOCK found.
        """
        try:
            with open(filepath, "r") as f:
                content = f.read()
        except Exception as e:
            print(f"[SOMA] _parse_rule_blocks failed to read {filepath}: {e}")
            return []

        rules = []
        lines = content.split("\n")
        i = 0
        while i < len(lines):
            start_match = _BLOCK_START.search(lines[i])
            if start_match:
                block_id = start_match.group(1)
                # Find the yaml fence inside this block
                i += 1
                yaml_lines = []
                in_yaml = False
                while i < len(lines):
                    if _BLOCK_END.search(lines[i]):
                        break
                    if not in_yaml and _YAML_FENCE_OPEN.match(lines[i].strip()):
                        in_yaml = True
                        i += 1
                        continue
                    if in_yaml and _YAML_FENCE_CLOSE.match(lines[i].strip()):
                        in_yaml = False
                        i += 1
                        continue
                    if in_yaml:
                        yaml_lines.append(lines[i])
                    i += 1

                if yaml_lines:
                    try:
                        parsed = yaml.safe_load("\n".join(yaml_lines))
                        if isinstance(parsed, dict) and "rule_id" in parsed:
                            rules.append(parsed)
                    except yaml.YAMLError as e:
                        print(f"[SOMA] YAML parse error in {filepath} block {block_id}: {e}")
            i += 1
        return rules

    def build_index(self):
        """Parse all .md files in knowledge/, extract YAML rule blocks, store in kb_rules.

        Phase 4.3 — after each rule is stored, validate table.column refs
        against the live SOMA schema. Invalid refs go to kb_violations
        (non-blocking — rule is still stored so the system never gets stuck).
        """
        if not _KB_DIR.is_dir():
            return

        now = self._now()

        # Phase 4.3 — lazy-load KBValidator for rule-reference checks.
        _validator = None
        try:
            from kb_validator import KBValidator
            _validator = KBValidator(self.bridge)
        except Exception as e:
            print(f"[SOMA] kb_reader: rule-ref validator unavailable: {e}")

        for md_file in sorted(_KB_DIR.glob("*.md")):
            file_hash = self._file_md5(md_file)
            source_file = md_file.name
            rules = self._parse_rule_blocks(md_file)

            for rule in rules:
                rule_id = rule["rule_id"]
                source_module = rule.get("source_module")
                if isinstance(source_module, list):
                    source_module = ",".join(source_module)
                confidence = rule.get("confidence", 1.0)
                rule_data_json = json.dumps(rule)

                try:
                    self.bridge.conn.execute(
                        """INSERT OR REPLACE INTO kb_rules
                           (rule_id, source_file, source_module, rule_data,
                            confidence, file_hash, parsed_at, schema_version)
                           VALUES (?, ?, ?, ?, ?, ?, ?, 3)""",
                        (rule_id, source_file, source_module, rule_data_json,
                         confidence, file_hash, now),
                    )
                except Exception as e:
                    print(f"[SOMA] kb_reader build_index failed for {rule_id}: {e}")

                # Phase 4.3 — rule-reference validation (non-blocking)
                if _validator is not None:
                    try:
                        _validator.validate_rule_references(
                            rule_id=rule_id,
                            rule_data=rule,
                            source_module=source_module or "SOMA",
                        )
                    except Exception as e:
                        print(f"[SOMA] kb_reader rule-ref validation failed for {rule_id}: {e}")

        try:
            self.bridge.conn.commit()
        except Exception as e:
            print(f"[SOMA] kb_reader commit failed: {e}")

        # Refresh in-memory cache
        self._cache.clear()
        self._load_cache()

    def is_index_stale(self) -> bool:
        """Compare current file hashes to stored hashes. Return True if any KB file changed."""
        if not _KB_DIR.is_dir():
            return True

        try:
            rows = self.bridge.conn.execute(
                "SELECT DISTINCT source_file, file_hash FROM kb_rules"
            ).fetchall()
        except Exception as e:
            print(f"[SOMA] is_index_stale failed: {e}")
            return True

        if not rows:
            # No rules indexed yet — check if any .md files exist
            return any(_KB_DIR.glob("*.md"))

        stored = {row["source_file"]: row["file_hash"] for row in rows}

        for md_file in _KB_DIR.glob("*.md"):
            try:
                current_hash = self._file_md5(md_file)
                if md_file.name not in stored or stored[md_file.name] != current_hash:
                    return True
            except Exception as e:
                print(f"[SOMA] could not compute hash for {md_file}: {e}")
                return True

        return False

    def refresh_cache(self) -> dict:
        """Phase 4.1 — reload changed rules from disk, mid-run.

        Calls `is_index_stale()`; if any KB file hash changed, runs
        `build_index()` (which also refreshes the in-memory cache). If
        nothing changed, just reloads the in-memory cache from SQLite
        in case another process wrote rules.

        Returns a summary dict: {reloaded: bool, cache_size: int}.
        Safe to call at the start of every `run_day.py` step.
        """
        try:
            stale = self.is_index_stale()
        except Exception as e:
            print(f"[SOMA] refresh_cache staleness check failed: {e}")
            stale = False

        if stale:
            try:
                self.build_index()  # also clears + reloads _cache
                return {"reloaded": True, "cache_size": len(self._cache)}
            except Exception as e:
                print(f"[SOMA] refresh_cache build_index failed: {e}")

        # Not stale — but another process may have updated kb_rules; refresh memory.
        self._cache.clear()
        self._load_cache()
        return {"reloaded": False, "cache_size": len(self._cache)}

    def get_rule(self, rule_id: str) -> dict:
        """Return parsed rule dict from cache. Raise KeyError if not found."""
        if rule_id not in self._cache:
            raise KeyError(f"Rule '{rule_id}' not found in KB index")
        return self._cache[rule_id]

    def get_rules_for_module(self, module_name: str) -> dict:
        """Return all rules where source_module contains module_name."""
        results = {}
        try:
            rows = self.bridge.conn.execute(
                "SELECT rule_id, rule_data FROM kb_rules WHERE source_module LIKE ?",
                (f"%{module_name}%",),
            ).fetchall()
            for row in rows:
                results[row["rule_id"]] = json.loads(row["rule_data"])
        except Exception as e:
            print(f"[SOMA] get_rules_for_module failed for {module_name}: {e}")
        return results

    def get_all_rules(self) -> dict:
        """Return dict of all rule_id -> rule_data."""
        return dict(self._cache)

    def log_rule_usage(self, rule_id, module, run_id=None, context=None):
        """Write to kb_audit_log."""
        try:
            now = self._now()
            context_json = json.dumps(context) if context else None
            self.bridge.conn.execute(
                """INSERT INTO kb_audit_log
                   (rule_id, read_by_module, read_at, run_id,
                    decision_context, write_timestamp)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (rule_id, module, now, run_id, context_json, now),
            )
            self.bridge.conn.commit()
        except Exception as e:
            print(f"[SOMA] log_rule_usage failed: {e}")

    def get_rule_audit(self, rule_id: str | None = None, module: str | None = None,
                       limit: int = 50) -> list[dict]:
        """Read audit log, optionally filtered by rule_id or module."""
        try:
            if rule_id and module:
                rows = self.bridge.conn.execute(
                    "SELECT * FROM kb_audit_log WHERE rule_id = ? AND read_by_module = ? "
                    "ORDER BY id DESC LIMIT ?",
                    (rule_id, module, limit),
                ).fetchall()
            elif rule_id:
                rows = self.bridge.conn.execute(
                    "SELECT * FROM kb_audit_log WHERE rule_id = ? ORDER BY id DESC LIMIT ?",
                    (rule_id, limit),
                ).fetchall()
            elif module:
                rows = self.bridge.conn.execute(
                    "SELECT * FROM kb_audit_log WHERE read_by_module = ? ORDER BY id DESC LIMIT ?",
                    (module, limit),
                ).fetchall()
            else:
                rows = self.bridge.conn.execute(
                    "SELECT * FROM kb_audit_log ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            print(f"[SOMA] get_rule_audit failed: {e}")
            return []
