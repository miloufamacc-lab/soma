#!/usr/bin/env python3
"""
soma_bookmark_sync.py — X.com Bookmark Intelligence Pipeline
============================================================
DABEIBA SOMA Pipeline | Module: CROSS_AI

Scrapes, filters, and processes X.com bookmarks for Claude/AI-related
intelligence. Saves enriched data as JSON, imports rules into SOMA DB,
and generates a weekly digest PDF.

Usage:
  python3 soma_bookmark_sync.py               # Full sync (uses last sync date)
  python3 soma_bookmark_sync.py --since 2026-01-01  # Custom start date
  python3 soma_bookmark_sync.py --mode report-only  # Regenerate PDF from cached data
  python3 soma_bookmark_sync.py --mode stats         # Show stats only

Architecture:
  - Step 1: Load previous state (last sync date, known tweet IDs)
  - Step 2: Read raw bookmark JSON (populated by Cowork Chrome session)
  - Step 3: Filter for AI/Claude-relevant content
  - Step 4: Score and categorize each bookmark
  - Step 5: Append new entries to the master JSON store
  - Step 6: Generate PDF digest report
  - Step 7: Print SOMA KB rule candidates for manual review

Scheduled via: Cowork scheduled task (weekly)
Data directory: shared/soma/data/bookmarks/
"""

import json
import sys
import os
import argparse
from datetime import datetime, timezone
from pathlib import Path

# ─── Paths ────────────────────────────────────────────────────────────────────
SOMA_DIR = Path(__file__).parent
DATA_DIR  = SOMA_DIR / "data" / "bookmarks"
DATA_DIR.mkdir(parents=True, exist_ok=True)

RAW_JSON       = DATA_DIR / "raw_bookmarks_2026.json"
PROCESSED_JSON = DATA_DIR / "processed_ai_bookmarks.json"
STATE_FILE     = DATA_DIR / "sync_state.json"
DIGEST_PDF     = DATA_DIR / "claude_intel_digest.pdf"

# ─── AI Relevance Filter ──────────────────────────────────────────────────────
import re

AI_KEYWORDS = re.compile(
    r"claude|anthropic|MCP|model.?context.?protocol|LLM|GPT|openai|gemini|"
    r"cursor|agent|agentic|cowork|skill|prompt.?eng|AI.?tool|token.?limit|"
    r"context.?window|automation|copilot|grok|phi.?mini|llama|mistral|"
    r"hugging.?face|fine.?tun|embedding|RAG|vector.?db|inference|benchmark|"
    r"foundation.?model|transformer|diffusion|generative.?AI|vibe.?cod|"
    r"claude.?code|claude.?desktop|cowork.?mode|MCP.?server|tool.?use|"
    r"system.?prompt|orchestrat|multi.?agent|subagent|agent.?framework|"
    r"dexscreener|jupyter|notebook|AI.?research|phi4|sonnet|haiku|opus|"
    r"deep.?research|turbo.?quant|jina\.ai|r\.jina|AGENT_LEARNINGS",
    re.IGNORECASE
)

# ─── Category Tags ────────────────────────────────────────────────────────────
CATEGORIES = {
    "CLAUDE_CODE":     re.compile(r"claude.?code|claude.?skill|hook|subagent|orchestrat|effort.?level", re.I),
    "CLAUDE_MCP":      re.compile(r"MCP|model.?context.?protocol|MCP.?server|connector", re.I),
    "CLAUDE_FEATURES": re.compile(r"claude|anthropic|cowork|claude.?desktop|sonnet|haiku|opus", re.I),
    "PROMPT_STRATEGY": re.compile(r"prompt|system.?prompt|vibe.?cod|prompt.?master|prompting", re.I),
    "AGENT_FRAMEWORKS":re.compile(r"agent|agentic|multi.?agent|orchestrat|framework|AgentHub|OpenClaw", re.I),
    "LLM_ECOSYSTEM":   re.compile(r"LLM|GPT|openai|gemini|grok|llama|mistral|phi|turbo.?quant|benchmark", re.I),
    "AI_TOOLS":        re.compile(r"cursor|copilot|AI.?tool|automation|workflow|tool.?use|coindex", re.I),
    "DATA_INFRA":      re.compile(r"RAG|vector|embedding|fine.?tun|training|dataset|hugging|jina|token", re.I),
    "CRYPTO_AI":       re.compile(r"dexscreener|solana|onchain|defi|crypto.*agent|agent.*crypto", re.I),
}

# ─── Scoring ─────────────────────────────────────────────────────────────────
HIGH_SIGNAL_AUTHORS = {
    "RoundtableSpace", "claudeai", "AnthropicAI", "sama", "GregBrockman",
    "karpathy", "ylecun", "emollick", "svpino", "hasantoxr", "heynavtoor",
    "itsolelehmann", "alex_prompter", "tom_doerr", "vishisinghal_",
    "aaronjmars", "charliejhills", "MilkRoadAI", "HeyZaraKhan",
}

def score_bookmark(b: dict) -> int:
    score = 0
    handle = b.get("handle", "").replace("@", "")
    text = b.get("text", "")
    if handle in HIGH_SIGNAL_AUTHORS:
        score += 3
    if re.search(r"claude|anthropic|cowork", text, re.I):
        score += 2
    if re.search(r"BREAKING|just (dropped|launched|released|announced)", text, re.I):
        score += 1
    if re.search(r"free|open.?source", text, re.I):
        score += 1
    if re.search(r"MCP|claude.?code|skill|hook|orchestrat", text, re.I):
        score += 2
    return score

def categorize(b: dict) -> list:
    text = b.get("text", "")
    tags = [name for name, pattern in CATEGORIES.items() if pattern.search(text)]
    return tags or ["GENERAL_AI"]

def is_ai_relevant(b: dict) -> bool:
    return bool(AI_KEYWORDS.search(b.get("text", "")) or
                AI_KEYWORDS.search(b.get("user", "")) or
                AI_KEYWORDS.search(b.get("handle", "")))

# ─── State Management ─────────────────────────────────────────────────────────
def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"last_sync": "2026-01-01T00:00:00.000Z", "known_ids": [], "total_processed": 0}

def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2))

# ─── Core Processing ──────────────────────────────────────────────────────────
def process_raw_bookmarks(since: str) -> dict:
    """Load raw bookmarks, filter, score, categorize."""
    if not RAW_JSON.exists():
        print(f"[SYNC] No raw bookmark file found at {RAW_JSON}")
        print("[SYNC] Run a Cowork Chrome session to scrape bookmarks first.")
        return {"new": [], "skipped": 0}

    raw = json.loads(RAW_JSON.read_text())
    bookmarks = raw.get("bookmarks", raw) if isinstance(raw, dict) else raw

    # Load existing processed
    existing = {}
    if PROCESSED_JSON.exists():
        for b in json.loads(PROCESSED_JSON.read_text()):
            existing[b["url"]] = b

    new_entries = []
    skipped = 0
    for b in bookmarks:
        if b.get("datetime", "") < since:
            skipped += 1
            continue
        if b.get("url") in existing:
            continue
        if not is_ai_relevant(b):
            continue

        enriched = {
            **b,
            "categories": categorize(b),
            "signal_score": score_bookmark(b),
            "full_text": b.get("full_text", b.get("text", "")),
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }
        new_entries.append(enriched)

    return {"new": new_entries, "existing": list(existing.values()), "skipped": skipped}

def save_processed(result: dict):
    all_entries = result.get("existing", []) + result.get("new", [])
    all_entries.sort(key=lambda b: b.get("datetime", ""), reverse=True)
    PROCESSED_JSON.write_text(json.dumps(all_entries, indent=2, ensure_ascii=False))
    print(f"[SYNC] Saved {len(all_entries)} total processed bookmarks.")

# ─── PDF Generation ───────────────────────────────────────────────────────────
def generate_pdf(entries: list, output_path: Path):
    """Generate a comprehensive PDF digest from processed bookmark entries."""
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable, Table, TableStyle
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_LEFT, TA_CENTER
    except ImportError:
        print("[PDF] reportlab not installed. Run: pip install reportlab --break-system-packages")
        return False

    doc = SimpleDocTemplate(str(output_path), pagesize=letter,
                            leftMargin=0.8*inch, rightMargin=0.8*inch,
                            topMargin=0.8*inch, bottomMargin=0.8*inch)
    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle("title", parent=styles["Title"], fontSize=20,
                                  textColor=colors.HexColor("#1a1a2e"), spaceAfter=4)
    subtitle_style = ParagraphStyle("subtitle", parent=styles["Normal"], fontSize=11,
                                     textColor=colors.HexColor("#555"), spaceAfter=16)
    h1_style = ParagraphStyle("h1", parent=styles["Heading1"], fontSize=14,
                               textColor=colors.HexColor("#0f3460"), spaceBefore=18, spaceAfter=6)
    h2_style = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=11,
                               textColor=colors.HexColor("#16213e"), spaceBefore=12, spaceAfter=4)
    body_style = ParagraphStyle("body", parent=styles["Normal"], fontSize=9,
                                 leading=14, spaceAfter=4)
    tag_style = ParagraphStyle("tag", parent=styles["Normal"], fontSize=8,
                                textColor=colors.HexColor("#0f3460"), spaceAfter=8)
    meta_style = ParagraphStyle("meta", parent=styles["Normal"], fontSize=8,
                                 textColor=colors.HexColor("#888"), spaceAfter=2)

    story = []
    now = datetime.now().strftime("%B %d, %Y")

    # Header
    story.append(Paragraph("DABEIBA — Claude Intelligence Digest", title_style))
    story.append(Paragraph(f"X.com Bookmark Analysis | Generated {now} | SOMA Knowledge Pipeline", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#0f3460")))
    story.append(Spacer(1, 12))

    # Summary stats
    cat_counts = {}
    for b in entries:
        for c in b.get("categories", []):
            cat_counts[c] = cat_counts.get(c, 0) + 1

    top_authors = {}
    for b in entries:
        h = b.get("handle", "?")
        top_authors[h] = top_authors.get(h, 0) + 1
    top_5_authors = sorted(top_authors.items(), key=lambda x: -x[1])[:5]

    date_range_oldest = min(b.get("datetime","") for b in entries)[:10] if entries else "N/A"
    date_range_newest = max(b.get("datetime","") for b in entries)[:10] if entries else "N/A"

    story.append(Paragraph("Executive Summary", h1_style))
    summary_data = [
        ["Metric", "Value"],
        ["Total AI-relevant bookmarks", str(len(entries))],
        ["Date range", f"{date_range_oldest} → {date_range_newest}"],
        ["Top category", max(cat_counts, key=cat_counts.get) if cat_counts else "N/A"],
        ["Most bookmarked author", top_5_authors[0][0] if top_5_authors else "N/A"],
        ["High-signal entries (score ≥ 4)", str(sum(1 for b in entries if b.get("signal_score",0) >= 4))],
    ]
    t = Table(summary_data, colWidths=[3*inch, 3.5*inch])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#0f3460")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTSIZE", (0,0), (-1,-1), 9),
        ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#ccc")),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#f5f8ff")]),
        ("LEFTPADDING", (0,0), (-1,-1), 8),
    ]))
    story.append(t)
    story.append(Spacer(1, 16))

    # Category distribution
    story.append(Paragraph("Category Breakdown", h1_style))
    cat_data = [["Category", "Count"]] + [[k, str(v)] for k,v in sorted(cat_counts.items(), key=lambda x: -x[1])]
    ct = Table(cat_data, colWidths=[3.5*inch, 1.5*inch])
    ct.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#16213e")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTSIZE", (0,0), (-1,-1), 9),
        ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#ccc")),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#f5f8ff")]),
        ("LEFTPADDING", (0,0), (-1,-1), 8),
    ]))
    story.append(ct)
    story.append(Spacer(1, 16))

    # Entries by category
    cat_order = ["CLAUDE_CODE", "CLAUDE_FEATURES", "CLAUDE_MCP", "PROMPT_STRATEGY",
                 "AGENT_FRAMEWORKS", "AI_TOOLS", "LLM_ECOSYSTEM", "DATA_INFRA", "CRYPTO_AI", "GENERAL_AI"]
    seen_urls = set()

    for cat in cat_order:
        cat_entries = [b for b in entries if cat in b.get("categories", []) and b.get("url") not in seen_urls]
        if not cat_entries:
            continue
        cat_entries.sort(key=lambda b: b.get("signal_score", 0), reverse=True)

        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#ccc")))
        story.append(Paragraph(f"■  {cat.replace('_', ' ')}", h1_style))

        for b in cat_entries:
            seen_urls.add(b.get("url"))
            date_str = b.get("datetime", "")[:10]
            user = b.get("user", "?")
            handle = b.get("handle", "?")
            score = b.get("signal_score", 0)
            text = b.get("full_text", b.get("text", ""))
            all_cats = " · ".join(b.get("categories", []))
            url = b.get("url", "")
            status_id = url.split("/status/")[-1] if "/status/" in url else ""

            story.append(Paragraph(f"<b>{user}</b> ({handle})", h2_style))
            story.append(Paragraph(f"📅 {date_str}  |  Signal score: {score}/8  |  Tags: {all_cats}", meta_style))
            # Sanitize text for PDF
            safe_text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            story.append(Paragraph(safe_text[:800], body_style))
            if status_id:
                story.append(Paragraph(f"🔗 x.com/{handle.replace('@','')}/status/{status_id}", tag_style))
            story.append(Spacer(1, 6))

    # High-signal entries summary (top 15 by score, not already in a section)
    story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#0f3460")))
    story.append(Paragraph("⭐  Top Picks — Highest Signal Bookmarks", h1_style))
    top_picks = sorted(entries, key=lambda b: b.get("signal_score", 0), reverse=True)[:15]
    for i, b in enumerate(top_picks, 1):
        date_str = b.get("datetime", "")[:10]
        user = b.get("user", "?")
        text = b.get("full_text", b.get("text", ""))
        score = b.get("signal_score", 0)
        safe_text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        story.append(Paragraph(f"<b>#{i} — {user}</b> · {date_str} · Score {score}/8", h2_style))
        story.append(Paragraph(safe_text[:400], body_style))
        story.append(Spacer(1, 4))

    doc.build(story)
    print(f"[PDF] Generated: {output_path}")
    return True

# ─── SOMA Rule Suggestions ────────────────────────────────────────────────────
def suggest_soma_rules(entries: list):
    """Print top candidates for new SOMA KB rules."""
    high_signal = [b for b in entries if b.get("signal_score", 0) >= 4]
    high_signal.sort(key=lambda b: b.get("signal_score", 0), reverse=True)
    print(f"\n[SOMA] Top {min(10, len(high_signal))} rule candidates (score ≥ 4):")
    for b in high_signal[:10]:
        print(f"  [{b['signal_score']}/8] {b['user']} ({b['datetime'][:10]})")
        print(f"       {b['text'][:120]}...")
        print()

# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="SOMA Bookmark Sync Pipeline")
    parser.add_argument("--since", default=None, help="Sync bookmarks since date (YYYY-MM-DD)")
    parser.add_argument("--mode", default="full", choices=["full", "report-only", "stats"],
                        help="Run mode: full sync, report only, or stats")
    args = parser.parse_args()

    state = load_state()
    since = args.since or state["last_sync"]

    print(f"\n{'='*60}")
    print(f"  SOMA Bookmark Sync | Since: {since[:10]}")
    print(f"  Mode: {args.mode}")
    print(f"{'='*60}\n")

    if args.mode == "stats":
        if PROCESSED_JSON.exists():
            entries = json.loads(PROCESSED_JSON.read_text())
            print(f"[STATS] Processed bookmarks: {len(entries)}")
            print(f"[STATS] Last sync: {state['last_sync']}")
            suggest_soma_rules(entries)
        else:
            print("[STATS] No processed data yet. Run full sync first.")
        return

    if args.mode == "report-only":
        if PROCESSED_JSON.exists():
            entries = json.loads(PROCESSED_JSON.read_text())
            generate_pdf(entries, DIGEST_PDF)
        else:
            print("[REPORT] No processed data. Run full sync first.")
        return

    # Full sync
    print(f"[SYNC] Processing bookmarks since {since[:10]}...")
    result = process_raw_bookmarks(since)
    new = result.get("new", [])
    print(f"[SYNC] Found {len(new)} new AI-relevant bookmarks.")
    print(f"[SYNC] Skipped {result.get('skipped', 0)} (before cutoff date).")

    if new:
        save_processed(result)
        suggest_soma_rules(new)

        print(f"\n[PDF] Generating digest report...")
        all_entries = result.get("existing", []) + new
        generate_pdf(sorted(all_entries, key=lambda b: b.get("datetime",""), reverse=True), DIGEST_PDF)

        # Update state
        state["last_sync"] = datetime.now(timezone.utc).isoformat()
        state["total_processed"] = state.get("total_processed", 0) + len(new)
        state["known_ids"] = list(set(state.get("known_ids", [])) | {
            b["url"].split("/status/")[-1] for b in new if "/status/" in b.get("url","")
        })
        save_state(state)
    else:
        print("[SYNC] No new entries. Nothing to process.")

    print(f"\n[SYNC] Done. Data: {DATA_DIR}")
    print(f"[PDF]  Digest: {DIGEST_PDF}")

if __name__ == "__main__":
    main()
