# RAPTOR_PROHIBITED_TERMS_V1

**Module:** RAPTOR | **Version:** 1 | **Status:** ACTIVE  
**Source:** raptor_compliance.py — ComplianceEngine, _DEFAULT_PROHIBITED_PATTERNS

---

## Rule

All prospect-facing communications must be scanned before send.
BLOCK severity = must not send. WARN severity = review before sending.

## Categories & Patterns

### PERFORMANCE_GUARANTEE (BLOCK)
Any language implying guaranteed returns or risk-free outcomes.

**Trigger phrases (EN):**
- "guaranteed return", "guaranteed profit", "guaranteed income"
- "risk-free", "no risk", "zero risk", "capital guaranteed", "principal guaranteed"
- Proximity pattern: investment/fund/portfolio within 60 chars of "guaranteed/garanti"

**Trigger phrases (FR):**
- "rendement garanti", "sans risque"
- "placement garanti", "investissement garanti"
- Bidirectional: "garanti(e)" near "placement/investissement/rendement/fonds/portefeuille"

**Regulation:** NI 81-102, NI 31-103; AMF strict prohibition

---

### RISK_MISREPRESENTATION (BLOCK)
Downplaying or mischaracterizing investment risk.

**Trigger phrases (EN):**
- "safe investment", "completely safe", "totally safe"
- "no chance of loss", "never lose", "won't lose"
- "low risk, high return", "high return, low risk"

**Trigger phrases (FR):**
- "investissement sûr", "sans risque"
- "aucune chance de perte", "ne perdrez jamais"

**Regulation:** NI 31-103 s.13.2 suitability; AMF disclosure rules

---

### COMPARATIVE_CLAIM (WARN)
Comparative claims without documented substantiation.

**Trigger phrases:**
- "better than your bank", "outperform", "beat the market"
- "superior returns", "higher returns than"

**Regulation:** CIRO Rule 3400 advertising standards

---

### MISLEADING_REGISTRATION (BLOCK)
Implying credentials or registrations not held.

**Trigger phrases:**
- "financial planner", "portfolio manager" (if not licensed as such)
- "we manage your money" (if advisor, not PM)

**Regulation:** NI 31-103 registration categories

---

### PROHIBITED_TITLE (BLOCK)
Unregistered use of protected titles.

**Trigger phrases:**
- "wealth manager" (protected in some provinces)
- "financial advisor" without disclosure
- "investment advisor" without registration disclosure

**Regulation:** Provincial securities acts

---

### FORWARD_LOOKING_CLAIM (WARN)
Unreasonably positive forward-looking statements.

**Trigger phrases:**
- "will achieve", "will generate", "expected return of X%"
- "projected return", "target return" (without proper disclaimer)

**Regulation:** NI 51-102 forward-looking information rules

---

### CAUTION_TITLE (WARN)
Trigger phrases requiring careful framing (not prohibited, but require disclaimer).

**Trigger phrases:**
- "double your money", "triple your money"
- "market-beating", "alpha generation"

---

## Scanning Behaviour

- `scan_communication(text)` → returns `{violations: [{category, severity, snippet, guidance}]}`
- Shadow table `raptor_compliance_shadow` logs all scans for audit trail
- BLOCK findings prevent send; WARN findings flag for advisor review
- Full bilingual (EN + FR) pattern coverage
- Patterns compiled at import time (regex with IGNORECASE | DOTALL flags)
