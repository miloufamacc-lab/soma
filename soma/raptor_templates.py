"""
RAPTOR — Compliance-approved outreach templates (Phase 2)

All templates use {placeholders} for personalization.
Required fields are documented per template.
NEVER modify the legal footer blocks without AMF/CIRO legal review.

Title guidance (Quebec — AMF registered individuals):
  Approved:   "Investment Advisor" / "Conseiller en investissement"
              "Portfolio Manager" / "Gestionnaire de portefeuille"
              "Mutual Funds Representative" / "Représentant en épargne collective"
  Prohibited: "Financial Advisor", "Financial Planner" (unless holder of Pl. Fin. designation)
              "Advisor Emeritus", "No. 1 Advisor", "Top Advisor"
"""

# ── Compliant footer blocks ───────────────────────────────────────────────────

EMAIL_FOOTER_EN = """\
---
{first_name} {last_name}
{title} | {firm_name}
AMF Registration No.: {amf_number}
{address}
T: {phone}  |  E: {email}

To unsubscribe from our communications, reply with "UNSUBSCRIBE" or \
contact us at {email}.
Your personal information is managed in accordance with Quebec's Law 25 \
(Act respecting the protection of personal information in the private sector). \
View our privacy policy at {privacy_url}.
This message and any attachments are confidential and intended solely for \
the named recipient(s).
"""

EMAIL_FOOTER_FR = """\
---
{first_name} {last_name}
{title} | {firm_name}
No d'inscription AMF : {amf_number}
{address}
T : {phone}  |  C : {email}

Pour vous désabonner de nos communications, répondez « DÉSABONNEMENT » \
ou communiquez avec nous à {email}.
Vos renseignements personnels sont gérés conformément à la Loi 25 du Québec \
(Loi sur la protection des renseignements personnels dans le secteur privé). \
Consultez notre politique de confidentialité à {privacy_url}.
Ce message et toutes les pièces jointes sont confidentiels et destinés \
uniquement au(x) destinataire(s) nommé(s).
"""

# ── Email templates ───────────────────────────────────────────────────────────

EMAIL_INITIAL_OUTREACH_EN = """\
Subject: Introduction — {advisor_first_name} {advisor_last_name}, {title}

Hi {prospect_first_name},

{referral_intro_or_context}

I specialize in working with {target_profile} in the {city} area. \
My approach focuses on {value_proposition}.

I would welcome the opportunity to have a brief conversation — \
no commitment required — to understand your situation and share \
how I may be able to add value.

Would you be available for a 20-minute call in the coming weeks?

Best regards,

{EMAIL_FOOTER_EN}
"""

EMAIL_INITIAL_OUTREACH_FR = """\
Objet : Présentation — {advisor_first_name} {advisor_last_name}, {title}

Bonjour {prospect_first_name},

{referral_intro_or_context}

Je me spécialise dans l'accompagnement de {target_profile} dans la région de {city}. \
Mon approche est axée sur {value_proposition}.

Je serais heureux(se) d'avoir une brève conversation — sans engagement — \
pour mieux comprendre votre situation et vous expliquer comment je pourrais \
vous apporter de la valeur.

Seriez-vous disponible pour un appel de 20 minutes dans les prochaines semaines ?

Cordialement,

{EMAIL_FOOTER_FR}
"""

EMAIL_FOLLOWUP_EN = """\
Subject: Following up — {advisor_first_name} {advisor_last_name}

Hi {prospect_first_name},

I wanted to follow up on my earlier message. I understand your time is valuable, \
so I'll keep this brief.

{followup_context}

If now isn't the right time, I'm happy to reconnect at a more convenient moment. \
You can reach me directly at {phone} or {email}.

Best regards,

{EMAIL_FOOTER_EN}
"""

EMAIL_FOLLOWUP_FR = """\
Objet : Suivi — {advisor_first_name} {advisor_last_name}

Bonjour {prospect_first_name},

Je voulais faire suite à mon message précédent. Je sais que votre temps est précieux, \
alors je serai bref(ve).

{followup_context}

Si ce n'est pas le bon moment, je suis disponible pour reprendre contact \
à votre convenance. Vous pouvez me joindre directement au {phone} ou à {email}.

Cordialement,

{EMAIL_FOOTER_FR}
"""

# ── Event follow-up templates ─────────────────────────────────────────────────

EMAIL_EVENT_FOLLOWUP_EN = """\
Subject: Great meeting you at {event_name}

Hi {prospect_first_name},

It was a pleasure meeting you at {event_name} on {event_date}. \
I enjoyed our conversation about {conversation_topic}.

{specific_followup_note}

I would welcome the opportunity to continue our discussion. \
Would you be open to a brief call in the next few weeks?

Best regards,

{EMAIL_FOOTER_EN}
"""

EMAIL_EVENT_FOLLOWUP_FR = """\
Objet : Ravi(e) de vous avoir rencontré à {event_name}

Bonjour {prospect_first_name},

C'était un plaisir de vous rencontrer lors de {event_name} le {event_date}. \
J'ai beaucoup apprécié notre conversation sur {conversation_topic}.

{specific_followup_note}

Je serais heureux(se) de poursuivre notre discussion. \
Seriez-vous ouvert(e) à un bref appel dans les prochaines semaines ?

Cordialement,

{EMAIL_FOOTER_FR}
"""

# ── LinkedIn outreach templates ───────────────────────────────────────────────

LINKEDIN_OUTREACH_EN = """\
Hi {prospect_first_name},

{connection_context}

I work with {target_profile} in the {city} area as a {title} at {firm_name}. \
I'd welcome the opportunity to connect and learn more about your financial goals.

Best,
{advisor_first_name} {advisor_last_name}
{title} | {firm_name} | AMF Reg. {amf_number}
"""

LINKEDIN_OUTREACH_FR = """\
Bonjour {prospect_first_name},

{connection_context}

Je travaille avec {target_profile} dans la région de {city} en tant que \
{title} chez {firm_name}. J'aimerais beaucoup me connecter et en savoir plus \
sur vos objectifs financiers.

Cordialement,
{advisor_first_name} {advisor_last_name}
{title} | {firm_name} | No AMF {amf_number}
"""

# ── Template registry ─────────────────────────────────────────────────────────

TEMPLATES = {
    "email_footer":          {"EN": EMAIL_FOOTER_EN,            "FR": EMAIL_FOOTER_FR},
    "initial_outreach":      {"EN": EMAIL_INITIAL_OUTREACH_EN,  "FR": EMAIL_INITIAL_OUTREACH_FR},
    "followup":              {"EN": EMAIL_FOLLOWUP_EN,           "FR": EMAIL_FOLLOWUP_FR},
    "event_followup":        {"EN": EMAIL_EVENT_FOLLOWUP_EN,     "FR": EMAIL_EVENT_FOLLOWUP_FR},
    "linkedin_outreach":     {"EN": LINKEDIN_OUTREACH_EN,        "FR": LINKEDIN_OUTREACH_FR},
}


def get_template(template_name: str, language: str = "EN") -> str:
    """Return a template string by name and language (EN or FR).

    Raises KeyError if template_name or language not found.
    """
    lang = language.upper()
    tmpl = TEMPLATES.get(template_name)
    if not tmpl:
        raise KeyError(f"Unknown template: '{template_name}'. "
                       f"Available: {list(TEMPLATES.keys())}")
    result = tmpl.get(lang)
    if result is None:
        raise KeyError(f"Language '{lang}' not available for template '{template_name}'.")
    return result
