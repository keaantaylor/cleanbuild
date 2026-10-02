"""The health report's single view: verdict, the three counts, the top fixes,
findings by who must fix them, duplicates, money and what could not be
checked. Built once when a report is processed and stored in the summary, so
the app, the PDF and every export read the same numbers.

Definitions (one per number):
- Errors: findings whose rule outcome is FAIL (red), including exact
  duplicates. Equal to the exceptions export rows with status FAIL.
- Warnings: findings whose rule outcome is REVIEW (amber): unusual values,
  values read but not in a checkable form, probable duplicates. Equal to the
  export rows with status REVIEW.
- Couldn't check: checks that could not run on some or all rows, each with its
  reason and the rows affected (export rows with status NOT_EVALUABLE), plus
  checks that could not run at all because a column was not mapped.
Money is never added across currencies.
"""

from __future__ import annotations

import re
from collections import defaultdict

import pandas as pd
from bordereaux.rules import SEVERITY_ORDER
from bordereaux.rules import rule as catalogue_rule
from openpyxl.utils import get_column_letter

VERSION = 1
TOP_FIXES = 5
EXAMPLES = 3

# Checks that need a column the sender may not have provided; when the field
# is mapped on no sheet the check cannot run at all.
_FIELD_CHECKS = (
    (("TB_INCEPTION", "TB_EXPIRY"), "policy_period", "Loss inside the policy period",
     "No policy inception or expiry column was mapped."),
    (("TB_POLICY_LIMIT",), "policy_limit", "Incurred within the policy limit", "No policy limit column was mapped."),
    (("CR0110CM",), "currency", "Currency codes", "No currency column was mapped."),
    (("CR0105CM",), "status", "Claim status", "No claim status column was mapped."),
)

_NE_LABEL = "Total incurred could not be reconciled"


def _blank(v) -> bool:
    try:
        return v is None or bool(pd.isna(v))
    except (TypeError, ValueError):
        return False


class CellLocator:
    """Turns (sheet, field, source row) into a spreadsheet cell such as F14.
    Rows are read from A1 (no column is ever skipped), so a column's letter is
    its position among the sheet's stored headers."""

    def __init__(self, headers_by_sheet: dict[str, list[str]], mapping_by_sheet: dict[str, dict[str, str]]):
        self._col: dict[tuple[str, str], tuple[str, str]] = {}
        for sheet, mapping in mapping_by_sheet.items():
            headers = [str(h) for h in headers_by_sheet.get(sheet) or []]
            for field_code, source_column in mapping.items():
                if source_column in headers:
                    self._col[(sheet, field_code)] = (get_column_letter(headers.index(source_column) + 1),
                                                       source_column)

    def locate(self, sheet: str | None, field_code: str | None, source_row) -> tuple[str | None, str | None]:
        """(cell, source column name); cell is the row reference alone
        ("row 14") when the finding concerns the whole row."""
        row = None if _blank(source_row) else int(source_row)
        hit = self._col.get((sheet or "", field_code or ""))
        if hit and row:
            return f"{hit[0]}{row}", hit[1]
        return (f"row {row}" if row else None), (hit[1] if hit else None)


def where(sheet: str | None, cell: str | None) -> str:
    if not sheet and not cell:
        return ""
    if cell and cell.startswith("row "):
        return f"{sheet!s}, {cell}" if sheet else cell
    return f"{sheet!s}!{cell}" if sheet and cell else (sheet or cell or "")


_CODE_PREFIX = re.compile(r"^[A-Z]{2}\d{4}[A-Z]*\s*\(([^)]+)\)")


def sentence(rule_code: str, detail: str) -> str:
    """One plain-English sentence: the check, then what was found (field
    codes such as CR0104M are replaced by the field's name)."""
    r = catalogue_rule(rule_code)
    d = _CODE_PREFIX.sub(lambda m: m.group(1), (detail or "").strip()).rstrip(".")
    if not d:
        return f"{r.label}."
    if len(d) > 1 and d[0].isupper() and d[1].islower():
        d = d[0].lower() + d[1:]
    return f"{r.label}: {d}."


def _money_cols(canonical: pd.DataFrame):
    n = len(canonical)
    ccy = canonical["CR0110CM"].tolist() if "CR0110CM" in canonical.columns else [None] * n
    inc = canonical["CR0155CM"].tolist() if "CR0155CM" in canonical.columns else [None] * n
    return ccy, inc


def build(result, canonical: pd.DataFrame, summary: dict, locator: CellLocator,
          partly_mapped: list[dict] | None = None) -> dict:
    canonical = canonical.reset_index(drop=True)
    sheets = canonical["_source_sheet"].tolist() if "_source_sheet" in canonical.columns else []
    src_rows = canonical["_source_row"].tolist() if "_source_row" in canonical.columns else []
    refs = canonical["CR0104M"].tolist() if "CR0104M" in canonical.columns else []
    ccy, inc = _money_cols(canonical)

    groups: dict[str, dict] = {}

    def add(rule_code: str, pos: int, detail: str, field_code: str | None):
        g = groups.setdefault(rule_code, {"rows": set(), "count": 0, "money": defaultdict(float), "examples": []})
        g["count"] += 1
        if pos not in g["rows"]:
            g["rows"].add(pos)
            amount = inc[pos] if pos < len(inc) else None
            if not _blank(amount):
                g["money"][("UNKNOWN" if _blank(ccy[pos]) or not str(ccy[pos]).strip() else str(ccy[pos]))] += abs(float(amount))
        if len(g["examples"]) < EXAMPLES:
            sheet = sheets[pos] if pos < len(sheets) else None
            cell, column = locator.locate(sheet, field_code, src_rows[pos] if pos < len(src_rows) else None)
            ref = refs[pos] if pos < len(refs) else None
            g["examples"].append({"sheet": sheet, "cell": cell, "column": column,
                                  "claim_ref": None if _blank(ref) else str(ref),
                                  "where": where(sheet, cell), "sentence": sentence(rule_code, detail)})

    exc = result.validation_result.exceptions
    fields = exc["field_code"].tolist() if "field_code" in exc.columns else [None] * len(exc)
    for pos, rule_code, detail, field in zip(exc["row_index"].tolist(), exc["rule"].tolist(),
                                             exc["detail"].tolist(), fields):
        add(rule_code, int(pos), detail, field)
    dups = result.duplicates
    for a, mt, detail in zip(dups["row_index_a"].tolist(), dups["match_type"].tolist(), dups["detail"].tolist()):
        add(mt, int(a), detail, "CR0104M")

    rules_out = []
    for code, g in groups.items():
        r = catalogue_rule(code)
        rules_out.append({
            "rule": code, "label": r.label, "severity": r.severity, "outcome": r.outcome, "owner": r.owner,
            "check_type": r.check_type, "fix": r.fix, "findings": g["count"], "rows": len(g["rows"]),
            "money_at_risk": [{"currency": c, "amount": round(v, 2)} for c, v in sorted(g["money"].items(),
                                                                                    key=lambda kv: -kv[1])],
            "examples": g["examples"],
        })

    def rank(x):
        top_money = max((m["amount"] for m in x["money_at_risk"]), default=0.0)
        return (0 if x["outcome"] == "FAIL" else 1, SEVERITY_ORDER.get(x["severity"], 9), -top_money, -x["findings"])

    rules_out.sort(key=rank)
    errors = sum(x["findings"] for x in rules_out if x["outcome"] == "FAIL")
    warnings = sum(x["findings"] for x in rules_out if x["outcome"] == "REVIEW")
    error_rows = len(set().union(*[groups[x["rule"]]["rows"] for x in rules_out if x["outcome"] == "FAIL"]))

    couldnt = _couldnt_check(result, summary) + [
        {"key": f"sheet:{m['sheet_name']}", "label": f"Sheet “{m['sheet_name']}”", "reason": m["message"],
         "rows": None, "fix": "mapping"} for m in partly_mapped or []]
    verdict = "fix" if errors else "ready"
    return {
        "version": VERSION,
        "verdict": verdict,
        "verdict_label": "Fix before submitting" if errors else "Ready to submit",
        "verdict_reason": (
            f"{errors:,} error{'s' if errors != 1 else ''} on {error_rows:,} row{'s' if error_rows != 1 else ''} "
            "must be fixed before this file is sent." if errors else
            "No errors were found." + (f" {len(couldnt)} check{'s' if len(couldnt) != 1 else ''} could not run; "
                                       "see Couldn't check." if couldnt else "")),
        "counts": {"errors": errors, "error_rows": error_rows, "warnings": warnings, "couldnt_check": len(couldnt),
                   "couldnt_check_rows": sum(c.get("rows") or 0 for c in couldnt)},
        "top_fixes": rules_out[:TOP_FIXES],
        "rules": rules_out,
        "by_owner": {"sender": [x["rule"] for x in rules_out if x["owner"] == "sender"],
                     "us": [x["rule"] for x in rules_out if x["owner"] == "us"]},
        "couldnt_check": couldnt,
        "duplicates": {
            "exact_pairs": int(summary.get("exact_duplicates") or 0),
            "probable_pairs": summary.get("probable_duplicates"),
            "probable_high_confidence": int(sum(
                1 for mt, c in zip(dups["match_type"].tolist(),
                                   dups["confidence"].tolist() if "confidence" in dups.columns else [None] * len(dups))
                if mt == "probable_duplicate" and not _blank(c) and c >= 80)),
            "repeat_period_unknown": int(summary.get("period_unknown_repeats") or 0),
            "development_pairs": int(summary.get("development_pairs") or 0),
        },
        "money_by_currency": summary.get("totals_by_currency") or [],
    }


def _couldnt_check(result, summary: dict) -> list[dict]:
    out: list[dict] = []
    ne = result.validation_result.not_evaluable_detail
    if not ne.empty:
        for reason, grp in ne.groupby("reason", sort=False):
            mapping = reason.endswith("_unmapped") or reason in ("fees_partially_mapped",)
            out.append({"key": f"arithmetic:{reason}", "label": _NE_LABEL, "reason": str(grp["detail"].iloc[0]),
                        "rows": len(grp), "fix": "mapping" if mapping else "data"})
    for c in summary.get("not_assessed_checks") or []:
        out.append({"key": f"check:{c['check']}", "label": c["label"], "reason": c["reason"], "rows": None,
                    "fix": "mapping"})
    never = {f["field_code"] for f in summary.get("field_completeness") or [] if f.get("never_mapped")}
    for codes, key, label, why in _FIELD_CHECKS:
        if all(c in never for c in codes):
            out.append({"key": f"field:{key}", "label": label, "reason": why + " This check did not run.",
                        "rows": None, "fix": "mapping"})
    for s in summary.get("unmapped_sheets") or []:
        out.append({"key": f"sheet:{s['sheet_name']}", "label": f"Sheet “{s['sheet_name']}”",
                    "reason": s["reason"], "rows": None, "fix": "mapping"})
    return out
