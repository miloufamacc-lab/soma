# DABEIBA — Data Resilience & Cache Architecture

**Last updated:** 2026-03-21
**Applies to:** All modules (ORACLE, CIPHER, MANTIS, SOMA)

---

## Data Resilience Chain

Every piece of data in DABEIBA flows through a multi-tier protection chain.
Each tier is fire-and-forget — failure at any tier never crashes the pipeline.

```
TIER  LAYER              LOCATION                           RETENTION
─────────────────────────────────────────────────────────────────────────
 T0   API Protection     gurufocus_client.py                 Monthly gate
 T1   API Cache          oracle/cache/                       744h TTL (31d)
 T2   Snapshot Fallback  oracle/output/last_good_snapshot    Rolling + 3 backups
 T3   SOMA Database      shared/soma/data/soma.db            WAL mode, persistent
 T4   Local Backups      shared/soma/backups/                30 rolling copies
 T5   Cloud Offsite      ~/DABEIBA_Cloud/{module}/            7 daily + latest
 T6   What Changed Logs  shared/soma/logs/                   JSON archive (forever)
 T7   Git History        GitHub (miloufamacc-lab/*)          Full commit history
```

---

## T0: GuruFocus API Protection (ORACLE)

Three independent locks prevent erroneous API calls:

1. **Monthly refresh gate** — `_month_already_refreshed()` in `gurufocus_client.py`.
   After the first-of-month refresh is logged in `api_refresh_tracker.json`,
   ALL subsequent `GuruFocusClient()` instances set `_quota_exhausted = True`
   at construction time. This blocks the `_get()` HTTP method entirely.

2. **Hard call counter** — `_MAX_API_CALLS_PER_MONTH = 500`. Atomic file-locked
   counter incremented on every API call (including 429s). If count >= 500,
   `_quota_exhausted = True`.

3. **Cache TTL = 744 hours** — Set in `config/settings.py`. Cache files never
   expire within a calendar month, so `_get_cached()` always hits the file cache.

**Result:** After the monthly refresh, no code path in ORACLE can make a live
GuruFocus API call. Not `main.py`, not `add_ticker.py`, not even `--refresh-cache`.
The only way to make live calls is to manually edit `api_refresh_tracker.json`.

---

## T1: API File Cache (ORACLE)

- **Location:** `oracle/cache/{TICKER}_{endpoint}.json`
- **TTL:** 744 hours (configurable via `CACHE_TTL_HOURS` in settings.py)
- **Format:** Raw JSON response from GuruFocus API
- **Behavior:** `_get_cached()` checks file age, returns cached data if fresh,
  falls back to live API only if cache miss AND quota not exhausted

---

## T2: Snapshot Fallback (ORACLE)

- **Location:** `oracle/output/last_good_snapshot.json`
- **Trigger:** If API returns mostly empty data (<25% tickers have prices),
  ORACLE automatically falls back to the last good snapshot
- **Content:** Full ticker data + DCF valuations from last successful run
- **Redundancy:** 3 additional backup copies (.backup, .bak2, _backup.json)
- **Email tag:** `[CACHED]` added to subject line when using snapshot data

---

## T3: SOMA Database

- **Location:** `shared/soma/data/soma.db`
- **Mode:** SQLite with WAL (Write-Ahead Logging) — concurrent reads during writes
- **Schema:** Versioned via `migrations/` folder (current: v2)
- **Tables:** regime_history, valuations, trade_log, outlook_snapshots,
  portfolio_state, events, client_profiles, client_interactions
- **Traceability:** Every row has `write_timestamp` (ISO-8601) + `module_version`
- **Grouping:** `run_id` (UUID) links all writes from a single pipeline run
- **Freshness:** `is_fresh()` function — MANTIS aborts if regime data >48h stale

### Module Write Paths:
- **ORACLE → SOMA:** regime (GLI + VIX/UST10Y/DXY spot) + valuations (DCF)
- **MANTIS → SOMA:** trade_log + portfolio_state
- **CIPHER → SOMA:** outlook_snapshots (reads regime + valuations first)
- **add_ticker.py → SOMA:** UNIVERSE_ADD events

---

## T4: Local Backups

- **Location:** `shared/soma/backups/soma_backup_YYYYMMDD_HHMMSS.db`
- **Trigger:** Automatic — Step 0 of `run_day.py` before any pipeline work
- **Retention:** 30 most recent backups kept, older ones auto-pruned
- **Can also run standalone:** `python3 backup_soma.py`

---

## T5: Cloud Offsite Sync (Google Drive — jacobo.pae@gmail.com)

- **Symlink:** `~/DABEIBA_Cloud` → Google Drive `My Drive/DABEIBA/`
- **Setup:** Run once: `python3 ~/Desktop/DABEIBA/shared/setup_cloud.py`
- **Config:** `shared/cloud_config.py` — all modules import `get_cloud_dir("module_name")`
- **Structure:**
  ```
  ~/DABEIBA_Cloud/
      soma/       ← soma_latest.db + 7 daily snapshots
      oracle/     ← last_good_snapshot.json, api_tracker
      mantis/     ← backtest results, portfolio state
      cipher/     ← generated reports, outlooks
      exports/    ← on-demand exports (Excel, HTML, PDF)
  ```
- **Trigger:** Automatic — each module's backup script writes via `get_cloud_dir()`
- **Failure mode:** If symlink doesn't exist, all cloud writes silently skip
- **Provider-agnostic:** To switch from Google Drive to iCloud/Dropbox/etc.,
  just repoint the symlink. Zero code changes.

---

## T6: What Changed Logs

- **Location:** `shared/soma/logs/what_changed_YYYYMMDD_HHMMSS.json`
- **Content:** Regime transitions, GLI deltas, momentum flips, valuation changes
- **Thresholds:** 7 quantitative triggers (from Grok's cross-AI review)
- **Materiality:** Scored 0-5, with historical context for similar past events

---

## T7: Git History

- **Repos:** `miloufamacc-lab/{oracle, cipher, mantis, soma}`
- **Auto-backup:** `oracle/run_git_backup.sh` (weekly via launchd or manual)
- **Note:** Database files (.db) and cache directories are .gitignored

---

## Recovery Playbook

| Scenario | Recovery Path |
|----------|--------------|
| API down mid-month | T1 cache serves all requests (744h TTL) |
| API returns garbage | T2 snapshot fallback auto-triggers |
| SOMA corrupted | T4 local backup → copy to data/soma.db |
| Disk failure | T5 Google Drive → download from ~/DABEIBA_Cloud/ |
| Need historical state | T6 What Changed logs + T7 git history |
| Accidental code change | T7 git revert |
