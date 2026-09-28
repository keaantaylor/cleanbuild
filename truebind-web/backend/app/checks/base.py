"""Shared contract for check modules.

A module is a pure function `run(inp: CheckInput) -> ModuleResult`. It sees
the processed claim rows (exact Decimals, parsed dates), which fields each
sheet actually mapped, and the sheet read notes. It never touches the
database, so the same code runs in the API, the worker and the golden
tests.

Rules for every module:
- a rule whose inputs are not mapped on a sheet reports that sheet's rows as
  NOT_ASSESSED with the reason -- never as passed;
- a finding is FAIL (a breach the data proves) or REVIEW (a person must
  decide, e.g. an ambiguous date or a possible sanctions match);
- every finding explains itself in plain English and points at the sheet,
  the 1-based source row and the field;
- amounts are Decimal with an ISO 4217 currency, or no currency when the
  row did not state a valid one (said so in the explanation).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

# Active ISO 4217 alphabetic codes (funds and precious-metal codes excluded).
ISO_4217 = frozenset(
    """
AED AFN ALL AMD ANG AOA ARS AUD AWG AZN BAM BBD BDT BGN BHD BIF BMD BND BOB BRL BSD BTN BWP BYN BZD CAD CDF
CHF CLP CNY COP CRC CUP CVE CZK DJF DKK DOP DZD EGP ERN ETB EUR FJD FKP GBP GEL GHS GIP GMD GNF GTQ GYD HKD
HNL HTG HUF IDR ILS INR IQD IRR ISK JMD JOD JPY KES KGS KHR KMF KPW KRW KWD KYD KZT LAK LBP LKR LRD LSL LYD
MAD MDL MGA MKD MMK MNT MOP MRU MUR MVR MWK MXN MYR MZN NAD NGN NIO NOK NPR NZD OMR PAB PEN PGK PHP PKR PLN
PYG QAR RON RSD RUB RWF SAR SBD SCR SDG SEK SGD SHP SLE SOS SRD SSP STN SVC SYP SZL THB TJS TMT TND TOP TRY
TTD TWD TZS UAH UGX USD UYU UZS VES VND VUV WST XAF XCD XOF XPF YER ZAR ZMW ZWG
""".split()  # noqa: SIM905 -- a word list reads better than 160 quoted strings
)

_SYMBOLS = {"£": "GBP", "€": "EUR", "STERLING": "GBP", "EURO": "EUR", "EUROS": "EUR"}


def iso_currency(value: str | None) -> str | None:
    """The ISO 4217 code a cell states, or None. '$' is ambiguous (USD, CAD,
    AUD, ...) and is never guessed."""
    if not value:
        return None
    v = value.strip().upper()
    v = _SYMBOLS.get(v, v)
    return v if v in ISO_4217 else None


@dataclass(frozen=True)
class RowView:
    claim_row_id: str
    sheet_name: str
    row_number: int | None
    claim_reference: str | None = None
    insured_name: str | None = None
    claim_status: str | None = None
    date_of_loss: date | None = None
    date_notified: date | None = None
    reporting_period: str | None = None
    paid_amount: Decimal | None = None
    paid_this_month: Decimal | None = None
    reserve_amount: Decimal | None = None
    fees_paid_to_date: Decimal | None = None
    incurred_amount: Decimal | None = None
    currency: str | None = None


@dataclass(frozen=True)
class SheetView:
    name: str
    mapped: dict[str, str]  # field_code -> source column
    ambiguous_date_columns: frozenset[str] = frozenset()

    def missing(self, codes: tuple[str, ...]) -> list[str]:
        return [c for c in codes if c not in self.mapped]


@dataclass
class CheckInput:
    report_id: str
    sheets: dict[str, SheetView]
    rows: list[RowView]
    config: dict[str, Any] = field(default_factory=dict)
    # Optional services a module may use (FX conversion, sanctions entries).
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class FindingDraft:
    rule_code: str
    status: str
    severity: str
    title: str
    explanation: str
    sheet_name: str | None = None
    row_number: int | None = None
    field_code: str | None = None
    source_column: str | None = None
    claim_row_id: str | None = None
    claim_reference: str | None = None
    amount: Decimal | None = None
    currency: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)

    def fingerprint(self, module: str) -> str:
        """Stable identity across re-runs, so a person's disposition carries over."""
        key = "|".join(
            str(x)
            for x in (
                module,
                self.rule_code,
                self.sheet_name,
                self.row_number,
                self.field_code,
                self.claim_reference,
                self.amount,
                self.currency,
            )
        )
        return hashlib.sha256(key.encode()).hexdigest()


@dataclass
class RuleCoverage:
    code: str
    label: str
    assessed: int = 0
    not_assessed: int = 0
    reasons: list[str] = field(default_factory=list)

    def skip(self, n: int, reason: str) -> None:
        self.not_assessed += n
        if reason not in self.reasons:
            self.reasons.append(reason)

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "label": self.label,
            "assessed": self.assessed,
            "not_assessed": self.not_assessed,
            "reasons": self.reasons,
        }


@dataclass
class ModuleResult:
    state: str  # ASSESSED | PARTIAL | NOT_ASSESSED
    reason: str | None
    rules: list[RuleCoverage]
    findings: list[FindingDraft]
    config: dict[str, Any] | None = None


def not_assessed(reason: str, rules: list[RuleCoverage], config: dict[str, Any] | None = None) -> ModuleResult:
    return ModuleResult("NOT_ASSESSED", reason, rules, [], config)


def finish(rules: list[RuleCoverage], findings: list[FindingDraft], config: dict[str, Any] | None) -> ModuleResult:
    assessed = sum(r.assessed for r in rules)
    skipped = sum(r.not_assessed for r in rules)
    if assessed == 0:
        reasons = "; ".join(dict.fromkeys(x for r in rules for x in r.reasons)) or "no rows to assess"
        return ModuleResult("NOT_ASSESSED", reasons, rules, [], config)
    state = "PARTIAL" if skipped else "ASSESSED"
    reason = None
    if skipped:
        reason = "; ".join(dict.fromkeys(x for r in rules for x in r.reasons))
    findings.sort(key=lambda f: (f.sheet_name or "", f.row_number or 0, f.rule_code))
    return ModuleResult(state, reason, rules, findings, config)


def money(value: Decimal | None, ccy: str | None) -> str:
    if value is None:
        return "an unknown amount"
    text = f"{value:,.2f}"
    return f"{ccy} {text}" if ccy else f"{text} (currency not stated)"


def field_label(code: str) -> str:
    from bordereaux.schema import FIELDS

    return next((f.name for f in FIELDS if f.code == code), code)


_WS = re.compile(r"\s+")


def norm_ref(value: str | None) -> str:
    return _WS.sub("", (value or "").upper())
