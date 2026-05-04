#!/usr/bin/env python3
"""
numeric_validator.py — Numerical Claim Validation for DABEIBA

Takes the P5 output (numeric/temporal claims from five_pass_scanner.py) and
validates them against VAULT data and known wiki facts. Outputs a validation
table that feeds into the scratchpad and deck stat-box badges.

Usage:
  # Validate scanner P5 output against VAULT and wiki
  python3 numeric_validator.py validate scanner_results.json

  # Validate a single claim manually
  python3 numeric_validator.py check "$1.8T" --context "private credit market size" --ticker ""

  # Validate all ticker-related claims against VAULT
  python3 numeric_validator.py vault-check scanner_results.json

Output: JSON with validation status (VERIFIED / UNVERIFIED / DISPUTED / STALE)
and confidence adjustment recommendations.

Validation statuses:
  VERIFIED   — claim matches a known data source within 10% tolerance
  DISPUTED   — claim differs from known data by >20%
  STALE      — claim references data older than 90 days with no recent update
  UNVERIFIED — no matching data source found (default — not a red flag)
"""

import argparse
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

def _resolve_dabeiba_root() -> Path:
    """3-tier fallback: $DABEIBA_ROOT -> ~/Desktop/DABEIBA -> walk up from __file__."""
    env = os.environ.get("DABEIBA_ROOT")
    if env:
        return Path(env)
    default_home = Path.home() / "Desktop" / "DABEIBA"
    if default_home.exists():
        return default_home
    here = Path(__file__).resolve()
    for parent in here.parents:
        if parent.name == "DABEIBA":
            return parent
    return default_home


_DABEIBA = _resolve_dabeiba_root()
VAULT_DB = _DABEIBA / "oracle" / "vault" / "oracle_vault.db"
WIKI_DB = _DABEIBA / "wiki" / "indexes" / "articles.sqlite"

# Tolerance thresholds
MATCH_TOLERANCE = 0.10     # within 10% = VERIFIED
DISPUTE_TOLERANCE = 0.20   # beyond 20% = DISPUTED
STALE_DAYS = 90            # data older than 90 days = STALE


def parse_money(s: str) -> float | None:
    """Parse money amounts like '$1.8 trillion', '$950 million', '$73,300'."""
    s = s.strip().replace(",", "")
    multipliers = {
        'trillion': 1e12, 'T': 1e12,
        'billion': 1e9, 'B': 1e9,
        'million': 1e6, 'M': 1e6,
        'thousand': 1e3, 'K': 1e3,
    }

    # Remove $ sign
    s = s.replace('$', '')

    # Try with named multipliers
    for word, mult in multipliers.items():
        if word.lower() in s.lower():
            num_part = re.search(r'[\d.]+', s)
            if num_part:
                return float(num_part.group()) * mult

    # Try with suffix letters ($1.8T, $950M)
    m = re.match(r'([\d.]+)\s*([TBMK])', s, re.IGNORECASE)
    if m:
        num = float(m.group(1))
        suffix = m.group(2).upper()
        for word, mult in multipliers.items():
            if word == suffix:
                return num * mult

    # Plain number
    try:
        return float(s)
    except ValueError:
        return None


def parse_percentage(s: str) -> float | None:
    """Parse percentages like '41.9%', '-7%', '300%'."""
    m = re.search(r'-?[\d.]+', s.replace('%', ''))
    if m:
        return float(m.group())
    return None


def check_vault_ticker(ticker: str) -> dict | None:
    """Query VAULT for latest valuation data for a ticker."""
    if not VAULT_DB.exists():
        return None

    try:
        conn = sqlite3.connect(str(VAULT_DB))
        c = conn.cursor()
        c.execute("""
            SELECT v.ticker, v.price_usd, v.dcf_fair_value, v.implied_upside,
                   v.mktcap_b, v.gf_score, r.date
            FROM valuations v
            JOIN runs r ON v.run_id = r.run_id
            WHERE v.ticker = ?
            ORDER BY r.date DESC LIMIT 1
        """, (ticker.upper(),))
        row = c.fetchone()
        conn.close()

        if row:
            return {
                "ticker": row[0],
                "price_usd": row[1],
                "dcf_fair_value": row[2],
                "implied_upside": row[3],
                "mktcap_b": row[4],
                "gf_score": row[5],
                "date": row[6],
            }
    except Exception:
        pass
    return None


def search_wiki_for_number(context: str) -> list:
    """Search wiki FTS5 for articles matching the context of a numeric claim."""
    if not WIKI_DB.exists():
        return []

    results = []
    try:
        conn = sqlite3.connect(str(WIKI_DB))
        c = conn.cursor()
        # Clean context for FTS5 query
        clean = re.sub(r'[^\w\s]', '', context)
        words = clean.split()[:5]  # max 5 keywords
        if not words:
            return []
        query = " ".join(words)
        c.execute("""
            SELECT m.slug, snippet(articles_fts, 0, '>>>', '<<<', '...', 20)
            FROM articles_fts f
            JOIN articles_meta m ON f.rowid = m.rowid
            WHERE articles_fts MATCH ?
            ORDER BY rank LIMIT 3
        """, (query,))
        for row in c.fetchall():
            results.append({"slug": row[0], "snippet": row[1]})
        conn.close()
    except Exception:
        pass
    return results


def validate_claim(value_str: str, context: str, known_data: dict = None) -> dict:
    """
    Validate a single numeric claim.

    Returns: {status, confidence_adjustment, reason, reference}
    """
    result = {
        "original": value_str,
        "context": context,
        "status": "UNVERIFIED",
        "confidence_adjustment": 0.0,
        "reason": "No matching reference data found",
        "reference": None,
    }

    parsed = parse_money(value_str) or parse_percentage(value_str)
    if parsed is None:
        result["reason"] = "Could not parse numeric value"
        return result

    # Check against provided known data
    if known_data:
        ref_val = known_data.get("value")
        if ref_val is not None:
            try:
                ref_val = float(ref_val)
                if ref_val != 0:
                    delta = abs(parsed - ref_val) / abs(ref_val)
                    result["reference"] = {
                        "value": ref_val,
                        "source": known_data.get("source", "VAULT"),
                        "date": known_data.get("date", "unknown"),
                    }

                    if delta <= MATCH_TOLERANCE:
                        result["status"] = "VERIFIED"
                        result["confidence_adjustment"] = 0.05
                        result["reason"] = f"Within {delta:.1%} of reference ({ref_val})"
                    elif delta <= DISPUTE_TOLERANCE:
                        result["status"] = "UNVERIFIED"
                        result["confidence_adjustment"] = 0.0
                        result["reason"] = f"Close but {delta:.1%} off reference ({ref_val})"
                    else:
                        result["status"] = "DISPUTED"
                        result["confidence_adjustment"] = -0.10
                        result["reason"] = f"Off by {delta:.1%} from reference ({ref_val})"

                    # Check staleness
                    ref_date = known_data.get("date")
                    if ref_date:
                        try:
                            d = datetime.strptime(ref_date, "%Y-%m-%d")
                            if (datetime.now() - d).days > STALE_DAYS:
                                result["status"] = "STALE"
                                result["reason"] += f" — reference data is {(datetime.now() - d).days} days old"
                        except ValueError:
                            pass
            except (ValueError, TypeError):
                pass

    # Search wiki for context
    wiki_hits = search_wiki_for_number(context)
    if wiki_hits:
        result["wiki_references"] = wiki_hits

    return result


def validate_scanner_output(scanner_json_path: str) -> dict:
    """Validate all numeric claims from a five_pass_scanner.py output file."""
    with open(scanner_json_path) as f:
        scanner = json.load(f)

    p5 = scanner.get("pass_5_numerics", {})
    results = {
        "source": scanner_json_path,
        "validated_at": datetime.now().isoformat(),
        "money_validations": [],
        "percentage_validations": [],
        "summary": {
            "total_claims": 0,
            "verified": 0,
            "disputed": 0,
            "stale": 0,
            "unverified": 0,
        },
    }

    # Validate money amounts
    for amount in p5.get("money_amounts", []):
        v = validate_claim(amount, f"money amount: {amount}")
        results["money_validations"].append(v)
        results["summary"]["total_claims"] += 1
        results["summary"][v["status"].lower()] += 1

    # Validate percentages
    for pct in p5.get("percentages", []):
        v = validate_claim(pct, f"percentage: {pct}")
        results["percentage_validations"].append(v)
        results["summary"]["total_claims"] += 1
        results["summary"][v["status"].lower()] += 1

    return results


def vault_check(scanner_json_path: str) -> dict:
    """Cross-check ticker-related claims against VAULT."""
    with open(scanner_json_path) as f:
        scanner = json.load(f)

    # Extract tickers mentioned in the scanner context
    full_text = json.dumps(scanner)
    # Common ticker patterns
    ticker_pattern = r'\b([A-Z]{2,5})\b'
    potential_tickers = set(re.findall(ticker_pattern, full_text))

    # Filter to plausible tickers (not common words)
    exclude = {'THE', 'AND', 'FOR', 'NOT', 'BUT', 'ALL', 'CAN', 'HAS', 'HIS',
               'HOW', 'ITS', 'MAY', 'NEW', 'NOW', 'OLD', 'OUR', 'OUT', 'OWN',
               'SAY', 'SHE', 'TOO', 'USE', 'WAY', 'WHO', 'BOY', 'DID', 'GET',
               'HIM', 'HIT', 'LET', 'PUT', 'RUN', 'SAT', 'TOP', 'RED', 'YES',
               'USD', 'EUR', 'GBP', 'CAD', 'BTC', 'ETH', 'SOL', 'FED', 'GDP',
               'CPI', 'PCE', 'NFP', 'ATH', 'BLS', 'SEC', 'IPO', 'CEO', 'COO',
               'CFO', 'CTO', 'API', 'JSON', 'SQL', 'FTS', 'CLI', 'PASS', 'META'}

    tickers = [t for t in potential_tickers if t not in exclude and len(t) >= 2]

    results = {"tickers_checked": [], "vault_matches": []}

    for ticker in tickers:
        vault_data = check_vault_ticker(ticker)
        if vault_data:
            results["vault_matches"].append(vault_data)
            results["tickers_checked"].append(ticker)

    return results


def main():
    parser = argparse.ArgumentParser(description="Numerical Claim Validator for DABEIBA")
    sub = parser.add_subparsers(dest="command")

    # validate command
    vp = sub.add_parser("validate", help="Validate all numeric claims from scanner output")
    vp.add_argument("scanner_json", help="Path to five_pass_scanner.py output JSON")
    vp.add_argument("--output", help="Output JSON path")

    # check command
    cp = sub.add_parser("check", help="Validate a single claim")
    cp.add_argument("value", help="The numeric value to check (e.g., '$1.8T')")
    cp.add_argument("--context", default="", help="Context for the claim")
    cp.add_argument("--reference", type=float, help="Known reference value for comparison")
    cp.add_argument("--ref-source", default="manual", help="Source of reference value")
    cp.add_argument("--ref-date", default="", help="Date of reference value (YYYY-MM-DD)")

    # vault-check command
    vc = sub.add_parser("vault-check", help="Cross-check against VAULT ticker data")
    vc.add_argument("scanner_json", help="Path to five_pass_scanner.py output JSON")

    args = parser.parse_args()

    if args.command == "validate":
        results = validate_scanner_output(args.scanner_json)
        output = json.dumps(results, indent=2)
        if args.output:
            Path(args.output).write_text(output)
            print(f"Validation written to {args.output}", file=sys.stderr)
        else:
            print(output)

        # Print summary
        s = results["summary"]
        print(f"\n=== Validation Summary ===", file=sys.stderr)
        print(f"Total claims: {s['total_claims']}", file=sys.stderr)
        print(f"  VERIFIED:   {s['verified']}", file=sys.stderr)
        print(f"  DISPUTED:   {s['disputed']}", file=sys.stderr)
        print(f"  STALE:      {s['stale']}", file=sys.stderr)
        print(f"  UNVERIFIED: {s['unverified']}", file=sys.stderr)

    elif args.command == "check":
        known = None
        if args.reference is not None:
            known = {"value": args.reference, "source": args.ref_source, "date": args.ref_date}
        result = validate_claim(args.value, args.context, known)
        print(json.dumps(result, indent=2))

    elif args.command == "vault-check":
        results = vault_check(args.scanner_json)
        print(json.dumps(results, indent=2))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
