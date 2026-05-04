"""
HORIZON Event / Geopolitical Lens — Calendar & Regime Risk (Weight: 7%)
Pipeline: SOMA/HORIZON | Module: SOMA

Reads from Synthesis (SOMA):
    - events table (upcoming economic calendar, regulatory, market structure)
    - regime_history (to contextualize event impact)

Reads from web_context (optional):
    - fomc_dates, cpi_dates, earnings_dates, regulatory_events,
      geopolitical_events, tariff_events

Produces:
    - Calendar risk signal (clear runway / event cluster / high event risk)
    - Days-to-next-catalyst computation
    - Event density score (events per week in next 4 weeks)
    - Per-ticker event risk (earnings, regulatory specific to TSLA/MSTR)

CFA grounding: "Event risk is a non-diversifiable short-term risk factor.
Concentrated positions face asymmetric event exposure — a single regulatory
ruling or earnings miss can dominate quarterly returns." — CFA L3 Portfolio.

Design: This lens is conservative by nature. It rarely produces strong BUY
signals (events create risk, not opportunity). Its main role is to flag
windows where action should be DELAYED or ACCELERATED.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from typing import Optional

from ..horizon_dataclasses import (
    Direction,
    HoldingSignal,
    LensName,
    LensResult,
)
from ..soma_bridge import SomaBridge


# ─── Event Risk Thresholds ─────────────────────────────────────────────────

# Days to event proximity
_EVENT_IMMINENT = 3          # Within 3 trading days
_EVENT_NEAR = 7              # Within 1 week
_EVENT_MEDIUM = 14           # Within 2 weeks
_EVENT_FAR = 28              # Within 4 weeks

# Event density (events per 2-week window)
_DENSITY_LOW = 1
_DENSITY_MODERATE = 3
_DENSITY_HIGH = 5
_DENSITY_EXTREME = 8

# Impact weights by event type
_EVENT_IMPACT = {
    "fomc": 0.9,              # Federal Reserve decisions
    "cpi": 0.8,               # Inflation data
    "jobs": 0.7,              # NFP / employment
    "gdp": 0.6,               # GDP releases
    "earnings": 0.8,          # Portfolio company earnings
    "tariff": 0.85,           # Trade policy (highly relevant 2025-2026)
    "regulatory": 0.7,        # SEC, NHTSA, EPA rulings
    "geopolitical": 0.6,      # Conflict, sanctions, elections
    "opex": 0.5,              # Options expiration
    "debt_ceiling": 0.9,      # Government funding
    "other": 0.3,
}

# ─── Known Calendar (hardcoded for near-term, refreshed by orchestrator) ───

# FOMC 2026 meeting dates (announcement days)
_FOMC_2026 = [
    "2026-01-28", "2026-03-18", "2026-05-06", "2026-06-17",
    "2026-07-29", "2026-09-16", "2026-11-04", "2026-12-16",
]

# CPI release dates 2026 (approximate — usually 2nd week of month)
_CPI_2026 = [
    "2026-01-14", "2026-02-12", "2026-03-12", "2026-04-10",
    "2026-05-13", "2026-06-11", "2026-07-14", "2026-08-12",
    "2026-09-10", "2026-10-13", "2026-11-12", "2026-12-10",
]

# NFP release dates 2026 (usually first Friday of month)
_NFP_2026 = [
    "2026-01-09", "2026-02-06", "2026-03-06", "2026-04-03",
    "2026-05-08", "2026-06-05", "2026-07-02", "2026-08-07",
    "2026-09-04", "2026-10-02", "2026-11-06", "2026-12-04",
]

# Quarterly OpEx (triple/quad witching) — 3rd Friday of Mar/Jun/Sep/Dec
_OPEX_2026 = ["2026-03-20", "2026-06-19", "2026-09-18", "2026-12-18"]


class EventLens:
    """Event / Geopolitical lens — calendar risk for HORIZON.

    Usage:
        with EventLens() as lens:
            result = lens.analyze(tickers=["TSLA", "MSTR"])
    """

    def __init__(self, db_path=None):
        self.db_path = db_path
        self._bridge: Optional[SomaBridge] = None

    def __enter__(self):
        self._bridge = SomaBridge(self.db_path)
        self._bridge.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._bridge:
            self._bridge.__exit__(exc_type, exc_val, exc_tb)
            self._bridge = None
        return False

    # ── Main analysis ────────────────────────────────────────────────

    def analyze(
        self,
        tickers: list[str] | None = None,
        web_context: dict | None = None,
    ) -> LensResult:
        """Run the event/geopolitical lens analysis.

        Args:
            tickers: Portfolio tickers to analyze.
            web_context: Optional enriched data from orchestrator.
                Keys: earnings_dates ({ticker: date_str}),
                      regulatory_events (list of {date, description, impact}),
                      geopolitical_events (list of {date, description, impact}),
                      tariff_events (list of {date, description, impact})

        Returns:
            LensResult with event risk signal.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        today = datetime.now(timezone.utc).date()
        tickers = [t.upper() for t in (tickers or [])]
        web_context = web_context or {}

        # 1. Build unified event calendar
        events = self._build_event_calendar(today, tickers, web_context)

        # 2. Read SOMA events table for any custom entries
        soma_events = self._read_soma_events()
        events.extend(soma_events)

        # 3. Sort by date
        events.sort(key=lambda e: e.get("date", "9999-12-31"))

        # 4. Compute calendar metrics
        metrics = self._compute_calendar_metrics(events, today)

        # 5. Compute per-ticker event risk
        ticker_risks = {}
        for ticker in tickers:
            ticker_risks[ticker] = self._compute_ticker_risk(
                ticker, events, today, web_context
            )

        # 6. Synthesize into signal
        signal, confidence, drivers, rationale = self._synthesize(
            metrics, ticker_risks, events, today, tickers
        )

        # 7. Build per-holding signals
        holding_signals = []
        for ticker in tickers:
            t_risk = ticker_risks.get(ticker, {})
            t_signal = max(-1.0, min(1.0, signal + t_risk.get("signal_adj", 0)))
            holding_signals.append(HoldingSignal(
                ticker=ticker,
                signal=t_signal,
                direction=self._signal_to_direction(t_signal),
                confidence=confidence,
                rationale=t_risk.get("rationale", f"Event risk for {ticker}"),
                data_points={
                    "days_to_next_event": metrics.get("days_to_next", 999),
                    "event_density_2w": metrics.get("density_2w", 0),
                    "ticker_specific_events": t_risk.get("n_events", 0),
                },
            ))

        return LensResult(
            lens_name=LensName.GEOPOLITICAL,
            timestamp=now_iso,
            signal=signal,
            direction=self._signal_to_direction(signal),
            confidence=confidence,
            rationale=rationale,
            holding_signals=holding_signals,
            data_freshness_hours=0.0,  # Calendar data is static
            key_drivers=drivers[:3],
            warnings=self._build_warnings(events, web_context),
            raw_data={
                "n_events_4w": metrics.get("n_events_4w", 0),
                "density_2w": metrics.get("density_2w", 0),
                "days_to_next": metrics.get("days_to_next", 999),
                "next_event": metrics.get("next_event_desc", "none"),
                "calendar_state": metrics.get("calendar_state", "UNKNOWN"),
                "events": [
                    {k: v for k, v in e.items() if k != "raw"}
                    for e in events[:10]
                ],
            },
        )

    # ── Event calendar builder ───────────────────────────────────────

    def _build_event_calendar(
        self,
        today,
        tickers: list[str],
        web_context: dict,
    ) -> list[dict]:
        """Build a unified event calendar from hardcoded + web sources."""
        events = []
        cutoff = today + timedelta(days=_EVENT_FAR)

        # FOMC dates
        for d in _FOMC_2026:
            dt = self._parse_date(d)
            if dt and today <= dt <= cutoff:
                events.append({
                    "date": d,
                    "type": "fomc",
                    "description": f"FOMC meeting decision",
                    "impact": _EVENT_IMPACT["fomc"],
                    "source": "hardcoded_calendar",
                })

        # CPI dates
        for d in _CPI_2026:
            dt = self._parse_date(d)
            if dt and today <= dt <= cutoff:
                events.append({
                    "date": d,
                    "type": "cpi",
                    "description": "CPI inflation release",
                    "impact": _EVENT_IMPACT["cpi"],
                    "source": "hardcoded_calendar",
                })

        # NFP dates
        for d in _NFP_2026:
            dt = self._parse_date(d)
            if dt and today <= dt <= cutoff:
                events.append({
                    "date": d,
                    "type": "jobs",
                    "description": "Non-Farm Payrolls release",
                    "impact": _EVENT_IMPACT["jobs"],
                    "source": "hardcoded_calendar",
                })

        # Quarterly OpEx
        for d in _OPEX_2026:
            dt = self._parse_date(d)
            if dt and today <= dt <= cutoff:
                events.append({
                    "date": d,
                    "type": "opex",
                    "description": "Quarterly options expiration",
                    "impact": _EVENT_IMPACT["opex"],
                    "source": "hardcoded_calendar",
                })

        # Web context events
        for key, event_type in [
            ("regulatory_events", "regulatory"),
            ("geopolitical_events", "geopolitical"),
            ("tariff_events", "tariff"),
        ]:
            ctx_events = web_context.get(key, [])
            for evt in ctx_events:
                if isinstance(evt, dict) and evt.get("date"):
                    dt = self._parse_date(evt["date"])
                    if dt and today <= dt <= cutoff:
                        events.append({
                            "date": evt["date"],
                            "type": event_type,
                            "description": evt.get("description", f"{event_type} event"),
                            "impact": evt.get("impact", _EVENT_IMPACT.get(event_type, 0.5)),
                            "source": "web_context",
                        })

        # Earnings dates from web context
        earnings = web_context.get("earnings_dates", {})
        for ticker in tickers:
            if ticker in earnings:
                d = earnings[ticker]
                dt = self._parse_date(d)
                if dt and today <= dt <= cutoff:
                    events.append({
                        "date": d,
                        "type": "earnings",
                        "ticker": ticker,
                        "description": f"{ticker} earnings release",
                        "impact": _EVENT_IMPACT["earnings"],
                        "source": "web_context",
                    })

        return events

    # ── SOMA events ──────────────────────────────────────────────────

    def _read_soma_events(self) -> list[dict]:
        """Read upcoming events from SOMA events table."""
        if not self._bridge or not self._bridge.conn:
            return []

        try:
            rows = self._bridge.conn.execute(
                """SELECT * FROM events
                   WHERE date(substr(write_timestamp, 1, 10)) >= date('now', '-7 days')
                   ORDER BY id DESC LIMIT 20"""
            ).fetchall()

            events = []
            for row in rows:
                entry = dict(row)
                events.append({
                    "date": entry.get("date", entry.get("write_timestamp", "")[:10]),
                    "type": entry.get("event_type", "other"),
                    "description": entry.get("description", "SOMA event"),
                    "impact": _EVENT_IMPACT.get(entry.get("event_type", "other"), 0.3),
                    "source": "soma_events",
                })
            return events

        except Exception:
            return []

    # ── Calendar metrics ─────────────────────────────────────────────

    def _compute_calendar_metrics(self, events: list[dict], today) -> dict:
        """Compute calendar-level risk metrics."""
        if not events:
            return {
                "n_events_4w": 0,
                "density_2w": 0,
                "days_to_next": 999,
                "next_event_desc": "No events in window",
                "calendar_state": "CLEAR_RUNWAY",
            }

        # Filter to future events
        future = []
        for e in events:
            dt = self._parse_date(e.get("date", ""))
            if dt and dt >= today:
                e["_date"] = dt
                future.append(e)

        if not future:
            return {
                "n_events_4w": 0,
                "density_2w": 0,
                "days_to_next": 999,
                "next_event_desc": "No future events",
                "calendar_state": "CLEAR_RUNWAY",
            }

        # Days to next event
        days_to_next = (future[0]["_date"] - today).days
        next_desc = future[0].get("description", "unknown")

        # Events in next 2 weeks
        two_weeks = today + timedelta(days=14)
        events_2w = [e for e in future if e["_date"] <= two_weeks]
        density_2w = len(events_2w)

        # Events in next 4 weeks
        n_events_4w = len(future)

        # Weighted impact score (sum of impact * proximity weight)
        impact_score = 0
        for e in future:
            days = max(1, (e["_date"] - today).days)
            proximity_weight = 1.0 / (days / 7)  # Closer = heavier weight
            impact_score += e.get("impact", 0.5) * min(proximity_weight, 3.0)

        # Calendar state classification
        if density_2w >= _DENSITY_EXTREME:
            calendar_state = "EXTREME_EVENT_CLUSTER"
        elif density_2w >= _DENSITY_HIGH:
            calendar_state = "HIGH_EVENT_DENSITY"
        elif density_2w >= _DENSITY_MODERATE:
            calendar_state = "MODERATE_EVENT_DENSITY"
        elif days_to_next <= _EVENT_IMMINENT:
            calendar_state = "IMMINENT_EVENT"
        elif days_to_next > _EVENT_MEDIUM:
            calendar_state = "CLEAR_RUNWAY"
        else:
            calendar_state = "NORMAL"

        return {
            "n_events_4w": n_events_4w,
            "density_2w": density_2w,
            "days_to_next": days_to_next,
            "next_event_desc": next_desc,
            "calendar_state": calendar_state,
            "impact_score": impact_score,
        }

    # ── Per-ticker risk ──────────────────────────────────────────────

    def _compute_ticker_risk(
        self, ticker: str, events: list[dict], today, web_context: dict
    ) -> dict:
        """Compute ticker-specific event risk."""
        # Find events specific to this ticker
        ticker_events = [
            e for e in events
            if e.get("ticker") == ticker or (
                ticker == "TSLA" and e.get("type") in ("regulatory", "tariff")
            ) or (
                ticker == "MSTR" and e.get("type") == "regulatory"
            )
        ]

        signal_adj = 0.0
        parts = []

        # Earnings proximity
        for e in ticker_events:
            if e.get("type") == "earnings":
                dt = self._parse_date(e.get("date", ""))
                if dt:
                    days = (dt - today).days
                    if days <= 3:
                        signal_adj -= 0.15  # Imminent earnings = uncertainty
                        parts.append(f"Earnings in {days}d — high uncertainty")
                    elif days <= 7:
                        signal_adj -= 0.1
                        parts.append(f"Earnings in {days}d")

        # TSLA-specific: tariff risk, regulatory (NHTSA, EPA)
        if ticker == "TSLA":
            tariff_events = [e for e in events if e.get("type") == "tariff"]
            if tariff_events:
                signal_adj -= 0.05
                parts.append(f"{len(tariff_events)} tariff events in window")

        # MSTR-specific: SEC/crypto regulatory risk
        if ticker == "MSTR":
            reg_events = [e for e in events if e.get("type") == "regulatory"]
            if reg_events:
                signal_adj -= 0.03
                parts.append(f"{len(reg_events)} regulatory events")

        signal_adj = max(-0.3, min(0.1, signal_adj))

        return {
            "signal_adj": signal_adj,
            "n_events": len(ticker_events),
            "rationale": f"{ticker}: " + ("; ".join(parts) if parts else "No ticker-specific events"),
        }

    # ── Signal synthesis ─────────────────────────────────────────────

    def _synthesize(
        self,
        metrics: dict,
        ticker_risks: dict,
        events: list[dict],
        today,
        tickers: list[str],
    ) -> tuple[float, float, list[str], str]:
        """Synthesize event calendar into a signal.

        NOTE: This lens is naturally bearish/neutral — events create risk,
        not opportunity. A clear runway is the only positive signal.
        """
        signal = 0.0
        drivers = []

        calendar_state = metrics.get("calendar_state", "NORMAL")
        days_to_next = metrics.get("days_to_next", 999)
        density_2w = metrics.get("density_2w", 0)

        # ── Calendar state component (main driver) ───────────────────
        if calendar_state == "CLEAR_RUNWAY":
            signal += 0.2
            drivers.append("Clear runway — no major events in next 2 weeks")
        elif calendar_state == "EXTREME_EVENT_CLUSTER":
            signal -= 0.4
            drivers.append(f"Extreme event cluster: {density_2w} events in 2 weeks")
        elif calendar_state == "HIGH_EVENT_DENSITY":
            signal -= 0.25
            drivers.append(f"High event density: {density_2w} events in 2 weeks")
        elif calendar_state == "MODERATE_EVENT_DENSITY":
            signal -= 0.1
            drivers.append(f"Moderate event density: {density_2w} events in 2 weeks")
        elif calendar_state == "IMMINENT_EVENT":
            signal -= 0.2
            next_desc = metrics.get("next_event_desc", "unknown")
            drivers.append(f"Imminent: {next_desc} in {days_to_next}d")
        else:
            signal += 0.05  # Normal = slight positive

        # ── FOMC proximity (extra weight — biggest single-day risk) ──
        fomc_events = [e for e in events if e.get("type") == "fomc"]
        if fomc_events:
            fomc_dt = self._parse_date(fomc_events[0].get("date", ""))
            if fomc_dt:
                fomc_days = (fomc_dt - today).days
                if fomc_days <= 3:
                    signal -= 0.15
                    drivers.append(f"FOMC in {fomc_days}d — peak uncertainty")
                elif fomc_days <= 7:
                    signal -= 0.1
                    drivers.append(f"FOMC in {fomc_days}d")

        # ── Clamp ────────────────────────────────────────────────────
        signal = max(-1.0, min(1.0, signal))

        # ── Confidence ───────────────────────────────────────────────
        confidence = 0.55  # Base — calendar data is reliable but impact is uncertain
        if calendar_state in ("EXTREME_EVENT_CLUSTER", "IMMINENT_EVENT"):
            confidence += 0.15  # High confidence when risk is clear
        elif calendar_state == "CLEAR_RUNWAY":
            confidence += 0.1
        # Less confident about far-future events
        if days_to_next > 14:
            confidence -= 0.1
        confidence = max(0.1, min(1.0, confidence))

        # ── Rationale ────────────────────────────────────────────────
        direction = self._signal_to_direction(signal)
        rationale = (
            f"Calendar state: {calendar_state}. "
            f"{metrics.get('n_events_4w', 0)} events in next 4 weeks, "
            f"{density_2w} in next 2 weeks. "
            f"Next event: {metrics.get('next_event_desc', 'none')} in {days_to_next}d. "
            f"Signal: {signal:+.2f} ({direction.value})."
        )

        return signal, confidence, drivers, rationale

    # ── Helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _parse_date(date_str: str):
        """Parse a YYYY-MM-DD string into a date object."""
        try:
            return datetime.strptime(date_str[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _signal_to_direction(signal: float) -> Direction:
        if signal <= -0.6:
            return Direction.STRONG_SELL
        if signal <= -0.2:
            return Direction.SELL
        if signal >= 0.6:
            return Direction.STRONG_BUY
        if signal >= 0.2:
            return Direction.BUY
        return Direction.NEUTRAL

    def _build_warnings(self, events: list[dict], web_context: dict) -> list[str]:
        warnings = []
        if not web_context:
            warnings.append("No enriched event data — using hardcoded calendar only")
        if not any(e.get("type") == "earnings" for e in events):
            warnings.append("No earnings dates available — check manually")
        return warnings

    def _empty_result(self, timestamp: str, reason: str) -> LensResult:
        return LensResult(
            lens_name=LensName.GEOPOLITICAL,
            timestamp=timestamp,
            signal=0.0,
            direction=Direction.NEUTRAL,
            confidence=0.0,
            rationale=f"Event/geopolitical lens unavailable: {reason}",
            warnings=[reason],
        )
