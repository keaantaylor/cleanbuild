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

from .iso4217 import VALID_CURRENCY_CODES
from .mapping import split_trailing_parenthetical
from .schema import CURRENCY_CODE, FIELDS, FIELDS_BY_CODE

# Tried in order; whichever format parses the most values for a given
# column wins. A final flexible-parser pass catches anything left over.
_DATE_FORMATS = ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%b-%Y", "%Y/%m/%d", "%d.%m.%Y",
                  "%Y-%m-%d %H:%M:%S"]

HEADER_SCAN_ROWS = 30  # how many leading rows to consider as candidate headers -- TB-002:
# a title band, an embedded logo image, or a couple of blank spacer rows
# routinely push a real header past row 5 (openpyxl returns None for
# every cell an image merely floats over -- it doesn't occupy a row --
# but the title/spacer rows above a real header still do), and a header
# past the scan window was previously indistinguishable from "no header
# at all", silently dropping the whole sheet with no error and no trace.
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
        return [_safe_build_sheet(name, lambda r=rows: r) for name, rows in _iter_legacy_xls_rows(path)]

    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    sheets: list[SheetData] = []
    try:
        for name in wb.sheetnames:
            sheets.append(_safe_build_sheet(name, lambda n=name: _read_bounded_rows(wb[n])))
    finally:
        wb.close()
    return sheets


# TB-005: a single stray value far outside a sheet's real data (e.g. one
# cell at A1048576, or column formatting run out to XFD) inflates
# openpyxl's declared used-range to the entire worksheet -- Excel's
# absolute limits, not this file's actual content -- and a naive read
# then walks all of it: 1,048,576 rows x 16,384 columns for a sheet that
# might hold a few hundred real rows. That is not a volume problem, it
# is reading empty space as though it were data, and it is what froze
# the whole request thread (and with it, the UI) on such a file. Bound
# both dimensions: stop once real data has clearly ended (a long run of
# consecutive blank rows) and cap the column width read per row.
_MAX_CONSECUTIVE_EMPTY_ROWS = 500
_MAX_SCAN_COLUMNS = 500


def _row_looks_blank(row: tuple) -> bool:
    return all(c is None or (isinstance(c, str) and not c.strip()) for c in row)


def _read_bounded_rows(ws) -> list[tuple]:
    """Reads `ws` lazily (openpyxl's read_only row iterator never
    materializes the full declared range up front) and stops as soon as
    real data has clearly run out, rather than trusting the sheet's
    declared dimension. This is what keeps a stray cell at the edge of
    Excel's absolute limits from turning one pathological file into an
    unbounded read.

    max_col is only capped when the sheet's own declared width is
    already pathological (ws.max_column is a cheap metadata read in
    read_only mode, not a full scan) -- passing it unconditionally would
    pad every row of an ordinary, narrow sheet out to _MAX_SCAN_COLUMNS
    with spurious blank columns, corrupting header detection for every
    normal file."""
    read_kwargs: dict = {"values_only": True}
    if ws.max_column and ws.max_column > _MAX_SCAN_COLUMNS:
        read_kwargs["max_col"] = _MAX_SCAN_COLUMNS

    rows: list[tuple] = []
    empty_streak = 0
    hit_limit = False
    for row in ws.iter_rows(**read_kwargs):
        rows.append(row)
        if _row_looks_blank(row):
            empty_streak += 1
            if empty_streak >= _MAX_CONSECUTIVE_EMPTY_ROWS:
                hit_limit = True
                break
        else:
            empty_streak = 0
    if hit_limit:
        # Only strip the specific run that triggered early termination --
        # an ordinary trailing blank row (well under the threshold) is
        # left in place for the existing row-classification pass to
        # count and report as "blank", same as it always has.
        del rows[-_MAX_CONSECUTIVE_EMPTY_ROWS:]
    return rows


def _safe_build_sheet(name: str, load_rows) -> SheetData:
    """A crash reading or scoring one sheet (a corrupt cell, an
    unexpected value type, anything) must never abort the rest of the
    workbook -- every other sheet the file actually contains would
    otherwise silently vanish along with the one that failed. Isolate it
    per sheet, name the sheet and the real exception, and let the
    workbook keep loading."""
    try:
        rows = load_rows()
        return _build_sheet_data(name, rows)
    except Exception as exc:  # noqa: BLE001 -- isolated per sheet, surfaced by name, never swallowed
        return SheetData(name, 0, pd.DataFrame(), skipped=True,
                          skip_reason=f"error while reading this sheet: {exc}", raw_row_count=0)


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
    index (and its score). Falls back to a structural (non-semantic)
    header guess -- see _structural_header_row() -- when no row's text
    matches enough known English aliases, so a real data sheet in another
    language is never treated the same as a genuinely empty/notes sheet
    just because its headers don't match the alias dictionary."""
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

    if best_idx is not None and best_score >= MIN_HEADER_MATCHES:
        return best_idx, best_score

    structural_idx = _structural_header_row(rows)
    if structural_idx is not None:
        return structural_idx, 0  # a header row, but with zero alias-matched fields

    return None, best_score


def _structural_header_row(rows: list[tuple]) -> int | None:
    """No row's text aliased to a known field -- this is either a sheet
    with an unrecognized layout (a different language, unfamiliar
    terminology, an abbreviation dictionary can't cover) or a genuine
    non-data sheet (a notes/cover tab). Distinguish them by shape alone:
    a real header row populates most of its columns and is followed by
    data rows of comparable width; a notes tab is typically one or two
    populated cells (a title/paragraph) with nothing tabular below it.
    Fix spec: a sheet must never be silently dropped just because its
    headers don't match English aliases -- only a sheet that also fails
    this structural test (no plausible tabular shape at all) is skipped."""
    best_idx, best_width = None, 0
    for i, row in enumerate(rows[:HEADER_SCAN_ROWS]):
        width = sum(1 for c in row if c is not None and str(c).strip())
        if width > best_width:
            best_idx, best_width = i, width

    if best_idx is None or best_width < MIN_HEADER_MATCHES:
        return None

    following = rows[best_idx + 1: best_idx + 1 + HEADER_SCAN_ROWS]
    has_comparable_data = any(
        sum(1 for c in row if c is not None and str(c).strip()) >= max(2, best_width // 2)
        for row in following
    )
    return best_idx if has_comparable_data else None


_CURRENCY_SYMBOL_RE = re.compile(r"[€£$¥₹]")

# TB-004(d): a formula-error cell (openpyxl returns the sentinel string
# itself when data_only=True can't resolve it -- e.g. the workbook was
# never recalculated in Excel/LibreOffice) must never reach float() and
# raise. Recognized and treated as unparseable text, same as any other
# non-numeric cell content.
_EXCEL_ERROR_SENTINELS = frozenset({
    "#DIV/0!", "#N/A", "#REF!", "#VALUE!", "#NAME?", "#NULL!", "#NUM!",
})


def unparseable_flag_column(field_code: str) -> str:
    """Name of the tracking column apply_mapping() adds alongside a
    decimal field: True where the source cell had real (non-blank) text
    that still could not be parsed as a number, even after stripping
    currency symbols and normalizing both thousands-separator
    conventions. Never conflated with "genuinely blank" (which stays the
    established $0/not-yet-reported convention) or "never mapped"
    (tracked separately via sheet_field_state) -- validation.py reads
    this to force NOT_EVALUABLE for arithmetic reconciliation rather than
    silently treating a parsing failure as a zero."""
    return f"_unparseable_{field_code}"


def _parse_amount_cell(text: str) -> float | None:
    """'€900,000.00' -> 900000.0, '£1,234.56' -> 1234.56, '1.234,56'
    (European decimal-comma) -> 1234.56, '(500.00)' -> -500.0. Returns
    None if the text is genuinely empty OR if it still can't be read as
    a number after all of that -- the caller distinguishes those two
    cases itself (it already knows whether the raw cell was blank)."""
    t = unicodedata.normalize("NFKC", text).strip()
    if not t:
        return None
    if t.upper() in _EXCEL_ERROR_SENTINELS:
        return None
    t = t.replace("−", "-")  # Unicode minus sign (U+2212), distinct from ASCII hyphen-minus
    t = _CURRENCY_SYMBOL_RE.sub("", t)
    t = "".join(t.split())  # drop all internal whitespace, incl. non-breaking (already normalized above)

    negative = False
    if t.startswith("(") and t.endswith(")"):
        negative, t = True, t[1:-1]
    if t.startswith("-"):
        negative, t = True, t[1:]
    if t.startswith("+"):
        t = t[1:]
    if not t:
        return None

    has_comma, has_dot = "," in t, "." in t
    if has_comma and has_dot:
        if t.rfind(",") > t.rfind("."):
            t = t.replace(".", "").replace(",", ".")  # comma is the decimal separator (1.234,56)
        else:
            t = t.replace(",", "")  # dot is the decimal separator (1,234.56)
    elif has_comma:
        # Ambiguous with only a comma present: thousands grouping (1,234
        # or 12,345) vs. a European decimal comma (1234,56). Thousands
        # groups are conventionally exactly 3 digits; a decimal fraction
        # is conventionally 1-2. A single comma followed by 1-2 digits is
        # read as decimal; 3 digits (or more than one comma) is grouping.
        parts = t.split(",")
        if len(parts) == 2 and len(parts[1]) in (1, 2):
            t = t.replace(",", ".")
        else:
            t = t.replace(",", "")

    try:
        value = float(t)
    except ValueError:
        return None
    return -value if negative else value


def _parse_amount_series(series: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Returns (parsed float values, unparseable mask). `series` is
    expected to already have empty strings normalized to NA by the
    caller, so `notna()` reliably means "the source cell had text"."""
    had_text = series.notna()
    parsed = series.map(lambda v: _parse_amount_cell(str(v)) if pd.notna(v) else None)
    parsed_numeric = pd.array(parsed, dtype="Float64")
    unparseable = had_text & pd.isna(parsed_numeric)
    return parsed_numeric, unparseable


# Excel represents a date as a day count from a fixed epoch. 1899-12-30
# (not 1900-01-01) is the standard trick that reproduces Excel's own
# well-known "1900 is a leap year" bug, so it agrees with what Excel
# itself displays for the same serial number -- verified against known
# reference points (44197 -> 2021-01-01, 25569 -> 1970-01-01) before use.
_EXCEL_SERIAL_EPOCH = pd.Timestamp("1899-12-30")
# A plausible-claims-date guard, not a technical limit: rejects small
# integers (an ID, a count, "1", "2") that are valid serials in principle
# but are never a real bordereau date, while still covering any date a
# real claims file would plausibly carry (serial 1000 ~= 1902-09-26,
# serial 100000 ~= 2173-10-15).
_EXCEL_SERIAL_MIN, _EXCEL_SERIAL_MAX = 1000, 100_000


def _parse_excel_serial_dates(series: pd.Series) -> pd.Series:
    """A cell stored as a bare number with no Excel date formatting
    applied -- common when a bordereau is exported to CSV, or a date
    column was pasted as values -- still needs to resolve to a real
    calendar date instead of silently coming back NaT. Only called on
    values that already failed every recognized date-string format (see
    _best_date_parse), and only ever reached for a column already
    confirmed-mapped to a date-type canonical field, so this never
    reinterprets an ordinary reference number living in some other
    column as a date."""
    numeric = pd.to_numeric(series, errors="coerce")
    plausible = numeric.between(_EXCEL_SERIAL_MIN, _EXCEL_SERIAL_MAX)
    parsed = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")
    valid = plausible & numeric.notna()
    if valid.any():
        parsed.loc[valid] = _EXCEL_SERIAL_EPOCH + pd.to_timedelta(numeric.loc[valid], unit="D")
    return parsed


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
            best_score, best_parsed = fallback_score, fallback

    if best_score < target:
        # Whatever's still unresolved wasn't recognizable as a date
        # string at all -- try reading it as a bare Excel serial number
        # instead of leaving it NaT.
        still_missing = best_parsed.isna() & series.notna()
        if still_missing.any():
            serial_parsed = _parse_excel_serial_dates(series[still_missing])
            if serial_parsed.notna().any():
                best_parsed = best_parsed.copy()
                best_parsed.loc[still_missing] = serial_parsed

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
    currency_hint: str | None = None
    unparseable_cols: dict[str, pd.Series] = {}

    for source_col, code in mapping.items():
        if source_col not in raw.columns or code not in FIELDS_BY_CODE:
            continue
        spec = FIELDS_BY_CODE[code]
        series = raw[source_col].astype("string").str.strip()
        series = series.mask(series == "", pd.NA)

        if spec.dtype == "date":
            out[code] = _best_date_parse(series)
        elif spec.dtype == "decimal":
            parsed, unparseable = _parse_amount_series(series)
            out[code] = parsed
            unparseable_cols[code] = unparseable
            # A monetary column's own header sometimes states its currency
            # directly -- "Paid Amount (GBP)" -- where the sheet has no
            # separate Currency column at all. That's not the same as
            # guessing a default: the file itself said so in the header,
            # so it's read rather than discarded. Only used as a last
            # resort, see below, when no Currency column was mapped.
            if currency_hint is None:
                _, suffix = split_trailing_parenthetical(source_col)
                if suffix and suffix.strip().upper() in VALID_CURRENCY_CODES:
                    currency_hint = suffix.strip().upper()
        elif spec.dtype == "enum":
            out[code] = series.str.lower()
        elif spec.dtype == "currency":
            out[code] = series.str.upper()
        else:
            out[code] = series

    for f in FIELDS:
        if f.code not in out.columns:
            out[f.code] = _empty_column(f.dtype, len(out), out.index)

    decimal_codes = [f.code for f in FIELDS if f.dtype == "decimal"]
    for code in decimal_codes:
        out[unparseable_flag_column(code)] = unparseable_cols.get(code, pd.Series(False, index=out.index))

    if currency_hint and CURRENCY_CODE not in mapping.values() and len(out):
        out[CURRENCY_CODE] = pd.array([currency_hint] * len(out), dtype="string")

    from .schema import SOURCE_SHEET_CODE
    out[SOURCE_SHEET_CODE] = pd.array([sheet_name] * len(out), dtype="string")

    return out[[f.code for f in FIELDS] + [SOURCE_SHEET_CODE] + [unparseable_flag_column(c) for c in decimal_codes]]


def _empty_column(dtype: str, length: int, index) -> pd.Series:
    """An all-null column of the right dtype for a field the caller's
    mapping doesn't cover, so pandera can coerce it like any other."""
    if dtype == "date":
        return pd.Series([pd.NaT] * length, index=index, dtype="datetime64[ns]")
    if dtype == "decimal":
        return pd.Series([np.nan] * length, index=index, dtype="float64")
    return pd.Series([pd.NA] * length, index=index, dtype="string")
