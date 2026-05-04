"""
DABEIBA Staging Batch Processor — Routes intelligence artifacts to consumers.

Scans shared/soma/staging/ for YAML files, reads the `type:` header, and routes
each file to the appropriate handler (SOMA DB writes, wiki updates, model flags).

Usage:
    # From run_day.py (daily batch):
    from shared.soma.staging_dispatcher import StagingDispatcher
    from shared.soma.soma_bridge import SomaBridge
    with SomaBridge() as db:
        dispatcher = StagingDispatcher(staging_dir, db)
        results = dispatcher.process_all()

    # CLI (on-demand):
    python3 shared/soma/staging_dispatcher.py [--dry-run]

Design principles:
    - Handlers MUST NOT write new files to staging/ (no circular triggers)
    - Per-file error isolation (one bad file doesn't kill the batch)
    - DB-backed processing log for idempotency (dedup by source_hash)
    - Advisory lock prevents concurrent runs
    - 90-day cleanup of processed/ directory

See: ~/Desktop/DABEIBA/tasks/CROSS_SKILL_INTEGRATION_PLAN.md for full architecture.
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
import re
import shutil
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import yaml

# Phase 4.4 — parallelization tuning
_DISPATCHER_MAX_WORKERS = int(os.environ.get("SOMA_DISPATCHER_WORKERS", "4"))
# Handlers that write to disk (wiki files) or that call other handlers
# must run serially to avoid concurrent file-write collisions.
_SERIAL_TYPES = {"WIKI_UPDATE", "VALUATION"}

# ── Path setup ────────────────────────────────────────────────────────
_THIS = Path(__file__).resolve()
_PROJECT_ROOT = str(_THIS.parent.parent.parent)
for _p in [_PROJECT_ROOT, str(_THIS.parent.parent), str(_THIS.parent)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from shared.soma.soma_bridge import SomaBridge

log = logging.getLogger("staging_dispatcher")

# ── Processing priority (lower = first) ──────────────────────────────
TYPE_PRIORITY = {
    "MODEL_FLAG": 0,
    "PRISM": 1,
    "DOCTRINE_EVIDENCE": 2,
    "DOCTRINE_CANDIDATE": 2,
    "HORIZON": 3,
    "WIKI_UPDATE": 4,
    "VALUATION": 5,
    # Phase 5.1 — RAPTOR inbound
    "PROSPECT_CANDIDATE": 6,
    "REFERRAL_EVENT": 6,
}

MODULE_VERSION = "staging_dispatcher_v1"


class StagingDispatcher:
    """Batch processor for DABEIBA staging files."""

    def __init__(self, staging_dir=None, soma_bridge=None):
        if staging_dir is None:
            staging_dir = Path(os.path.expanduser(
                "~/Desktop/DABEIBA/shared/soma/staging"
            ))
        self.staging_dir = Path(staging_dir)
        self.processed_dir = self.staging_dir / "processed"
        self.errors_dir = self.staging_dir / "errors"
        self.lock_file = self.staging_dir / ".lock"
        self.soma = soma_bridge
        self.processed_dir.mkdir(exist_ok=True)
        self.errors_dir.mkdir(exist_ok=True)

        # Handler registry — add new types here
        self.handlers = {
            "PRISM": self._handle_prism,
            "DOCTRINE_EVIDENCE": self._handle_doctrine_evidence,
            "DOCTRINE_CANDIDATE": self._handle_doctrine_candidate,
            "HORIZON": self._handle_horizon,
            "MODEL_FLAG": self._handle_model_flag,
            "WIKI_UPDATE": self._handle_wiki_update,
            "VALUATION": self._handle_valuation,
            "STANCE_DRIFT": self._handle_stance_drift,
            # Phase 5.1 — RAPTOR inbound
            "PROSPECT_CANDIDATE": self._handle_prospect_candidate,
            "REFERRAL_EVENT": self._handle_referral_event,
        }

        # Phase 4.4 — thread-safety primitives for parallel dispatch.
        # _soma_lock serializes all SomaBridge method calls (SQLite connection
        # is not shared-across-threads safe by default). _results_lock guards
        # mutation of the results dict.
        self._soma_lock = threading.Lock()
        self._results_lock = threading.Lock()

    # ── Main entry point ─────────────────────────────────────────────

    def process_all(self, dry_run=False):
        """Batch-scan staging/ for unprocessed YAML files, route to handlers.

        Returns summary dict for run_day.py integration.
        """
        # Advisory lock
        lock_fd = None
        try:
            lock_fd = open(self.lock_file, "w")
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (IOError, OSError):
            log.warning("Dispatcher already running (lock held). Skipping.")
            return {"skipped": True, "reason": "lock_held"}

        results = {
            "processed": 0,
            "errors": 0,
            "skipped": 0,
            "dry_run": dry_run,
            "model_flags": [],
            "wiki_updates": [],
            "doctrine_evidence": [],
            "by_type": {},
        }

        try:
            files = sorted(
                self.staging_dir.glob("*.yaml"),
                key=lambda f: (TYPE_PRIORITY.get(self._peek_type(f), 99), f.name),
            )
            if not files:
                log.info("No staging files to process.")

            # Phase 4.4 — split into parallel-safe vs serial buckets.
            # WIKI_UPDATE / VALUATION handlers touch the wiki filesystem and
            # must run serially to avoid concurrent writes to the same slug.
            # Everything else (SOMA-only writes) is parallel-safe under the
            # shared _soma_lock.
            parallel_files = [
                f for f in files if self._peek_type(f) not in _SERIAL_TYPES
            ]
            serial_files = [
                f for f in files if self._peek_type(f) in _SERIAL_TYPES
            ]

            # Parallel pass
            if parallel_files:
                max_workers = max(1, min(_DISPATCHER_MAX_WORKERS, len(parallel_files)))
                log.info(
                    f"Dispatching {len(parallel_files)} parallel-safe file(s) "
                    f"with {max_workers} worker(s)"
                )
                with ThreadPoolExecutor(max_workers=max_workers) as pool:
                    futures = [
                        pool.submit(self._process_one, f, results, dry_run)
                        for f in parallel_files
                    ]
                    for fut in as_completed(futures):
                        # _process_one handles its own errors; reap exceptions here.
                        try:
                            fut.result()
                        except Exception as e:
                            log.error(f"Dispatcher worker crashed: {e}")
                            with self._results_lock:
                                results["errors"] += 1

            # Serial pass — WIKI_UPDATE / VALUATION
            for f in serial_files:
                self._process_one(f, results, dry_run)
        finally:
            if lock_fd:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
                lock_fd.close()

        if not dry_run:
            self._cleanup_old(days=90)
        self._write_log(results)
        return results

    # ── File processing ──────────────────────────────────────────────

    def _peek_type(self, filepath):
        """Quick-read type field without full YAML parse (for sorting)."""
        try:
            with open(filepath) as f:
                for line in f:
                    if line.startswith("type:"):
                        return line.split(":", 1)[1].strip().strip("\"'")
        except Exception:
            pass
        return "UNKNOWN"

    def _process_one(self, filepath, results, dry_run=False):
        """Process one staging file with full error isolation.

        Phase 4.4 — thread-safe: all SomaBridge calls go through self._soma_lock,
        all results mutations through self._results_lock. YAML parse + file I/O
        run without locks (thread-safe / per-file).
        """
        # Parse YAML (no lock — pure file read + parse)
        try:
            doc = yaml.safe_load(filepath.read_text(encoding="utf-8"))
        except yaml.YAMLError as e:
            log.error(f"YAML parse error in {filepath.name}: {e}")
            if not dry_run:
                shutil.move(str(filepath), str(self.errors_dir / filepath.name))
                with self._soma_lock:
                    self.soma.log_staging_event(
                        filepath.name, "UNKNOWN", "error", str(e)
                    )
            with self._results_lock:
                results["errors"] += 1
            return

        if not isinstance(doc, dict):
            log.error(f"Invalid YAML structure in {filepath.name}")
            if not dry_run:
                shutil.move(str(filepath), str(self.errors_dir / filepath.name))
                with self._soma_lock:
                    self.soma.log_staging_event(
                        filepath.name, "UNKNOWN", "error", "Invalid structure"
                    )
            with self._results_lock:
                results["errors"] += 1
            return

        # Infer type from filename prefix if not in YAML (legacy file support)
        if "type" not in doc:
            inferred = self._infer_type_from_filename(filepath.name)
            if inferred:
                doc["type"] = inferred
                log.info(f"Inferred type '{inferred}' from filename {filepath.name}")
            else:
                log.error(f"Missing 'type' field in {filepath.name}")
                if not dry_run:
                    shutil.move(str(filepath), str(self.errors_dir / filepath.name))
                    with self._soma_lock:
                        self.soma.log_staging_event(
                            filepath.name, "UNKNOWN", "error", "Missing type field"
                        )
                with self._results_lock:
                    results["errors"] += 1
                return

        doc_type = doc["type"]
        source_hash = doc.get("source_hash")

        # Idempotency check (SOMA read)
        if source_hash:
            with self._soma_lock:
                already = self.soma.staging_hash_exists(source_hash, doc_type)
            if already:
                log.info(
                    f"Dedup: {filepath.name} (hash {source_hash}) already processed."
                )
                if not dry_run:
                    shutil.move(str(filepath), str(self.processed_dir / filepath.name))
                with self._results_lock:
                    results["skipped"] += 1
                return

        handler = self.handlers.get(doc_type)
        if not handler:
            log.warning(f"Unknown type '{doc_type}' in {filepath.name}")
            with self._results_lock:
                results["skipped"] += 1
            return  # leave in staging/ for future handler

        if dry_run:
            log.info(f"[DRY RUN] Would process {filepath.name} as {doc_type}")
            with self._results_lock:
                results["processed"] += 1
            return

        # Execute handler — all handlers touch SOMA; serialize under the lock.
        try:
            with self._soma_lock:
                handler(doc, filepath)
        except Exception as e:
            log.error(f"Handler '{doc_type}' failed on {filepath.name}: {e}")
            with self._soma_lock:
                self.soma.log_staging_event(
                    filepath.name, doc_type, "error", str(e), source_hash
                )
            shutil.move(str(filepath), str(self.errors_dir / filepath.name))
            with self._results_lock:
                results["errors"] += 1
            return

        # Log success + move
        with self._soma_lock:
            self.soma.log_staging_event(
                filepath.name, doc_type, "processed", source_hash=source_hash
            )
        shutil.move(str(filepath), str(self.processed_dir / filepath.name))

        with self._results_lock:
            results["processed"] += 1
            results["by_type"][doc_type] = results["by_type"].get(doc_type, 0) + 1
            # Collect summary
            if doc_type == "MODEL_FLAG":
                results["model_flags"].append(doc.get("ticker"))
            elif doc_type == "WIKI_UPDATE":
                results["wiki_updates"].append(doc.get("slug"))
            elif doc_type in ("DOCTRINE_EVIDENCE", "DOCTRINE_CANDIDATE"):
                results["doctrine_evidence"].append(doc.get("belief_id"))

    # ── Handlers ─────────────────────────────────────────────────────

    def _handle_prism(self, doc, filepath):
        """Ingest PRISM routing records into soma.db raw_intelligence."""
        intake = doc.get("prism_intake", doc)
        # Normalize: single record (dict) → list of one
        records = intake if isinstance(intake, list) else [intake]
        for record in records:
            self.soma.write_raw_intelligence(
                source_type=record.get("source_type", "transcript"),
                source_url=record.get("source_url", ""),
                title=(
                    record.get("key_claims", [""])[0][:80]
                    if record.get("key_claims")
                    else filepath.stem
                ),
                content=json.dumps(record.get("key_claims", [])),
                category=record["category"],
                target_pipeline=record["target_pipeline"],
                relevance_score=record.get("relevance_score", 5),
                key_claims_json=json.dumps(record.get("key_claims", [])),
                tags_json=json.dumps(record.get("tags", [])),
            )

    def _handle_doctrine_evidence(self, doc, filepath):
        """Ingest evidence for an existing DOCTRINE belief.

        Phase 3.3 extension — accept red-team shape:
          {claim, stance: counter, counter_argument, steelman_strength, ...}
        If `belief_id` is absent, synthesize one from hash(claim) and map
        `stance: counter` → supports=False. Impact/steelman strength map to
        evidence weight: STRONG=1.5, MODERATE=1.0, WEAK=0.5.
        """
        belief_id = doc.get("belief_id")
        supports = doc.get("supports", True)
        weight = doc.get("weight", 1.0)

        # Red-team counter path
        if not belief_id and doc.get("claim"):
            import hashlib as _h
            belief_id = "RT_" + _h.sha1(doc["claim"].encode("utf-8")).hexdigest()[:14]
            if doc.get("stance") == "counter":
                supports = False
            strength = (doc.get("steelman_strength") or "").upper()
            weight = {"STRONG": 1.5, "MODERATE": 1.0, "WEAK": 0.5}.get(strength, 1.0)

        if not belief_id:
            raise ValueError("DOCTRINE_EVIDENCE requires belief_id or claim")

        detail = doc.get("source_detail") or doc.get("counter_argument") or ""
        self.soma.write_evidence(
            belief_id=belief_id,
            source_module=doc.get("source", "PRISM"),
            source_detail=detail[:500],
            supports=supports,
            weight=weight,
        )

    def _handle_doctrine_candidate(self, doc, filepath):
        """Insert candidate belief as inactive for human review."""
        self.soma.add_belief_candidate(
            belief_id=doc["belief_id"],
            domain=doc["domain"],
            statement=doc["statement"],
            conviction=doc.get("conviction", 5),
            is_active=0,
        )

    def _handle_horizon(self, doc, filepath):
        """Ingest timing signal into horizon_analyses table."""
        signal = doc.get("horizon_signal", doc)
        self.soma.write_horizon_signal(
            lens=signal.get("lens", "MACRO"),
            direction=signal.get("direction", "NEUTRAL"),
            timeframe=signal.get("timeframe", ""),
            signal_detail=signal.get("signal_detail", ""),
            confidence=signal.get("confidence", 0.5),
            speaker_tier=signal.get("speaker_tier"),
            source=signal.get("source", ""),
        )

    def _handle_model_flag(self, doc, filepath):
        """Write model flag to soma.db. Auto-detect stale models."""
        ticker = doc["ticker"]

        self.soma.write_model_flag(
            ticker=ticker,
            flag_type=doc.get("flag", "FRESH_INTEL"),
            source=doc.get("source", ""),
            source_hash=doc.get("source_hash"),
            claims_summary=json.dumps(doc.get("claims_summary", [])),
            impact_on_valuation=doc.get("impact_on_valuation", ""),
        )

        # If existing model → add stale trigger
        model_dir = Path(os.path.expanduser(f"~/Desktop/DABEIBA/models/{ticker}"))
        if model_dir.is_dir():
            self.soma.write_model_flag(
                ticker=ticker,
                flag_type="STALE_TRIGGER",
                source=doc.get("source", ""),
                source_hash=doc.get("source_hash"),
                suggested_action=(
                    "deep_update"
                    if doc.get("impact_on_valuation")
                    else "refresh"
                ),
            )

    def _handle_stance_drift(self, doc, filepath):
        """Phase 3.2 — upsert speaker_accuracy.drift_count + raw_intelligence."""
        speaker = doc.get("speaker")
        topic = doc.get("topic")
        prior = doc.get("prior_stance")
        new = doc.get("new_stance")
        if not speaker or not topic:
            raise ValueError("STANCE_DRIFT requires 'speaker' and 'topic' fields")
        self.soma.write_stance_drift(
            speaker=speaker,
            topic=topic,
            prior_stance=prior,
            new_stance=new,
            as_of_prior=doc.get("as_of_prior"),
            as_of_new=doc.get("as_of_new"),
            source=doc.get("source", ""),
            details_json=doc.get("details_json"),
        )

    def _handle_prospect_candidate(self, doc, filepath):
        """Phase 5.1 — upsert a RAPTOR prospect from an inbound staging YAML.

        Required: prospect_id (str). Everything else is optional and maps 1:1
        to the raptor_prospects schema. Safe to re-dispatch: we UPDATE if the
        prospect already exists, INSERT if not.
        """
        prospect_id = doc.get("prospect_id")
        if not prospect_id:
            raise ValueError("PROSPECT_CANDIDATE requires 'prospect_id'")

        # Whitelist kwargs to schema columns (ignore type/source_hash/etc).
        fields = {
            k: v for k, v in doc.items()
            if k in {
                "first_name", "last_name", "display_name",
                "email", "phone", "linkedin_url",
                "language_pref", "province", "city",
                "estimated_assets_band", "current_custodian",
                "source_type", "source_detail",
                "pipeline_stage", "lead_score", "lead_score_updated",
                "notes", "module_version", "created_date",
            }
        }

        existing = self.soma.get_prospect(prospect_id)
        if existing:
            # In-place update (write_prospect would error on PK conflict).
            self.soma.update_prospect(prospect_id, **fields)
        else:
            self.soma.write_prospect(prospect_id, **fields)

    def _handle_referral_event(self, doc, filepath):
        """Phase 5.1 — log a COI referral into raptor_referrals.

        Required: coi_id, prospect_id, referral_date.
        Optional: disclosure_delivered, disclosure_date, outcome.
        """
        for required in ("coi_id", "prospect_id", "referral_date"):
            if not doc.get(required):
                raise ValueError(f"REFERRAL_EVENT requires '{required}'")

        # Guard: both ends of the foreign key must exist.
        if not self.soma.get_coi(doc["coi_id"]):
            raise ValueError(f"REFERRAL_EVENT: unknown coi_id '{doc['coi_id']}'")
        if not self.soma.get_prospect(doc["prospect_id"]):
            raise ValueError(
                f"REFERRAL_EVENT: unknown prospect_id '{doc['prospect_id']}'"
            )

        self.soma.write_referral(
            coi_id=doc["coi_id"],
            prospect_id=doc["prospect_id"],
            referral_date=doc["referral_date"],
            disclosure_delivered=bool(doc.get("disclosure_delivered", False)),
            disclosure_date=doc.get("disclosure_date"),
            outcome=doc.get("outcome", "pending"),
        )

    def _handle_wiki_update(self, doc, filepath):
        """Create or append to a wiki article.

        Phase 5.5 — dedup check: before writing, consult the wiki's
        `articles_meta` index for this slug. If an article already exists
        anywhere under `wiki/`, append to the existing path instead of
        creating a duplicate under the default `domain/subdomain`. Prevents
        silent fan-out when the same slug shows up with a different
        (domain, subdomain) than the original article.
        """
        slug = doc["slug"]
        domain = doc.get("domain", "finance")
        subdomain = doc.get("subdomain", "reports")
        content_source = doc.get("content_source", "")
        action = doc.get("action", "CREATE_OR_APPEND")

        wiki_root = Path(os.path.expanduser("~/Desktop/DABEIBA/wiki"))

        # Phase 5.5 — check articles_meta for an existing slug anywhere.
        existing_path = self._wiki_existing_path(slug, wiki_root)
        if existing_path and action == "CREATE_OR_APPEND":
            target_file = existing_path
            target_dir = target_file.parent
        else:
            target_dir = wiki_root / "compiled" / domain / subdomain
            target_file = target_dir / f"{slug}.md"
        target_dir.mkdir(parents=True, exist_ok=True)

        # Extract content from source (HTML → text)
        source_content = ""
        if content_source:
            src_path = Path(os.path.expanduser(content_source))
            if src_path.exists():
                raw = src_path.read_text(encoding="utf-8", errors="ignore")
                source_content = re.sub(r"<[^<]+?>", "", raw)[:5000]

        date_str = doc.get("date", datetime.now().strftime("%Y-%m-%d"))

        if target_file.exists() and action == "CREATE_OR_APPEND":
            existing = target_file.read_text(encoding="utf-8")
            new_section = f"\n\n## {date_str}\n\n{source_content[:2000]}\n"
            new_body = existing + new_section
            target_file.write_text(new_body, encoding="utf-8")
            if existing_path:
                log.info(
                    f"Wiki dedup: appended to existing article at {target_file}"
                    f" (requested domain/subdomain={domain}/{subdomain})"
                )
        else:
            article = f"""---
title: "{doc.get('title', slug)}"
domain: {domain}
subdomain: {subdomain}
entity_type: {doc.get('entity_type', 'report')}
freshness_policy: daily
confidence: 0.75
review_status: "auto"
---

## {date_str}

{source_content[:2000]}
"""
            target_file.write_text(article, encoding="utf-8")
            new_body = article

        # Phase 6.2 — record revision snapshot (fail-open, never blocks writes).
        try:
            import sys as _sys
            _wiki_tools = wiki_root / "tools"
            if str(_wiki_tools) not in _sys.path:
                _sys.path.insert(0, str(_wiki_tools))
            from wiki_common import snapshot_revision  # type: ignore
            snapshot_revision(
                slug=slug,
                path=target_file,
                content_body=new_body,
                written_by="staging_dispatcher",
                write_note=f"action={action} domain={domain} subdomain={subdomain}",
            )
        except Exception as _e:
            log.info(f"wiki revision snapshot skipped ({_e})")

    def _wiki_existing_path(self, slug: str, wiki_root: Path) -> Path | None:
        """Phase 5.5 — look up the existing path for a wiki slug, if any.

        Consults `wiki/indexes/articles.sqlite -> articles_meta`. Returns an
        absolute Path if the slug is indexed and the file still exists on
        disk; otherwise None (caller falls through to create-new behavior).
        """
        index_db = wiki_root / "indexes" / "articles.sqlite"
        if not index_db.exists():
            return None
        try:
            import sqlite3 as _sqlite
            with _sqlite.connect(str(index_db)) as c:
                row = c.execute(
                    "SELECT path FROM articles_meta WHERE slug = ? LIMIT 1",
                    (slug,),
                ).fetchone()
        except Exception as e:
            log.warning(f"wiki dedup lookup failed for '{slug}': {e}")
            return None
        if not row or not row[0]:
            return None
        # Paths in articles_meta may be absolute or wiki-root-relative.
        p = Path(row[0])
        if not p.is_absolute():
            p = wiki_root / p
        return p if p.exists() else None

    def _handle_valuation(self, doc, filepath):
        """Process valuation output: DOCTRINE evidence + wiki update."""
        # DOCTRINE evidence
        if doc.get("doctrine_evidence"):
            for ev in doc["doctrine_evidence"]:
                self.soma.write_evidence(
                    belief_id=ev["belief_id"],
                    source_module="VALUATION_SKILL",
                    source_detail=ev.get("source_detail", ""),
                    supports=ev.get("supports", True),
                    weight=ev.get("weight", 1.0),
                )

        # Wiki update
        if doc.get("wiki_slug"):
            self._handle_wiki_update(
                {
                    "slug": doc["wiki_slug"],
                    "domain": "finance",
                    "subdomain": "companies",
                    "title": f"{doc.get('ticker', '')} Valuation Update",
                    "action": "CREATE_OR_APPEND",
                    "date": doc.get("date", datetime.now().strftime("%Y-%m-%d")),
                },
                filepath,
            )

    # ── Utilities ────────────────────────────────────────────────────

    def _infer_type_from_filename(self, filename):
        """Infer staging type from filename prefix (legacy file support).

        Supports: PRISM_*, DOCTRINE_*, HORIZON_*, SCRATCHPAD_*, MODEL_FLAG_*
        Returns None if no match.
        """
        prefix_map = {
            "PRISM_": "PRISM",
            "DOCTRINE_": "DOCTRINE_EVIDENCE",  # default to evidence, not candidate
            "HORIZON_": "HORIZON",
            "MODEL_FLAG_": "MODEL_FLAG",
            "WIKI_": "WIKI_UPDATE",
            "VALUATION_": "VALUATION",
        }
        upper = filename.upper()
        for prefix, staging_type in prefix_map.items():
            if upper.startswith(prefix):
                return staging_type
        return None

    def _cleanup_old(self, days=90):
        """Remove files from processed/ older than N days."""
        cutoff = datetime.now(timezone.utc).timestamp() - (days * 86400)
        removed = 0
        for f in self.processed_dir.glob("*.yaml"):
            if f.stat().st_mtime < cutoff:
                f.unlink()
                removed += 1
        if removed:
            log.info(f"Cleaned up {removed} files older than {days} days.")

    def _write_log(self, results):
        """Write dispatcher run log for monitoring."""
        log_dir = self.staging_dir.parent / "logs"
        log_dir.mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = log_dir / f"dispatcher_{ts}.json"
        log_file.write_text(json.dumps(results, indent=2, default=str))


# ── CLI entry point ──────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="DABEIBA Staging Batch Processor")
    parser.add_argument("--dry-run", action="store_true", help="Preview without processing")
    parser.add_argument("--staging-dir", default=None, help="Override staging directory")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    staging = args.staging_dir or os.path.expanduser(
        "~/Desktop/DABEIBA/shared/soma/staging"
    )

    with SomaBridge() as db:
        db.initialize_db()
        dispatcher = StagingDispatcher(staging_dir=staging, soma_bridge=db)
        results = dispatcher.process_all(dry_run=args.dry_run)

    print(f"\n{'[DRY RUN] ' if args.dry_run else ''}Staging Dispatch Results:")
    print(f"  Processed: {results.get('processed', 0)}")
    print(f"  Errors:    {results.get('errors', 0)}")
    print(f"  Skipped:   {results.get('skipped', 0)}")
    if results.get("model_flags"):
        print(f"  Model flags: {', '.join(results['model_flags'])}")
    if results.get("wiki_updates"):
        print(f"  Wiki updates: {', '.join(results['wiki_updates'])}")
    if results.get("doctrine_evidence"):
        print(f"  Doctrine evidence: {', '.join(results['doctrine_evidence'])}")


if __name__ == "__main__":
    main()
