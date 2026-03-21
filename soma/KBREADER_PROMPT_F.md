# Claude Code Prompt F — Orchestration: Auto-Rebuild KB Index + Status Dashboard

## Context
SOMA is in ~/Desktop/DABEIBA/shared/soma/. Prompts A+B built the KB reader. Prompts C+D+E wired ORACLE, MANTIS, CIPHER to read rules. This prompt closes the loop: **run_day.py** auto-rebuilds the KB index when files change, and **soma_status.py** shows KB health at a glance.

## Files to Modify

### 1. Modify `run_day.py` — Add KB index rebuild step

Find the daily orchestrator steps (it currently has 7 steps: backup → ORACLE → What Changed → status → MANTIS portfolio → CIPHER outlook → action items).

**Add a new Step 0 (before everything else): KB Index Check**

**IMPORTANT:** run_day.py does NOT use a SomaBridge context manager for all steps — each step function opens its own connections as needed. The existing steps are standalone functions called from `main()`. Follow the same pattern.

The existing helper functions in run_day.py are:
- `_header(step, title)` — prints section header with step number
- `_step_ok(msg)` — prints green OK message
- `_step_fail(msg)` — prints red FAIL message
- ANSI codes: BOLD, DIM, RED, GREEN, YELLOW, CYAN, RESET

```python
# ── NEW Step: KB Index (insert BEFORE step_0_backup) ──────────────

def step_kb_index():
    """Rebuild KB rule index if any knowledge files changed."""
    _header("KB", "Knowledge Base Index")
    try:
        from shared.soma.soma_bridge import SomaBridge
        with SomaBridge() as db:
            db.initialize_db()
            kr = db.get_kb_reader()
            if kr.is_index_stale():
                print(f"  {YELLOW}KB files changed — rebuilding index...{RESET}")
                kr.build_index()
                rules = kr.get_all_rules()
                _step_ok(f"{len(rules)} rules re-indexed")
            else:
                rules = kr.get_all_rules()
                _step_ok(f"{len(rules)} rules up to date (no changes)")
            return True
    except Exception as e:
        _step_fail(f"KB index check failed: {e}")
        print(f"  {DIM}Continuing without KB — modules will use fallback values{RESET}")
        return True  # non-fatal — don't abort the pipeline
```

Add `step_kb_index()` as the FIRST call in `main()`, BEFORE `step_0_backup()`.

Update the docstring at the top of the file to include the KB step:
```
Steps:
    [KB]  KB Index Check — rebuild if knowledge files changed
    [0/6] Backup soma.db
    [1/6] Run ORACLE → writes regime + valuations to SOMA
    ...
```

Do NOT renumber existing steps (0-6) — just insert KB before them.

### 2. Modify `soma_status.py` — Add KB Rules section

Find the status dashboard rendering. Add a new section after the existing ones:

**IMPORTANT:** soma_status.py renders everything inside a single `with SomaBridge(db_path) as db:` block (lines 54-64), then renders OUTSIDE that block using the fetched data. The KB section needs to either:
(a) Fetch KB data inside the existing `with` block and render outside it, OR
(b) Open its own `with SomaBridge()` block for the KB section.

Option (b) is simpler and more consistent with the fire-and-forget pattern. The existing helper functions are `_bar(title)` and `_fresh_label(is_fresh, age_hours)`.

```python
# ── KB Rules Status ────────────────────────────────────────────────
# Add this section AFTER the SYSTEM HEALTH section, still inside print_status()
# Open a fresh SomaBridge connection for KB data:

    # KB RULES (after the "=" divider at the end, BEFORE it)
    print(f"\n{_bar('KB RULES')}")
    try:
        with SomaBridge(db_path) as db2:
            db2.initialize_db()
            kr = db2.get_kb_reader()
            rules = kr.get_all_rules()
            if not rules:
                print(f"  {DIM}No rules indexed. Run: python3 soma_query.py 'rebuild index'{RESET}")
            else:

                # Summary line
                stale = kr.is_index_stale()
                status_str = f"{YELLOW}STALE — rebuild needed{RESET}" if stale else f"{GREEN}current{RESET}"
                print(f"  Rules: {len(rules)}  |  Index: {status_str}")

                # Rules by source module
                by_module = {}
                for rid, rdata in rules.items():
                    modules = rdata.get("source_module", "UNKNOWN")
                    if isinstance(modules, list):
                        for m in modules:
                            by_module.setdefault(m, []).append(rid)
                    elif isinstance(modules, str):
                        for m in modules.split(","):
                            by_module.setdefault(m.strip(), []).append(rid)

                for module in sorted(by_module):
                    rule_ids = by_module[module]
                    print(f"  {module}: {len(rule_ids)} rules")

                # Recent audit activity (last 3 — keep dashboard compact)
                audits = kr.get_rule_audit(limit=3)
                if audits:
                    print(f"  Last read: {audits[0].get('read_at', '?')[:16]} by {audits[0].get('read_by_module', '?')}")
    except Exception as e:
        print(f"  {DIM}KB status unavailable: {e}{RESET}")
```

Insert this section in `print_status()` just BEFORE the final `print(f"\n{BOLD}{'=' * W}{RESET}\n")` line (line 219).

### 3. Modify `soma_query.py` — Enhance KB query output

The "rules" query section was added in Prompt A. Enhance it:

**Add "kb health" query:**

```python
# In the router, add:
elif query_lower in ("kb health", "kb status"):
    return query_kb_health(db)

def query_kb_health(db):
    """Comprehensive KB health check."""
    print(f"\n{BOLD}KB Health Report{RESET}")
    try:
        kr = db.get_kb_reader()
        rules = kr.get_all_rules()
        stale = kr.is_index_stale()

        print(f"  Total rules: {len(rules)}")
        print(f"  Index stale: {'YES — run: rebuild index' if stale else 'No'}")
        print()

        # Count by source file
        by_file = {}
        for rid, rdata in rules.items():
            sf = rdata.get("source_file", "unknown")
            by_file.setdefault(sf, []).append(rid)

        print("  Rules by file:")
        for f in sorted(by_file):
            print(f"    {f}: {len(by_file[f])} rules")
        print()

        # Audit summary
        audits = kr.get_rule_audit(limit=100)
        if audits:
            modules_seen = set(a.get("read_by_module", "?") for a in audits)
            print(f"  Audit entries: {len(audits)} (modules: {', '.join(sorted(modules_seen))})")
            # Most-read rules
            from collections import Counter
            reads = Counter(a.get("rule_id") for a in audits)
            print("  Most read:")
            for rid, count in reads.most_common(5):
                print(f"    {rid}: {count} reads")
        else:
            print("  No audit entries yet")

    except Exception as e:
        print(f"  ⚠ {e}")
```

**Add to help text:**

```
KB RULES
  rules              — list all indexed KB rules
  rule [ID]          — show full rule data
  rule audit         — show recent rule reads (audit log)
  rebuild index      — re-parse KB files and update index
  kb health          — comprehensive KB health report
```

### 4. Update `knowledge/changelog.md`

Add entry for Schema v3 + KB runtime reader:

```markdown
## Schema v3 — 2026-03-21
- **KB Runtime Reader (Phase 2.3b):** `kb_rules` + `kb_audit_log` tables
- KBReader: parses YAML rule blocks from KB markdown, caches in SQLite
- 12 rule blocks added across 4 KB files (REGIME_ALLOCATIONS, POSITION_SIZING, DRAWDOWN_CONTROLS, ADVICE_FRAMEWORK, etc.)
- Every rule read logged to kb_audit_log for full traceability
- soma_query.py: "rules", "rule [ID]", "rule audit", "rebuild index", "kb health"
- run_day.py: auto-rebuilds KB index if knowledge files changed (Step 0)
- soma_status.py: KB Rules section showing rule count, staleness, audit activity
- ORACLE/MANTIS/CIPHER wired to read rules via kb_integration.py modules (with fallbacks)
```

## Testing

```bash
# 1. Test run_day.py KB index step
cd ~/Desktop/DABEIBA/shared/soma
python3 -c "
from soma.soma_bridge import SomaBridge
with SomaBridge() as db:
    db.initialize_db()
    kr = db.get_kb_reader()
    # Simulate run_day Step 0
    if kr.is_index_stale():
        print('Index stale — rebuilding...')
        kr.build_index()
    rules = kr.get_all_rules()
    print(f'{len(rules)} rules indexed')
"

# 2. Test soma_status KB section
python3 soma_status.py

# 3. Test kb health query
python3 soma_query.py "kb health"

# 4. Test rebuild index
python3 soma_query.py "rebuild index"
python3 soma_query.py "rules"

# 5. Full run_day dry run
python3 run_day.py
```

## Important

- Step 0 (KB index) runs BEFORE anything else — modules need fresh rules
- If KB index fails, print warning but DON'T abort the run — modules have fallbacks
- soma_status.py KB section should be concise (one-screen dashboard constraint)
- Follow existing code style: ANSI colors (BOLD, DIM, RED, GREEN, YELLOW, CYAN, RESET), `_header(step, title)` in run_day.py, `_bar(title)` in soma_status.py
- Commit when done: `git add -A && git commit -m "KB orchestration: run_day auto-rebuild, soma_status KB section, kb health query"`
