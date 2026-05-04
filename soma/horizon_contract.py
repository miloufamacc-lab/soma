"""
HORIZON→MANTIS Sizing Contract
Pipeline: HORIZON→MANTIS | Module: SOMA (bridge layer)

Translates the latest HORIZON analysis into a concrete sizing multiplier
that MANTIS can consume during position sizing.

Design principles:
  - Regime gate: CONTRACTION blocks all signals (multiplier = 1.0)
  - Concordance gate: split/unclear signals blocked (multiplier = 1.0)
  - Confidence floor: low-confidence signals revert to 1.0
  - Scale cap: multiplier bounded to [MULTIPLIER_MIN, MULTIPLIER_MAX]
  - Direction clamp: BUY can never reduce; SELL can never increase
  - Safe fallback: any SOMA failure → multiplier = 1.0 (never crashes caller)

MANTIS consumes this via kb_integration.get_horizon_multiplier().
run_day.py must call HorizonContract().persist() BEFORE step_4_mantis fires.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# ── SOMA path ────────────────────────────────────────────────────────────────
_DEFAULT_DB_PATH = (
    Path(os.environ["SOMA_DB_PATH"])
    if "SOMA_DB_PATH" in os.environ
    else Path.home() / "Desktop" / "DABEIBA" / "shared" / "soma" / "data" / "soma.db"
)

# ── Contract constants (overridable via KB rule HORIZON_SIZING_CONTRACT_V1) ─
_DEFAULT_SCALE_FACTOR   = 0.50   # multiplier = 1.0 + score * confidence * scale
_DEFAULT_CONF_FLOOR     = 0.40   # below this, revert to 1.0
_DEFAULT_MULTIPLIER_MIN = 0.50
_DEFAULT_MULTIPLIER_MAX = 1.50
_FALLBACK_MULTIPLIER    = 1.00   # always-safe default on any failure

# Regimes that BLOCK the sizing contract (conservative override)
_CONTRACTION_REGIMES = {"CONTRACTION"}

# Directions that are bullish (multiplier >= 1.0) or bearish (multiplier <= 1.0)
_BULLISH_DIRECTIONS = {"BUY", "STRONG_BUY"}
_BEARISH_DIRECTIONS = {"SELL", "STRONG_SELL"}


@dataclass
class HorizonContractResult:
    """Immutable result from HorizonContract.compute().

    Consumed by HorizonContract.persist() → soma.horizon_signal table.
    MANTIS reads horizon_multiplier via kb_integration.get_horizon_multiplier().
    """
    signal_date: str
    run_id: str
    composite_direction: str
    final_confidence: float
    concordance_passed: bool
    regime: str | None
    regime_gate_pass: bool
    concordance_gate_pass: bool
    horizon_multiplier: float
    gate_failure_reason: str | None = None

    def __post_init__(self):
        # Hard invariant: multiplier must always be in valid range
        if not (0.0 < self.horizon_multiplier <= 2.0):
            raise ValueError(
                f"horizon_multiplier {self.horizon_multiplier} outside safe range (0, 2.0]"
            )


class HorizonContract:
    """Compute and persist the HORIZON→MANTIS sizing contract.

    Usage (in run_day.py, AFTER step_6_horizon and BEFORE step_4_mantis):
        contract = HorizonContract()
        result   = contract.compute()
        contract.persist(result)

    All SOMA failures are caught and logged; compute() always returns a
    valid HorizonContractResult (multiplier=1.0 on any failure path).
    """

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or str(_DEFAULT_DB_PATH)

    # ── Public API ───────────────────────────────────────────────────────────

    def compute(self) -> HorizonContractResult:
        """Compute the sizing contract from the latest HORIZON analysis.

        Gate logic (see spec §11):
          1. Regime gate  — CONTRACTION blocks → multiplier 1.0
          2. Concordance  — no agreement → multiplier 1.0
          3. Confidence   — below floor  → multiplier 1.0
          4. Direction    — NEUTRAL      → multiplier 1.0
          5. Raw compute  — 1 + (score * conf * scale_factor), direction-clamped
          6. Scale cap    — clamp to [min, max]
        """
        params = self._load_kb_params()

        try:
            from soma.soma_bridge import SomaBridge
            with SomaBridge(db_path=self.db_path) as db:
                db.initialize_db()
                row = db.conn.execute(
                    "SELECT * FROM horizon_analyses ORDER BY write_timestamp DESC LIMIT 1"
                ).fetchone()
        except Exception as e:
            logger.warning(f"[HorizonContract] SOMA read failed: {e} — returning fallback 1.0")
            return self._fallback_result(reason=f"soma_error: {e}")

        if row is None:
            logger.warning("[HorizonContract] No horizon_analyses rows found — returning fallback 1.0")
            return self._fallback_result(reason="no_horizon_analyses_rows")

        row = dict(row)

        # Extract fields with safe defaults
        signal_date       = (row.get("analysis_date") or datetime.now(timezone.utc).strftime("%Y-%m-%d"))
        run_id            = row.get("run_id", "unknown")
        raw_direction     = row.get("composite_direction") or "NEUTRAL"
        composite_score   = float(row.get("composite_score") or 0.0)
        raw_confidence    = float(row.get("final_confidence") or 0.0)
        concordance_int   = int(row.get("concordance_passed") or 0)
        regime            = row.get("regime")

        direction_str     = str(raw_direction).upper()

        # ── Gate 1: Regime ──────────────────────────────────────────────────
        regime_str = str(regime).upper() if regime else ""
        if regime_str in _CONTRACTION_REGIMES:
            return HorizonContractResult(
                signal_date=signal_date,
                run_id=run_id,
                composite_direction=direction_str,
                final_confidence=raw_confidence,
                concordance_passed=bool(concordance_int),
                regime=regime,
                regime_gate_pass=False,
                concordance_gate_pass=True,  # not evaluated
                horizon_multiplier=_FALLBACK_MULTIPLIER,
                gate_failure_reason=f"regime_gate: regime={regime} in block_list",
            )

        # ── Gate 2: Concordance ─────────────────────────────────────────────
        if concordance_int == 0:
            return HorizonContractResult(
                signal_date=signal_date,
                run_id=run_id,
                composite_direction=direction_str,
                final_confidence=raw_confidence,
                concordance_passed=False,
                regime=regime,
                regime_gate_pass=True,
                concordance_gate_pass=False,
                horizon_multiplier=_FALLBACK_MULTIPLIER,
                gate_failure_reason="concordance_gate: concordance_passed=0",
            )

        # ── Gate 3: Confidence floor ────────────────────────────────────────
        conf_floor = float(params.get("MULTIPLIER", {}).get("confidence_floor", _DEFAULT_CONF_FLOOR))
        if raw_confidence < conf_floor:
            return HorizonContractResult(
                signal_date=signal_date,
                run_id=run_id,
                composite_direction=direction_str,
                final_confidence=raw_confidence,
                concordance_passed=True,
                regime=regime,
                regime_gate_pass=True,
                concordance_gate_pass=True,
                horizon_multiplier=_FALLBACK_MULTIPLIER,
                gate_failure_reason=f"confidence_floor: confidence={raw_confidence:.3f} < floor={conf_floor:.3f}",
            )

        # ── Gate 4: NEUTRAL direction ───────────────────────────────────────
        if direction_str == "NEUTRAL" or direction_str not in (_BULLISH_DIRECTIONS | _BEARISH_DIRECTIONS):
            return HorizonContractResult(
                signal_date=signal_date,
                run_id=run_id,
                composite_direction=direction_str,
                final_confidence=raw_confidence,
                concordance_passed=True,
                regime=regime,
                regime_gate_pass=True,
                concordance_gate_pass=True,
                horizon_multiplier=_FALLBACK_MULTIPLIER,
                gate_failure_reason=None,  # NEUTRAL is a valid pass — no failure
            )

        # ── All gates passed: compute multiplier ────────────────────────────
        scale_factor   = float(params.get("MULTIPLIER", {}).get("scale_factor",   _DEFAULT_SCALE_FACTOR))
        mult_min       = float(params.get("MULTIPLIER", {}).get("min",             _DEFAULT_MULTIPLIER_MIN))
        mult_max       = float(params.get("MULTIPLIER", {}).get("max",             _DEFAULT_MULTIPLIER_MAX))

        # NaN guard on composite_score / confidence
        if composite_score != composite_score or raw_confidence != raw_confidence:
            logger.warning("[HorizonContract] NaN in composite_score or confidence — returning fallback 1.0")
            return HorizonContractResult(
                signal_date=signal_date,
                run_id=run_id,
                composite_direction=direction_str,
                final_confidence=raw_confidence,
                concordance_passed=True,
                regime=regime,
                regime_gate_pass=True,
                concordance_gate_pass=True,
                horizon_multiplier=_FALLBACK_MULTIPLIER,
                gate_failure_reason="nan_guard: composite_score or confidence is NaN",
            )

        raw_mult = 1.0 + (composite_score * raw_confidence * scale_factor)

        # Direction clamp: BUY never shrinks below 1.0; SELL never grows above 1.0
        if direction_str in _BULLISH_DIRECTIONS:
            raw_mult = max(1.0, raw_mult)
        elif direction_str in _BEARISH_DIRECTIONS:
            raw_mult = min(1.0, raw_mult)

        # Scale cap
        final_mult = max(mult_min, min(mult_max, raw_mult))

        logger.info(
            f"[HorizonContract] {signal_date} dir={direction_str} conf={raw_confidence:.3f} "
            f"score={composite_score:.3f} → multiplier={final_mult:.4f}"
        )

        return HorizonContractResult(
            signal_date=signal_date,
            run_id=run_id,
            composite_direction=direction_str,
            final_confidence=raw_confidence,
            concordance_passed=True,
            regime=regime,
            regime_gate_pass=True,
            concordance_gate_pass=True,
            horizon_multiplier=final_mult,
            gate_failure_reason=None,
        )

    def persist(self, result: HorizonContractResult) -> int:
        """Write HorizonContractResult to soma.horizon_signal. Returns rowid.

        Uses INSERT OR REPLACE — safe to call multiple times per day.
        Raises on SOMA write failure (callers in run_day.py should catch).
        """
        from soma.soma_bridge import SomaBridge
        with SomaBridge(db_path=self.db_path) as db:
            db.initialize_db()
            rowid = db.write_horizon_contract(
                signal_date=result.signal_date,
                run_id=result.run_id,
                composite_direction=result.composite_direction,
                final_confidence=result.final_confidence,
                concordance_passed=int(result.concordance_passed),
                regime=result.regime,
                regime_gate_pass=int(result.regime_gate_pass),
                concordance_gate_pass=int(result.concordance_gate_pass),
                horizon_multiplier=result.horizon_multiplier,
                gate_failure_reason=result.gate_failure_reason,
            )
        return rowid

    # ── Internals ────────────────────────────────────────────────────────────

    @staticmethod
    def _fallback_result(reason: str) -> HorizonContractResult:
        """Return a safe 1.0 multiplier result with both gates marked as failed."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return HorizonContractResult(
            signal_date=today,
            run_id="fallback",
            composite_direction="NEUTRAL",
            final_confidence=0.0,
            concordance_passed=False,
            regime=None,
            regime_gate_pass=False,
            concordance_gate_pass=False,
            horizon_multiplier=_FALLBACK_MULTIPLIER,
            gate_failure_reason=reason,
        )

    @staticmethod
    def _load_kb_params() -> dict:
        """Load HORIZON_SIZING_CONTRACT_V1 from KB. Returns empty dict on failure.

        Empty dict causes all compute() calls to use module-level defaults,
        which is the correct graceful-degradation behaviour.
        """
        try:
            from soma.soma_bridge import SomaBridge
            # Use a short-lived connection just for KB read
            _db_path = (
                Path(os.environ["SOMA_DB_PATH"])
                if "SOMA_DB_PATH" in os.environ
                else Path.home() / "Desktop" / "DABEIBA" / "shared" / "soma" / "data" / "soma.db"
            )
            with SomaBridge(db_path=str(_db_path)) as db:
                db.initialize_db()
                kr = db.get_kb_reader()
                rule = kr.get_rule("HORIZON_SIZING_CONTRACT_V1")
                if rule and "rules" in rule:
                    return rule["rules"]
        except Exception as e:
            logger.debug(f"[HorizonContract] KB param load failed: {e} — using defaults")
        return {}
