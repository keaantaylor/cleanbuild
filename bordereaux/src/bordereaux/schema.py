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
    FieldSpec(
        code="CR0126CM",
        name="Indemnity paid (this period)",
        dtype="decimal",
        requirement="conditional_pair",
        notes="Amount paid this reporting period, in settlement currency. "
              "Conditional pair with reserve: a row is flagged only if BOTH are null.",
        aliases=(
            "paid", "amount paid", "indemnity paid", "indemnitypaid",
            "paid this period", "cash paid ytd", "paid ytd", "paid to date",
            "paid amount", "amount paid to date", "paid amt",
        ),
    ),
    FieldSpec(
        code="CR0130CM",
        name="Indemnity reserve (outstanding)",
        dtype="decimal",
        requirement="conditional_pair",
        notes="Amount still expected to be paid. "
              "Conditional pair with paid: a row is flagged only if BOTH are null.",
        aliases=(
            "reserve", "o/s reserve", "outstanding reserve",
            "indemnity reserve", "indemnityreserve", "case reserve",
            "reserve outstanding", "reserve amount", "reserve o/s",
            "indemnity o/s",
        ),
    ),
    FieldSpec(
        code="CR0155CM",
        name="Total incurred",
        dtype="decimal",
        requirement="reconciled",
        notes="Checked via reconciliation (paid + reserve == incurred), not an "
              "independent non-null requirement -- see validation.py's three-outcome "
              "arithmetic check (MATCH / MISMATCH / NOT_EVALUABLE).",
        aliases=(
            "incurred", "total incurred", "totalincurred",
            "gross incurred", "incurred total", "incurred amount",
            "incurred to date", "total incurred amount",
        ),
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
RECONCILED_CODES = tuple(f.code for f in FIELDS if f.requirement == "reconciled")

POLICY_REF_CODE = "CR0029M"
PAID_CODE = "CR0126CM"
RESERVE_CODE = "CR0130CM"
INCURRED_CODE = "CR0155CM"
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
