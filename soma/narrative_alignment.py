"""
NarrativeAlignment — flags contradictions between CIPHER's outlook text
and MANTIS's portfolio positions + ORACLE's regime state.

Reads from SOMA:
    - outlook_snapshots  (CIPHER writes)
    - portfolio_state    (MANTIS writes)
    - regime_history     (ORACLE writes)

Output:
    - 0-5 inconsistencies with severity + contradiction_score
    - overall alignment score 0.0-1.0

Usage:
    with NarrativeAlignment() as na:
        result = na.analyze()
        na.print_terminal()
"""

import json
import os
import re
from datetime import datetime, timezone

from .soma_bridge import SomaBridge


# ── Keywords for sentiment detection ──────────────────────────────────

_BULLISH_KEYWORDS = [
    "bullish", "upside", "growth", "risk_on", "risk-on", "overweight",
    "buy", "accumulate", "accelerat", "momentum", "opportunit",
    "favorable", "constructive", "positive", "optimis", "recovery",
]

_BEARISH_KEYWORDS = [
    "bearish", "downside", "contraction", "risk_off", "risk-off",
    "underweight", "sell", "reduce", "defensive", "caution",
    "headwind", "deteriorat", "negative", "pessimis", "recession",
    "turbulence", "crisis", "protect", "preserve",
]

_REGIME_SENTIMENT = {
    "RISK_ON": "bullish",
    "SPECULATION": "bullish",
    "TURBULENCE": "bearish",
    "CRISIS": "bearish",
    "CONTRACTION": "bearish",
}


class NarrativeAlignment:
    """Scores alignment between narrative (outlook) and portfolio/regime reality."""

    def __init__(self, db_path=None):
        self.db_path = db_path
        self._bridge = None
        self._result = None

    def __enter__(self):
        self._bridge = SomaBridge(self.db_path)
        self._bridge.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._bridge:
            self._bridge.__exit__(exc_type, exc_val, exc_tb)
            self._bridge = None
        return False

    # ── Data fetching ──────────────────────────────────────────────────

    def _get_outlook(self):
        """Get latest outlook snapshot."""
        return self._bridge.get_latest_outlook()

    def _get_portfolio(self):
        """Get latest portfolio state."""
        return self._bridge.get_latest_portfolio_state()

    def _get_regime(self):
        """Get latest regime."""
        return self._bridge.get_latest_regime()

    def _get_regime_history(self, limit: int = 5) -> list[dict]:
        """Get recent regime history."""
        return self._bridge.get_regime_history(limit=limit)

    def _get_valuations(self):
        """Get latest valuations."""
        return self._bridge.get_latest_valuations()

    # ── Sentiment extraction ───────────────────────────────────────────

    def _extract_sentiment(self, text: str | None) -> float:
        """Score text sentiment as bullish (-1 to +1) based on keyword frequency.

        Returns:
            float: -1.0 (fully bearish) to +1.0 (fully bullish), 0.0 = neutral
        """
        if not text:
            return 0.0

        text_lower = text.lower()

        bull_count = sum(1 for kw in _BULLISH_KEYWORDS if kw in text_lower)
        bear_count = sum(1 for kw in _BEARISH_KEYWORDS if kw in text_lower)

        total = bull_count + bear_count
        if total == 0:
            return 0.0
        return (bull_count - bear_count) / total

    def _extract_conclusions(self, outlook):
        """Parse key conclusions from outlook snapshot."""
        if not outlook:
            return []
        try:
            raw = outlook.get("key_conclusions_json")
            if raw:
                return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            pass
        return []

    # ── Contradiction checks ───────────────────────────────────────────

    def _check_sentiment_vs_regime(self, outlook, regime):
        """Does the outlook tone match the current regime?"""
        if not outlook or not regime:
            return None

        conclusions = self._extract_conclusions(outlook)
        outlook_text = " ".join(conclusions) if conclusions else ""
        if not outlook_text:
            return None

        sentiment = self._extract_sentiment(outlook_text)
        regime_name = regime.get("regime", "")
        expected = _REGIME_SENTIMENT.get(regime_name)

        if expected is None:
            return None  # unknown regime, can't assess

        if expected == "bullish" and sentiment < -0.3:
            return {
                "type": "sentiment_vs_regime",
                "description": (
                    f"Outlook is bearish (score {sentiment:.2f}) "
                    f"but regime is {regime_name} (expected bullish tone)"
                ),
                "severity": "HIGH",
                "contradiction_score": abs(sentiment) * 0.8,
            }
        elif expected == "bearish" and sentiment > 0.3:
            return {
                "type": "sentiment_vs_regime",
                "description": (
                    f"Outlook is bullish (score {sentiment:.2f}) "
                    f"but regime is {regime_name} (expected defensive tone)"
                ),
                "severity": "HIGH",
                "contradiction_score": abs(sentiment) * 0.8,
            }
        return None

    def _check_exposure_vs_regime(self, portfolio, regime):
        """Does portfolio exposure match the regime signal?"""
        if not portfolio or not regime:
            return None

        cash_pct = portfolio.get("cash_pct")
        regime_name = regime.get("regime", "")
        expected = _REGIME_SENTIMENT.get(regime_name)

        if cash_pct is None or expected is None:
            return None

        exposure = 1.0 - cash_pct

        # Bearish regime but high exposure
        if expected == "bearish" and exposure > 0.80:
            return {
                "type": "exposure_vs_regime",
                "description": (
                    f"Portfolio exposure {exposure:.0%} is high "
                    f"for a {regime_name} regime (expected defensive)"
                ),
                "severity": "MEDIUM",
                "contradiction_score": (exposure - 0.60) * 1.5,
            }
        # Bullish regime but very low exposure
        elif expected == "bullish" and exposure < 0.40:
            return {
                "type": "exposure_vs_regime",
                "description": (
                    f"Portfolio exposure {exposure:.0%} is low "
                    f"for a {regime_name} regime (expected aggressive)"
                ),
                "severity": "MEDIUM",
                "contradiction_score": (0.60 - exposure) * 1.5,
            }
        return None

    def _check_outlook_vs_exposure(self, outlook, portfolio):
        """Does the outlook tone match portfolio positioning?"""
        if not outlook or not portfolio:
            return None

        conclusions = self._extract_conclusions(outlook)
        outlook_text = " ".join(conclusions) if conclusions else ""
        if not outlook_text:
            return None

        sentiment = self._extract_sentiment(outlook_text)
        cash_pct = portfolio.get("cash_pct")
        if cash_pct is None:
            return None

        exposure = 1.0 - cash_pct

        # Bullish outlook but defensive portfolio
        if sentiment > 0.3 and exposure < 0.40:
            return {
                "type": "outlook_vs_exposure",
                "description": (
                    f"Outlook is bullish (score {sentiment:.2f}) "
                    f"but portfolio is defensive ({exposure:.0%} exposure)"
                ),
                "severity": "MEDIUM",
                "contradiction_score": abs(sentiment) * (0.60 - exposure),
            }
        # Bearish outlook but aggressive portfolio
        elif sentiment < -0.3 and exposure > 0.80:
            return {
                "type": "outlook_vs_exposure",
                "description": (
                    f"Outlook is bearish (score {sentiment:.2f}) "
                    f"but portfolio is aggressive ({exposure:.0%} exposure)"
                ),
                "severity": "HIGH",
                "contradiction_score": abs(sentiment) * (exposure - 0.60),
            }
        return None

    def _check_drawdown_vs_outlook(self, outlook, portfolio):
        """Is the outlook optimistic despite a significant drawdown?"""
        if not outlook or not portfolio:
            return None

        dd = portfolio.get("dd_from_hwm")
        if dd is None:
            return None

        conclusions = self._extract_conclusions(outlook)
        outlook_text = " ".join(conclusions) if conclusions else ""
        sentiment = self._extract_sentiment(outlook_text)

        # Large drawdown + bullish narrative = possible conflict
        if dd < -15 and sentiment > 0.2:
            return {
                "type": "drawdown_vs_outlook",
                "description": (
                    f"Portfolio down {dd:.1f}% from HWM "
                    f"but outlook remains optimistic (score {sentiment:.2f})"
                ),
                "severity": "MEDIUM",
                "contradiction_score": abs(dd / 100) * sentiment,
            }
        return None

    def _check_regime_stability_vs_confidence(self, outlook, regime_history):
        """Is the outlook highly confident despite recent regime instability?"""
        if not outlook or len(regime_history) < 3:
            return None

        # Count regime changes in last 5 entries
        regimes = [h["regime"] for h in regime_history[:5]]
        changes = sum(1 for i in range(len(regimes) - 1) if regimes[i] != regimes[i + 1])

        conclusions = self._extract_conclusions(outlook)
        outlook_text = " ".join(conclusions) if conclusions else ""
        sentiment_strength = abs(self._extract_sentiment(outlook_text))

        # Unstable regime + strong conviction = inconsistency
        if changes >= 2 and sentiment_strength > 0.5:
            return {
                "type": "regime_instability",
                "description": (
                    f"{changes} regime changes in last {len(regimes)} entries "
                    f"but outlook shows strong conviction (|sentiment| = {sentiment_strength:.2f})"
                ),
                "severity": "LOW",
                "contradiction_score": changes * 0.15 * sentiment_strength,
            }
        return None

    # ── Main analysis ──────────────────────────────────────────────────

    def analyze(self):
        """Run all alignment checks.

        Returns:
            dict with 'inconsistencies', 'contradiction_score', 'alignment',
            'data_available', 'timestamp'
        """
        outlook = self._get_outlook()
        portfolio = self._get_portfolio()
        regime = self._get_regime()
        regime_history = self._get_regime_history(limit=5)
        valuations = self._get_valuations()

        # Track data availability
        data_available = {
            "outlook": outlook is not None,
            "portfolio": portfolio is not None,
            "regime": regime is not None,
            "valuations": len(valuations) > 0 if valuations else False,
        }

        inconsistencies = []

        # Run all checks
        checks = [
            self._check_sentiment_vs_regime(outlook, regime),
            self._check_exposure_vs_regime(portfolio, regime),
            self._check_outlook_vs_exposure(outlook, portfolio),
            self._check_drawdown_vs_outlook(outlook, portfolio),
            self._check_regime_stability_vs_confidence(outlook, regime_history),
        ]

        for result in checks:
            if result is not None:
                inconsistencies.append(result)

        # Compute overall contradiction score (0-1, higher = more contradictions)
        if inconsistencies:
            raw_score = sum(i["contradiction_score"] for i in inconsistencies)
            # Normalize: cap at 1.0
            contradiction_score = min(raw_score, 1.0)
        else:
            contradiction_score = 0.0

        # Alignment = inverse of contradiction
        alignment = round(1.0 - contradiction_score, 4)

        self._result = {
            "inconsistencies": inconsistencies,
            "contradiction_score": round(contradiction_score, 4),
            "alignment": alignment,
            "data_available": data_available,
            "checks_run": sum(1 for d in data_available.values() if d),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        return self._result

    # ── Terminal display ───────────────────────────────────────────────

    def print_terminal(self):
        """Print alignment results to terminal with ANSI colors."""
        if self._result is None:
            self.analyze()
        r = self._result

        BOLD = "\033[1m"
        RED = "\033[91m"
        YELLOW = "\033[93m"
        GREEN = "\033[92m"
        CYAN = "\033[96m"
        DIM = "\033[2m"
        RESET = "\033[0m"

        severity_color = {"HIGH": RED, "MEDIUM": YELLOW, "LOW": GREEN}

        print(f"\n{BOLD}{'=' * 60}{RESET}")
        print(f"{BOLD}  SOMA — Portfolio-Narrative Alignment{RESET}")
        print(f"{DIM}  {r['timestamp']}{RESET}")
        print(f"{BOLD}{'=' * 60}{RESET}")

        # Data availability
        da = r["data_available"]
        available = [k for k, v in da.items() if v]
        missing = [k for k, v in da.items() if not v]
        if missing:
            print(f"\n  {YELLOW}Missing data: {', '.join(missing)}{RESET}")
        if not available:
            print(f"\n  {RED}No data available — run ORACLE, MANTIS, and CIPHER first.{RESET}")
            return

        # Alignment score
        alignment = r["alignment"]
        if alignment >= 0.8:
            color = GREEN
            label = "ALIGNED"
        elif alignment >= 0.5:
            color = YELLOW
            label = "PARTIAL"
        else:
            color = RED
            label = "MISALIGNED"

        print(f"\n  {CYAN}Alignment:{RESET}  {color}{alignment:.0%} ({label}){RESET}")
        print(f"  {CYAN}Contradiction:{RESET}  {r['contradiction_score']:.2f}")

        # Inconsistencies
        if not r["inconsistencies"]:
            print(f"\n  {GREEN}No contradictions detected — narrative and portfolio are aligned.{RESET}")
        else:
            print(f"\n{BOLD}--- Inconsistencies ({len(r['inconsistencies'])}) ---{RESET}")
            for inc in r["inconsistencies"]:
                color = severity_color.get(inc["severity"], RESET)
                print(f"  {color}[{inc['severity']}]{RESET} {inc['description']}")

        print()

    # ── JSON log ───────────────────────────────────────────────────────

    def save_log(self):
        """Write alignment analysis to a JSON file in shared/soma/logs/."""
        if self._result is None:
            self.analyze()

        logs_dir = os.path.join(os.path.dirname(__file__), "logs")
        os.makedirs(logs_dir, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        path = os.path.join(logs_dir, f"alignment_{ts}.json")
        with open(path, "w") as f:
            json.dump(self._result, f, indent=2, default=str)
        return os.path.realpath(path)
