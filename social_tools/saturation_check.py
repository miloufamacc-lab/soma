"""
saturation_check.py
Builds a ready-to-paste Grok saturation prompt.

Usage:
    from shared.social_tools.saturation_check import build_grok_saturation_prompt

    prompt = build_grok_saturation_prompt(
        angle="optimus inference economics at scale",
        key_terms=["optimus", "inference cost", "robotics margin"],
        days_back=3,
    )
    print(prompt)  # paste into Grok DeepSearch
"""

from __future__ import annotations


def build_grok_saturation_prompt(
    angle: str,
    key_terms: list[str],
    days_back: int = 3,
) -> str:
    """
    Build a copy-paste-ready Grok saturation-check prompt.

    Args:
        angle:      The specific angle or thesis being considered for a post.
        key_terms:  Key words or phrases to search for on X/Twitter.
        days_back:  How many calendar days back to check. Default 3.

    Returns:
        A formatted string block ready to paste into Grok DeepSearch.
    """
    terms_formatted = "\n".join(f'  - "{t}"' for t in key_terms)

    return f"""\
━━━ SATURATION CHECK — PASTE INTO GROK DEEPSEARCH ━━━

Angle under review:
  {angle}

Key terms to search (X / Twitter, last {days_back} days):
{terms_formatted}

Answer the following for each key term and for the overall angle:

1. HOW MANY posts in the last {days_back} days address this exact angle or use
   these exact key terms? Give an approximate count.

2. WHAT specific claims or framings are already saturated (said multiple times)?
   Quote the most repeated framing in ≤ 15 words.

3. WHAT sub-angles or contrarian takes are NOT yet covered?
   List up to 3 gaps.

4. Did any accounts from the tier-1 watchlist post on this?
   If yes, name the account and summarize their angle in ≤ 10 words.

5. OVERALL SATURATION LEVEL for this angle:
   LOW (< 5 posts) / MEDIUM (5–20 posts) / HIGH (> 20 posts)

Paste Grok's full response below the line to proceed with drafting.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[PASTE GROK RESPONSE HERE]
"""
