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

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from .schema import FIELDS, FIELDS_BY_CODE

# Tried in order; whichever format parses the most values for a given
# column wins. A final flexible-parser pass catches anything left over.
_DATE_FORMATS = ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%b-%Y", "%Y/%m/%d", "%d.%m.%Y",
                  "%Y-%m-%d %H:%M:%S"]

HEADER_SCAN_ROWS = 5  # how many leading rows to consider as candidate headers
MIN_HEADER_MATCHES = 3  # a candidate row needs at least this many alias-matchable cells

EXCLUDED_ROW_REASON_LABELS = {
    "blank": "blank row",
    "subtotal": "subtotal/total row",
    "repeated_header": "repeated header row",
}


@dataclass
class ExcludedRow:
    """A row this sheet's raw data contained but that was filtered out
    before ever reaching mapping/validation -- never silently dropped:
    every one of these is counted and explained in WorkbookCoverage so the
    coverage summary accounts for every row in the source file (fix spec
    3.1's "never silently drop or silently count as claims", extended
    from whole-sheet skips down to individual rows)."""
    sheet_name: str
    row_number: int  # 1-based row number within the original sheet, as a user would see it in Excel
    reason: str  # "blank" | "subtotal" | "repeated_header"
    detail: str
    values: dict[str, str] = field(default_factory=dict)  # column name -> raw cell text, for drill-down


@dataclass
class SheetData:
    sheet_name: str
    header_row_index: int  # 0-based row index (within the sheet) the header was found at
    raw: pd.DataFrame  # data rows only, columns = the detected header row's text
    skipped: bool = False
    skip_reason: str | None = None
    raw_row_count: int = 0  # every row openpyxl saw in this sheet, header/banner included
    excluded_rows: list[ExcludedRow] = field(default_factory=list)


def load_raw(path: str | Path) -> pd.DataFrame:
    """Read a single-sheet/CSV bordereau as-is, all columns as strings.
    Kept for simple single-sheet callers; load_workbook_sheets() is the
    multi-sheet-aware, header-row-detecting entry point."""
    path = str(path)
    if path.lower().endswith(".csv"):
        return pd.read_csv(path, dtype="string")
    if path.lower().endswith(".xls"):
        # Legacy binary format (pre-2007). openpyxl only reads the
        # zip/XML-based .xlsx/.xlsm container, so a real .xls needs xlrd --
        # without this branch pandas' engine auto-detection silently tries
        # openpyxl anyway (by extension) and raises InvalidFileException.
        return pd.read_excel(path, dtype="string", engine="xlrd")
    return pd.read_excel(path, dtype="string", engine="openpyxl")


def load_workbook_sheets(path: str | Path) -> list[SheetData]:
    """Every sheet in the workbook (fix spec 3.1), each with its own
    detected header row (fix spec 3.2). A CSV has exactly one implicit
    "sheet" named after the file."""
    path = str(path)
    if path.lower().endswith(".csv"):
        return [_build_csv_sheet_data(path)]

    if path.lower().endswith(".xls"):
        return [_build_sheet_data(name, rows) for name, rows in _iter_legacy_xls_rows(path)]

    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    sheets: list[SheetData] = []
    try:
        for name in wb.sheetnames:
            ws = wb[name]
            rows = list(ws.iter_rows(values_only=True))
            sheets.append(_build_sheet_data(name, rows))
    finally:
        wb.close()
    return sheets


def _iter_legacy_xls_rows(path: str) -> list[tuple[str, list[tuple]]]:
    """Read every sheet of a real legacy .xls (BIFF/CDFV2) workbook via
    xlrd, normalized to look like openpyxl's `iter_rows(values_only=True)`
    output: blank cells as None, date cells as datetime, everything else
    as the underlying Python value -- so _build_sheet_data doesn't need to
    know which library produced its rows."""
    import xlrd

    book = xlrd.open_workbook(path)
    out: list[tuple[str, list[tuple]]] = []
    for sheet_name in book.sheet_names():
        ws = book.sheet_by_name(sheet_name)
        rows: list[tuple] = []
        for r in range(ws.nrows):
            row: list[object] = []
            for cell in ws.row(r):
                if cell.ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK) or cell.value == "":
                    row.append(None)
                elif cell.ctype == xlrd.XL_CELL_DATE:
                    row.append(xlrd.xldate.xldate_as_datetime(cell.value, book.datemode))
                else:
                    row.append(cell.value)
            rows.append(tuple(row))
        out.append((sheet_name, rows))
    return out


def _build_csv_sheet_data(path: str) -> SheetData:
    """A CSV's header is always row 1 (no banner-row ambiguity like a
    workbook sheet can have), but the same row-exclusion pass still
    applies -- a CSV export can carry trailing blank lines, an embedded
    subtotal line, or (e.g. two exports concatenated into one file) a
    repeated header line, same as a worksheet tab can."""
    raw = pd.read_csv(path, dtype="string")
    name = Path(path).stem
    columns = list(raw.columns)
    header_row = tuple(columns)
    candidate_rows = [tuple(r) for r in raw.itertuples(index=False, name=None)]
    total = len(candidate_rows) + 1  # + header row

    if not candidate_rows:
        return SheetData(name, 0, pd.DataFrame(columns=columns), skipped=True,
                          skip_reason="header row found but no data rows follow it", raw_row_count=total)

    kept_rows, excluded_rows = _classify_and_filter_rows(name, 0, header_row, columns, candidate_rows)
    if not kept_rows:
        return SheetData(name, 0, pd.DataFrame(columns=columns), skipped=True,
                          skip_reason="header row found but every following row was blank or excluded",
                          raw_row_count=total, excluded_rows=excluded_rows)

    df = pd.DataFrame(kept_rows, columns=columns).astype("string")
    return SheetData(name, 0, df, raw_row_count=total, excluded_rows=excluded_rows)


def _build_sheet_data(name: str, rows: list[tuple]) -> SheetData:
    total = len(rows)
    if not rows:
        return SheetData(name, 0, pd.DataFrame(), skipped=True, skip_reason="sheet is empty",
                          raw_row_count=total)

    header_idx, score = _detect_header_row(rows)
    if header_idx is None:
        return SheetData(name, 0, pd.DataFrame(), skipped=True,
                          skip_reason="no row in the first "
                                      f"{HEADER_SCAN_ROWS} matched enough known fields to be a header row",
                          raw_row_count=total)

    header_row = rows[header_idx]
    columns = _dedupe_columns([_clean_header_cell(c, i) for i, c in enumerate(header_row)])
    candidate_rows = rows[header_idx + 1:]
    if not candidate_rows:
        return SheetData(name, header_idx, pd.DataFrame(columns=columns), skipped=True,
                          skip_reason="header row found but no data rows follow it",
                          raw_row_count=total)

    kept_rows, excluded_rows = _classify_and_filter_rows(name, header_idx, header_row, columns, candidate_rows)
    if not kept_rows:
        return SheetData(name, header_idx, pd.DataFrame(columns=columns), skipped=True,
                          skip_reason="header row found but every following row was blank or excluded",
                          raw_row_count=total, excluded_rows=excluded_rows)

    df = pd.DataFrame(kept_rows, columns=columns)
    df = df.astype("string")
    return SheetData(name, header_idx, df, raw_row_count=total, excluded_rows=excluded_rows)


def _normalize_cell(value: object) -> str:
    """Trim, collapse internal/non-breaking whitespace, and casefold --
    the same normalization already used for header-alias matching, so a
    repeated header row with different casing or stray whitespace is
    still caught as a match rather than slipping through as "different
    text" (fix spec: a normalized compare, not an exact one)."""
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value))  # NBSP (U+00A0) etc. -> regular space
    return " ".join(text.split()).casefold()


_SUBTOTAL_PATTERN = re.compile(r"^(sub[\s-]?)?total:?$|^grand\s+total:?$")


def _row_is_blank(row: tuple) -> bool:
    return all(_normalize_cell(c) == "" for c in row)


def _row_matches_header(row: tuple, header_row: tuple) -> bool:
    """A repeated header row embedded mid-sheet (e.g. two monthly
    submissions pasted into one tab, each starting with a fresh header)
    -- majority of the header's own non-blank cells reappear at the same
    position in this row, normalized the same way header matching already
    is. Checked positionally (not just "these values appear somewhere in
    the row") so a genuine claim whose values happen to overlap a couple
    of header words in the wrong columns isn't misclassified."""
    header_norms = [_normalize_cell(c) for c in header_row]
    non_blank_positions = [i for i, h in enumerate(header_norms) if h]
    if not non_blank_positions:
        return False
    matches = sum(
        1 for i in non_blank_positions
        if _normalize_cell(row[i] if i < len(row) else None) == header_norms[i]
    )
    return matches / len(non_blank_positions) > 0.5


def _row_is_subtotal(row: tuple) -> bool:
    """The shape of a real-world embedded subtotal line: most cells blank,
    with one of the few non-blank cells reading like a total/grand total
    label. Requires the majority-blank shape (not just the word "total"
    anywhere) so a genuine claim row is never misclassified just because
    a free-text field happens to contain that word."""
    non_blank = [c for c in row if _normalize_cell(c) != ""]
    if not non_blank or len(non_blank) * 2 > len(row):
        return False
    return any(_SUBTOTAL_PATTERN.match(_normalize_cell(c)) for c in non_blank)


def _classify_row(row: tuple, header_row: tuple) -> tuple[str | None, str | None]:
    """Returns (reason, detail) for a row that should be excluded before
    mapping/validation ever sees it, or (None, None) for a genuine data
    row. Checked in this order: blank first (cheapest and unambiguous),
    then an exact repeated-header match (specific), then the subtotal
    heuristic (broadest) -- so a row that happens to match the header
    is never also reported as a subtotal."""
    if _row_is_blank(row):
        return "blank", "row is entirely blank"
    if _row_matches_header(row, header_row):
        return "repeated_header", "row repeats the sheet's own header text"
    if _row_is_subtotal(row):
        return "subtotal", "row looks like a subtotal/total line, not a claim"
    return None, None


def _classify_and_filter_rows(
    sheet_name: str, header_idx: int, header_row: tuple, columns: list[str], candidate_rows: list[tuple],
) -> tuple[list[tuple], list[ExcludedRow]]:
    kept: list[tuple] = []
    excluded: list[ExcludedRow] = []
    for offset, row in enumerate(candidate_rows):
        reason, detail = _classify_row(row, header_row)
        if reason is None:
            kept.append(row)
            continue
        row_number = header_idx + 1 + offset + 1  # 1-based, as a user would see it in the sheet
        values = {columns[i]: ("" if i >= len(row) or row[i] is None else str(row[i]))
                  for i in range(len(columns))}
        excluded.append(ExcludedRow(sheet_name=sheet_name, row_number=row_number,
                                     reason=reason, detail=detail, values=values))
    return kept, excluded


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
    index (and its score), or (None, 0) if nothing clears the bar."""
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

    if best_idx is None or best_score < MIN_HEADER_MATCHES:
        return None, best_score
    return best_idx, best_score


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


def apply_mapping(raw: pd.DataFrame, mapping: dict[str, str], sheet_name: str = "") -> pd.DataFrame:
    """mapping: {source_column_name: field_code}. Source columns absent
    from the mapping are dropped; canonical fields absent from the mapping
    come back as all-null columns so downstream code can always rely on
    every field code being present as a column -- but see schema.SOURCE_
    SHEET_CODE: validation/report consumers must check the mapping state
    (via a MappingBatchResult) before treating a null cell as "genuinely
    blank" rather than "column was never mapped"."""
    out = pd.DataFrame(index=raw.index)

    for source_col, code in mapping.items():
        if source_col not in raw.columns or code not in FIELDS_BY_CODE:
            continue
        spec = FIELDS_BY_CODE[code]
        series = raw[source_col].astype("string").str.strip()
        series = series.mask(series == "", pd.NA)

        if spec.dtype == "date":
            out[code] = _best_date_parse(series)
        elif spec.dtype == "decimal":
            out[code] = pd.to_numeric(series, errors="coerce")
        elif spec.dtype == "enum":
            out[code] = series.str.lower()
        elif spec.dtype == "currency":
            out[code] = series.str.upper()
        else:
            out[code] = series

    for f in FIELDS:
        if f.code not in out.columns:
            out[f.code] = _empty_column(f.dtype, len(out), out.index)

    from .schema import SOURCE_SHEET_CODE
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
