"""Load a raw bordereau file and apply a confirmed column mapping to
produce a canonical DataFrame keyed by the Section 3 field codes.

Fix spec 3.1/3.2: a workbook can carry multiple sheets (one per sender/
cedant), and a sheet's real header row isn't always row 1 -- some carry a
merged title banner above it. load_workbook_sheets() handles both: it
iterates every sheet (not just the active/first one) and, per sheet,
scores the first few rows by how many cells look like a known field
header, picking whichever row scores best rather than assuming row 1.
That scoring approach also solves the banner-row case for free: a merged
banner cell reads back as one non-null value with everything else in that
row None (openpyxl returns None for the cells a merge covers), so a real
banner row's score is always far below the actual header row's.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .schema import FIELDS, FIELDS_BY_CODE

logger = logging.getLogger(__name__)

# Tried in order; whichever format parses the most values for a given
# column wins. A final flexible-parser pass catches anything left over.
_DATE_FORMATS = ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%b-%Y", "%Y/%m/%d", "%d.%m.%Y",
                  "%Y-%m-%d %H:%M:%S"]

HEADER_SCAN_ROWS = 5  # how many leading rows to consider as candidate headers
MIN_HEADER_MATCHES = 3  # below this, a sheet is flagged low-confidence (fix spec 1.2)
                          # but is STILL processed, never silently dropped -- see
                          # _detect_header_row()'s docstring.


@dataclass
class SheetData:
    sheet_name: str
    header_row_index: int  # 0-based row index (within the sheet) the header was found at
    raw: pd.DataFrame  # data rows only, columns = the detected header row's text
    skipped: bool = False
    skip_reason: str | None = None
    raw_row_count: int = 0  # every row openpyxl saw in this sheet, header/banner included
    # Fix spec 1.2: True when a header row was found and the sheet WAS
    # processed, but too few of its columns matched a known field to be
    # confident this is really the header row (e.g. non-English headers).
    # Never a reason to skip -- see propose_mapping_for_workbook /
    # run_workbook_pipeline, which process this sheet like any other, so
    # it naturally ends up with 0 (or few) mapped fields, surfaced via the
    # ordinary "N of M fields mapped" coverage/mapping-completeness path
    # instead of vanishing from the file entirely.
    low_confidence_header: bool = False
    header_match_score: int = 0


def load_raw(path: str | Path) -> pd.DataFrame:
    """Read a single-sheet/CSV bordereau as-is, all columns as strings.
    Kept for simple single-sheet callers; load_workbook_sheets() is the
    multi-sheet-aware, header-row-detecting entry point."""
    path = str(path)
    if path.lower().endswith(".csv"):
        return pd.read_csv(path, dtype="string")
    return pd.read_excel(path, dtype="string", engine="openpyxl")


def load_workbook_sheets(path: str | Path, source_stem: str | None = None) -> list[SheetData]:
    """Every sheet in the workbook (fix spec 3.1), each with its own
    detected header row (fix spec 3.2). A CSV has exactly one implicit
    "sheet" named after the file.

    source_stem: the name to use for that implicit CSV sheet, overriding
    Path(path).stem. Needed because a caller may read the same logical
    file from two different physical paths at different times -- e.g. a
    freshly-uploaded temp file at upload time, then its permanently
    stored copy afterward -- and Path(path).stem would then silently
    produce two DIFFERENT sheet names for the same file (a random temp
    filename vs. the real one), breaking every later per-sheet lookup
    that expects the name recorded at upload time. Callers that read
    from a stable, permanently-named path don't need this; callers that
    read from a temp path before it's moved into permanent storage must
    pass the name that path will eventually have."""
    path = str(path)
    if path.lower().endswith(".csv"):
        raw = pd.read_csv(path, dtype="string")
        name = source_stem if source_stem is not None else Path(path).stem
        return [SheetData(sheet_name=name, header_row_index=0, raw=raw)]

    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    sheets: list[SheetData] = []
    try:
        for name in wb.sheetnames:
            # Fix spec 1.3: a crash reading/scoring ONE sheet must never
            # abort the rest of the workbook -- caught, logged with the
            # sheet name and the real exception, and surfaced as a named
            # per-sheet failure (skipped=True with the exception text as
            # the reason) rather than propagating out of load_workbook_
            # sheets() and failing the whole upload.
            try:
                ws = wb[name]
                rows = list(ws.iter_rows(values_only=True))
                sheets.append(_build_sheet_data(name, rows))
            except Exception as exc:  # noqa: BLE001 -- deliberately broad: isolate this sheet, not the file
                logger.exception("Failed to read sheet %r while loading workbook %r", name, str(path))
                sheets.append(SheetData(
                    name, 0, pd.DataFrame(), skipped=True,
                    skip_reason=f"error while reading this sheet: {exc.__class__.__name__}: {exc}",
                    raw_row_count=0,
                ))
    finally:
        wb.close()
    return sheets


def _build_sheet_data(name: str, rows: list[tuple]) -> SheetData:
    total = len(rows)
    if not rows:
        return SheetData(name, 0, pd.DataFrame(), skipped=True, skip_reason="sheet is empty",
                          raw_row_count=total)

    header_idx, score = _detect_header_row(rows)
    if header_idx is None:
        return SheetData(name, 0, pd.DataFrame(), skipped=True,
                          skip_reason="no row in the first "
                                      f"{HEADER_SCAN_ROWS} rows has any content to use as a header",
                          raw_row_count=total)

    columns = _dedupe_columns([_clean_header_cell(c, i) for i, c in enumerate(rows[header_idx])])
    data_rows = rows[header_idx + 1:]
    if not data_rows:
        return SheetData(name, header_idx, pd.DataFrame(columns=columns), skipped=True,
                          skip_reason="header row found but no data rows follow it",
                          raw_row_count=total)

    df = pd.DataFrame(data_rows, columns=columns)
    df = df.astype("string")
    # Fix spec 1.1/1.2: a sheet whose best candidate header row still
    # scores below MIN_HEADER_MATCHES (e.g. non-English headers that
    # don't match any known alias) is NEVER dropped -- it's ingested like
    # any other sheet, just flagged low_confidence_header so the mapping
    # audit trail and coverage/report summary can name it and say "0 of N
    # fields mapped -- needs manual review" instead of it silently
    # vanishing from the sheet count.
    low_confidence = score < MIN_HEADER_MATCHES
    if low_confidence:
        logger.warning("Sheet %r: best header-row candidate only scored %d/%d known-field matches "
                        "(need >= %d); processing it anyway with low_confidence_header=True",
                        name, score, len(columns), MIN_HEADER_MATCHES)
    return SheetData(name, header_idx, df, raw_row_count=total,
                      low_confidence_header=low_confidence, header_match_score=score)


def _clean_header_cell(value: object, position: int) -> str:
    if value is None:
        return f"__blank_col_{position}__"
    return str(value).strip()


def _dedupe_columns(columns: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    out = []
    for col in columns:
        if col not in seen:
            seen[col] = 0
            out.append(col)
        else:
            seen[col] += 1
            out.append(f"{col}__{seen[col]}")
    return out


def _detect_header_row(rows: list[tuple]) -> tuple[int | None, int]:
    """Score each of the first HEADER_SCAN_ROWS rows by how many of its
    cells fuzzy-match a known field alias; return the best-scoring row
    index (and its score).

    Fix spec 1.1/1.2: this used to return (None, score) -- causing the
    whole sheet to be dropped -- whenever the best score fell below
    MIN_HEADER_MATCHES. That conflated two very different situations:
    "this sheet has no plausible header content at all" (genuinely
    nothing to process) and "this sheet has real headers, they just
    don't match any known alias" (e.g. all-French column names) -- which
    is exactly the case that must still be ingested and reported as a
    low-confidence mapping, not silently excluded. Now: only a row with
    at least one non-empty cell is a header-row CANDIDATE at all; None is
    returned only when literally every scanned row is blank. Any
    candidate row -- even one that scores 0 -- wins as the header row if
    it's the best of the (non-empty) candidates; the caller decides what
    a low score means (flag low_confidence_header), it never means
    "skip"."""
    from .mapping import fuzzy_match_headers

    best_idx, best_score = None, -1
    for i, row in enumerate(rows[:HEADER_SCAN_ROWS]):
        cells = [str(c).strip() for c in row if c is not None and str(c).strip()]
        if not cells:
            continue
        matches = fuzzy_match_headers(cells)
        score = sum(1 for s in matches.values() if s.method != "unmapped")
        if score > best_score:
            best_idx, best_score = i, score

    return best_idx, max(best_score, 0)


def _best_date_parse(series: pd.Series) -> pd.Series:
    non_null = series.dropna()
    if non_null.empty:
        return pd.to_datetime(series, errors="coerce")

    target = int(non_null.shape[0])
    best_parsed = None
    best_score = -1
    for fmt in _DATE_FORMATS:
        parsed = pd.to_datetime(series, format=fmt, errors="coerce")
        score = int(parsed.notna().sum())
        if score > best_score:
            best_score, best_parsed = score, parsed
        if best_score == target:
            break  # every non-null value parsed; no need for a flexible fallback

    if best_score < target:
        fallback = pd.to_datetime(series, format="mixed", errors="coerce")
        fallback_score = int(fallback.notna().sum())
        if fallback_score > best_score:
            return fallback
    return best_parsed


# Fix spec 3.1: strip currency symbols before giving up on a monetary
# value. Not exhaustive of every world currency symbol, but covers the
# symbols the brief and real bordereaux traffic in; ISO codes that
# happen to appear inline (e.g. "GBP 900,000") are handled by the
# alphabetic strip below.
_CURRENCY_SYMBOL_RE = re.compile(r"[€£$¥₹]")
_PARENTHESIZED_NEGATIVE_RE = re.compile(r"^\((.*)\)$")


def _parse_decimal_series(series: pd.Series) -> pd.Series:
    """Fix spec 3.1: monetary values that arrive as text with a currency
    symbol (e.g. "€900,000.00") or thousands separators in either
    convention (1,234.56 comma-thousands/period-decimal, or 1.234,56
    period-thousands/comma-decimal) must still parse -- previously
    pd.to_numeric() gave up on any of these and returned NaN, which the
    arithmetic-reconciliation check then silently treated as a genuine
    blank (fix spec 3.2 covers the "blank must not become zero" half;
    this is the root-cause half: make fewer values blank in the first
    place). Only genuinely unparseable text still comes back as NaN."""
    cleaned = series.str.strip()
    cleaned = cleaned.str.replace(_CURRENCY_SYMBOL_RE, "", regex=True)
    cleaned = cleaned.str.strip()

    def _normalize_one(value: object) -> str | None:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return None
        text = str(value).strip()
        if not text:
            return None
        negative = False
        paren = _PARENTHESIZED_NEGATIVE_RE.match(text)
        if paren:
            negative, text = True, paren.group(1).strip()
        text = text.replace(" ", "")
        if text.startswith("-"):
            negative, text = True, text[1:]
        elif text.startswith("+"):
            text = text[1:]

        has_comma, has_dot = "," in text, "." in text
        if has_comma and has_dot:
            if text.rfind(",") > text.rfind("."):
                text = text.replace(".", "").replace(",", ".")  # comma is the decimal point
            else:
                text = text.replace(",", "")  # dot is the decimal point, commas are thousands
        elif has_comma and not has_dot:
            int_part, _, frac_part = text.partition(",")
            if len(frac_part) == 2 and len(int_part) <= 3:
                text = text.replace(",", ".")  # "12,34" -> decimal
            else:
                text = text.replace(",", "")  # "1,234" / "12,345" -> thousands

        return f"-{text}" if negative and text else text

    normalized = cleaned.map(_normalize_one)
    return pd.to_numeric(normalized, errors="coerce")


def apply_mapping(raw: pd.DataFrame, mapping: dict[str, str], sheet_name: str = "") -> pd.DataFrame:
    """mapping: {source_column_name: field_code}. Source columns absent
    from the mapping are dropped; canonical fields absent from the mapping
    come back as all-null columns so downstream code can always rely on
    every field code being present as a column -- but see schema.SOURCE_
    SHEET_CODE: validation/report consumers must check the mapping state
    (via a MappingBatchResult) before treating a null cell as "genuinely
    blank" rather than "column was never mapped"."""
    from .mapping import extract_currency_hint
    from .schema import CURRENCY_CODE, SOURCE_SHEET_CODE

    out = pd.DataFrame(index=raw.index)
    currency_hint: str | None = None

    for source_col, code in mapping.items():
        if source_col not in raw.columns or code not in FIELDS_BY_CODE:
            continue
        spec = FIELDS_BY_CODE[code]
        series = raw[source_col].astype("string").str.strip()
        series = series.mask(series == "", pd.NA)

        if spec.dtype == "date":
            out[code] = _best_date_parse(series)
        elif spec.dtype == "decimal":
            out[code] = _parse_decimal_series(series)
            if currency_hint is None:
                currency_hint = extract_currency_hint(source_col)
        elif spec.dtype == "enum":
            out[code] = series.str.lower()
        elif spec.dtype == "currency":
            out[code] = series.str.upper()
        else:
            out[code] = series

    for f in FIELDS:
        if f.code not in out.columns:
            out[f.code] = _empty_column(f.dtype, len(out), out.index)

    # Fix spec 2.2: a currency hint found in a stripped header suffix
    # (e.g. "Paid to Date (GBP)") only fills the Currency field when the
    # sheet has no column actually mapped to it -- never overriding a
    # real, mapped Currency column.
    if CURRENCY_CODE not in mapping.values() and currency_hint:
        out[CURRENCY_CODE] = pd.array([currency_hint] * len(out), dtype="string")

    out[SOURCE_SHEET_CODE] = pd.array([sheet_name] * len(out), dtype="string")

    return out[[f.code for f in FIELDS] + [SOURCE_SHEET_CODE]]


def _empty_column(dtype: str, length: int, index) -> pd.Series:
    """An all-null column of the right dtype for a field the caller's
    mapping doesn't cover, so pandera can coerce it like any other."""
    if dtype == "date":
        return pd.Series([pd.NaT] * length, index=index, dtype="datetime64[ns]")
    if dtype == "decimal":
        return pd.Series([np.nan] * length, index=index, dtype="float64")
    return pd.Series([pd.NA] * length, index=index, dtype="string")
