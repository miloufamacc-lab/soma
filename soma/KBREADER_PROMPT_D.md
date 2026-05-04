# Claude Code Prompt D — Wire MANTIS to Read KB Rules at Runtime

## Context
SOMA is in ~/Desktop/DABEIBA/shared/soma/. The KB runtime reader is built (Prompts A+B). MANTIS is in ~/Desktop/DABEIBA/mantis/convergence-backtester/.

MANTIS currently has hardcoded position sizing, drawdown tiers, circuit breakers, and regime transition parameters scattered across `sizing.py` and `v2_engine.py`. This prompt wires MANTIS to **read these from SOMA's KB** at runtime, with old values as fallbacks.

## Rules MANTIS Should Read

These 5 rules have `source_module` containing "MANTIS":

| Rule ID | Source File | What It Contains |
|---------|------------|-----------------|
| `REGIME_ALLOCATIONS_V1` | mantis_mechanics.md | Target equity/cash per regime — MANTIS uses this for position weighting |
| `REGIME_TRANSITION_RULES_V1` | mantis_mechanics.md | What to do on regime transitions (reduce equity %, sell highest-beta, etc.) |
| `TRANSITION_SPEED_V1` | mantis_mechanics.md | How fast to reduce/increase exposure (3-5 days reducing, 2-4 weeks increasing) |
| `POSITION_SIZING_V1` | mantis_mechanics.md | Max weight, concentration limits, inverse-vol formula, vol threshold |
| `DRAWDOWN_CONTROLS_V1` | mantis_mechanics.md | DD tier thresholds + actions, circuit breaker parameters |

## Architecture Pattern

Same as Research (ORACLE): try KB → fallback to hardcoded → log usage.

```python
def _load_kb_rule(rule_id, fallback, context=None):
    """Read a KB rule with graceful fallback."""
    try:
        from soma.soma_bridge import SomaBridge
        with SomaBridge() as db:
            rule = db.get_rule(rule_id)
            db.log_rule_usage(rule_id, "MANTIS", context=context)
            return rule.get("rules", fallback)
    except Exception:
        return fallback
```

## Files to Modify

### 1. Create `mantis/convergence-backtester/src/kb_integration.py` (NEW FILE)

```python
"""
MANTIS ↔ SOMA KB Integration Layer

Provides clean access to KB rules for the MANTIS backtester.
All methods include hardcoded fallbacks — MANTIS works with or without SOMA.
"""

import logging

logger = logging.getLogger(__name__)


# ── Hardcoded fallbacks (current v2_engine.py + sizing.py values) ──

# IMPORTANT: These fallback structures MUST mirror the actual YAML in
# shared/soma/knowledge/mantis_mechanics.md exactly.
# The KB POSITION_SIZING_V1 rule uses: POSITION_LIMITS, SIZING_FORMULA, UPSIDE_ADJUSTMENT, CONCENTRATION
# The KB DRAWDOWN_CONTROLS_V1 rule uses: CIRCUIT_BREAKERS, STOP_LOSS, RECOVERY

_FALLBACK_POSITION_SIZING = {
    "POSITION_LIMITS": {
        "core_holding_max": 0.08,
        "standard_position": 0.05,
        "speculative_max": 0.03,
        "single_name_hard_cap": 0.10,
    },
    "SIZING_FORMULA": {
        "base_weight": 0.05,
        "conviction_score_thresholds": {"full": 8.0, "moderate": 6.0},
        "conviction_multipliers": {"full": 1.0, "moderate": 0.75, "reduced": 0.5},
        "regime_multipliers": {"RISK_ON": 1.0, "TURBULENCE": 0.7, "CONTRACTION": 0.4},
    },
    "UPSIDE_ADJUSTMENT": {
        "above_30_pct": 0.08,
        "range_15_30_pct": 0.05,
        "range_5_15_pct": 0.03,
        "below_5_pct": 0.0,
    },
    "CONCENTRATION": {
        "top_5_max_combined": 0.35,
        "single_sector_max": 0.30,
        "single_country_ex_us_max": 0.15,
        "correlation_threshold": 0.80,
    },
}

_FALLBACK_DRAWDOWN_CONTROLS = {
    "CIRCUIT_BREAKERS": {
        "dd_5_pct": {"action": "review", "description": "Reassess all positions. No new buys until review complete."},
        "dd_10_pct": {"action": "reduce", "description": "Cut equity exposure by 20% of current level. Raise cash."},
        "dd_15_pct": {"action": "protect", "description": "Move to minimum equity allocation for current regime. Override buy-the-dip signals."},
        "dd_20_pct": {"action": "lockdown", "description": "Move to CONTRACTION allocation regardless of regime. 50%+ cash. No new equity."},
    },
    "STOP_LOSS": {
        "hard_stop_pct": -0.25,
        "trailing_stop_trigger_pct": 0.15,
        "trailing_stop_distance_pct": -0.10,
        "fundamental_stop_score": 5.0,
    },
    "RECOVERY": {
        "min_stable_readings": 2,
        "rebuild_rate_per_week": 0.05,
        "min_conviction_score": 8,
        "resume_threshold_from_hwm": -0.05,
    },
}

_FALLBACK_REGIME_TRANSITIONS = {
    "RISK_ON_to_TURBULENCE": {
        "action": "reduce_equity_15_25pct",
        "priority": "sell_highest_beta",
        "timeline_days": [3, 5],
    },
    "TURBULENCE_to_CONTRACTION": {
        "action": "further_reduce_sell_cyclicals",
        "cash_floor": 0.30,
        "timeline_days": [3, 5],
    },
    "CONTRACTION_to_RISK_ON": {
        "action": "rebuild_5pct_per_week",
        "priority": "cheapest_names_first",
        "timeline_weeks": [2, 4],
    },
    "TURBULENCE_to_RISK_ON": {
        "action": "restore_to_expansion",
        "priority": "favor_oversold",
        "timeline_weeks": [2, 4],
    },
}

_FALLBACK_TRANSITION_SPEED = {
    "reducing_exposure_days": [3, 5],
    "increasing_exposure_weeks": [2, 4],
}

_FALLBACK_REGIME_ALLOCATIONS = {
    "RISK_ON_REBOUND": {"equity_target": [0.80, 0.95], "cash_floor": 0.05, "risk_appetite": "aggressive"},
    "RISK_ON_EXPANSION": {"equity_target": [0.70, 0.85], "cash_floor": 0.10, "risk_appetite": "growth"},
    "TURBULENCE": {"equity_target": [0.50, 0.65], "cash_floor": 0.20, "risk_appetite": "defensive"},
    "CONTRACTION": {"equity_target": [0.30, 0.50], "cash_floor": 0.30, "risk_appetite": "preservation"},
}


# ── Public API ─────────────────────────────────────────────────────

def _load_rule(rule_id, fallback, context=None):
    """Internal: read a KB rule with graceful fallback."""
    try:
        from soma.soma_bridge import SomaBridge
        with SomaBridge() as db:
            rule = db.get_rule(rule_id)
            db.log_rule_usage(rule_id, "MANTIS", context=context)
            return rule.get("rules", fallback)
    except Exception as e:
        logger.debug(f"KB fallback for {rule_id}: {e}")
        return fallback


def get_position_sizing():
    """Read position sizing rules from KB."""
    return _load_rule("POSITION_SIZING_V1", _FALLBACK_POSITION_SIZING,
                      context={"source": "sizing"})


def get_drawdown_controls():
    """Read drawdown tier thresholds and circuit breaker params from KB."""
    return _load_rule("DRAWDOWN_CONTROLS_V1", _FALLBACK_DRAWDOWN_CONTROLS,
                      context={"source": "v2_engine"})


def get_regime_transitions():
    """Read regime transition action rules from KB."""
    return _load_rule("REGIME_TRANSITION_RULES_V1", _FALLBACK_REGIME_TRANSITIONS,
                      context={"source": "v2_engine"})


def get_transition_speed():
    """Read transition speed parameters from KB."""
    return _load_rule("TRANSITION_SPEED_V1", _FALLBACK_TRANSITION_SPEED,
                      context={"source": "v2_engine"})


def get_regime_allocations(regime_name=None):
    """Read target allocations per regime from KB."""
    allocations = _load_rule("REGIME_ALLOCATIONS_V1", _FALLBACK_REGIME_ALLOCATIONS,
                             context={"regime": regime_name, "source": "v2_engine"})
    if regime_name:
        return allocations.get(regime_name, {})
    return allocations
```

### 2. Modify `mantis/convergence-backtester/src/sizing.py`

Find the hardcoded POSITION_LIMITS / position sizing constants (around lines 28-41). Replace with KB reads:

```python
# At the top of the file, add:
from src.kb_integration import get_position_sizing

# Where POSITION_LIMITS or sizing constants are defined, change to:
def _get_position_limits():
    """Load position limits from KB (falls back to hardcoded).

    KB POSITION_SIZING_V1 structure:
      POSITION_LIMITS: { core_holding_max, standard_position, speculative_max, single_name_hard_cap }
      SIZING_FORMULA: { base_weight, conviction_score_thresholds, conviction_multipliers, regime_multipliers }
      CONCENTRATION: { top_5_max_combined, single_sector_max, ... }
    """
    sizing = get_position_sizing()
    limits = sizing.get("POSITION_LIMITS", {})
    formula = sizing.get("SIZING_FORMULA", {})
    return {
        "core_holding_max": limits.get("core_holding_max", 0.08),
        "standard_position": limits.get("standard_position", 0.05),
        "speculative_max": limits.get("speculative_max", 0.03),
        "single_name_hard_cap": limits.get("single_name_hard_cap", 0.10),
        "base_weight": formula.get("base_weight", 0.05),
        "regime_multipliers": formula.get("regime_multipliers", {}),
    }

# Then wherever POSITION_LIMITS was used, call _get_position_limits() instead
```

Keep the old constant definitions but comment them out with `# PRE-KB:` prefix so they're visible as documentation.

### 3. Modify `mantis/convergence-backtester/src/v2_engine.py`

**Section: Risk tier configuration (around lines 140-175)**

Find where `tier1_dd`, `tier2_dd`, `tier3_dd`, `recovery_buffer`, `circuit_breaker_dd`, `circuit_breaker_reentry` are defined.

```python
# At the top of the file, add:
from src.kb_integration import get_drawdown_controls, get_regime_allocations, get_transition_speed

# Replace the hardcoded tier config with:
def _load_risk_config(self):
    """Load risk configuration from KB rules.

    KB DRAWDOWN_CONTROLS_V1 structure:
      CIRCUIT_BREAKERS: { dd_5_pct: {action, description}, dd_10_pct: {...}, ... }
      STOP_LOSS: { hard_stop_pct, trailing_stop_trigger_pct, trailing_stop_distance_pct, fundamental_stop_score }
      RECOVERY: { min_stable_readings, rebuild_rate_per_week, min_conviction_score, resume_threshold_from_hwm }
    """
    dd = get_drawdown_controls()
    cb = dd.get("CIRCUIT_BREAKERS", {})
    sl = dd.get("STOP_LOSS", {})
    rec = dd.get("RECOVERY", {})

    # Map KB circuit breaker tiers to v2_engine's existing tier variables
    # KB uses dd_5_pct/dd_10_pct/dd_15_pct/dd_20_pct → engine uses tier1/2/3 + circuit_breaker
    self.tier1_dd = 0.05   # dd_5_pct: review
    self.tier2_dd = 0.10   # dd_10_pct: reduce
    self.tier3_dd = 0.15   # dd_15_pct: protect
    # dd_20_pct is the lockdown tier — maps to existing circuit_breaker logic
    self.circuit_breaker_dd = 0.65  # Keep portfolio-level CB from v2_engine
    self.circuit_breaker_reentry = 63

    # Store the full KB actions for richer decision-making
    self.kb_dd_actions = {
        0.05: cb.get("dd_5_pct", {}).get("action", "review"),
        0.10: cb.get("dd_10_pct", {}).get("action", "reduce"),
        0.15: cb.get("dd_15_pct", {}).get("action", "protect"),
        0.20: cb.get("dd_20_pct", {}).get("action", "lockdown"),
    }

    # Stop loss from KB
    self.hard_stop = sl.get("hard_stop_pct", -0.25)
    self.trailing_trigger = sl.get("trailing_stop_trigger_pct", 0.15)
    self.trailing_distance = sl.get("trailing_stop_distance_pct", -0.10)

    # Recovery from KB
    self.recovery_buffer = rec.get("resume_threshold_from_hwm", -0.05)
    self.rebuild_rate = rec.get("rebuild_rate_per_week", 0.05)
    self.min_conviction = rec.get("min_conviction_score", 8)

    # Transition speed
    speed = get_transition_speed()
    self.reduce_days = speed.get("reducing_exposure_days", [3, 5])
    self.increase_weeks = speed.get("increasing_exposure_weeks", [2, 4])
```

Call `_load_risk_config()` in `__init__` where these values are currently set.

**Section: Asset class caps (around lines 64-68)**

```python
# Replace hardcoded caps with:
from src.kb_integration import get_position_sizing

def _load_asset_caps(self):
    """Load asset class caps from KB POSITION_SIZING_V1 → CONCENTRATION."""
    sizing = get_position_sizing()
    conc = sizing.get("CONCENTRATION", {})
    # Note: KB has sector/country/correlation caps, not per-asset-class caps.
    # The per-asset-class caps (native_crypto 0.30, wrapped_crypto 0.25, equity 0.30)
    # are v2_engine-specific and NOT yet in the KB. Keep them hardcoded for now.
    # When a future KB rule covers these, wire it here.
    self.cap_native_crypto = 0.30
    self.cap_wrapped_crypto = 0.25
    self.cap_equity = 0.30

    # KB concentration limits (apply on top of asset-class caps)
    self.top_5_max = conc.get("top_5_max_combined", 0.35)
    self.single_sector_max = conc.get("single_sector_max", 0.30)
    self.correlation_threshold = conc.get("correlation_threshold", 0.80)
```

**Section: Circuit breaker state checks (around lines 534-546)**

No code change needed — the circuit breaker logic already reads from `self.circuit_breaker_dd` which is now KB-sourced via `_load_risk_config()`.

## Testing

After all modifications:

```bash
# 1. Verify MANTIS works in fallback mode (no SOMA)
cd ~/Desktop/DABEIBA/mantis/convergence-backtester
python3 -c "from src.kb_integration import get_position_sizing, get_drawdown_controls; print('Sizing:', get_position_sizing()); print('DD:', get_drawdown_controls())"

# 2. Verify KB reads work with SOMA
cd ~/Desktop/DABEIBA/shared/soma
python3 -c "
from soma.soma_bridge import SomaBridge
with SomaBridge() as db:
    db.initialize_db()
    kr = db.get_kb_reader()
    kr.build_index()

    # Read MANTIS rules
    for rid in ['POSITION_SIZING_V1', 'DRAWDOWN_CONTROLS_V1', 'REGIME_TRANSITION_RULES_V1', 'TRANSITION_SPEED_V1']:
        rule = db.get_rule(rid)
        print(f'{rid}: {list(rule.get(\"rules\", {}).keys())[:3]}...')
"

# 3. Check that KB structure matches expectations
cd ~/Desktop/DABEIBA/mantis/convergence-backtester
python3 -c "
from src.kb_integration import get_drawdown_controls, get_position_sizing
dd = get_drawdown_controls()
cb = dd.get('CIRCUIT_BREAKERS', {})
print('CB tiers:', {k: v.get('action') for k, v in cb.items()})
sl = dd.get('STOP_LOSS', {})
print('Stop loss:', sl)
rec = dd.get('RECOVERY', {})
print('Recovery:', rec)
sizing = get_position_sizing()
print('Position limits:', sizing.get('POSITION_LIMITS', {}))
print('Concentration:', sizing.get('CONCENTRATION', {}))
"
```

## Import Path Note

`from soma.soma_bridge import SomaBridge` requires `~/Desktop/DABEIBA/shared` on `sys.path`. MANTIS's `soma_integration.py` already sets this up. Follow the same pattern. If not set:
```python
import sys, os
sys.path.insert(0, os.path.expanduser("~/Desktop/DABEIBA/shared"))
```

## Critical: KB Structure vs v2_engine Structure

The KB DRAWDOWN_CONTROLS_V1 uses **named thresholds** (`dd_5_pct`, `dd_10_pct`, etc.) not numbered tiers. The v2_engine uses `tier1_dd`, `tier2_dd`, `tier3_dd` float variables. The `_load_risk_config()` method bridges this gap — mapping KB names to engine variables. Make sure this mapping is correct.

Similarly, KB POSITION_SIZING_V1 uses `POSITION_LIMITS`, `SIZING_FORMULA`, `CONCENTRATION` top-level keys — not `base_weight` or `concentration_limits` at the top level. Always access via `.get("POSITION_LIMITS", {})` etc.

## Important

- Do NOT change any MANTIS backtest results — the same values flow through, just sourced from KB now
- Every KB read has try/except fallback to the exact same values currently hardcoded
- Fallback dicts in `kb_integration.py` MUST mirror the KB YAML structure exactly (check mantis_mechanics.md)
- Comment out old constants with `# PRE-KB:` prefix (keep as documentation)
- The `kb_integration.py` module is the single import point — no scattered SOMA imports in MANTIS
- Log every rule usage for audit trail
- If SOMA import fails (e.g., not installed), MANTIS runs identically to before
- Per-asset-class caps (native_crypto 0.30, wrapped_crypto 0.25, equity 0.30) are NOT in the KB — keep hardcoded
- Commit when done: `git add -A && git commit -m "Wire MANTIS to read KB rules at runtime: 5 rules with fallbacks + audit logging"`
