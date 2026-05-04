#!/usr/bin/env python3
"""
SOMA-INTEL Step 1.3 — LLM Edge Extractor

Reads raw text (transcript snippet, news article, research note, MUSKONOMY
sitrep, etc.) and extracts structured relationship edges into the graph.

Pipeline:
  1. Load existing nodes from soma.db to build entity-resolution context
  2. Send text + context to LLM (Ollama phi4-mini or Claude)
  3. Parse JSON response → (src, edge_type, dst, confidence, evidence) tuples
  4. Validate: edge_type in VALID_EDGE_TYPES, confidence in [0.30, 0.95]
  5. Resolve / create stub nodes for any new entities
  6. Write edges via IntelStore (source_type="transcript"|"news"|"article"|etc.)
  7. All extracted edges enter the audit queue (audit_status='unaudited')

LLM backends (tried in order):
  1. Ollama at http://localhost:11434 (phi4-mini by default, no API key needed)
  2. Claude API via ANTHROPIC_API_KEY env var (claude-haiku-4-5-20251001)

Usage:
  python3 soma/intel/edge_extractor.py --text "NVIDIA dominates AI chips"
  python3 soma/intel/edge_extractor.py --file article.txt --apply
  python3 soma/intel/edge_extractor.py --file sitrep.txt --source-type transcript --apply
  echo "Tesla and AMD compete in auto silicon" | python3 soma/intel/edge_extractor.py --apply
  python3 soma/intel/edge_extractor.py --text "..." --model claude --apply --verbose
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import textwrap
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

# ── Path bootstrap ────────────────────────────────────────────────────────────
_HERE    = Path(__file__).resolve().parent
_DABEIBA = _HERE.parent.parent.parent
for _p in [str(_DABEIBA), str(_DABEIBA / "shared")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from soma.intel.store import IntelStore, VALID_EDGE_TYPES

log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
DB_PATH = (
    Path(os.environ["SOMA_DB_PATH"])
    if "SOMA_DB_PATH" in os.environ
    else _DABEIBA / "shared" / "soma" / "data" / "soma.db"
)

OLLAMA_URL    = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL  = os.environ.get("OLLAMA_MODEL", "phi4-mini")
CLAUDE_MODEL  = "claude-haiku-4-5-20251001"

# Confidence gate: LLM edges below this are rejected pre-write
_MIN_CONFIDENCE = 0.30
_MAX_CONFIDENCE = 0.95
# Context: max nodes to include in LLM prompt (too many → exceeds context window)
_MAX_CONTEXT_NODES = 300


# ════════════════════════════════════════════════════════════════════════════
# Node context loader
# ════════════════════════════════════════════════════════════════════════════

def _load_node_context(store: IntelStore) -> dict[str, str]:
    """
    Build a dict of node_id → name for the LLM prompt context.
    Prioritises company, platform, regime, and security nodes (most linkable).
    """
    rows = store._c.execute(
        """
        SELECT node_id, node_type, name FROM soma_intel_node
        ORDER BY
          CASE node_type
            WHEN 'company'  THEN 0
            WHEN 'platform' THEN 1
            WHEN 'regime'   THEN 2
            WHEN 'security' THEN 3
            WHEN 'person'   THEN 4
            WHEN 'thesis'   THEN 5
            WHEN 'concept'  THEN 6
            ELSE 7
          END,
          node_id
        LIMIT ?
        """,
        (_MAX_CONTEXT_NODES,),
    ).fetchall()
    return {r["node_id"]: r["name"] for r in rows}


# ════════════════════════════════════════════════════════════════════════════
# Prompt builder
# ════════════════════════════════════════════════════════════════════════════

def _build_prompt(text: str, node_context: dict[str, str]) -> str:
    """
    Build the LLM extraction prompt.

    The prompt instructs the LLM to return ONLY a JSON array of edge objects.
    Node IDs must match the known list (or follow naming conventions for new nodes).
    """
    edge_types_str = "\n".join(f"  - {et}" for et in sorted(VALID_EDGE_TYPES))

    # Format known nodes as a compact two-column list
    node_lines = [
        f"  {nid:<28} {name}"
        for nid, name in list(node_context.items())[:_MAX_CONTEXT_NODES]
    ]
    nodes_block = "\n".join(node_lines)

    node_id_rules = textwrap.dedent("""
    Node ID naming conventions (for NEW nodes not in the known list):
      company:  co_<TICKER>   e.g. co_AAPL, co_GOOGL
      security: sec_<TICKER>  e.g. sec_BTC, sec_ETH
      person:   pn_<slug>     e.g. pn_jensen-huang
      thesis:   th_<slug>     e.g. th_ai-infrastructure-build-out
      concept:  cn_<slug>     e.g. cn-semiconductors
      platform: pl_<id>       e.g. pl_ai, pl_blockchain
      regime:   rg_<id>       e.g. rg_us, rg_conflict
    """).strip()

    prompt = f"""You are a financial intelligence graph builder. Your task is to extract structured relationship edges from the text below and return them as a JSON array.

VALID EDGE TYPES:
{edge_types_str}

KNOWN NODES (prefer these IDs — exact match required):
{nodes_block}

{node_id_rules}

EXTRACTION RULES:
1. Only extract relationships EXPLICITLY stated or STRONGLY implied in the text.
2. Each edge must have: src, edge_type, dst, confidence (float 0.30–0.95), evidence (quote/paraphrase).
3. Use node IDs from the known list wherever possible. Only create new node IDs for entities clearly named in the text and not in the list.
4. confidence reflects your certainty: 0.85+ for direct statements, 0.65–0.84 for strong implications, 0.30–0.64 for weak signals.
5. Do NOT hallucinate relationships not supported by the text.
6. Return ONLY the JSON array — no preamble, no commentary, no markdown fences.

OUTPUT FORMAT (JSON array):
[
  {{
    "src": "co_NVDA",
    "edge_type": "competes_with",
    "dst": "co_AMD",
    "confidence": 0.85,
    "evidence": "NVIDIA and AMD both compete in the GPU market for AI training workloads"
  }}
]

If no edges can be extracted, return an empty array: []

TEXT TO ANALYSE:
{text}"""

    return prompt


# ════════════════════════════════════════════════════════════════════════════
# LLM backends
# ════════════════════════════════════════════════════════════════════════════

def _call_ollama(prompt: str, model: str = OLLAMA_MODEL, timeout: int = 90) -> str:
    """Call Ollama generate API. Returns raw response string."""
    payload = json.dumps({
        "model":  model,
        "prompt": prompt,
        "stream": False,
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        return result.get("response", "")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Ollama unavailable at {OLLAMA_URL}: {e}") from e


def _call_claude(prompt: str, model: str = CLAUDE_MODEL) -> str:
    """Call Claude API via anthropic SDK. Requires ANTHROPIC_API_KEY."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    try:
        import anthropic  # type: ignore[import]
    except ImportError:
        raise RuntimeError("anthropic package not installed: pip install anthropic")

    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model=model,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


def _call_claude_http(prompt: str, model: str = CLAUDE_MODEL) -> str:
    """
    Fallback Claude caller using urllib only (no anthropic package).
    Requires ANTHROPIC_API_KEY.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    payload = json.dumps({
        "model": model,
        "max_tokens": 2048,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "Content-Type":      "application/json",
            "x-api-key":         api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        return result["content"][0]["text"]
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Claude API error {e.code}: {body}") from e


def _call_llm(prompt: str, model_hint: str = "auto") -> str:
    """
    Dispatch to the best available LLM backend.

    model_hint:
      "auto"   — try Ollama first, fall back to Claude HTTP
      "ollama" — Ollama only (error if unavailable)
      "claude" — Claude API (try anthropic SDK, fall back to urllib)
    """
    if model_hint in ("auto", "ollama"):
        try:
            return _call_ollama(prompt)
        except RuntimeError as e:
            if model_hint == "ollama":
                raise
            log.warning("Ollama unavailable (%s), falling back to Claude HTTP", e)

    # Claude path
    try:
        return _call_claude(prompt)
    except (RuntimeError, ImportError):
        return _call_claude_http(prompt)


# ════════════════════════════════════════════════════════════════════════════
# Response parser
# ════════════════════════════════════════════════════════════════════════════

_JSON_ARRAY_RE = re.compile(r"\[.*?\]", re.DOTALL)


def _parse_llm_response(raw: str) -> list[dict]:
    """
    Extract and parse the JSON array from LLM output.

    Handles cases where the model wraps output in markdown fences or
    adds preamble text.
    """
    raw = raw.strip()

    # Strip markdown fences if present
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
        raw = raw.strip()

    # Try direct parse first
    try:
        result = json.loads(raw)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass

    # Find JSON array anywhere in the string
    m = _JSON_ARRAY_RE.search(raw)
    if m:
        try:
            result = json.loads(m.group())
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass

    return []


# ════════════════════════════════════════════════════════════════════════════
# Validation
# ════════════════════════════════════════════════════════════════════════════

def _validate_proposed_edges(
    proposed: list[dict],
    node_context: dict[str, str],
) -> tuple[list[dict], list[dict]]:
    """
    Validate proposed edges. Returns (valid, rejected).

    Checks:
    - Required fields present
    - edge_type in VALID_EDGE_TYPES
    - confidence in [_MIN_CONFIDENCE, _MAX_CONFIDENCE]
    - src and dst are non-empty strings
    """
    valid:    list[dict] = []
    rejected: list[dict] = []

    for item in proposed:
        if not isinstance(item, dict):
            rejected.append({"raw": item, "reason": "not a dict"})
            continue

        src        = str(item.get("src", "")).strip()
        dst        = str(item.get("dst", "")).strip()
        edge_type  = str(item.get("edge_type", "")).strip()
        confidence = item.get("confidence")
        evidence   = item.get("evidence", "")

        reasons = []
        if not src:
            reasons.append("missing src")
        if not dst:
            reasons.append("missing dst")
        if edge_type not in VALID_EDGE_TYPES:
            reasons.append(f"unknown edge_type '{edge_type}'")
        if confidence is None:
            reasons.append("missing confidence")
        elif not isinstance(confidence, (int, float)):
            reasons.append(f"confidence not numeric: {confidence!r}")
        elif not (_MIN_CONFIDENCE <= float(confidence) <= _MAX_CONFIDENCE):
            reasons.append(
                f"confidence {confidence} out of range "
                f"[{_MIN_CONFIDENCE}, {_MAX_CONFIDENCE}]"
            )

        if reasons:
            item["_reject_reasons"] = reasons
            rejected.append(item)
        else:
            valid.append({
                "src":        src,
                "dst":        dst,
                "edge_type":  edge_type,
                "confidence": float(confidence),
                "evidence":   str(evidence).strip(),
                "is_new_src": src not in node_context,
                "is_new_dst": dst not in node_context,
            })

    return valid, rejected


# ════════════════════════════════════════════════════════════════════════════
# Node resolver — create stubs for new entities
# ════════════════════════════════════════════════════════════════════════════

_NODE_TYPE_FROM_PREFIX = {
    "co_":     "company",
    "sec_":    "security",
    "pn_":     "person",
    "th_":     "thesis",
    "cn_":     "concept",
    "pl_":     "platform",
    "rg_":     "regime",
}


def _resolve_node_type(node_id: str) -> str:
    for prefix, nt in _NODE_TYPE_FROM_PREFIX.items():
        if node_id.startswith(prefix):
            return nt
    return "concept"  # safe fallback


def _ensure_nodes_exist(
    store: IntelStore,
    valid_edges: list[dict],
    dry_run: bool,
    verbose: bool,
) -> list[str]:
    """
    Upsert stub nodes for src/dst that don't exist yet.
    Returns list of new node IDs created.
    """
    created: list[str] = []
    seen: set[str] = set()

    for edge in valid_edges:
        for nid in (edge["src"], edge["dst"]):
            if nid in seen:
                continue
            seen.add(nid)
            is_new = edge.get("is_new_src") if nid == edge["src"] else edge.get("is_new_dst")
            if not is_new:
                continue

            nt   = _resolve_node_type(nid)
            name = nid.split("_", 1)[-1].replace("-", " ").title()
            if verbose:
                print(f"  [stub node] {nid}  type={nt}  name={name!r}")
            if not dry_run:
                store.upsert_node(
                    nid, nt, name,
                    aliases=[nid],
                    metadata={"stub": True, "oracle_source": "edge_extractor"},
                )
            created.append(nid)

    return created


# ════════════════════════════════════════════════════════════════════════════
# Core extract function
# ════════════════════════════════════════════════════════════════════════════

def extract(
    text: str,
    source_id: str,
    source_type: str = "article",
    dry_run: bool = True,
    model: str = "auto",
    verbose: bool = False,
) -> dict:
    """
    Extract edges from text and write to soma.db.

    Args:
        text:        raw text to analyse.
        source_id:   provenance ID (e.g. "news/2026-05-04/reuters-nvda.txt").
        source_type: 'transcript'|'news'|'article'|'manual'|'10k'|'derived'.
        dry_run:     if True, parse + validate but do NOT write to DB.
        model:       'auto'|'ollama'|'claude'.
        verbose:     print per-edge detail.

    Returns:
        dict with keys: proposed, valid, rejected, written, new_nodes, raw_response
    """
    stats = {
        "proposed":     0,
        "valid":        0,
        "rejected":     0,
        "written":      0,
        "new_nodes":    0,
        "raw_response": "",
    }

    with IntelStore(db_path=DB_PATH) as store:
        # 1. Load entity context
        node_context = _load_node_context(store)
        if verbose:
            print(f"  context: {len(node_context)} nodes loaded for prompt")

        # 2. Build prompt + call LLM
        prompt = _build_prompt(text, node_context)
        if verbose:
            print(f"  calling LLM ({model})...")

        raw = _call_llm(prompt, model_hint=model)
        stats["raw_response"] = raw
        if verbose:
            print(f"  LLM raw ({len(raw)} chars):")
            for line in raw.splitlines()[:20]:
                print(f"    {line}")

        # 3. Parse
        proposed = _parse_llm_response(raw)
        stats["proposed"] = len(proposed)
        if verbose:
            print(f"  parsed: {len(proposed)} proposed edge(s)")

        if not proposed:
            if verbose:
                print("  no edges extracted.")
            return stats

        # 4. Validate
        valid, rejected = _validate_proposed_edges(proposed, node_context)
        stats["valid"]    = len(valid)
        stats["rejected"] = len(rejected)

        if verbose and rejected:
            print(f"  rejected {len(rejected)} edge(s):")
            for r in rejected:
                print(f"    {r.get('src','?')} -[{r.get('edge_type','?')}]-> "
                      f"{r.get('dst','?')} : {r.get('_reject_reasons', '?')}")

        if not valid:
            if verbose:
                print("  no valid edges to write.")
            return stats

        # 5. Ensure nodes exist (create stubs for new entities)
        created = _ensure_nodes_exist(store, valid, dry_run=dry_run, verbose=verbose)
        stats["new_nodes"] = len(created)

        # 6. Write edges
        for edge in valid:
            if verbose:
                ev_preview = (edge["evidence"][:60] + "...") if len(edge["evidence"]) > 60 else edge["evidence"]
                status = "[DRY RUN]" if dry_run else "[WRITE]"
                print(f"  {status} {edge['src']} -[{edge['edge_type']}]-> "
                      f"{edge['dst']}  conf={edge['confidence']:.2f}")
                if edge["evidence"]:
                    print(f"    evidence: {ev_preview}")

            if not dry_run:
                store.upsert_edge(
                    src         = edge["src"],
                    dst         = edge["dst"],
                    edge_type   = edge["edge_type"],
                    confidence  = edge["confidence"],
                    source_id   = source_id,
                    evidence    = edge["evidence"] or None,
                    source_type = source_type,
                    audit_status= "unaudited",
                )
                stats["written"] += 1
            else:
                stats["written"] += 1   # count as "would write" in dry-run

    return stats


# ════════════════════════════════════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract relationship edges from text into SOMA-INTEL graph"
    )
    src_group = parser.add_mutually_exclusive_group()
    src_group.add_argument("--text", "-t",
                           help="Text to analyse (inline string)")
    src_group.add_argument("--file", "-f",
                           type=Path,
                           help="Path to text file to analyse")

    parser.add_argument("--apply",
                        action="store_true",
                        help="Write to DB (default: dry run)")
    parser.add_argument("--source-type",
                        default="article",
                        choices=["transcript", "news", "article", "manual",
                                 "10k", "derived", "sitrep"],
                        help="Provenance category (default: article)")
    parser.add_argument("--source-id",
                        default="",
                        help="Provenance ID/path (auto-generated if omitted)")
    parser.add_argument("--model",
                        default="auto",
                        choices=["auto", "ollama", "claude"],
                        help="LLM backend (default: auto → Ollama then Claude)")
    parser.add_argument("--verbose", "-v",
                        action="store_true",
                        help="Show per-edge detail")

    args = parser.parse_args()

    # Read text
    text = ""
    if args.text:
        text = args.text
    elif args.file:
        if not args.file.exists():
            print(f"ERROR: file not found: {args.file}", file=sys.stderr)
            sys.exit(1)
        text = args.file.read_text(encoding="utf-8", errors="replace")
    elif not sys.stdin.isatty():
        text = sys.stdin.read()
    else:
        parser.print_help()
        sys.exit(1)

    text = text.strip()
    if not text:
        print("ERROR: empty input", file=sys.stderr)
        sys.exit(1)

    # Auto source_id
    from datetime import datetime, timezone
    now_str   = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    source_id = args.source_id or f"{args.source_type}/{now_str}"

    dry_run = not args.apply
    if dry_run:
        print("DRY RUN — pass --apply to write to DB")

    print(f"\nExtracting from {len(text):,} chars  source_type={args.source_type}")
    print(f"  source_id: {source_id}")
    print(f"  model:     {args.model}")

    try:
        stats = extract(
            text        = text,
            source_id   = source_id,
            source_type = args.source_type,
            dry_run     = dry_run,
            model       = args.model,
            verbose     = args.verbose,
        )
    except RuntimeError as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        print("Hint: ensure Ollama is running (ollama serve) or set ANTHROPIC_API_KEY",
              file=sys.stderr)
        sys.exit(1)

    action = "would write" if dry_run else "written"
    print(f"\nResult:")
    print(f"  proposed:  {stats['proposed']}")
    print(f"  valid:     {stats['valid']}")
    print(f"  rejected:  {stats['rejected']}")
    print(f"  {action}:   {stats['written']}")
    if stats["new_nodes"]:
        print(f"  new nodes: {stats['new_nodes']} stub(s) created")

    if dry_run and stats["valid"] > 0:
        print("\nDRY RUN complete — pass --apply to write to DB")


if __name__ == "__main__":
    main()
