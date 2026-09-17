"""Truebind 2.3: Lloyd's Coverholder Reporting Standards v5.2 claims
template -- sourced from the official 118-page PDF ("Coverholder
Reporting Standards User Guide Version 5.2", 20 August 2019), fetched
from assets.lloyds.com and text-extracted during this build. Every field
code, name and mandatory-status claim below traces to a specific quote
from that PDF (see LLOYDS_CLAIMS_FIELDS); nothing here is guessed.

IMPORTANT -- two things this module does NOT claim:

1. The `M`/`CM` suffixes on our internal field codes (CR0104M, CR0105CM,
   ...) are NOT part of the official Lloyd's notation -- the real
   standard uses bare codes (CR0104, CR0105, ...). The suffix is this
   project's own internal convention, invented earlier in this project
   before this real data was sourced. This module maps real bare Lloyd's
   codes to our internal suffixed codes; it never presents the suffix as
   if Lloyd's defined it.

2. The Market Business Glossary's authoritative red/yellow mandatory/
   conditional grid needs a portal account (glossary.londonmarketgroup.
   co.uk) this build didn't have. Where the PDF's prose explicitly says a
   field "must be reported", `mandatory=True` below cites that quote.
   Where it doesn't, this falls back to our own schema.py's existing
   required/optional split for that field -- flagged inline as an
   assumption to verify against the MBG later, not presented as Lloyd's
   own classification.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from .db.models import Template
from .templates import create_template

SOURCE = (
    "Lloyd's Coverholder Reporting Standards User Guide, Version 5.2, "
    "20 August 2019 (assets.lloyds.com/assets/pdf-reporting-standards-"
    "lloyds-coverholder-reporting-standards-user-guide-v52)"
)

TEMPLATE_NAME = "Lloyd's Standard v5.2"

# The real 12-value Claim Status enum (CR0105), PDF p.24. Stored as
# template metadata for reference/display -- NOT used to replace our
# internal schema's 4-value (open/closed/reopened/other) enum, which
# every other part of the pipeline (validation, dedupe, export) already
# depends on. A future pass could add a proper mapping table from these
# 12 values down to the 4; for now this is descriptive metadata only.
LLOYDS_CLAIM_STATUS_VALUES = [
    "Open", "Open - Coverage agreed", "Open - Amount agreed",
    "Open - Claim paid, fees outstanding", "Open - Fees paid, claims outstanding",
    "Open - Claim and fees paid", "Closed", "Closed this month", "Re-opened",
    "Closed but Subrogation/Recovery being pursued", "Withdrawn", "Structured Settlement",
]

# (real Lloyd's field code, real Lloyd's field name, our internal field
# code, mandatory, source note)
LLOYDS_CLAIMS_FIELDS: list[tuple[str, str, str, bool, str]] = [
    ("CR0104", "Claim Reference / Number", "CR0104M", True,
     'PDF p.23: "A unique reference must be reported for the claim (CR0104)."'),
    ("CR0105", "Claim Status", "CR0105CM", True,
     'PDF p.24: "The current status of the claim (CR0105) must be reported."'),
    ("CR0119", "Date of Loss (From)", "CR0119CM", True,
     'PDF p.24, "Key dates": "The date of the loss from... (CR0119)", listed under '
     '"the following key dates must be reported where they apply".'),
    ("CR0136", "Date Claim First Advised / Date Claim Made", "CR0136CM", True,
     'PDF p.24, "Key dates": "The date the claim was first advised... (CR0136)."'),
    ("CR0035", "Insured Full Name, Last Name or Company Name", "CR0035M", True,
     'PDF p.22-23: "Insured full name, last name or company name (CR0035)... must '
     'be reported", under "Mandatory information for all claims".'),
    ("CR0029", "Certificate Reference", "CR0029M", True,
     'PDF p.23: "Certificate reference (CR0029)", under "Mandatory information for '
     'all claims". NOTE: the real standard\'s CR0029 is "Certificate Reference", a '
     'related but distinct concept from "Policy or Group Ref" (real code CR0026) -- '
     'mapped here to our internal CR0029M ("Risk / policy reference") as the closest '
     'existing field, not an exact concept match. Flagged for review.'),
    ("CR0126", "Paid this month - Indemnity", "CR0126CM", False,
     'PDF p.24, "Indemnity and fees": "The following must be reported for each '
     'claim" heads the whole paid/reserve/incurred group, but no individual field '
     'in it (paid this month, previously paid, reserve) carries the PDF\'s crisper '
     'single-field "must be reported" phrasing -- consistent with our schema\'s '
     'existing conditional-pair treatment (at least one of paid/reserve non-null).'),
    ("CR0130", "Reserve - Indemnity", "CR0130CM", False,
     "Same section/reasoning as CR0126 above."),
    ("CR0155", "Total Incurred", "CR0155CM", False,
     'PDF p.24: "The total incurred as a result of any fees and/or claims (CR0155)" '
     '-- mentioned within the indemnity/fees section without the crisper "must be '
     'reported" phrasing used for CR0104/CR0105/CR0035/CR0029/CR0119/CR0136. Kept '
     "non-mandatory here, consistent with our schema's reconciled-not-independently-"
     'required treatment of this field.'),
    ("CR0110", "Settlement Currency", "CR0110CM", False,
     'PDF p.23: "...and where appropriate the settlement currency (CR0110)..." -- '
     "explicitly conditional (\"where appropriate\"), not unconditionally mandatory."),
]

# Real header text variants a coverholder submission might actually use
# for these fields (drawn from the PDF's own field names above), fed into
# the template's fuzzy-matching alongside the bare codes themselves.
LLOYDS_HEADER_ALIASES: dict[str, list[str]] = {
    "CR0104M": ["Claim Reference / Number", "Claim Reference", "CR0104"],
    "CR0105CM": ["Claim Status", "CR0105"],
    "CR0119CM": ["Date of Loss (From)", "Date of Loss", "CR0119"],
    "CR0136CM": ["Date Claim First Advised", "Date Claim Made", "CR0136"],
    "CR0035M": ["Insured Full Name, Last Name or Company Name", "Insured Name", "CR0035"],
    "CR0029M": ["Certificate Reference", "CR0029"],
    "CR0126CM": ["Paid this month - Indemnity", "CR0126"],
    "CR0130CM": ["Reserve - Indemnity", "CR0130"],
    "CR0155CM": ["Total Incurred", "CR0155"],
    "CR0110CM": ["Settlement Currency", "CR0110"],
}


def seed_lloyds_template(session: Session) -> Template:
    """Idempotent: returns the existing Lloyd's template if one's already
    seeded, otherwise creates it. Non-deletable (is_deletable=False), per
    the redevelopment prompt's "built-in, non-deletable" requirement."""
    existing = session.query(Template).filter(
        Template.name == TEMPLATE_NAME, Template.template_type == "STANDARD",
    ).first()
    if existing is not None:
        return existing

    field_mappings: list[tuple[str, str, bool]] = []
    for lloyds_code, lloyds_name, internal_code, mandatory, _source_note in LLOYDS_CLAIMS_FIELDS:
        for header_text in [lloyds_code, lloyds_name, *LLOYDS_HEADER_ALIASES.get(internal_code, [])]:
            field_mappings.append((header_text, internal_code, mandatory))

    return create_template(
        session,
        name=TEMPLATE_NAME,
        template_type="STANDARD",
        field_mappings=field_mappings,
        created_by="system",
        is_deletable=False,
        metadata={
            "source": SOURCE,
            "claim_status_values": LLOYDS_CLAIM_STATUS_VALUES,
            "fields": [
                {"lloyds_code": c, "lloyds_name": n, "internal_code": ic, "mandatory": m, "source_note": s}
                for c, n, ic, m, s in LLOYDS_CLAIMS_FIELDS
            ],
        },
    )
