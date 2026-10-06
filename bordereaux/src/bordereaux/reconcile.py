"""Deterministic reconciliation across rows, sheets and submissions.

No AI: every rule here is plain arithmetic or exact matching, versioned in the
rule catalogue (rules.py), and every finding carries the numbers it compared
and the source cells they came from.

  totals_mismatch       a total/subtotal line in the sheet disagrees with the
                        sum of the claim rows it covers
  cross_sheet_conflict  the same claim and reporting period appears on two
                        sheets with different amounts
  paid_decreased        paid to date is lower than in the previous submission
  rollforward_break     "previously paid" does not equal last submission's
                        paid to date

Findings use validation.EXCEPTION_COLUMNS plus `at_row`: the 1-based source
row the cell lives on when it is not the claim row itself (a total line).
"""

from __future__ import annotations

import re

import pandas as pd

from . import schema as S
from .dedupe import row_periods

# A total of n rounded amounts can be off by up to half a cent per row.
TOTALS_TOLERANCE_PER_ROW = 0.005
AMOUNT_CODES = (S.PAID_TD_CODE, S.PAID_MONTH_CODE, S.RESERVE_CODE, S.INCURRED_CODE)
COLUMNS = ["row_index", "claim_ref", "rule", "detail", "field_code", "expected", "actual", "at_row"]

_NUM = re.compile(r"^\(?-?[\d,]*\.?\d+\)?-?$")


def parse_amount(text: object) -> float | None:
    """A number written in a cell: '1,234.50', '(1,234.50)', '1234.5-', '€ 12'.
    None when it is not a plain number (never guessed)."""
    if text is None:
        return None
    if isinstance(text, (int, float)) and not isinstance(text, bool):
        return None if pd.isna(text) else float(text)
    s = re.sub(r"[\s€£$¥]|[A-Z]{3}", "", str(text).strip())
    if not s or not _NUM.match(s):
        return None
    neg = s.startswith("(") and s.endswith(")") or s.endswith("-") or s.startswith("-")
    v = float(s.strip("()-").replace(",", ""))
    return -v if neg else v


def _num(df: pd.DataFrame, code: str) -> pd.Series:
    if code not in df.columns:
        return pd.Series(float("nan"), index=df.index)
    return pd.to_numeric(df[code], errors="coerce")


def _fmt(v: float) -> str:
    return f"{v:,.2f}"


def _label(code: str) -> str:
    f = S.FIELDS_BY_CODE.get(code)
    return f.name if f else code


def _frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=COLUMNS)


def totals_vs_detail(canonical: pd.DataFrame, excluded_rows: list,
                     confirmed_mappings: dict[str, dict[str, str]]) -> pd.DataFrame:
    """Each total line excluded from a sheet (reason "subtotal") against the
    claim rows above it: its own section (since the previous total line) or
    everything above it (a grand total). Passes if either agrees."""
    out: list[dict] = []
    if canonical.empty or S.SOURCE_SHEET_CODE not in canonical.columns or "_source_row" not in canonical.columns:
        return _frame(out)
    for sheet, mapping in confirmed_mappings.items():
        totals = sorted((er for er in excluded_rows if er.sheet_name == sheet and er.reason == "subtotal"),
                        key=lambda er: er.row_number)
        if not totals:
            continue
        col_for = {code: col for col, code in mapping.items() if code}
        part = canonical[canonical[S.SOURCE_SHEET_CODE] == sheet]
        src = pd.to_numeric(part["_source_row"], errors="coerce")
        if S.CURRENCY_CODE in part.columns and part[S.CURRENCY_CODE].dropna().nunique() > 1:
            continue  # a single total across currencies has no meaning
        prev_row = 0
        for er in totals:
            above = part[src < er.row_number]
            section = part[(src > prev_row) & (src < er.row_number)]
            prev_row = er.row_number
            if section.empty or above.empty:
                continue
            for code in AMOUNT_CODES:
                col = col_for.get(code)
                stated = parse_amount(er.values.get(col)) if col else None
                if stated is None:
                    continue
                sec_sum, all_sum = float(_num(section, code).sum()), float(_num(above, code).sum())
                tol_sec = max(S.ARITHMETIC_TOLERANCE, TOTALS_TOLERANCE_PER_ROW * len(section))
                tol_all = max(S.ARITHMETIC_TOLERANCE, TOTALS_TOLERANCE_PER_ROW * len(above))
                if abs(stated - sec_sum) <= tol_sec or abs(stated - all_sum) <= tol_all:
                    continue
                last = section.index[-1]
                out.append({
                    "row_index": int(last), "claim_ref": None, "rule": "totals_mismatch", "field_code": code,
                    "expected": round(sec_sum, 2), "actual": stated, "at_row": int(er.row_number),
                    "detail": (f"Total line on row {er.row_number} shows {_fmt(stated)} for {_label(code)}; the "
                               f"{len(section)} claim rows above it (rows {int(src[section.index].min())}-"
                               f"{int(src[section.index].max())}) add up to {_fmt(sec_sum)}, difference "
                               f"{_fmt(stated - sec_sum)}"),
                })
    return _frame(out)


def cross_sheet_conflicts(canonical: pd.DataFrame) -> pd.DataFrame:
    """The same claim reference in the same known reporting period on two
    sheets, with a different amount. Each later occurrence is compared with
    the first; the finding sits on the later row's differing cell."""
    out: list[dict] = []
    need = {S.CLAIM_REF_CODE, S.SOURCE_SHEET_CODE}
    if canonical.empty or not need <= set(canonical.columns):
        return _frame(out)
    ref = canonical[S.CLAIM_REF_CODE].astype("string").str.strip().str.upper()
    period = row_periods(canonical)
    keyed = canonical[ref.notna() & (ref != "") & period.notna()]
    if keyed.empty:
        return _frame(out)
    nums = {c: _num(canonical, c) for c in (S.PAID_TD_CODE, S.RESERVE_CODE, S.INCURRED_CODE)}
    for (r, p), grp in keyed.groupby([ref[keyed.index], period[keyed.index]], sort=False):
        if grp[S.SOURCE_SHEET_CODE].nunique() < 2:
            continue
        first = grp.index[0]
        first_sheet = grp.at[first, S.SOURCE_SHEET_CODE]
        for idx in grp.index[1:]:
            if grp.at[idx, S.SOURCE_SHEET_CODE] == first_sheet:
                continue
            for code, ser in nums.items():
                a, b = ser[first], ser[idx]
                if pd.isna(a) or pd.isna(b) or abs(a - b) <= S.ARITHMETIC_TOLERANCE:
                    continue
                out.append({
                    "row_index": int(idx), "claim_ref": canonical.at[idx, S.CLAIM_REF_CODE], "rule": "cross_sheet_conflict",
                    "field_code": code, "expected": float(a), "actual": float(b), "at_row": None,
                    "detail": (f"Claim {canonical.at[idx, S.CLAIM_REF_CODE]}, period {p}: sheet '{first_sheet}' row "
                               f"{_src(canonical, first)} has {_label(code)} {_fmt(a)}; sheet "
                               f"'{canonical.at[idx, S.SOURCE_SHEET_CODE]}' row {_src(canonical, idx)} has {_fmt(b)}, "
                               f"difference {_fmt(b - a)}"),
                })
                break  # one finding per conflicting row: the first differing amount
    return _frame(out)


def _src(df: pd.DataFrame, idx) -> str:
    v = df.at[idx, "_source_row"] if "_source_row" in df.columns else None
    return "?" if v is None or pd.isna(v) else str(int(v))


def against_previous(current: pd.DataFrame, previous: pd.DataFrame, previous_label: str) -> pd.DataFrame:
    """Record-level matching with the previous submission, by claim reference
    (and currency, when both state one). `previous` needs the claim reference,
    paid to date, currency, `_source_sheet` and `_source_row` columns; the
    latest occurrence of each reference is the one compared."""
    out: list[dict] = []
    if current.empty or previous.empty or S.CLAIM_REF_CODE not in current.columns:
        return _frame(out)
    prev_ref = previous[S.CLAIM_REF_CODE].astype("string").str.strip().str.upper()
    prev = previous.assign(_ref=prev_ref)[prev_ref.notna() & (prev_ref != "")].drop_duplicates("_ref", keep="last")
    prev = prev.set_index("_ref")
    prev_paid = _num(prev, S.PAID_TD_CODE)
    cur_ref = current[S.CLAIM_REF_CODE].astype("string").str.strip().str.upper()
    cur_paid, cur_prev_paid = _num(current, S.PAID_TD_CODE), _num(current, S.PREV_PAID_CODE)
    for idx in current.index[cur_ref.notna() & cur_ref.isin(prev.index)]:
        key = cur_ref[idx]
        ccy_now = current.at[idx, S.CURRENCY_CODE] if S.CURRENCY_CODE in current.columns else None
        ccy_then = prev.at[key, S.CURRENCY_CODE] if S.CURRENCY_CODE in prev.columns else None
        if _known(ccy_now) and _known(ccy_then) and str(ccy_now).upper() != str(ccy_then).upper():
            continue  # reported in another currency: amounts are not comparable
        then = prev_paid[key]
        if pd.isna(then):
            continue
        where = f"{previous_label}, sheet '{prev.at[key, S.SOURCE_SHEET_CODE]}' row {_src(prev, key)}"
        ref = current.at[idx, S.CLAIM_REF_CODE]
        now = cur_paid[idx]
        if not pd.isna(now) and now < then - S.ARITHMETIC_TOLERANCE:
            out.append({"row_index": int(idx), "claim_ref": ref, "rule": "paid_decreased", "field_code": S.PAID_TD_CODE,
                        "expected": float(then), "actual": float(now), "at_row": None,
                        "detail": (f"Claim {ref}: paid to date is {_fmt(now)}, down from {_fmt(then)} in the previous "
                                   f"submission ({where}), difference {_fmt(now - then)}")})
        pp = cur_prev_paid[idx]
        if not pd.isna(pp) and abs(pp - then) > S.ARITHMETIC_TOLERANCE:
            out.append({"row_index": int(idx), "claim_ref": ref, "rule": "rollforward_break", "field_code": S.PREV_PAID_CODE,
                        "expected": float(then), "actual": float(pp), "at_row": None,
                        "detail": (f"Claim {ref}: previously paid is {_fmt(pp)}, but the previous submission showed "
                                   f"paid to date {_fmt(then)} ({where}), difference {_fmt(pp - then)}")})
    return _frame(out)


def _known(v) -> bool:
    return v is not None and not (isinstance(v, float) and pd.isna(v)) and str(v).strip() != ""
