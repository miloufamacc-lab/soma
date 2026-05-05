"""
RAPTOR — Compliance Enforcement Engine (Phase 2)
Pre-dispatch compliance checking for outreach communications.

Regulatory framework:
  - Law 25 (Quebec) — personal data consent before contact
  - CASL — express/implied consent, unsubscribe mechanism, sender ID
  - AMF — prohibited titles, prohibited performance language
  - CIRO / NI 31-103 — referral disclosure, registration titles

Usage:
    from soma.soma_bridge import SomaBridge
    from soma.raptor_compliance import RaptorCompliance, seed_compliance_rules

    with SomaBridge() as bridge:
        seed_compliance_rules(bridge)          # idempotent
        compliance = RaptorCompliance(bridge)
        result = compliance.validate_outreach(prospect_id, email_body)
        if result["approved"]:
            send_email(...)
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

# ── Prohibited term definitions ───────────────────────────────────────────────
# Each entry: (pattern, flags, category, guidance)
# Compiled at module load; reloaded from kb_rules if RAPTOR_PROHIBITED_TERMS_V1 exists.

_DEFAULT_PROHIBITED_PATTERNS: list[tuple[str, int, str, str]] = [
    # Performance guarantees (EN)
    (r"\bguaranteed?\s+(?:return|profit|gain|income|investment|yield)s?\b",
     re.IGNORECASE, "PERFORMANCE_GUARANTEE",
     "Replace with 'historical returns' or 'past performance does not guarantee future results'."),
    (r"\bguarantee\s+(?:any\s+)?(?:return|profit|gain)\b",
     re.IGNORECASE, "PERFORMANCE_GUARANTEE",
     "Avoid guaranteeing financial outcomes."),
    (r"\brisk[\s\-]?free\b",
     re.IGNORECASE, "RISK_MISREPRESENTATION",
     "All investments carry risk. Use 'lower-risk' or describe specific risk profile."),
    (r"\bno[\s\-]risk\b",
     re.IGNORECASE, "RISK_MISREPRESENTATION",
     "All investments carry risk. Qualified language required."),
    (r"\bcapital\s+(?:is\s+)?guaranteed\b",
     re.IGNORECASE, "PERFORMANCE_GUARANTEE",
     "Capital guarantee claims require specific product backing and disclosure."),
    (r"\bsure\s+thing\b",
     re.IGNORECASE, "PERFORMANCE_GUARANTEE",
     "Implies certainty of outcome — prohibited."),
    # Performance guarantees (FR)
    (r"\brendements?\s+garantis?\b",
     re.IGNORECASE, "PERFORMANCE_GUARANTEE",
     "Remplacer par 'rendements historiques' ou 'les rendements passés ne garantissent pas les résultats futurs'."),
    (r"\bsans\s+risque\b",
     re.IGNORECASE, "RISK_MISREPRESENTATION",
     "Tout placement comporte des risques. Utiliser 'faible risque' avec qualification."),
    (r"\baucun\s+risque\b",
     re.IGNORECASE, "RISK_MISREPRESENTATION",
     "Tout placement comporte des risques."),
    (r"\bcapital\s+garanti\b",
     re.IGNORECASE, "PERFORMANCE_GUARANTEE",
     "Toute garantie de capital doit être appuyée par un produit spécifique et une divulgation."),
    (r"\b(?:placement|investissement|rendement|fonds|portefeuille)\b.{0,60}\bgaranti[e]?s?\b",
     re.IGNORECASE | re.DOTALL, "PERFORMANCE_GUARANTEE",
     "Eviter de qualifier un placement ou un investissement de 'garanti'. "
     "Utiliser 'historique' ou divulguer explicitement le mécanisme de garantie."),
    (r"\bgaranti[e]?s?\b.{0,60}\b(?:placement|investissement|rendement|fonds|portefeuille)\b",
     re.IGNORECASE | re.DOTALL, "PERFORMANCE_GUARANTEE",
     "Eviter de qualifier un placement ou un investissement de 'garanti'."),
    # Comparative / superiority claims
    (r"\bNo\.?\s*1\b|\b#\s*1\b|\bnumber\s+one\b",
     re.IGNORECASE, "COMPARATIVE_CLAIM",
     "Comparative superlatives require substantiation. Avoid unverified rankings."),
    (r"\bbest\s+(?:performing|advisor|investment|return)\b",
     re.IGNORECASE, "COMPARATIVE_CLAIM",
     "Superlative performance claims require full substantiation and CIRO approval."),
    (r"\btop\s+(?:advisor|performer|fund|investment)\b",
     re.IGNORECASE, "COMPARATIVE_CLAIM",
     "Comparative rankings require substantiation."),
    # AMF/regulatory approval claims
    (r"\bapproved\s+by\s+(?:the\s+)?AMF\b",
     re.IGNORECASE, "MISLEADING_REGISTRATION",
     "AMF does not 'approve' investments or advisors — it registers them."),
    (r"\bapprouvé\s+par\s+l['']\s*AMF\b",
     re.IGNORECASE, "MISLEADING_REGISTRATION",
     "L'AMF n'approuve pas les investissements ou les conseillers — elle les inscrit."),
    (r"\bduly\s+registered\s+with\s+(?:the\s+)?AMF\b",
     re.IGNORECASE, "MISLEADING_REGISTRATION",
     "Acceptable phrasing: 'registered with the AMF' (without 'duly')."),
    (r"\bSEC[\s\-]approved\b|\bFINRA[\s\-]approved\b",
     re.IGNORECASE, "MISLEADING_REGISTRATION",
     "Regulatory bodies do not 'approve' specific investments."),
    # Prohibited titles (AMF-Quebec)
    (r"\bAdvisor\s+Emeritus\b",
     re.IGNORECASE, "PROHIBITED_TITLE",
     "Prohibited title under AMF regulations. Use only approved registration categories."),
    (r"\bFinancial\s+Advisor\b",
     re.IGNORECASE, "CAUTION_TITLE",
     "In Quebec, 'Financial Advisor' may only be used by Planificateurs financiers (Pl. Fin.). "
     "Registered individuals should use 'Investment Advisor' or 'Portfolio Manager'."),
    # Forward-looking performance promises
    (r"\bwill\s+(?:definitely\s+)?(?:double|triple|quadruple)\b",
     re.IGNORECASE, "FORWARD_LOOKING_CLAIM",
     "Specific future performance promises are prohibited."),
    (r"\b(?:guaranteed\s+to|certain\s+to)\s+(?:grow|return|appreciate|increase)\b",
     re.IGNORECASE, "FORWARD_LOOKING_CLAIM",
     "Do not promise future investment performance."),
    (r"\byou\s+(?:will|would|can)\s+(?:definitely\s+)?(?:make|earn|gain|profit)\b",
     re.IGNORECASE, "FORWARD_LOOKING_CLAIM",
     "Avoid promising specific financial outcomes to the prospect."),
]

# Severity: BLOCK stops approval; WARN allows approval with flags
_BLOCK_CATEGORIES = {
    "PERFORMANCE_GUARANTEE", "RISK_MISREPRESENTATION", "COMPARATIVE_CLAIM",
    "MISLEADING_REGISTRATION", "PROHIBITED_TITLE", "FORWARD_LOOKING_CLAIM",
}
_WARN_CATEGORIES = {"CAUTION_TITLE"}

# Unsubscribe mechanism keywords (CASL S.11)
_UNSUBSCRIBE_PATTERNS = re.compile(
    r"\b(?:unsubscribe|opt[\s\-]out|désabonner|désabonnement|se\s+désabonner)\b",
    re.IGNORECASE,
)

# Sender identification (CASL S.6(2)(b)) — phone or email in message
_SENDER_ID_PHONE = re.compile(r"\b\d{3}[\s.\-]?\d{3}[\s.\-]?\d{4}\b")
_SENDER_ID_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")


class RaptorCompliance:
    """Pre-dispatch compliance checker for RAPTOR outreach.

    Checks:
      1. Active CASL / Law 25 consent on record
      2. AMF/CIRO prohibited language scan (keyword-based)
      3. Unsubscribe mechanism present (CASL S.11)
      4. Sender identification present (CASL S.6(2)(b))

    All methods are pure (no DB writes). Validates only — does not block sends.
    Caller is responsible for honouring the returned `approved` flag.
    """

    def __init__(self, bridge):
        self.bridge   = bridge
        self._patterns = self._load_patterns()

    # ── Pattern loading ───────────────────────────────────────────────────────

    def _load_patterns(self) -> list[tuple]:
        """Load prohibited patterns from kb_rules if available; else use defaults."""
        try:
            row = self.bridge.conn.execute(
                "SELECT rule_data FROM kb_rules "
                "WHERE rule_id = 'RAPTOR_PROHIBITED_TERMS_V1'"
            ).fetchone()
            if row:
                data = json.loads(row["rule_data"])
                patterns = data.get("patterns", [])
                if patterns:
                    compiled = []
                    for p in patterns:
                        flags = re.IGNORECASE if p.get("ignorecase", True) else 0
                        compiled.append((
                            p["pattern"], flags,
                            p.get("category", "UNKNOWN"),
                            p.get("guidance", ""),
                        ))
                    return compiled
        except Exception:
            pass
        return list(_DEFAULT_PROHIBITED_PATTERNS)

    # ── Core methods ──────────────────────────────────────────────────────────

    def validate_outreach(
        self, prospect_id: str, content_text: str
    ) -> dict[str, Any]:
        """Run full compliance check before sending outreach.

        Returns:
            approved        — True only if zero BLOCK-severity violations
            violations      — list of {code, severity, message, ...}
            suggestions     — list of corrective action strings
            scan_timestamp  — ISO-8601 UTC
        """
        violations: list[dict] = []
        suggestions: list[str] = []

        # 1. Consent check (Law 25 + CASL)
        has_consent = (
            self.bridge.check_consent(prospect_id, "casl_express")
            or self.bridge.check_consent(prospect_id, "casl_implied")
            or self.bridge.check_consent(prospect_id, "law25_explicit")
        )
        if not has_consent:
            violations.append({
                "code":     "CASL_NO_CONSENT",
                "severity": "BLOCK",
                "message":  "No active CASL or Law 25 consent on record. "
                            "Obtain consent before sending commercial electronic messages.",
            })
            suggestions.append(
                "Record consent via write_consent() before initiating outreach."
            )

        # 2. Prohibited terms scan
        for hit in self.scan_prohibited_terms(content_text):
            severity = "BLOCK" if hit["category"] in _BLOCK_CATEGORIES else "WARN"
            violations.append({
                "code":     "PROHIBITED_TERM",
                "severity": severity,
                "term":     hit["term"],
                "category": hit["category"],
                "message":  f"Prohibited language detected: '{hit['term']}' "
                            f"[{hit['category']}]. {hit['guidance']}",
            })
            suggestions.append(hit["guidance"])

        # 3. Unsubscribe mechanism (CASL S.11)
        if not self._has_unsubscribe(content_text):
            violations.append({
                "code":     "MISSING_UNSUBSCRIBE",
                "severity": "BLOCK",
                "message":  "No unsubscribe mechanism detected. Required by CASL S.11 "
                            "for all commercial electronic messages.",
            })
            suggestions.append(
                "Add: 'To unsubscribe, reply UNSUBSCRIBE or contact us at [email].' "
                "(EN) / 'Pour vous désabonner, répondez DÉSABONNEMENT.' (FR)"
            )

        # 4. Sender identification (CASL S.6(2)(b))
        if not self._has_sender_id(content_text):
            violations.append({
                "code":     "MISSING_SENDER_ID",
                "severity": "WARN",
                "message":  "Sender contact information (phone or email) not detected. "
                            "Required by CASL S.6(2)(b).",
            })
            suggestions.append(
                "Include your phone number and email address in the message footer."
            )

        approved = not any(v["severity"] == "BLOCK" for v in violations)
        return {
            "approved":       approved,
            "violations":     violations,
            "suggestions":    list(dict.fromkeys(suggestions)),  # deduplicate
            "scan_timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def scan_prohibited_terms(self, text: str) -> list[dict]:
        """Scan text for AMF/CIRO prohibited language.

        Returns list of {term, category, guidance} for each match found.
        Each distinct match position returned once.
        """
        hits: list[dict] = []
        seen: set[str] = set()
        for pattern, flags, category, guidance in self._patterns:
            for match in re.finditer(pattern, text, flags):
                term = match.group(0).strip()
                key  = f"{category}:{term.lower()}"
                if key not in seen:
                    seen.add(key)
                    hits.append({
                        "term":     term,
                        "category": category,
                        "guidance": guidance,
                        "span":     match.span(),
                    })
        return hits

    def generate_compliant_footer(
        self,
        language:     str  = "EN",
        first_name:   str  = "{first_name}",
        last_name:    str  = "{last_name}",
        title:        str  = "{title}",
        firm_name:    str  = "{firm_name}",
        amf_number:   str  = "{amf_number}",
        address:      str  = "{address}",
        phone:        str  = "{phone}",
        email:        str  = "{email}",
        privacy_url:  str  = "{privacy_url}",
    ) -> str:
        """Return an AMF-compliant email footer with required disclosures.

        Includes: name + title, AMF registration number, unsubscribe,
        Law 25 / CASL privacy notice.
        """
        from soma.raptor_templates import EMAIL_FOOTER_EN, EMAIL_FOOTER_FR
        template = EMAIL_FOOTER_EN if language.upper() == "EN" else EMAIL_FOOTER_FR
        return template.format(
            first_name=first_name, last_name=last_name,
            title=title, firm_name=firm_name, amf_number=amf_number,
            address=address, phone=phone, email=email, privacy_url=privacy_url,
        )

    def check_referral_compliance(self, prospect_id: str) -> dict:
        """NI 31-103 referral disclosure check.

        Verifies:
          - Any linked COI has a signed referral agreement
          - Referral disclosure has been delivered to the prospect

        Returns:
            compliant   — True if all checks pass (or no referrals)
            missing     — list of {check, coi_name, referral_id} for each gap
        """
        referrals = self.bridge.get_referrals_by_prospect(prospect_id)
        if not referrals:
            return {"compliant": True, "missing": []}

        missing: list[dict] = []
        for ref in referrals:
            coi = self.bridge.get_coi(ref["coi_id"])
            coi_name = coi["name"] if coi else f"COI {ref['coi_id'][:8]}"

            if coi and not coi["referral_agreement_signed"]:
                missing.append({
                    "check":       "REFERRAL_AGREEMENT_UNSIGNED",
                    "coi_name":    coi_name,
                    "referral_id": ref["referral_id"],
                    "message":     f"COI '{coi_name}' has no signed referral agreement "
                                   "(NI 31-103 S.13.7 requires written agreement before referral fees).",
                })

            if not ref.get("disclosure_delivered"):
                missing.append({
                    "check":       "DISCLOSURE_NOT_DELIVERED",
                    "coi_name":    coi_name,
                    "referral_id": ref["referral_id"],
                    "message":     f"Referral disclosure not delivered to prospect "
                                   f"(originated from COI '{coi_name}'). "
                                   "NI 31-103 S.13.7 requires written disclosure to client.",
                })

        return {"compliant": len(missing) == 0, "missing": missing}

    # ── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _has_unsubscribe(text: str) -> bool:
        return bool(_UNSUBSCRIBE_PATTERNS.search(text))

    @staticmethod
    def _has_sender_id(text: str) -> bool:
        return bool(
            _SENDER_ID_PHONE.search(text) or _SENDER_ID_EMAIL.search(text)
        )


# ── Rule seeder ───────────────────────────────────────────────────────────────

def seed_compliance_rules(bridge) -> bool:
    """Write RAPTOR_PROHIBITED_TERMS_V1 to soma.db kb_rules if not present.

    Stores all prohibited patterns in a DB-tunable format.
    Returns True if inserted, False if already existed.
    """
    existing = bridge.conn.execute(
        "SELECT 1 FROM kb_rules WHERE rule_id = 'RAPTOR_PROHIBITED_TERMS_V1'"
    ).fetchone()
    if existing:
        return False

    now = datetime.now(timezone.utc).isoformat()
    # Serialize default patterns to JSON-friendly format
    patterns_json = [
        {
            "pattern":    p[0],
            "ignorecase": bool(p[1] & re.IGNORECASE),
            "category":   p[2],
            "guidance":   p[3],
        }
        for p in _DEFAULT_PROHIBITED_PATTERNS
    ]
    rule_data = json.dumps({
        "rule_id":      "RAPTOR_PROHIBITED_TERMS_V1",
        "source_module": ["RAPTOR"],
        "confidence":   0.90,
        "description":  "AMF/CIRO prohibited language patterns for outreach compliance. "
                        "Phase 2a: keyword matching. Phase 2b: upgrade to spaCy NER.",
        "patterns":     patterns_json,
        "block_categories": list(_BLOCK_CATEGORIES),
        "warn_categories":  list(_WARN_CATEGORIES),
        "regulatory_refs": [
            "CASL S.6, S.11 (unsubscribe + sender ID)",
            "Law 25 Quebec (consent before contact)",
            "AMF — prohibited titles and performance language",
            "NI 31-103 S.13.7 (referral disclosure)",
            "CIRO Rule 3804 (7-year retention)",
        ],
    })

    bridge.conn.execute(
        """INSERT OR IGNORE INTO kb_rules
           (rule_id, source_file, source_module, rule_data, confidence, parsed_at, schema_version)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            "RAPTOR_PROHIBITED_TERMS_V1",
            "shared/soma/raptor_compliance.py",
            "RAPTOR",
            rule_data,
            0.90,
            now,
            3,
        ),
    )
    bridge.conn.commit()
    return True
