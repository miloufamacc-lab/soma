"""
SOMA-INTEL P5.3.d — Backtest Report Generator

Produces a Markdown report + calibration PNG for a completed backtest run.

9 sections:
  §1  Headline metrics
  §2  §E target table (P1 precision vs stop-ship / target)
  §3  By-regime breakdown
  §4  By-sector breakdown  (uses soma_intel_universe.platform_tags as sector proxy)
  §5  By-signal-type breakdown  (uses signal.horizon: tactical/thematic/structural)
  §6  Calibration plot PNG (anomaly_score bucket → observed hit rate)
  §7  Top failure cases  (miss signals with highest anomaly_score)
  §8  Coverage stats (data_unavailable analysis)
  §9  No-look-ahead audit (lookahead_clean summary)

OOS comparison (§10, --oos-run-id):
  Compares in-sample vs OOS precision. Flags overfitting if
  OOS precision < in_sample_precision × 0.70.

Outputs:
  tasks/backtest_report_<run_id>.md
  tasks/backtest_calibration_<run_id>.png  (if matplotlib available)

CLI:
  python3 backtest_report.py --run-id in_sample_20240506_20260305
  python3 backtest_report.py --run-id in_sample_... --oos-run-id oos_...
"""

from __future__ import annotations

import argparse
import logging
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ── Path bootstrap ─────────────────────────────────────────────────────────────
_HERE         = Path(__file__).resolve().parent
_DABEIBA_ROOT = _HERE.parent.parent.parent
for _p in [str(_DABEIBA_ROOT), str(_DABEIBA_ROOT / "shared")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from soma.intel.store import IntelStore

# ── Constants ─────────────────────────────────────────────────────────────────
_SOMA_DB = _DABEIBA_ROOT / "shared" / "soma" / "data" / "soma.db"
_TASKS   = _DABEIBA_ROOT / "tasks"

P1_TARGET_PRECISION   = 0.60
P1_STOP_SHIP          = 0.40
P1_MAX_DAILY_SIGNALS  = 8      # stop-ship trigger if average > this for 5d
OOS_OVERFIT_THRESHOLD = 0.70   # OOS precision must be >= in-sample × 0.70

logging.basicConfig(format="%(levelname)-5s %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)


# ── Data helpers ───────────────────────────────────────────────────────────────

def _fetch_run(store: IntelStore, run_id: str) -> list[dict]:
    rows = store._c.execute(
        "SELECT * FROM soma_intel_signal_backtest WHERE backtest_run_id=?",
        (run_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def _precision(hits: int, misses: int) -> Optional[float]:
    total = hits + misses
    return hits / total if total > 0 else None


def _pct(n: Optional[float]) -> str:
    if n is None:
        return "N/A"
    return f"{n:.1%}"


def _trend_state(regime_label: Optional[str]) -> str:
    if not regime_label:
        return "unknown"
    first = regime_label.split("_")[0].lower()
    return first if first in ("bull", "bear", "transition") else "unknown"


# ── §1 Headline metrics ───────────────────────────────────────────────────────

def _section_headline(rows: list[dict]) -> str:
    total = len(rows)
    hits    = sum(1 for r in rows if r["outcome"] == "hit")
    misses  = sum(1 for r in rows if r["outcome"] == "miss")
    unavail = sum(1 for r in rows if r["outcome"] == "data_unavailable")
    unscored= sum(1 for r in rows if r["outcome"] is None)
    lookahead_viol = sum(1 for r in rows if r.get("lookahead_clean") == 0)

    overall_prec = _precision(hits, misses)
    days = len(set(r["sim_date"] for r in rows))

    lines = [
        "## §1 Headline Metrics\n",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total signals | {total:,} |",
        f"| Days covered | {days} |",
        f"| Avg signals/day | {total/max(days,1):.1f} |",
        f"| Hits | {hits:,} |",
        f"| Misses | {misses:,} |",
        f"| Data unavailable | {unavail:,} |",
        f"| Unscored | {unscored:,} |",
        f"| Overall precision (hit/hit+miss) | {_pct(overall_prec)} |",
        f"| No-look-ahead violations | {lookahead_viol:,} |",
    ]
    return "\n".join(lines)


# ── §2 §E target table ────────────────────────────────────────────────────────

def _section_e_targets(rows: list[dict]) -> str:
    from collections import defaultdict
    by_priority: dict[str, dict] = defaultdict(lambda: {"hits": 0, "misses": 0, "unavail": 0})
    for r in rows:
        p = r.get("priority") or "UNKNOWN"
        o = r.get("outcome")
        if o == "hit":
            by_priority[p]["hits"] += 1
        elif o == "miss":
            by_priority[p]["misses"] += 1
        else:
            by_priority[p]["unavail"] += 1

    lines = [
        "\n## §2 Priority Precision vs §E Targets\n",
        f"| Priority | Hits | Misses | N/A | Precision | Target | Status |",
        f"|----------|------|--------|-----|-----------|--------|--------|",
    ]

    for priority in sorted(by_priority):
        d = by_priority[priority]
        prec = _precision(d["hits"], d["misses"])
        is_p1 = priority in ("P1", "HIGH")
        target = f"≥{P1_TARGET_PRECISION:.0%}" if is_p1 else "—"

        if prec is None:
            status = "no_data"
        elif is_p1 and prec < P1_STOP_SHIP:
            status = "**STOP_SHIP**"
        elif is_p1 and prec >= P1_TARGET_PRECISION:
            status = "ON_TARGET"
        elif is_p1:
            status = "below_target"
        else:
            status = "ok"

        lines.append(
            f"| {priority} | {d['hits']} | {d['misses']} | {d['unavail']} "
            f"| {_pct(prec)} | {target} | {status} |"
        )

    return "\n".join(lines)


# ── §3 By-regime breakdown ────────────────────────────────────────────────────

def _section_by_regime(rows: list[dict]) -> str:
    from collections import defaultdict
    by_regime: dict[str, dict] = defaultdict(lambda: {"hits": 0, "misses": 0, "unavail": 0})
    for r in rows:
        regime = _trend_state(r.get("regime_label"))
        o = r.get("outcome")
        if o == "hit":     by_regime[regime]["hits"] += 1
        elif o == "miss":  by_regime[regime]["misses"] += 1
        else:              by_regime[regime]["unavail"] += 1

    lines = [
        "\n## §3 By Regime (Trend State)\n",
        f"| Trend State | Hits | Misses | N/A | Precision |",
        f"|-------------|------|--------|-----|-----------|",
    ]
    for regime in sorted(by_regime):
        d = by_regime[regime]
        prec = _precision(d["hits"], d["misses"])
        lines.append(
            f"| {regime} | {d['hits']} | {d['misses']} | {d['unavail']} | {_pct(prec)} |"
        )
    return "\n".join(lines)


# ── §4 By-sector breakdown ────────────────────────────────────────────────────

def _section_by_sector(rows: list[dict], store: IntelStore) -> str:
    """Uses soma_intel_universe.platform_tags as sector proxy."""
    import json
    from collections import defaultdict

    # Build ticker → first platform_tag map
    ticker_tags: dict[str, str] = {}
    try:
        universe_rows = store._c.execute(
            "SELECT ticker, platform_tags FROM soma_intel_universe WHERE active=1"
        ).fetchall()
        for ur in universe_rows:
            tags = ur["platform_tags"]
            if tags:
                try:
                    tag_list = json.loads(tags)
                    if tag_list:
                        ticker_tags[ur["ticker"]] = tag_list[0]
                except Exception:
                    pass
    except Exception:
        pass

    by_sector: dict[str, dict] = defaultdict(lambda: {"hits": 0, "misses": 0, "unavail": 0})
    for r in rows:
        sector = ticker_tags.get(r["ticker"], "untagged")
        o = r.get("outcome")
        if o == "hit":     by_sector[sector]["hits"] += 1
        elif o == "miss":  by_sector[sector]["misses"] += 1
        else:              by_sector[sector]["unavail"] += 1

    lines = [
        "\n## §4 By Sector (Platform Tag)\n",
        f"| Platform Tag | Hits | Misses | N/A | Precision |",
        f"|--------------|------|--------|-----|-----------|",
    ]
    for sector in sorted(by_sector, key=lambda s: -(by_sector[s]["hits"] + by_sector[s]["misses"])):
        d = by_sector[sector]
        prec = _precision(d["hits"], d["misses"])
        lines.append(
            f"| {sector} | {d['hits']} | {d['misses']} | {d['unavail']} | {_pct(prec)} |"
        )
    return "\n".join(lines)


# ── §5 By-signal-type (horizon) ───────────────────────────────────────────────

def _section_by_signal_type(rows: list[dict]) -> str:
    from collections import defaultdict
    by_horizon: dict[str, dict] = defaultdict(lambda: {"hits": 0, "misses": 0, "unavail": 0})
    for r in rows:
        horizon = r.get("horizon") or "unknown"
        o = r.get("outcome")
        if o == "hit":     by_horizon[horizon]["hits"] += 1
        elif o == "miss":  by_horizon[horizon]["misses"] += 1
        else:              by_horizon[horizon]["unavail"] += 1

    lines = [
        "\n## §5 By Signal Type (Horizon)\n",
        f"| Horizon | Hits | Misses | N/A | Precision |",
        f"|---------|------|--------|-----|-----------|",
    ]
    for horizon in sorted(by_horizon):
        d = by_horizon[horizon]
        prec = _precision(d["hits"], d["misses"])
        lines.append(
            f"| {horizon} | {d['hits']} | {d['misses']} | {d['unavail']} | {_pct(prec)} |"
        )
    return "\n".join(lines)


# ── §6 Calibration plot ───────────────────────────────────────────────────────

def _build_calibration_plot(rows: list[dict], out_path: Path) -> bool:
    """
    Bar chart: anomaly_score (z-score) bucket → observed hit rate.
    Buckets are z-score bands: [1.5-2.0), [2.0-2.5), [2.5-3.0), [3.0-4.0), [4.0-6.0), [6.0+).
    Only includes rows with outcome hit or miss (excludes data_unavailable).
    Returns True if PNG written, False if matplotlib unavailable.
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        log.warning("matplotlib not installed — skipping calibration plot.")
        return False

    scored = [r for r in rows if r.get("outcome") in ("hit", "miss")]
    if not scored:
        log.info("No scored signals — skipping calibration plot.")
        return False

    # Z-score bands suited to actual anomaly_score range (all signals ≥ 1.5)
    import math
    _INF = math.inf
    bucket_defs = [
        (1.5, 2.0, "1.5-2.0"),
        (2.0, 2.5, "2.0-2.5"),
        (2.5, 3.0, "2.5-3.0"),
        (3.0, 4.0, "3.0-4.0"),
        (4.0, 6.0, "4.0-6.0"),
        (6.0, _INF, "6.0+"),
    ]
    bucket_labels, hit_rates, bucket_sizes = [], [], []

    for lo, hi, label in bucket_defs:
        bucket_rows = [r for r in scored if lo <= (r.get("anomaly_score") or 0) < hi]
        if not bucket_rows:
            continue
        h = sum(1 for r in bucket_rows if r["outcome"] == "hit")
        rate = h / len(bucket_rows)
        bucket_labels.append(label)
        hit_rates.append(rate)
        bucket_sizes.append(len(bucket_rows))

    if not bucket_labels:
        return False

    fig, ax = plt.subplots(figsize=(8, 5))
    x = range(len(bucket_labels))
    bars = ax.bar(x, hit_rates, color="steelblue", alpha=0.75, edgecolor="white")

    # Target reference line
    ax.axhline(P1_TARGET_PRECISION, color="green", linestyle="--", linewidth=1.2,
               label=f"Target ({P1_TARGET_PRECISION:.0%})")
    ax.axhline(P1_STOP_SHIP, color="red", linestyle=":", linewidth=1.2,
               label=f"Stop-ship ({P1_STOP_SHIP:.0%})")

    # Annotate bar count
    for bar, size, rate in zip(bars, bucket_sizes, hit_rates):
        ax.text(bar.get_x() + bar.get_width() / 2, rate + 0.01, f"n={size}",
                ha="center", va="bottom", fontsize=8)

    ax.set_xticks(list(x))
    ax.set_xticklabels(bucket_labels)
    ax.set_xlabel("Anomaly Score (Z-score Band)")
    ax.set_ylabel("Observed Hit Rate")
    ax.set_title("Signal Calibration — Hit Rate by Z-score Band")
    ax.set_ylim(0, 1.1)
    ax.legend(loc="upper left")
    ax.grid(axis="y", alpha=0.3)

    plt.tight_layout()
    plt.savefig(out_path, dpi=120)
    plt.close()
    log.info("Calibration plot: %s", out_path)
    return True


def _section_calibration(rows: list[dict], run_id: str, tasks_dir: Path) -> str:
    png_path = tasks_dir / f"backtest_calibration_{run_id}.png"
    written  = _build_calibration_plot(rows, png_path)
    if written:
        rel = png_path.name
        return f"\n## §6 Calibration Plot\n\n![Calibration]({rel})\n"
    return (
        "\n## §6 Calibration Plot\n\n"
        "_Plot unavailable — no scored signals or matplotlib not installed._\n"
        "_Run `pip install matplotlib --break-system-packages` then re-generate report._\n"
    )


# ── §7 Top failure cases ──────────────────────────────────────────────────────

def _section_failure_cases(rows: list[dict], top_n: int = 10) -> str:
    misses = sorted(
        [r for r in rows if r.get("outcome") == "miss"],
        key=lambda r: -(r.get("anomaly_score") or 0),
    )[:top_n]

    lines = [
        f"\n## §7 Top Failure Cases (top {top_n} misses by anomaly_score)\n",
        f"| Ticker | Date | Priority | Anomaly | Regime | FwdReturn | Direction |",
        f"|--------|------|----------|---------|--------|-----------|-----------|",
    ]
    for r in misses:
        fwd = f"{r['forward_return']:.2%}" if r.get("forward_return") is not None else "N/A"
        lines.append(
            f"| {r['ticker']} | {r['date']} | {r['priority']} "
            f"| {r.get('anomaly_score', 0):.2f} | {r.get('regime_label','?')} "
            f"| {fwd} | {r.get('direction_label','?')} |"
        )
    if not misses:
        lines.append("| — | No misses found | | | | | |")
    return "\n".join(lines)


# ── §8 Coverage stats ─────────────────────────────────────────────────────────

def _section_coverage(rows: list[dict]) -> str:
    total   = len(rows)
    unavail = sum(1 for r in rows if r["outcome"] == "data_unavailable")
    scored  = total - unavail
    unscored= sum(1 for r in rows if r["outcome"] is None)

    tickers_total   = len(set(r["ticker"] for r in rows))
    tickers_scored  = len(set(r["ticker"] for r in rows if r["outcome"] in ("hit", "miss")))
    coverage        = tickers_scored / max(tickers_total, 1)

    lines = [
        "\n## §8 Coverage Statistics\n",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total signals | {total:,} |",
        f"| Scored (hit+miss) | {scored:,} ({scored/max(total,1):.1%}) |",
        f"| Data unavailable | {unavail:,} ({unavail/max(total,1):.1%}) |",
        f"| Unscored | {unscored:,} |",
        f"| Distinct tickers in run | {tickers_total} |",
        f"| Tickers with scored signals | {tickers_scored} |",
        f"| Ticker coverage | {coverage:.1%} |",
    ]

    if unavail == total:
        lines.append(
            "\n> **WARNING:** All signals are data_unavailable. "
            "Run `backtest_prices.py --download` to load price history, "
            "then re-score with `backtest_outcomes.py --score --force`."
        )
    return "\n".join(lines)


# ── §9 No-look-ahead audit ────────────────────────────────────────────────────

def _section_lookahead_audit(rows: list[dict]) -> str:
    total      = len(rows)
    violations = sum(1 for r in rows if r.get("lookahead_clean") == 0)
    clean      = total - violations

    lines = [
        "\n## §9 No-Look-Ahead Audit\n",
        f"| Metric | Count |",
        f"|--------|-------|",
        f"| Total signals | {total:,} |",
        f"| Clean (lookahead_clean=1) | {clean:,} |",
        f"| Violations (lookahead_clean=0) | {violations:,} |",
    ]
    if violations:
        lines.append(
            "\n> **Note:** Violations indicate that newer regime/edge data existed "
            "in the live DB at score time — NOT that the original signal used future data. "
            "In a frozen-snapshot backtest (production), violations should be zero. "
            "See OPUS_BRIEF_P5_3a_data_gap.md."
        )
    else:
        lines.append("\n> No look-ahead violations detected.")
    return "\n".join(lines)


# ── §10 OOS comparison ────────────────────────────────────────────────────────

def _section_oos_comparison(
    is_rows: list[dict],
    oos_rows: list[dict],
    is_run_id: str,
    oos_run_id: str,
) -> str:
    def _prec_for_priority(rows: list[dict], priority: str) -> Optional[float]:
        h = sum(1 for r in rows if r["outcome"] == "hit" and r.get("priority") == priority)
        m = sum(1 for r in rows if r["outcome"] == "miss" and r.get("priority") == priority)
        return _precision(h, m)

    priorities = sorted(set(
        r.get("priority") for r in is_rows + oos_rows if r.get("priority")
    ))

    lines = [
        "\n## §10 In-Sample vs OOS Comparison (Overfitting Check)\n",
        f"| Priority | In-Sample | OOS | Ratio | Overfit? |",
        f"|----------|-----------|-----|-------|----------|",
    ]

    for p in priorities:
        is_prec  = _prec_for_priority(is_rows, p)
        oos_prec = _prec_for_priority(oos_rows, p)

        if is_prec is None or oos_prec is None:
            ratio    = "N/A"
            overfit  = "insufficient data"
        else:
            r = oos_prec / is_prec if is_prec > 0 else float("inf")
            ratio   = f"{r:.2f}"
            overfit = "YES" if r < OOS_OVERFIT_THRESHOLD else "no"

        lines.append(
            f"| {p} | {_pct(is_prec)} | {_pct(oos_prec)} | {ratio} | {overfit} |"
        )

    lines.append(f"\nOverfitting threshold: OOS / in-sample ≥ {OOS_OVERFIT_THRESHOLD:.0%}")
    return "\n".join(lines)


# ── Main report builder ───────────────────────────────────────────────────────

def build_report(
    store: IntelStore,
    run_id: str,
    oos_run_id: Optional[str] = None,
) -> Path:
    rows = _fetch_run(store, run_id)
    if not rows:
        log.warning("No rows found for run_id=%s", run_id)

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    parts = [
        f"# SOMA-INTEL Backtest Report\n",
        f"**Run ID:** {run_id}  ",
        f"**Generated:** {now_str}  ",
        f"**Signals:** {len(rows):,}  ",
        f"\n---\n",
        _section_headline(rows),
        _section_e_targets(rows),
        _section_by_regime(rows),
        _section_by_sector(rows, store),
        _section_by_signal_type(rows),
        _section_calibration(rows, run_id, _TASKS),
        _section_failure_cases(rows),
        _section_coverage(rows),
        _section_lookahead_audit(rows),
    ]

    if oos_run_id:
        oos_rows = _fetch_run(store, oos_run_id)
        parts.append(
            _section_oos_comparison(rows, oos_rows, run_id, oos_run_id)
        )

    report_text = "\n".join(parts)
    out_path = _TASKS / f"backtest_report_{run_id}.md"
    out_path.write_text(report_text)
    log.info("Report written: %s", out_path)
    return out_path


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="SOMA-INTEL backtest report generator (P5.3.d)"
    )
    parser.add_argument("--run-id",     required=True, help="Primary (in-sample) run ID")
    parser.add_argument("--oos-run-id", default=None,  help="OOS run ID for §10 comparison")
    parser.add_argument("--db",         default=str(_SOMA_DB), help="Path to soma.db")
    args = parser.parse_args()

    with IntelStore(db_path=args.db) as store:
        out = build_report(store, args.run_id, oos_run_id=args.oos_run_id)
        print(f"Report: {out}")
        if args.oos_run_id:
            print("Includes §10 OOS comparison.")


if __name__ == "__main__":
    main()
