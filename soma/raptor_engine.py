"""
RAPTOR — Lead Scoring Engine (Phase 1)
Calculates and maintains lead scores for all prospects in the pipeline.

Usage:
    from soma.soma_bridge import SomaBridge
    from soma.raptor_engine import RaptorEngine, seed_scoring_rule

    with SomaBridge() as bridge:
        seed_scoring_rule(bridge)        # idempotent — seeds kb_rule on first run
        engine = RaptorEngine(bridge)
        score  = engine.calculate_lead_score(prospect_id)
        queue  = engine.get_action_queue()
        stats  = engine.get_pipeline_analytics()
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from itertools import groupby

_VERSION = "RAPTOR-1.1"

# ── Default scoring weights (override via SOMA kb_rule RAPTOR_LEAD_SCORING_V1) ─
_DEFAULT_WEIGHTS: dict[str, float] = {
    "assets":      0.35,
    "source":      0.25,
    "recency":     0.15,
    "engagement":  0.10,
    "geo_lang":    0.10,
    "complexity":  0.05,
}

# ── Factor lookup tables ────────────────────────────────────────────────────
_ASSET_SCORES: dict[str, int] = {
    "5M+": 100, "2M-5M": 80, "1M-2M": 60, "500K-1M": 40,
}

_SOURCE_SCORES: dict[str, int] = {
    "referral": 100, "coi": 90, "inbound": 80,
    "event": 60, "digital": 40, "cold": 20,
}

_GEO_LANG_SCORES: dict[tuple, int] = {
    ("QC", "FR"): 100, ("QC", "EN"): 80,
    ("ON", "FR"): 70,  ("ON", "EN"): 65,
    ("BC", "FR"): 65,  ("BC", "EN"): 60,
    ("AB", "FR"): 65,  ("AB", "EN"): 60,
}

# ── Action queue thresholds ─────────────────────────────────────────────────
THRESHOLD_IMMEDIATE = 80.0
THRESHOLD_NURTURE   = 50.0
OVERDUE_DAYS        = 30     # days without touchpoint → overdue follow-up
DECAY_RATE          = 0.90   # multiplier per 30-day inactive period
DECAY_FLOOR         = 5.0    # minimum score after decay


class RaptorEngine:
    """Lead scoring and action queue engine for RAPTOR.

    Scoring model (6 factors, weights sum to 1.0):
        assets      35%  — estimated AUM band
        source      25%  — prospect origin quality
        recency     15%  — days since last touchpoint
        engagement  10%  — number of touchpoints
        geo_lang    10%  — province + language fit
        complexity   5%  — advisory complexity proxy (maps to AUM band)

    Decay: raw_score × DECAY_RATE ^ (days_inactive / 30), floor at DECAY_FLOOR.
    """

    def __init__(self, bridge):
        self.bridge   = bridge
        self._weights = self._load_weights()

    # ── Weight loading ────────────────────────────────────────────────────

    def _load_weights(self) -> dict[str, float]:
        """Load weights from SOMA kb_rules. Falls back to _DEFAULT_WEIGHTS."""
        try:
            row = self.bridge.conn.execute(
                "SELECT rule_data FROM kb_rules WHERE rule_id = 'RAPTOR_LEAD_SCORING_V1'"
            ).fetchone()
            if row:
                data = json.loads(row["rule_data"])
                w = data.get("weights", {})
                if w and abs(sum(w.values()) - 1.0) < 0.01:
                    return w
        except Exception:
            pass
        return dict(_DEFAULT_WEIGHTS)

    # ── Static factor scorers ─────────────────────────────────────────────

    @staticmethod
    def _score_assets(band: str | None) -> float:
        return float(_ASSET_SCORES.get(band or "", 20))

    @staticmethod
    def _score_source(source_type: str | None) -> float:
        return float(_SOURCE_SCORES.get(source_type or "", 10))

    @staticmethod
    def _score_recency(last_activity_date: str | None) -> float:
        """Days since last touchpoint / update → score."""
        if not last_activity_date:
            return 10.0
        try:
            last = date.fromisoformat(last_activity_date[:10])
            days = (date.today() - last).days
        except ValueError:
            return 10.0
        if days <= 7:   return 100.0
        if days <= 30:  return 75.0
        if days <= 90:  return 50.0
        if days <= 180: return 25.0
        return 10.0

    @staticmethod
    def _score_engagement(touchpoint_count: int) -> float:
        if touchpoint_count >= 5: return 100.0
        if touchpoint_count >= 3: return 75.0
        if touchpoint_count == 2: return 50.0
        if touchpoint_count == 1: return 25.0
        return 0.0

    @staticmethod
    def _score_geo_lang(province: str | None, language: str | None) -> float:
        key = ((province or "").upper(), (language or "").upper())
        score = _GEO_LANG_SCORES.get(key)
        if score is not None:
            return float(score)
        if key[0]:   # known province, unknown or unexpected language
            return 50.0
        return 40.0  # fully unknown

    @staticmethod
    def _score_complexity(band: str | None) -> float:
        """Advisory complexity proxy — higher AUM = more complex needs."""
        return float(_ASSET_SCORES.get(band or "", 30))

    @staticmethod
    def _apply_decay(raw_score: float, last_activity_date: str | None) -> float:
        """Decay score by DECAY_RATE per 30-day inactive period. Floor at DECAY_FLOOR."""
        if not last_activity_date:
            # No known activity — assume 6 months idle
            return max(DECAY_FLOOR, raw_score * (DECAY_RATE ** 6))
        try:
            last = date.fromisoformat(last_activity_date[:10])
            days_inactive = max(0, (date.today() - last).days)
        except ValueError:
            return raw_score
        months = days_inactive / 30.0
        return max(DECAY_FLOOR, raw_score * (DECAY_RATE ** months))

    # ── Core scoring ──────────────────────────────────────────────────────

    def calculate_lead_score(
        self, prospect_id: str, write_back: bool = True
    ) -> float:
        """Score a single prospect and optionally persist it to DB.

        Returns score in [0, 100] (float, rounded to 2 dp).
        Raises ValueError if prospect_id not found.
        """
        p = self.bridge.get_prospect(prospect_id)
        if not p:
            raise ValueError(f"[RAPTOR] Unknown prospect_id: {prospect_id}")

        # Last activity = most recent touchpoint date, else prospect update date
        tps = self.bridge.get_touchpoints(prospect_id)
        last_tp = max((t["date"][:10] for t in tps), default=None) if tps else None
        last_activity = last_tp or p.get("updated_date") or p.get("created_date")

        # Factor scores (each 0–100)
        s_assets      = self._score_assets(p.get("estimated_assets_band"))
        s_source      = self._score_source(p.get("source_type"))
        s_recency     = self._score_recency(last_activity)
        s_engagement  = self._score_engagement(len(tps))
        s_geo_lang    = self._score_geo_lang(p.get("province"), p.get("language_pref"))
        s_complexity  = self._score_complexity(p.get("estimated_assets_band"))

        w = self._weights
        raw = (
            w["assets"]     * s_assets    +
            w["source"]     * s_source    +
            w["recency"]    * s_recency   +
            w["engagement"] * s_engagement +
            w["geo_lang"]   * s_geo_lang  +
            w["complexity"] * s_complexity
        )

        score = round(self._apply_decay(raw, last_activity), 2)
        score = min(100.0, max(0.0, score))

        if write_back:
            self.bridge.update_prospect(
                prospect_id,
                lead_score=score,
                lead_score_updated=date.today().isoformat(),
            )
        return score

    def score_all_prospects(self) -> dict[str, float]:
        """Batch-score all non-terminal prospects. Returns {prospect_id: score}.

        Skips: active, lost, dormant.
        """
        terminal = {"active", "lost", "dormant"}
        results: dict[str, float] = {}
        for p in self.bridge.get_all_prospects():
            if p["pipeline_stage"] in terminal:
                continue
            try:
                results[p["prospect_id"]] = self.calculate_lead_score(
                    p["prospect_id"], write_back=True
                )
            except Exception as exc:
                print(f"[RAPTOR] score_all error for {p['prospect_id']}: {exc}")
        return results

    # ── Action queue ──────────────────────────────────────────────────────

    def get_action_queue(self) -> dict:
        """Return prioritized action lists.

        immediate_outreach  — score > 80
        nurture             — 50 <= score <= 80
        passive             — score < 50
        re_consent          — consent expiring within 30 days
        overdue_followup    — mid-funnel, no touchpoint for OVERDUE_DAYS+ days
        """
        mid_funnel = {"contacted", "meeting_set", "proposal_sent"}
        immediate, nurture, passive, overdue = [], [], [], []

        for p in self.bridge.get_all_prospects():
            stage = p["pipeline_stage"]
            if stage in {"active", "lost", "dormant"}:
                continue

            pid   = p["prospect_id"]
            score = p.get("lead_score") or 0.0
            entry = {
                "prospect_id":    pid,
                "display_name":   (
                    p.get("display_name")
                    or f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()
                ),
                "pipeline_stage": stage,
                "lead_score":     score,
            }

            if score > THRESHOLD_IMMEDIATE:
                immediate.append(entry)
            elif score >= THRESHOLD_NURTURE:
                nurture.append(entry)
            else:
                passive.append(entry)

            # Overdue follow-up — mid-funnel only
            if stage in mid_funnel:
                tps = self.bridge.get_touchpoints(pid)
                if not tps:
                    overdue.append({**entry, "days_since_touchpoint": None})
                else:
                    last_tp = max(t["date"][:10] for t in tps)
                    days = (date.today() - date.fromisoformat(last_tp)).days
                    if days >= OVERDUE_DAYS:
                        overdue.append({**entry, "days_since_touchpoint": days})

        for lst in [immediate, nurture, passive]:
            lst.sort(key=lambda x: x["lead_score"], reverse=True)

        return {
            "immediate_outreach": immediate,
            "nurture":            nurture,
            "passive":            passive,
            "re_consent":         self.bridge.get_expiring_consents(days_ahead=30),
            "overdue_followup":   overdue,
        }

    # ── Pipeline analytics ────────────────────────────────────────────────

    def get_pipeline_analytics(self) -> dict:
        """Return dashboard-ready pipeline analytics.

        stage_distribution    {stage: count}
        conversion_rates      {"A→B": rate, ...}
        avg_days_in_stage     {stage: float days}
        source_effectiveness  {source_type: {total, converted, rate}}
        coi_leaderboard       [{coi_id, name, total, converted, rate}]
        """
        conn = self.bridge.conn

        # Stage distribution
        rows = conn.execute(
            "SELECT pipeline_stage, COUNT(*) AS n "
            "FROM raptor_prospects GROUP BY pipeline_stage"
        ).fetchall()
        stage_dist = {r["pipeline_stage"]: r["n"] for r in rows}

        # Conversion rates from pipeline_log
        trans_rows = conn.execute(
            "SELECT from_stage, to_stage, COUNT(*) AS n "
            "FROM raptor_pipeline_log GROUP BY from_stage, to_stage"
        ).fetchall()
        # Denominator: count of prospects who were ever in from_stage
        # Approximation: prospects currently in stage + those who exited it
        entered: dict[str, int] = {}
        for t in trans_rows:
            entered[t["to_stage"]] = entered.get(t["to_stage"], 0) + t["n"]
        conversion_rates: dict[str, float] = {}
        for t in trans_rows:
            denom = entered.get(t["from_stage"], stage_dist.get(t["from_stage"], 0)) or 1
            conversion_rates[f"{t['from_stage']}→{t['to_stage']}"] = round(
                t["n"] / denom, 3
            )

        # Average days in each stage (from pipeline_log time diffs)
        log_rows = conn.execute(
            "SELECT prospect_id, from_stage, to_stage, transition_date "
            "FROM raptor_pipeline_log ORDER BY prospect_id, transition_date"
        ).fetchall()
        stage_durations: dict[str, list[float]] = {}
        for pid, entries in groupby(log_rows, key=lambda r: r["prospect_id"]):
            log = list(entries)
            for i, row in enumerate(log):
                entry_date = row["transition_date"][:10]
                exit_date = (
                    log[i + 1]["transition_date"][:10]
                    if i + 1 < len(log)
                    else date.today().isoformat()
                )
                try:
                    days = (
                        date.fromisoformat(exit_date) - date.fromisoformat(entry_date)
                    ).days
                    stage_durations.setdefault(row["from_stage"], []).append(float(days))
                except ValueError:
                    pass
        avg_days_in_stage = {
            s: round(sum(v) / len(v), 1)
            for s, v in stage_durations.items()
            if v
        }

        # Source effectiveness
        src_rows = conn.execute(
            "SELECT source_type, COUNT(*) AS total, "
            "SUM(CASE WHEN pipeline_stage = 'active' THEN 1 ELSE 0 END) AS converted "
            "FROM raptor_prospects WHERE source_type IS NOT NULL GROUP BY source_type"
        ).fetchall()
        source_effectiveness = {
            r["source_type"]: {
                "total":     r["total"] or 0,
                "converted": r["converted"] or 0,
                "rate":      round((r["converted"] or 0) / (r["total"] or 1), 3),
            }
            for r in src_rows
        }

        # COI leaderboard
        coi_rows = conn.execute(
            "SELECT c.coi_id, c.name, COUNT(r.referral_id) AS total, "
            "SUM(CASE WHEN r.outcome = 'converted' THEN 1 ELSE 0 END) AS converted "
            "FROM raptor_coi_network c "
            "LEFT JOIN raptor_referrals r ON c.coi_id = r.coi_id "
            "GROUP BY c.coi_id ORDER BY total DESC, converted DESC"
        ).fetchall()
        coi_leaderboard = [
            {
                "coi_id":    r["coi_id"],
                "name":      r["name"],
                "total":     r["total"] or 0,
                "converted": r["converted"] or 0,
                "rate":      round((r["converted"] or 0) / (r["total"] or 1), 3),
            }
            for r in coi_rows
        ]

        return {
            "stage_distribution":   stage_dist,
            "conversion_rates":     conversion_rates,
            "avg_days_in_stage":    avg_days_in_stage,
            "source_effectiveness": source_effectiveness,
            "coi_leaderboard":      coi_leaderboard,
        }


# ── Rule seeder ───────────────────────────────────────────────────────────────

def seed_scoring_rule(bridge) -> bool:
    """Write RAPTOR_LEAD_SCORING_V1 to soma.db kb_rules if not present.

    Safe to call on every startup — INSERT OR IGNORE is idempotent.
    Returns True if inserted, False if already existed.
    """
    existing = bridge.conn.execute(
        "SELECT 1 FROM kb_rules WHERE rule_id = 'RAPTOR_LEAD_SCORING_V1'"
    ).fetchone()
    if existing:
        return False

    now = datetime.now(timezone.utc).isoformat()
    rule_data = json.dumps({
        "rule_id":       "RAPTOR_LEAD_SCORING_V1",
        "source_module": ["RAPTOR"],
        "confidence":    0.80,
        "description":   (
            "Lead scoring weights for RAPTOR prospect prioritization. "
            "Tune via soma.db kb_rules — no code change required."
        ),
        "weights": dict(_DEFAULT_WEIGHTS),
        "thresholds": {
            "immediate_outreach":    THRESHOLD_IMMEDIATE,
            "nurture":               THRESHOLD_NURTURE,
            "decay_rate_per_month":  DECAY_RATE,
            "overdue_followup_days": OVERDUE_DAYS,
            "decay_floor":           DECAY_FLOOR,
        },
        "asset_scores":  _ASSET_SCORES,
        "source_scores": _SOURCE_SCORES,
    })

    bridge.conn.execute(
        """INSERT OR IGNORE INTO kb_rules
           (rule_id, source_file, source_module, rule_data, confidence, parsed_at, schema_version)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            "RAPTOR_LEAD_SCORING_V1",
            "shared/soma/raptor_engine.py",
            "RAPTOR",
            rule_data,
            0.80,
            now,
            3,
        ),
    )
    bridge.conn.commit()
    return True
