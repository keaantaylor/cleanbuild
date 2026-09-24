"""Canonical V0 skeleton schema for claims bordereaux.

Field codes match the Lloyd's Coverholder Reporting Standard v5.2 claims
questionnaire, per the build brief Section 3. This module is the single
source of truth for field identity used by every later phase (validation,
mapping, dedupe, reporting) -- including field-requiredness (fix spec
3.6), which lives here as one `requirement` tag per field rather than
being hardcoded separately in the report or validation layers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Requirement = Literal["required", "optional", "conditional_pair", "reconciled"]


@dataclass(frozen=True)
class FieldSpec:
    code: str
    name: str
    dtype: str  # "string" | "enum" | "date" | "decimal" | "currency"
    requirement: Requirement
    notes: str
    enum_values: tuple[str, ...] = ()
    # Known header aliases (lowercased, punctuation-insensitive) seen across
    # real-world bordereaux. Used by the fuzzy-matching mapping pass.
    aliases: tuple[str, ...] = field(default_factory=tuple)
    # Aliases that bind to this field but leave its meaning ambiguous (e.g. a
    # bare "Paid" could be cumulative or this-period). A match through one of
    # these is proposed for REVIEW, never as a high-confidence mapping.
    ambiguous_aliases: tuple[str, ...] = field(default_factory=tuple)

    @property
    def required(self) -> bool:
        return self.requirement == "required"


FIELDS: list[FieldSpec] = [
    FieldSpec(
        code="CR0104M",
        name="Claim reference",
        dtype="string",
        requirement="required",
        notes="Unique per claim. Primary key for de-duplication. Unconditionally required.",
        aliases=(
            "claim ref", "claim reference", "claim no", "claim number",
            "claim id", "claimref", "claimreference", "claim no.",
            "case id", "case ref", "case reference", "claims reference",
            "reference", "claim reference no", "claim reference number",
        ),
    ),
    FieldSpec(
        code="CR0105CM",
        name="Claim status",
        dtype="enum",
        requirement="optional",
        notes="Drives the segregate-by-status view. Validated when present, not mandatory.",
        enum_values=("open", "closed", "reopened", "other"),
        aliases=(
            "claim status", "status", "claimstatus", "case status",
            "case state", "state", "claim state", "current status",
            "status code",
        ),
    ),
    FieldSpec(
        code="CR0119CM",
        name="Date of loss",
        dtype="date",
        requirement="optional",
        notes="When the loss occurred. Validated (date order/sanity) when present, not mandatory.",
        aliases=(
            "date of loss", "loss date", "lossdate", "dol",
            "incident date", "date of incident", "date loss occurred",
        ),
    ),
    FieldSpec(
        code="CR0136CM",
        name="Date first notified",
        dtype="date",
        requirement="optional",
        notes='Also called "date first advised". Must be >= date of loss when both present.',
        aliases=(
            "date first notified", "date notified", "notification date",
            "first notified date", "date first advised", "notified date",
            "reported on", "date reported", "advised date", "first notified",
            "date claim notified",
        ),
    ),
    FieldSpec(
        code="CR0035M",
        name="Insured name",
        dtype="string",
        requirement="required",
        notes="Individual or company name. Unconditionally required.",
        aliases=(
            "insured", "insured name", "insuredname", "client",
            "client name", "policyholder", "policyholder name",
            "name of insured", "insured party",
        ),
    ),
    FieldSpec(
        code="CR0029M",
        name="Risk / policy reference",
        dtype="string",
        requirement="optional",
        notes="Links claim to the underlying policy. Not independently mandatory.",
        aliases=(
            "policy ref", "policy reference", "policy no", "policy number",
            "risk reference", "riskreference", "policyref", "policynumber",
            "contract ref", "contract reference", "contract no",
            "policy reference no", "policy identifier",
        ),
    ),
    # --- Monetary fields, per Lloyd's Coverholder Reporting Standards v5.2
    # (User Guide, 20 Aug 2019). CR0155 "Total Incurred" is defined there as
    # the sum of paid-this-month, previously-paid and reserve, for indemnity
    # AND fees. Earlier versions of this schema treated CR0126 (which v5.2
    # defines as *this month's* paid) as cumulative paid and omitted
    # previously-paid and fees entirely, so any genuine v5.2 file with prior
    # payments produced false arithmetic mismatches. See
    # AI/RESEARCH/TRUEBIND_PRODUCT_REVALIDATION.md section 3.2.
    FieldSpec(
        code="TB_PAID_TD",
        name="Indemnity paid to date (cumulative)",
        dtype="decimal",
        requirement="conditional_pair",
        notes="NOT a v5.2 field: the cumulative indemnity paid many senders report in one "
              "column. Equivalent to v5.2 CR0126 + CR0128. Conditional pair with reserve.",
        aliases=(
            "paid to date", "paid ytd", "cash paid ytd", "amount paid to date",
            "paid todate", "indemnity paid to date", "total paid", "cumulative paid",
            "paid", "amount paid", "paid amount", "paid amt", "indemnity paid", "indemnitypaid",
        ),
        ambiguous_aliases=("paid", "amount paid", "paid amount", "paid amt", "indemnity paid", "indemnitypaid"),
    ),
    FieldSpec(
        code="CR0126CM",
        name="Paid this month - indemnity",
        dtype="decimal",
        requirement="optional",
        notes="v5.2 CR0126: indemnity paid in THIS reporting period only.",
        aliases=(
            "paid this month", "paid this period", "paid in period", "paid in month",
            "paid this month indemnity", "indemnity paid this month", "period paid", "movement paid",
        ),
    ),
    FieldSpec(
        code="CR0128CM",
        name="Previously paid - indemnity",
        dtype="decimal",
        requirement="optional",
        notes="v5.2 CR0128: indemnity paid in prior periods.",
        aliases=("previously paid", "previously paid indemnity", "paid previously", "prior paid", "paid prior"),
    ),
    FieldSpec(
        code="CR0130CM",
        name="Indemnity reserve (outstanding)",
        dtype="decimal",
        requirement="conditional_pair",
        notes="v5.2 CR0130. Conditional pair with paid: a row is flagged only if no paid component "
              "and no reserve is present.",
        aliases=(
            "reserve", "o/s reserve", "outstanding reserve",
            "indemnity reserve", "indemnityreserve", "case reserve",
            "reserve outstanding", "reserve amount", "reserve o/s",
            "indemnity o/s", "outstanding",
        ),
    ),
    FieldSpec(
        code="CR0127CM",
        name="Paid this month - fees",
        dtype="decimal",
        requirement="optional",
        notes="v5.2 CR0127.",
        aliases=("fees paid this month", "paid this month fees", "fees paid this period"),
    ),
    FieldSpec(
        code="CR0129CM",
        name="Previously paid - fees",
        dtype="decimal",
        requirement="optional",
        notes="v5.2 CR0129.",
        aliases=("previously paid fees", "fees previously paid", "prior fees paid"),
    ),
    FieldSpec(
        code="CR0131CM",
        name="Reserve - fees",
        dtype="decimal",
        requirement="optional",
        notes="v5.2 CR0131.",
        aliases=("reserve fees", "fees reserve", "fee reserve", "expense reserve"),
    ),
    FieldSpec(
        code="CR0134CM",
        name="Total incurred - indemnity",
        dtype="decimal",
        requirement="reconciled",
        notes="v5.2 CR0134: indemnity paid (this month + previously) + indemnity reserve.",
        aliases=("total incurred indemnity", "incurred indemnity", "indemnity incurred"),
    ),
    FieldSpec(
        code="CR0155CM",
        name="Total incurred",
        dtype="decimal",
        requirement="reconciled",
        notes="v5.2 CR0155: paid this month + previously paid + reserve, for indemnity AND fees. "
              "Checked via validation.py's three-outcome arithmetic (MATCH / MISMATCH / NOT_EVALUABLE).",
        aliases=(
            "incurred", "total incurred", "totalincurred",
            "gross incurred", "incurred total", "incurred amount",
            "incurred to date", "total incurred amount",
        ),
    ),
    FieldSpec(
        code="TB_PERIOD",
        name="Reporting period",
        dtype="string",
        requirement="optional",
        notes="NOT a v5.2 field: the bordereau period (e.g. 2024-03) a row belongs to. Distinct from "
              "date of loss / notification. Never inferred when absent.",
        aliases=("reporting period", "bordereau period", "bordereau month", "report period",
                 "reporting month", "period"),
    ),
    FieldSpec(
        code="CR0110CM",
        name="Settlement currency",
        dtype="currency",
        requirement="optional",
        notes="ISO 4217 code. Validated when present, not mandatory.",
        aliases=(
            "currency", "ccy", "settlement currency", "currency code",
            "settlementcurrency", "ccy code", "settlement ccy",
        ),
    ),
]

FIELDS_BY_CODE: dict[str, FieldSpec] = {f.code: f for f in FIELDS}

REQUIRED_CODES = [f.code for f in FIELDS if f.requirement == "required"]
CONDITIONAL_PAIR_CODES = tuple(f.code for f in FIELDS if f.requirement == "conditional_pair")
MONETARY_CODES = tuple(f.code for f in FIELDS if f.dtype == "decimal")
RECONCILED_CODES = tuple(f.code for f in FIELDS if f.requirement == "reconciled")

POLICY_REF_CODE = "CR0029M"
PAID_TD_CODE = "TB_PAID_TD"
PAID_CODE = PAID_TD_CODE  # legacy name: the cumulative paid figure used for completeness/pair checks
PAID_MONTH_CODE = "CR0126CM"
PREV_PAID_CODE = "CR0128CM"
RESERVE_CODE = "CR0130CM"
FEES_PAID_MONTH_CODE = "CR0127CM"
FEES_PREV_PAID_CODE = "CR0129CM"
FEES_RESERVE_CODE = "CR0131CM"
FEE_CODES = (FEES_PAID_MONTH_CODE, FEES_PREV_PAID_CODE, FEES_RESERVE_CODE)
INCURRED_IND_CODE = "CR0134CM"
INCURRED_CODE = "CR0155CM"
PERIOD_CODE = "TB_PERIOD"
PAID_COMPONENT_CODES = (PAID_TD_CODE, PAID_MONTH_CODE, PREV_PAID_CODE)
LOSS_DATE_CODE = "CR0119CM"
NOTIFIED_DATE_CODE = "CR0136CM"
CLAIM_REF_CODE = "CR0104M"
CURRENCY_CODE = "CR0110CM"
STATUS_CODE = "CR0105CM"
INSURED_NAME_CODE = "CR0035M"
POLICY_REF_CODE = "CR0029M"

ARITHMETIC_TOLERANCE = 0.01

# Provenance column stamped onto every canonical row by ingest.apply_mapping:
# which workbook sheet (or file, for a single-sheet source) it came from.
# Not a Section 3 field -- used to look up per-sheet mapping state (fix
# spec 3.3) so a field left UNMAPPED on one sheet never gets silently
# treated as "mapped, but blank" once rows from many sheets are combined.
SOURCE_SHEET_CODE = "_source_sheet"
