"""Canonical V0 skeleton schema for claims bordereaux.

Field codes match the Lloyd's Coverholder Reporting Standard v5.2 claims
questionnaire, per the build brief Section 3. This module is the single
source of truth for field identity used by every later phase (validation,
mapping, dedupe, reporting).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class FieldSpec:
    code: str
    name: str
    dtype: str  # "string" | "enum" | "date" | "decimal" | "currency"
    required: bool
    notes: str
    enum_values: tuple[str, ...] = ()
    # Known header aliases (lowercased, punctuation-insensitive) seen across
    # real-world bordereaux. Used by the Phase 3 fuzzy-matching pass.
    aliases: tuple[str, ...] = field(default_factory=tuple)


FIELDS: list[FieldSpec] = [
    FieldSpec(
        code="CR0104M",
        name="Claim reference",
        dtype="string",
        required=True,
        notes="Unique per claim. Primary key for de-duplication.",
        aliases=(
            "claim ref", "claim reference", "claim no", "claim number",
            "claim id", "claimref", "claimreference", "claim no.",
            "case id", "case ref", "case reference", "claims reference",
        ),
    ),
    FieldSpec(
        code="CR0105CM",
        name="Claim status",
        dtype="enum",
        required=True,
        notes="Drives the segregate-by-status view.",
        enum_values=("open", "closed", "reopened", "other"),
        aliases=(
            "claim status", "status", "claimstatus", "case status",
            "case state",
        ),
    ),
    FieldSpec(
        code="CR0119CM",
        name="Date of loss",
        dtype="date",
        required=True,
        notes="When the loss occurred.",
        aliases=(
            "date of loss", "loss date", "lossdate", "dol",
            "incident date", "date of incident",
        ),
    ),
    FieldSpec(
        code="CR0136CM",
        name="Date first notified",
        dtype="date",
        required=True,
        notes='Also called "date first advised". Must be >= date of loss.',
        aliases=(
            "date first notified", "date notified", "notification date",
            "first notified date", "date first advised", "notified date",
            "reported on", "date reported",
        ),
    ),
    FieldSpec(
        code="CR0035M",
        name="Insured name",
        dtype="string",
        required=True,
        notes="Individual or company name.",
        aliases=(
            "insured", "insured name", "insuredname", "client",
            "client name", "policyholder", "policyholder name",
        ),
    ),
    FieldSpec(
        code="CR0029M",
        name="Risk / policy reference",
        dtype="string",
        required=True,
        notes="Links claim to the underlying policy.",
        aliases=(
            "policy ref", "policy reference", "policy no", "policy number",
            "risk reference", "riskreference", "policyref", "policynumber",
            "contract ref", "contract reference",
        ),
    ),
    FieldSpec(
        code="CR0126CM",
        name="Indemnity paid (this period)",
        dtype="decimal",
        required=False,
        notes="Amount paid this reporting period, in settlement currency. "
              "Required if reserve is null.",
        aliases=(
            "paid", "amount paid", "indemnity paid", "indemnitypaid",
            "paid this period", "cash paid ytd", "paid ytd",
        ),
    ),
    FieldSpec(
        code="CR0130CM",
        name="Indemnity reserve (outstanding)",
        dtype="decimal",
        required=False,
        notes="Amount still expected to be paid. Required if paid is null.",
        aliases=(
            "reserve", "o/s reserve", "outstanding reserve",
            "indemnity reserve", "indemnityreserve", "case reserve",
            "reserve outstanding",
        ),
    ),
    FieldSpec(
        code="CR0155CM",
        name="Total incurred",
        dtype="decimal",
        required=True,
        notes="Should equal paid + reserve within tolerance.",
        aliases=(
            "incurred", "total incurred", "totalincurred",
            "gross incurred", "incurred total",
        ),
    ),
    FieldSpec(
        code="CR0110CM",
        name="Settlement currency",
        dtype="currency",
        required=True,
        notes="ISO 4217 code.",
        aliases=(
            "currency", "ccy", "settlement currency", "currency code",
            "settlementcurrency",
        ),
    ),
]

FIELDS_BY_CODE: dict[str, FieldSpec] = {f.code: f for f in FIELDS}

REQUIRED_CODES = [f.code for f in FIELDS if f.required]
# Paid/reserve are "conditionally required": at least one of the two must
# be present per row (enforced in validation.py, not per-column here).
PAID_CODE = "CR0126CM"
RESERVE_CODE = "CR0130CM"
INCURRED_CODE = "CR0155CM"
LOSS_DATE_CODE = "CR0119CM"
NOTIFIED_DATE_CODE = "CR0136CM"
CLAIM_REF_CODE = "CR0104M"
CURRENCY_CODE = "CR0110CM"
STATUS_CODE = "CR0105CM"
INSURED_NAME_CODE = "CR0035M"

ARITHMETIC_TOLERANCE = 0.01
