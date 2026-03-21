# Claude Code Prompt C — Wire ORACLE to Read KB Rules at Runtime

## Context
SOMA is in ~/Desktop/DABEIBA/shared/soma/. The KB runtime reader is built (Prompts A+B). There are 12 YAML rule blocks indexed in the `kb_rules` table. ORACLE is in ~/Desktop/DABEIBA/oracle/.

ORACLE currently has hardcoded thresholds and regime logic. This prompt wires ORACLE to **read rules from SOMA's KB** instead of using hardcoded values, with the old values kept as fallbacks.

## Rules ORACLE Should Read

These 5 rules have `source_module` containing "ORACLE":

| Rule ID | Source File | What It Contains |
|---------|------------|-----------------|
| `REGIME_ALLOCATIONS_V1` | mantis_mechanics.md | Target equity/cash allocations per regime (RISK_ON_REBOUND, RISK_ON_EXPANSION, TURBULENCE, CONTRACTION) |
| `YIELD_CURVE_SIGNALS_V1` | macro_regimes.md | Yield curve shape → positioning (steep_upward, flat_inverted, bear_steepening, bull_flattening) |
| `INFLATION_ASSET_MAP_V1` | macro_regimes.md | Inflation scenario → asset class impact map |
| `CREDIT_SPREAD_THRESHOLDS_V1` | macro_regimes.md | HY spread thresholds → opportunity signals |
| `VALUATION_METHOD_SELECTOR_V1` | valuation_models.md | When to use DCF vs DDM vs Relative vs SOTP vs Real Options |

## Architecture Pattern

Every integration point follows this pattern:

```python
# 1. Try to read KB rule (with fallback to old hardcoded value)
# 2. Log the rule usage for audit trail
# 3. Use the rule data in the decision

def _get_regime_allocations(self):
    """Read regime allocations from KB, fall back to hardcoded defaults."""
    try:
        from soma.soma_bridge import SomaBridge
        with SomaBridge() as db:
            rule = db.get_rule("REGIME_ALLOCATIONS_V1")
            db.log_rule_usage("REGIME_ALLOCATIONS_V1", "ORACLE", context={"source": "gli_engine"})
            return rule.get("rules", {})
    except Exception:
        # Fallback: return hardcoded defaults (pre-KB behavior)
        return {
            "RISK_ON_REBOUND": {"equity_target": [0.80, 0.95], "cash_floor": 0.05, "duration_stance": "short", "risk_appetite": "aggressive"},
            "RISK_ON_EXPANSION": {"equity_target": [0.70, 0.85], "cash_floor": 0.10, "duration_stance": "neutral", "risk_appetite": "growth"},
            "TURBULENCE": {"equity_target": [0.50, 0.65], "cash_floor": 0.20, "duration_stance": "extend_slightly", "risk_appetite": "defensive"},
            "CONTRACTION": {"equity_target": [0.30, 0.50], "cash_floor": 0.30, "duration_stance": "long", "risk_appetite": "preservation"},
        }
```

## Files to Modify

### 1. `oracle/oracle/gli/gli_engine.py`

**Section: Regime detection (around lines 273-286)**

The regime detection currently uses hardcoded heuristics. Add a helper that reads `REGIME_ALLOCATIONS_V1` to enrich the regime output with allocation targets:

```python
# After the existing regime detection logic, ADD:

def _enrich_regime_with_kb(self, regime_name, regime_data):
    """Attach KB-sourced allocation targets to the regime result."""
    try:
        from soma.soma_bridge import SomaBridge
        with SomaBridge() as db:
            rule = db.get_rule("REGIME_ALLOCATIONS_V1")
            db.log_rule_usage("REGIME_ALLOCATIONS_V1", "ORACLE",
                              context={"regime": regime_name, "source": "gli_engine"})
            allocations = rule.get("rules", {})
            if regime_name in allocations:
                regime_data["kb_allocations"] = allocations[regime_name]
                regime_data["kb_confidence"] = rule.get("confidence", 0.95)
    except Exception:
        pass  # graceful fallback — regime works without KB enrichment
    return regime_data
```

Call this method right before returning the regime result.

**Section: Signal thresholds (around lines 78-81)**

Current hardcoded values:
```python
SIGNAL_BULLISH_THRESHOLD = 0.3
SIGNAL_BEARISH_THRESHOLD = -0.3
```

Leave these hardcoded for now. There is no `GLI_THRESHOLDS` rule block in the KB yet. When one is added in the future, wire it here using the same pattern as regime allocations. **Do NOT add dead code** — only wire rules that exist.

### 2. `oracle/oracle/shared/data_bridge.py`

The DataBridge already dual-writes to SOMA. Add one enrichment: when writing regime data, also attach KB allocation targets if available.

Find where `write_regime()` or regime data is written to SOMA. Before that write, enrich the data:

```python
# Before writing regime to SOMA, try to attach KB allocations
try:
    kb_reader = db.get_kb_reader()
    if kb_reader.is_index_stale():
        kb_reader.build_index()
    alloc_rule = kb_reader.get_rule("REGIME_ALLOCATIONS_V1")
    regime_data["kb_allocations"] = alloc_rule.get("rules", {}).get(regime_name, {})
    kb_reader.log_rule_usage("REGIME_ALLOCATIONS_V1", "ORACLE",
                              context={"regime": regime_name, "via": "data_bridge"})
except Exception:
    pass  # KB enrichment is optional
```

### 3. Create `oracle/oracle/kb_integration.py` (NEW FILE)

A clean helper module that ORACLE code can import for KB rule access:

```python
"""
ORACLE ↔ SOMA KB Integration Layer

Provides clean access to KB rules for ORACLE modules.
All methods include fallbacks — ORACLE works with or without SOMA.
"""

import logging

logger = logging.getLogger(__name__)

# ── Hardcoded fallbacks (pre-KB behavior) ──────────────────────────

_FALLBACK_YIELD_CURVE = {
    "steep_upward": {"positioning": "bullish_equities", "sectors": ["cyclicals"]},
    "flat_inverted": {"positioning": "defensive", "sectors": ["long_duration_bonds"]},
    "bear_steepening": {"positioning": "real_assets", "sectors": ["TIPS", "commodities"]},
    "bull_flattening": {"positioning": "early_cycle", "sectors": []},
}

_FALLBACK_INFLATION_MAP = {
    "within_expectations": {"cash": "neutral", "bonds": "neutral", "equity": "neutral"},
    "above_expectations": {"cash": "positive", "bonds": "negative", "equity": "negative", "commodities": "positive"},
    "deflation": {"cash": "positive_real", "bonds": "positive", "equity": "negative"},
}

_FALLBACK_CREDIT_SPREADS = {
    "hy_distressed_threshold_bps": 500,
    "signal": "distressed_opportunity_approaching",
}

_FALLBACK_VALUATION_SELECTOR = {
    "DCF": {"when": "predictable cash flows, mature companies"},
    "DDM": {"when": "stable dividends, sustainable payout"},
    "Relative": {"when": "sufficient comparables, standard multiples"},
    "SOTP": {"when": "conglomerates, diverse business lines"},
    "Real_Options": {"when": "significant optionality, high uncertainty"},
}


def get_yield_curve_signals():
    """Read yield curve positioning rules from KB."""
    try:
        from soma.soma_bridge import SomaBridge
        with SomaBridge() as db:
            rule = db.get_rule("YIELD_CURVE_SIGNALS_V1")
            db.log_rule_usage("YIELD_CURVE_SIGNALS_V1", "ORACLE")
            return rule.get("rules", _FALLBACK_YIELD_CURVE)
    except Exception as e:
        logger.debug(f"KB fallback for yield_curve_signals: {e}")
        return _FALLBACK_YIELD_CURVE


def get_inflation_asset_map():
    """Read inflation scenario → asset impact from KB."""
    try:
        from soma.soma_bridge import SomaBridge
        with SomaBridge() as db:
            rule = db.get_rule("INFLATION_ASSET_MAP_V1")
            db.log_rule_usage("INFLATION_ASSET_MAP_V1", "ORACLE")
            return rule.get("rules", _FALLBACK_INFLATION_MAP)
    except Exception as e:
        logger.debug(f"KB fallback for inflation_asset_map: {e}")
        return _FALLBACK_INFLATION_MAP


def get_credit_spread_thresholds():
    """Read credit spread threshold signals from KB."""
    try:
        from soma.soma_bridge import SomaBridge
        with SomaBridge() as db:
            rule = db.get_rule("CREDIT_SPREAD_THRESHOLDS_V1")
            db.log_rule_usage("CREDIT_SPREAD_THRESHOLDS_V1", "ORACLE")
            return rule.get("rules", _FALLBACK_CREDIT_SPREADS)
    except Exception as e:
        logger.debug(f"KB fallback for credit_spread_thresholds: {e}")
        return _FALLBACK_CREDIT_SPREADS


def get_valuation_method_selector():
    """Read valuation method selection criteria from KB."""
    try:
        from soma.soma_bridge import SomaBridge
        with SomaBridge() as db:
            rule = db.get_rule("VALUATION_METHOD_SELECTOR_V1")
            db.log_rule_usage("VALUATION_METHOD_SELECTOR_V1", "ORACLE")
            return rule.get("rules", _FALLBACK_VALUATION_SELECTOR)
    except Exception as e:
        logger.debug(f"KB fallback for valuation_method_selector: {e}")
        return _FALLBACK_VALUATION_SELECTOR


def get_regime_allocations(regime_name=None):
    """Read target allocations for a given regime (or all regimes)."""
    try:
        from soma.soma_bridge import SomaBridge
        with SomaBridge() as db:
            rule = db.get_rule("REGIME_ALLOCATIONS_V1")
            db.log_rule_usage("REGIME_ALLOCATIONS_V1", "ORACLE",
                              context={"regime": regime_name})
            allocations = rule.get("rules", {})
            if regime_name:
                return allocations.get(regime_name, {})
            return allocations
    except Exception as e:
        logger.debug(f"KB fallback for regime_allocations: {e}")
        return {}
```

### 4. Wire into existing ORACLE modules

**In `gli_engine.py`** — wherever regime context is built, add:

```python
from oracle.kb_integration import get_regime_allocations

# After determining regime_name:
kb_alloc = get_regime_allocations(regime_name)
if kb_alloc:
    result["target_equity"] = kb_alloc.get("equity_target")
    result["cash_floor"] = kb_alloc.get("cash_floor")
    result["risk_appetite"] = kb_alloc.get("risk_appetite")
```

**In `execution_scorer.py`** — where valuation approach is selected, add:

```python
from oracle.kb_integration import get_valuation_method_selector

# When choosing valuation method:
val_rules = get_valuation_method_selector()
# Use val_rules to inform method selection logic
```

## Testing

After all modifications:

```bash
# 1. Verify ORACLE still runs without SOMA (fallback mode)
cd ~/Desktop/DABEIBA/oracle
python3 -c "from oracle.kb_integration import get_regime_allocations; print(get_regime_allocations('RISK_ON_EXPANSION'))"

# 2. Verify ORACLE reads from KB when SOMA is available
python3 -c "
from soma.soma_bridge import SomaBridge
with SomaBridge() as db:
    db.initialize_db()
    kr = db.get_kb_reader()
    kr.build_index()
    rule = db.get_rule('REGIME_ALLOCATIONS_V1')
    print('KB rule loaded:', list(rule.get('rules', {}).keys()))
"

# 3. Check audit log shows ORACLE reads
python3 -c "
from soma.soma_bridge import SomaBridge
with SomaBridge() as db:
    db.initialize_db()
    kr = db.get_kb_reader()
    kr.build_index()
    from oracle.kb_integration import get_regime_allocations
    alloc = get_regime_allocations('TURBULENCE')
    print('Turbulence allocation:', alloc)
    audits = kr.get_rule_audit(module='ORACLE', limit=5)
    print(f'{len(audits)} ORACLE audit entries')
"
```

## Import Path Note

The `from soma.soma_bridge import SomaBridge` import works because ORACLE's `data_bridge.py` already adds `~/Desktop/DABEIBA/shared` to `sys.path` (it has to, for existing SOMA dual-writes). Verify this path is set before adding KB imports. If ORACLE is run standalone (e.g., `python3 oracle/main.py`), make sure `shared/` is still importable — check how `data_bridge.py` handles it and follow the same pattern.

If `from soma.soma_bridge import SomaBridge` doesn't resolve, use:
```python
import sys, os
sys.path.insert(0, os.path.expanduser("~/Desktop/DABEIBA/shared"))
```

## Important

- Do NOT change any existing ORACLE behavior — only ADD KB reads alongside existing logic
- Every KB read has a try/except fallback to old behavior
- The `kb_integration.py` module is the single import point — no scattered SOMA imports in ORACLE modules
- Log every rule usage with `log_rule_usage()` for the audit trail
- Fallback values in `kb_integration.py` MUST match the actual KB YAML exactly (including `duration_stance` and `risk_appetite` fields in REGIME_ALLOCATIONS_V1)
- The `get_rule()` method returns the FULL parsed YAML as a dict — so `rule.get("rules", {})` returns the inner `rules:` block
- Commit when done: `git add -A && git commit -m "Wire ORACLE to read KB rules at runtime: 5 rules with fallbacks + audit logging"`
