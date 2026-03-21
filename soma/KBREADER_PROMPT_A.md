# Claude Code Prompt A — KB Runtime Reader Infrastructure

## Context
SOMA is in ~/Desktop/DABEIBA/shared/soma/. It has:
- `soma_bridge.py` — SQLite read/write API (SomaBridge class, context manager, WAL mode, fire-and-forget writes)
- `knowledge/` — 4 KB markdown files (macro_regimes.md, valuation_models.md, communication_compliance.md, mantis_mechanics.md)
- `migrations/001_initial_schema.sql` and `002_client_profiles.sql` — numbered migration pattern
- `pyproject.toml` — installed via `pip install -e .`
- Schema is currently at v2

The KB files contain CFA knowledge in prose/tables. We're adding YAML rule blocks inside the KB markdown that modules can read at runtime. Format example (this will be added to KB files in a separate step):

```markdown
### 2.1 Target Allocations by Regime

(prose and tables stay as-is)

<!-- RULE_BLOCK: REGIME_ALLOCATIONS_V1 -->
```yaml
rule_id: REGIME_ALLOCATIONS_V1
source_module: [ORACLE, MANTIS]
confidence: 0.95
rules:
  RISK_ON_REBOUND:
    equity_target: [0.80, 0.95]
    cash_floor: 0.05
    risk_appetite: aggressive
  RISK_ON_EXPANSION:
    equity_target: [0.70, 0.85]
    cash_floor: 0.10
    risk_appetite: growth
  TURBULENCE:
    equity_target: [0.50, 0.65]
    cash_floor: 0.20
    risk_appetite: defensive
  CONTRACTION:
    equity_target: [0.30, 0.50]
    cash_floor: 0.30
    risk_appetite: preservation
```
<!-- END_RULE_BLOCK -->
```

## Task: Build 4 files

### 1. `migrations/003_kb_rules.sql`

Create two tables:

```sql
CREATE TABLE IF NOT EXISTS kb_rules (
    rule_id         TEXT PRIMARY KEY,
    source_file     TEXT NOT NULL,
    source_module   TEXT,              -- comma-separated: "ORACLE,MANTIS"
    rule_data       TEXT NOT NULL,     -- JSON of the YAML rule block
    confidence      REAL DEFAULT 1.0,
    file_hash       TEXT,              -- MD5 of source file at parse time
    parsed_at       TEXT NOT NULL,     -- ISO-8601
    schema_version  INTEGER DEFAULT 3
);

CREATE TABLE IF NOT EXISTS kb_audit_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id         TEXT NOT NULL,
    read_by_module  TEXT NOT NULL,     -- ORACLE, CIPHER, MANTIS
    read_at         TEXT NOT NULL,     -- ISO-8601
    run_id          TEXT,              -- links to SOMA run_id
    decision_context TEXT,             -- JSON: what triggered the read
    write_timestamp TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_rule ON kb_audit_log(rule_id);
CREATE INDEX IF NOT EXISTS idx_audit_module ON kb_audit_log(read_by_module);

INSERT OR IGNORE INTO schema_version (version, applied_at, description)
VALUES (3, datetime('now'), 'KB rules index + audit log (Phase 2.3b)');
```

### 2. `kb_reader.py`

```python
class KBReader:
    """
    Deterministic rule retrieval from KB markdown files.

    Parses YAML rule blocks embedded in KB markdown (between
    <!-- RULE_BLOCK: ID --> and <!-- END_RULE_BLOCK --> markers).
    Caches parsed rules in SQLite (kb_rules table).
    Provides get_rule(rule_id) for modules to read at runtime.
    Logs every read to kb_audit_log for full traceability.
    """
```

Methods needed:
- `__init__(self, soma_bridge)` — takes an active SomaBridge instance
- `build_index(self)` — parse all .md files in knowledge/, extract YAML rule blocks, store in kb_rules table. Use MD5 hash of each file to detect changes.
- `is_index_stale(self)` — compare current file hashes to stored hashes. Return True if any KB file changed.
- `get_rule(self, rule_id)` — return parsed rule dict from cache. Raise KeyError if not found.
- `get_rules_for_module(self, module_name)` — return all rules where source_module contains module_name.
- `get_all_rules(self)` — return dict of all rule_id → rule_data.
- `log_rule_usage(self, rule_id, module, run_id=None, context=None)` — write to kb_audit_log.
- `get_rule_audit(self, rule_id=None, module=None, limit=50)` — read audit log.

Parsing logic:
1. Walk all .md files in knowledge/
2. Find blocks between `<!-- RULE_BLOCK: {ID} -->` and `<!-- END_RULE_BLOCK -->`
3. Inside those markers, find the ```yaml ... ``` code block
4. Parse YAML with `yaml.safe_load()`
5. Validate: must have `rule_id` field
6. Store: rule_id, source_file, source_module (from YAML), rule_data (as JSON), confidence, file MD5, timestamp
7. In-memory cache: dict of rule_id → parsed dict (loaded from SQLite on init, refreshed on build_index)

Import: `import yaml, json, hashlib, os, re`
Dependencies: PyYAML (add to pyproject.toml if not there)

Fire-and-forget pattern: all writes wrapped in try/except like SomaBridge.

### 3. Extend `soma_bridge.py`

Add these methods to SomaBridge class (after the client profile methods):

```python
# ── KB RULES (Phase 2.3b — Runtime KB Reader) ─────────────────────

def get_kb_reader(self):
    """Lazy-initialize and return a KBReader instance."""
    if not hasattr(self, '_kb_reader'):
        from soma.kb_reader import KBReader
        self._kb_reader = KBReader(self)
    return self._kb_reader

def get_rule(self, rule_id):
    """Convenience wrapper: get a KB rule by ID."""
    return self.get_kb_reader().get_rule(rule_id)

def log_rule_usage(self, rule_id, module, run_id=None, context=None):
    """Convenience wrapper: log a KB rule read."""
    self.get_kb_reader().log_rule_usage(rule_id, module, run_id, context)
```

### 4. Add to `soma_query.py`

Add a "rules" query section:
- `"rules"` or `"kb rules"` → list all indexed rules (rule_id, source_file, confidence)
- `"rule REGIME_ALLOCATIONS_V1"` → show full rule data
- `"rule audit"` → show last 20 audit log entries
- `"rebuild index"` → trigger KBReader.build_index()

Add to the help text under a "KB RULES" section.
Add to the router.
Add to the health check (show rule count + last indexed time).

### 5. Test everything

After building all files:
1. Run migration: `python3 -c "from soma.soma_bridge import SomaBridge; db=SomaBridge(); db.__enter__(); db.initialize_db(); print('v'+str(db.get_schema_version()))"`
2. Build should print "Schema v3"
3. Since no rule blocks exist in KB files yet, `get_all_rules()` should return empty dict
4. Create a test: write a temporary .md file with a RULE_BLOCK, parse it, verify extraction, clean up

## Important
- Follow existing code style exactly (ANSI colors, _title(), _no_data(), fire-and-forget pattern)
- Do NOT modify the existing KB markdown files — that's a separate prompt
- PyYAML: add `pyyaml` to pyproject.toml dependencies if not already there
- All new files go in ~/Desktop/DABEIBA/shared/soma/
- Commit when done: `git add -A && git commit -m "KB runtime reader: kb_reader.py, kb_rules table, audit log, query CLI integration"`
