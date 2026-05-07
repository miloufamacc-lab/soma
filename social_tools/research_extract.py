"""
research_extract.py
Builds a ready-to-paste Gemini research extraction prompt.

Usage:
    from shared.social_tools.research_extract import build_gemini_extract_prompt

    prompt = build_gemini_extract_prompt(
        source_url="https://example.com/article",
        extraction_targets=[
            "Current Optimus unit production rate",
            "Target cost per unit",
            "Timeline for commercial deployment",
        ],
    )
    print(prompt)  # paste into Gemini
"""

from __future__ import annotations


def build_gemini_extract_prompt(
    source_url: str,
    extraction_targets: list[str],
) -> str:
    """
    Build a copy-paste-ready Gemini research extraction prompt.

    Args:
        source_url:          URL of the source article / document / transcript.
        extraction_targets:  List of specific facts or data points to extract.

    Returns:
        A formatted string block ready to paste into Gemini.
    """
    targets_formatted = "\n".join(
        f"  {i + 1}. {t}" for i, t in enumerate(extraction_targets)
    )

    return f"""\
━━━ RESEARCH EXTRACT — PASTE INTO GEMINI ━━━

Source:
  {source_url}

Extract the following from the source above:
{targets_formatted}

For EACH extraction target, provide:

  a) QUOTE — the most relevant passage from the source (≤ 50 words, verbatim).
             If nothing directly addresses it, write "NOT FOUND".

  b) REFERENCE — the exact section, paragraph heading, timestamp, or page number
                 where the quote appears.

  c) AMBIGUITY — note any conflicting signals, caveats, or missing context.
                 Write "NONE" if the claim is unambiguous.

  d) CONFIDENCE — rate your extraction confidence:
                  HIGH (directly stated) / MEDIUM (implied) / LOW (inferred)

Format: one numbered block per target. Do not summarize across targets.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[PASTE GEMINI RESPONSE HERE]
"""
