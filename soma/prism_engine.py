"""
PRISM — Pipeline for Raw Intelligence Sorting & Materiality
Pipeline: SOMA/PRISM | Module: SOMA | Status: BUILT

Universal ingestion funnel — processes files from the scraper inbox,
classifies them, extracts structured content, and routes to SOMA's
raw_intelligence table for downstream consumption by other pipelines.

Supported formats:
    .txt       — plain text (X threads, notes, GEM dumps)
    .json      — structured data (YouTube extractor output, API responses)
    .md        — markdown notes
    .pdf       — PDF documents (requires pdfplumber)
    .csv       — tabular data

Workflow:
    1. Scan shared/scrapers/inbox/ for new files
    2. Detect source type from filename patterns + content
    3. Extract text content
    4. Classify: category (macro/crypto/equities/geopolitical/philosophy/risk)
    5. Route: assign target_pipeline based on category
    6. Write to SOMA raw_intelligence table
    7. Move processed file to shared/scrapers/archive/

Usage:
    with PrismEngine() as prism:
        result = prism.process_inbox()
        prism.print_terminal()

    # Or standalone:
    python3 -m soma.prism_engine
"""

import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .soma_bridge import SomaBridge
from .pipeline_registry import get_category_routing, resolve


# ── Category keywords for classification ─────────────────────────────
# NOTE: These PRISM categories (macro, crypto, equities, geopolitical, philosophy, risk)
# are SEPARATE from CIPHER's Advisory categories (Macro, Holdings, Geopolitics,
# Monetary_Policy, Thematic, Musk Ecosystem, Bitcoin). PRISM routes raw intelligence
# to Research/Synthesis pipelines. CIPHER categorizes client-facing notes.
# The two taxonomies are intentionally different by design (April 15, 2026).

CATEGORY_KEYWORDS = {
    "crypto": [
        "bitcoin", "btc", "ethereum", "eth", "solana", "sol", "defi",
        "blockchain", "on-chain", "onchain", "mvrv", "nupl", "sopr",
        "mempool", "staking", "nft", "token", "altcoin", "crypto",
        "coinbase", "binance", "jupiter", "raydium", "phantom",
        "self-custody", "wallet", "ledger", "mstr", "saylor",
    ],
    "macro": [
        "fed", "fomc", "rate", "inflation", "cpi", "gdp", "pmi",
        "employment", "payroll", "yield", "treasury", "bond",
        "liquidity", "gli", "central bank", "monetary", "fiscal",
        "recession", "expansion", "growth", "debt", "deficit",
        "tariff", "trade war", "dollar", "dxy", "oil", "commodity",
    ],
    "equities": [
        "stock", "equity", "earnings", "revenue", "valuation",
        "pe ratio", "eps", "dividend", "buyback", "ipo",
        "nasdaq", "s&p", "sp500", "tsx", "market cap",
        "tsla", "tesla", "nvda", "nvidia", "aapl", "apple",
        "pltr", "palantir", "msft", "microsoft", "amzn", "amazon",
        "sector", "industry", "analyst", "guidance", "downgrade", "upgrade",
    ],
    "geopolitical": [
        "geopolitical", "war", "conflict", "sanction", "nato",
        "china", "russia", "ukraine", "taiwan", "iran", "israel",
        "middle east", "military", "nuclear", "diplomacy", "election",
        "coup", "regime change", "embargo", "territorial",
    ],
    "philosophy": [
        "thesis", "conviction", "belief", "philosophy", "framework",
        "strategy", "principle", "discipline", "behavioral", "bias",
        "contrarian", "momentum", "value investing", "risk management",
        "position sizing", "drawdown", "compounding",
    ],
    "risk": [
        "risk", "volatility", "vix", "drawdown", "hedge",
        "tail risk", "black swan", "correlation", "diversification",
        "stress test", "scenario", "crisis", "contagion", "leverage",
    ],
}

# ── Category → target pipeline routing ───────────────────────────────
# Loaded from pipeline_registry.py — single source of truth.
# To change routing, edit the "categories" field in pipeline_registry.py.

CATEGORY_TO_PIPELINE = get_category_routing()

# Default fallback pipeline when category is unknown
_DEFAULT_PIPELINE = resolve("TITAN") or "TITAN"

# ── Source type detection patterns ────────────────────────────────────

SOURCE_PATTERNS = {
    "youtube": [
        r"youtube\.com", r"youtu\.be", r"video_id", r"transcript",
        r"youtube_extractor", r"\[VIDEO\]",
    ],
    "x_thread": [
        r"twitter\.com", r"x\.com", r"@\w+", r"tweet",
        r"thread", r"🧵",
    ],
    "rss": [
        r"reuters", r"bloomberg", r"ap news", r"bbc",
        r"<item>", r"<entry>", r"feed",
    ],
    "gem_dump": [
        r"gem_", r"gemini", r"scraped_",
    ],
}


class PrismEngine:
    """PRISM — universal ingestion funnel for DABEIBA.

    Scans the scraper inbox, classifies files, extracts content,
    and writes structured intelligence to SOMA's raw_intelligence table.
    """

    MODULE_VERSION = "PRISM-1.0.0"

    def __init__(self, db_path=None, inbox_path=None, archive_path=None):
        self.db_path = db_path
        self._bridge = None
        self._result = None

        # Default paths relative to DABEIBA root
        dabeiba_root = Path.home() / "Desktop" / "DABEIBA"
        self.inbox_path = Path(inbox_path) if inbox_path else dabeiba_root / "shared" / "scrapers" / "inbox"
        self.archive_path = Path(archive_path) if archive_path else dabeiba_root / "shared" / "scrapers" / "archive"

    def __enter__(self):
        self._bridge = SomaBridge(self.db_path)
        self._bridge.__enter__()
        self._bridge.initialize_db()  # ensure migration 008 applied
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._bridge:
            self._bridge.__exit__(exc_type, exc_val, exc_tb)
            self._bridge = None
        return False

    # ── Inbox scanning ───────────────────────────────────────────────

    def _scan_inbox(self):
        """Return list of files in the inbox, sorted by modification time."""
        if not self.inbox_path.exists():
            return []
        files = []
        for f in self.inbox_path.iterdir():
            if f.is_file() and not f.name.startswith("."):
                files.append(f)
        files.sort(key=lambda f: f.stat().st_mtime)
        return files

    # ── Content extraction ───────────────────────────────────────────

    def _extract_content(self, filepath):
        """Extract text content from a file based on its extension.

        Returns (content_text, metadata_dict).
        """
        ext = filepath.suffix.lower()
        metadata = {"filename": filepath.name, "extension": ext}

        try:
            if ext in (".txt", ".md"):
                content = filepath.read_text(encoding="utf-8", errors="replace")
                return content, metadata

            elif ext == ".json":
                raw = filepath.read_text(encoding="utf-8", errors="replace")
                data = json.loads(raw)
                # Handle YouTube extractor JSON format
                if isinstance(data, dict):
                    if "transcript" in data:
                        content = data.get("title", "") + "\n\n" + data["transcript"]
                        metadata["source_url"] = data.get("url", "")
                        metadata["title"] = data.get("title", "")
                        return content, metadata
                    elif "content" in data:
                        content = data.get("title", "") + "\n\n" + data["content"]
                        metadata["source_url"] = data.get("url", "")
                        metadata["title"] = data.get("title", "")
                        return content, metadata
                # Generic JSON — stringify it
                return json.dumps(data, indent=2), metadata

            elif ext == ".csv":
                content = filepath.read_text(encoding="utf-8", errors="replace")
                lines = content.strip().split("\n")
                metadata["rows"] = len(lines) - 1  # minus header
                return content, metadata

            elif ext == ".pdf":
                try:
                    import pdfplumber
                    text_parts = []
                    with pdfplumber.open(str(filepath)) as pdf:
                        metadata["pages"] = len(pdf.pages)
                        for page in pdf.pages:
                            text = page.extract_text()
                            if text:
                                text_parts.append(text)
                    return "\n\n".join(text_parts), metadata
                except ImportError:
                    return f"[PDF file — pdfplumber not installed: {filepath.name}]", metadata

            else:
                # Try reading as text
                content = filepath.read_text(encoding="utf-8", errors="replace")
                return content, metadata

        except Exception as e:
            return f"[Error extracting {filepath.name}: {e}]", metadata

    # ── Classification ───────────────────────────────────────────────

    def _detect_source_type(self, content, metadata):
        """Detect the source type from content patterns and filename."""
        filename = metadata.get("filename", "").lower()
        content_lower = content[:2000].lower()  # scan first 2000 chars

        # Check filename patterns first
        for source_type, patterns in SOURCE_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, filename, re.IGNORECASE):
                    return source_type

        # Then check content patterns
        for source_type, patterns in SOURCE_PATTERNS.items():
            matches = 0
            for pattern in patterns:
                if re.search(pattern, content_lower):
                    matches += 1
            if matches >= 2:  # need at least 2 pattern hits
                return source_type

        # PDF → 'pdf'
        if metadata.get("extension") == ".pdf":
            return "pdf"

        return "manual"  # default fallback

    def _classify_category(self, content):
        """Classify content into a category based on keyword density.

        Returns (category, confidence_score).
        """
        content_lower = content[:5000].lower()  # scan first 5000 chars
        scores = {}

        for category, keywords in CATEGORY_KEYWORDS.items():
            score = 0
            for kw in keywords:
                count = min(content_lower.count(kw), 5)
                score += count
            scores[category] = score

        if not scores or max(scores.values()) == 0:
            return "macro", 3  # default category, low confidence

        best_category = max(scores, key=scores.get)
        best_score = scores[best_category]

        total = sum(scores.values())
        if total > 0:
            confidence = min(10, int((best_score / total) * 10) + 3)
        else:
            confidence = 3

        return best_category, confidence

    def _extract_title(self, content, metadata):
        """Extract a title from content or metadata."""
        if metadata.get("title"):
            return metadata["title"]

        for line in content.split("\n"):
            stripped = line.strip()
            if stripped and len(stripped) > 5:
                stripped = re.sub(r"^#+\s*", "", stripped)
                return stripped[:120]

        return metadata.get("filename", "Untitled")

    def _extract_claims(self, content):
        """Extract key claims from content using simple heuristics.

        Returns a list of strings (max 5 claims).
        """
        claims = []

        bullet_pattern = re.compile(r"(?:^|\n)\s*(?:\d+[\.\)]\s*|[-•*]\s+)(.+)", re.MULTILINE)
        bullets = bullet_pattern.findall(content[:3000])
        for b in bullets[:5]:
            claim = b.strip()
            if len(claim) > 20:
                claims.append(claim[:200])

        if not claims:
            sentences = re.split(r"[.!?]\s+", content[:2000])
            for s in sentences[:3]:
                s = s.strip()
                if len(s) > 20:
                    claims.append(s[:200])

        return claims[:5]

    def _generate_tags(self, content, category):
        """Generate search tags from content."""
        tags = [category]
        content_lower = content[:3000].lower()

        for cat, keywords in CATEGORY_KEYWORDS.items():
            hits = sum(1 for kw in keywords if kw in content_lower)
            if hits >= 2 and cat != category:
                tags.append(cat)

        tickers = re.findall(r"\$([A-Z]{2,5})", content[:3000])
        for t in set(tickers[:5]):
            tags.append(f"${t}")

        return tags[:10]

    # ── Core processing ──────────────────────────────────────────────

    def process_inbox(self):
        """Process all files in the scraper inbox.

        For each file:
            1. Extract content
            2. Detect source type
            3. Classify category
            4. Route to target pipeline
            5. Write to raw_intelligence
            6. Archive the file

        Returns a result dict summarizing what was processed.
        """
        files = self._scan_inbox()
        processed = []
        errors = []

        for filepath in files:
            try:
                result = self._process_file(filepath)
                if result:
                    processed.append(result)
                    self._archive_file(filepath)
            except Exception as e:
                errors.append({"file": filepath.name, "error": str(e)})
                print(f"[PRISM] Error processing {filepath.name}: {e}")

        self._result = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "inbox_path": str(self.inbox_path),
            "files_scanned": len(files),
            "files_processed": len(processed),
            "files_errored": len(errors),
            "processed": processed,
            "errors": errors,
            "summary": self._build_summary(processed, errors),
        }
        return self._result

    def _process_file(self, filepath):
        """Process a single file through the PRISM pipeline."""
        content, metadata = self._extract_content(filepath)
        if not content or content.startswith("[Error"):
            return None

        source_type = self._detect_source_type(content, metadata)
        category, relevance = self._classify_category(content)
        target_pipeline = CATEGORY_TO_PIPELINE.get(category, _DEFAULT_PIPELINE)
        title = self._extract_title(content, metadata)
        claims = self._extract_claims(content)
        tags = self._generate_tags(content, category)
        source_url = metadata.get("source_url", "")
        now = datetime.now(timezone.utc).isoformat()

        try:
            self._bridge.conn.execute(
                """INSERT INTO raw_intelligence
                   (source_type, source_url, title, content, category,
                    target_pipeline, relevance_score, key_claims_json,
                    tags_json, file_origin, write_timestamp, module_version)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (source_type, source_url, title, content, category,
                 target_pipeline, relevance, json.dumps(claims),
                 json.dumps(tags), filepath.name, now, self.MODULE_VERSION),
            )
            self._bridge.conn.commit()
        except Exception as e:
            print(f"[PRISM] DB write failed for {filepath.name}: {e}")
            return None

        return {
            "file": filepath.name,
            "source_type": source_type,
            "category": category,
            "target_pipeline": target_pipeline,
            "relevance": relevance,
            "title": title[:80],
            "claims": len(claims),
            "content_length": len(content),
        }

    def _archive_file(self, filepath):
        """Move a processed file to the archive folder."""
        try:
            self.archive_path.mkdir(parents=True, exist_ok=True)
            date_prefix = datetime.now(timezone.utc).strftime("%Y%m%d_")
            dest = self.archive_path / f"{date_prefix}{filepath.name}"
            counter = 1
            while dest.exists():
                stem = filepath.stem
                dest = self.archive_path / f"{date_prefix}{stem}_{counter}{filepath.suffix}"
                counter += 1
            shutil.move(str(filepath), str(dest))
        except Exception as e:
            print(f"[PRISM] Archive failed for {filepath.name}: {e}")

    # ── Direct ingestion (no file needed) ────────────────────────────

    def ingest_text(self, text, source_type="manual", title=None,
                    source_url=None, category=None):
        """Ingest raw text directly without going through the inbox.

        Useful for Claude-interactive processing: user pastes content,
        Claude calls prism.ingest_text() to write it to SOMA.
        """
        if not category:
            category, relevance = self._classify_category(text)
        else:
            relevance = 7

        target_pipeline = CATEGORY_TO_PIPELINE.get(category, _DEFAULT_PIPELINE)
        title = title or self._extract_title(text, {})
        claims = self._extract_claims(text)
        tags = self._generate_tags(text, category)
        now = datetime.now(timezone.utc).isoformat()

        try:
            self._bridge.conn.execute(
                """INSERT INTO raw_intelligence
                   (source_type, source_url, title, content, category,
                    target_pipeline, relevance_score, key_claims_json,
                    tags_json, processed, write_timestamp, module_version)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)""",
                (source_type, source_url, title, text, category,
                 target_pipeline, relevance, json.dumps(claims),
                 json.dumps(tags), now, self.MODULE_VERSION),
            )
            self._bridge.conn.commit()
            return {
                "status": "ok",
                "category": category,
                "target_pipeline": target_pipeline,
                "relevance": relevance,
                "title": title[:80],
            }
        except Exception as e:
            print(f"[PRISM] ingest_text failed: {e}")
            return {"status": "error", "error": str(e)}

    # ── Summary ──────────────────────────────────────────────────────

    def _build_summary(self, processed, errors):
        if not processed and not errors:
            return "Inbox empty — no files to process."
        parts = []
        if processed:
            parts.append(f"Processed {len(processed)} file(s).")
            by_pipeline = {}
            for p in processed:
                pipe = p["target_pipeline"]
                by_pipeline[pipe] = by_pipeline.get(pipe, 0) + 1
            routing = ", ".join(f"{k}: {v}" for k, v in sorted(by_pipeline.items()))
            parts.append(f"Routed to: {routing}.")
        if errors:
            parts.append(f"{len(errors)} file(s) had errors.")
        return " ".join(parts)

    # ── Persistence ──────────────────────────────────────────────────

    def save_log(self) -> str:
        """Write PRISM processing log to JSON file."""
        if self._result is None:
            self.process_inbox()
        logs_dir = Path(__file__).parent / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        path = logs_dir / f"prism_{ts}.json"
        with open(path, "w") as f:
            json.dump(self._result, f, indent=2, default=str)
        return str(path.resolve())

    # ── Terminal display ─────────────────────────────────────────────

    def print_terminal(self):
        """Pretty-print PRISM results with ANSI colours."""
        if self._result is None:
            self.process_inbox()
        r = self._result

        BOLD = "\033[1m"
        RED = "\033[91m"
        GREEN = "\033[92m"
        YELLOW = "\033[93m"
        CYAN = "\033[96m"
        DIM = "\033[2m"
        MAGENTA = "\033[95m"
        RESET = "\033[0m"

        print(f"\n{BOLD}{'=' * 60}{RESET}")
        print(f"{BOLD}  PRISM — Intelligence Ingestion Funnel{RESET}")
        print(f"{DIM}  {r['timestamp']}{RESET}")
        print(f"{BOLD}{'=' * 60}{RESET}")

        print(f"\n{CYAN}Inbox:{RESET}    {r['inbox_path']}")
        print(f"{CYAN}Scanned:{RESET}  {r['files_scanned']} file(s)")

        if not r["processed"] and not r["errors"]:
            print(f"\n  {DIM}Inbox empty — nothing to process.{RESET}")
        else:
            if r["processed"]:
                print(f"\n{BOLD}--- Processed ---{RESET}")
                for p in r["processed"]:
                    print(f"  {GREEN}OK{RESET} {p['file']}")
                    print(f"     {CYAN}Type:{RESET} {p['source_type']}  "
                          f"{CYAN}Cat:{RESET} {p['category']}  "
                          f"{MAGENTA}→ {p['target_pipeline']}{RESET}  "
                          f"{DIM}R={p['relevance']}{RESET}")
                    print(f"     {DIM}{p['title']}{RESET}")

            if r["errors"]:
                print(f"\n{BOLD}--- Errors ---{RESET}")
                for e in r["errors"]:
                    print(f"  {RED}FAIL{RESET} {e['file']}: {e['error']}")

        print(f"\n{DIM}{r.get('summary', '')}{RESET}")
        print(f"{BOLD}{'=' * 60}{RESET}\n")


# ── CLI entry point ──────────────────────────────────────────────────

if __name__ == "__main__":
    with PrismEngine() as prism:
        result = prism.process_inbox()
        prism.print_terminal()
        if result["files_processed"] > 0:
            log_path = prism.save_log()
            print(f"Log saved: {log_path}")
