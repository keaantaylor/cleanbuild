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
from .mapping import parse_currency_suffix, parse_scale_suffix, split_trailing_parenthetical
from .schema import CURRENCY_CODE, FIELDS, FIELDS_BY_CODE

# Tried in order; whichever format parses the most values for a given
# column wins. A final flexible-parser pass catches anything left over.
_DATE_FORMATS = ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%b-%Y", "%Y/%m/%d", "%d.%m.%Y",
                  "%Y-%m-%d %H:%M:%S"]

HEADER_SCAN_ROWS = 50  # how many leading rows to consider as candidate headers -- TB-002:
# a title band, an embedded logo image, or a couple of blank spacer rows
# routinely push a real header past row 5 (openpyxl returns None for
# every cell an image merely floats over -- it doesn't occupy a row --
# but the title/spacer rows above a real header still do), and a header
# past the scan window was previously indistinguishable from "no header
# at all", silently dropping the whole sheet with no error and no trace.
# Raised from 30 to 50 after a real Lloyd's-style multi-paragraph
# preamble (syndicate/broker/coverholder detail blocks) was observed
# pushing a header to row 41 -- 30 was itself an improvement over the
# original 5, but still not generous enough for every real preamble.
MIN_HEADER_MATCHES = 3  # a candidate row needs at least this many alias-matchable cells

EXCLUDED_ROW_REASON_LABELS = {
    "blank": "blank row",
    "subtotal": "subtotal/total row",
    "repeated_header": "repeated header row",
    "title": "section title/banner row",
    "blank_run": "run of blank rows",
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
    reason: str  # "blank" | "blank_run" | "subtotal" | "repeated_header" | "title"
    detail: str
    values: dict[str, str] = field(default_factory=dict)  # column name -> raw cell text, for drill-down
    count: int = 1  # >1 only for a collapsed run of consecutive blank rows ("blank_run")


@dataclass
class SheetData:
    sheet_name: str
    header_row_index: int  # 0-based row index (within the sheet) the header was found at
    raw: pd.DataFrame  # data rows only, columns = the detected header row's text
    skipped: bool = False
    skip_reason: str | None = None
    raw_row_count: int = 0  # every row openpyxl saw in this sheet, header/banner included
    excluded_rows: list[ExcludedRow] = field(default_factory=list)
    hidden: bool = False  # sheet_state hidden/veryHidden in the workbook -- processed, but disclosed
    trailing_blank_rows: int = 0  # blank rows after the last populated row: not data, reported, not counted
    notes: list[str] = field(default_factory=list)  # read-limit and parsing disclosures for this sheet

    @property
    def excluded_row_count(self) -> int:
        return sum(er.count for er in self.excluded_rows)


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


def load_workbook_sheets(path: str | Path, source_stem: str | None = None) -> list[SheetData]:
    """Every sheet in the workbook (fix spec 3.1), each with its own
    detected header row (fix spec 3.2). A CSV has exactly one implicit
    "sheet" named after the file."""
    path = str(path)
    if path.lower().endswith(".csv"):
        return [_build_csv_sheet_data(path, source_stem)]

    if path.lower().endswith(".xls"):
        return [_safe_build_sheet(name, lambda r=rows: r) for name, rows in _iter_legacy_xls_rows(path)]

    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    sheets: list[SheetData] = []
    try:
        for name in wb.sheetnames:
            sd = _safe_build_sheet(name, lambda n=name: _read_bounded_rows(wb[n]))
            try:
                sd.hidden = getattr(wb[name], "sheet_state", "visible") != "visible"
            except Exception:  # noqa: BLE001 -- disclosure only; never blocks reading
                pass
            if sd.hidden:
                sd.notes.append("sheet is hidden in the workbook; its rows were processed like any other sheet")
            sheets.append(sd)
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


class _BlankRun:
    """Placeholder for a run of consecutive blank rows collapsed during
    reading (see _read_bounded_rows). Carries the count so row numbering and
    the row ledger stay exact without materialising every empty tuple."""
    __slots__ = ("count",)

    def __init__(self, count: int):
        self.count = count


class _ReadResult(list):
    """A list of rows (tuples or _BlankRun markers) plus read disclosures."""
    trailing_blank_rows: int = 0
    notes: list


def _read_bounded_rows(ws) -> "_ReadResult":
    """Reads `ws` lazily and never silently stops early.

    TB-005 originally *stopped* reading after 500 consecutive blank rows so
    that a stray cell at A1048576 could not freeze the server. That also
    silently dropped any genuine data below a long blank gap (forensic defect
    P2: 10 of 20 rows lost while reconciliation reported "reconciles"). Now a
    long blank run is collapsed into one counted _BlankRun marker and reading
    continues to the end of the sheet: memory stays bounded (blank rows are
    not stored) and every populated row is read. Blank rows after the last
    populated row are reported as trailing_blank_rows, not as data.

    Columns are capped at _MAX_SCAN_COLUMNS only when the declared width is
    pathological, and the cap is disclosed in notes."""
    read_kwargs: dict = {"values_only": True}
    notes: list[str] = []
    try:
        declared_cols = ws.max_column
    except Exception:  # noqa: BLE001
        declared_cols = None
    if declared_cols and declared_cols > _MAX_SCAN_COLUMNS:
        read_kwargs["max_col"] = _MAX_SCAN_COLUMNS
        notes.append(f"sheet declares {declared_cols} columns; only the first {_MAX_SCAN_COLUMNS} were read")

    rows = _ReadResult()
    pending: list[tuple] = []  # blank rows not yet known to be trailing
    pending_count = 0
    for row in ws.iter_rows(**read_kwargs):
        if _row_looks_blank(row):
            pending_count += 1
            if pending_count <= _MAX_CONSECUTIVE_EMPTY_ROWS:
                pending.append(row)
            continue
        if pending_count:
            if pending_count <= _MAX_CONSECUTIVE_EMPTY_ROWS:
                rows.extend(pending)
            else:
                rows.append(_BlankRun(pending_count))
            pending, pending_count = [], 0
        rows.append(row)
    if pending_count > _MAX_CONSECUTIVE_EMPTY_ROWS:
        rows.trailing_blank_rows = pending_count
    else:
        rows.extend(pending)  # a short trailing run is still counted row-by-row, as before
    rows.notes = notes
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
        sd = _build_sheet_data(name, rows)
        sd.trailing_blank_rows = getattr(rows, "trailing_blank_rows", 0)
        sd.notes.extend(getattr(rows, "notes", []) or [])
        if sd.trailing_blank_rows:
            sd.notes.append(f"{sd.trailing_blank_rows} blank rows after the last populated row were not read as data")
        return sd
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


_CSV_ENCODINGS = ("utf-8-sig", "cp1252", "latin-1")


def _read_csv_rows(path: str) -> tuple[list[tuple], list[str]]:
    """CSV is read as raw rows and then goes through exactly the same header
    detection and row classification as a worksheet (forensic P13/P13c: the
    old path assumed the header was row 1, and a title line above it produced
    garbage columns). Encoding: UTF-8 (with or without BOM) first, then
    cp1252 -- the common Excel-on-Windows export -- and only then latin-1;
    whichever succeeded is disclosed. Delimiter: sniffed from the first 64 KiB
    among , ; tab | (P13b: European ';' exports became one column)."""
    import csv

    raw = Path(path).read_bytes()
    text, used = None, None
    for enc in _CSV_ENCODINGS:
        try:
            text, used = raw.decode(enc), enc
            break
        except UnicodeDecodeError:
            continue
    notes = [] if used == "utf-8-sig" else [f"file is not UTF-8; decoded as {used}"]
    sample = text[:65536]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ","
    if delimiter != ",":
        notes.append(f"delimiter detected as {delimiter!r}")
    rows = [tuple((c if c != "" else None) for c in r) for r in csv.reader(text.splitlines(), delimiter=delimiter)]
    return rows, notes


def _build_csv_sheet_data(path: str, source_stem: str | None = None) -> SheetData:
    name = source_stem or Path(path).stem
    rows, notes = _read_csv_rows(path)
    sd = _build_sheet_data(name, rows)
    sd.notes.extend(notes)
    return sd


def _is_blank_run(row) -> bool:
    return isinstance(row, _BlankRun)


def _row_width(row) -> int:
    if _is_blank_run(row):
        return 0
    return sum(1 for c in row if c is not None and str(c).strip())


def _physical_row_count(rows) -> int:
    return sum(r.count if _is_blank_run(r) else 1 for r in rows)


def _build_sheet_data(name: str, rows: list) -> SheetData:
    total = _physical_row_count(rows)
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
    header_physical = _physical_row_count(rows[:header_idx])  # 0-based physical row of the header
    columns = _dedupe_columns([_clean_header_cell(c, i) for i, c in enumerate(header_row)])
    candidate_rows = rows[header_idx + 1:]
    if not candidate_rows:
        return SheetData(name, header_physical, pd.DataFrame(columns=columns), skipped=True,
                          skip_reason="header row found but no data rows follow it",
                          raw_row_count=total)

    kept_rows, excluded_rows = _classify_and_filter_rows(name, header_physical, header_row, columns, candidate_rows)
    if not kept_rows:
        return SheetData(name, header_physical, pd.DataFrame(columns=columns), skipped=True,
                          skip_reason="header row found but every following row was blank or excluded",
                          raw_row_count=total, excluded_rows=excluded_rows)

    width = len(columns)
    kept_rows = [tuple(r[:width]) + (None,) * (width - len(r)) if len(r) != width else r for r in kept_rows]
    df = pd.DataFrame(kept_rows, columns=columns)
    df = df.astype("string")
    return SheetData(name, header_physical, df, raw_row_count=total, excluded_rows=excluded_rows)


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


_SUBTOTAL_PATTERN = re.compile(
    r"^(sub[\s-]?)?totals?\b.*$|^grand\s+totals?\b.*$|^sum(\s+of\b.*)?:?$|^summary:?$|^totals?:?$"
)
# A lone cell shaped like an identifier (CLM-00123, C2, 2024/0001) is a claim
# row with missing fields, not a banner (forensic P1).
_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z]{0,8}[-_/.# ]?\d[\w\-/.#]*$")


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
    """A total/subtotal/summary line. Two independent shapes:

    1. The FIRST populated cell is a total label ("Total", "TOTAL CLAIMS",
       "Grand total", "Sum", "Subtotal - GBP") and it is followed only by
       numbers or blanks. That is how a totals line looks at the bottom of a
       claims table whatever its width (forensic F2/P17: a "Total" row in a
       7-column sheet was ingested as a claim, doubling incurred).
    2. The original majority-blank shape with a total label anywhere among
       the few populated cells.

    A genuine claim whose free text merely contains the word "total"
    ("Total Logistics Ltd" in the insured column, after a claim reference)
    matches neither: its first populated cell is the claim reference."""
    non_blank = [c for c in row if _normalize_cell(c) != ""]
    if not non_blank:
        return False
    first = _normalize_cell(non_blank[0])
    if _SUBTOTAL_PATTERN.match(first) and all(
        isinstance(c, (int, float)) or _looks_numeric_text(c) for c in non_blank[1:]
    ):
        return True
    if len(non_blank) * 2 > len(row):
        return False
    return any(_SUBTOTAL_PATTERN.match(_normalize_cell(c)) for c in non_blank)


def _looks_numeric_text(value: object) -> bool:
    if isinstance(value, (int, float)):
        return True
    return _parse_amount_cell(str(value)) is not None


def _row_is_title(row: tuple) -> bool:
    """TB-007b: a section banner embedded mid-sheet -- 'Table B — GBP
    claims', 'UNDERWRITING YEAR 2023' -- has exactly one populated cell,
    holding text, with every other cell in the row genuinely blank.
    Distinct from a subtotal line (which names a total/sum explicitly
    among a handful of populated cells): this is any row shaped like a
    lone banner, whatever it says."""
    populated = [c for c in row if _normalize_cell(c) != ""]
    if len(populated) != 1 or not isinstance(populated[0], str):
        return False
    return not _IDENTIFIER_PATTERN.match(populated[0].strip())


def _classify_row(row: tuple, header_row: tuple) -> tuple[str | None, str | None]:
    """Returns (reason, detail) for a row that should be excluded before
    mapping/validation ever sees it, or (None, None) for a genuine data
    row. Checked in this order: blank first (cheapest and unambiguous),
    then an exact repeated-header match (specific), then the subtotal
    heuristic, then the lone-title-cell shape (broadest two last) -- so
    a row that happens to match the header is never also reported as a
    subtotal or title."""
    if _row_is_blank(row):
        return "blank", "row is entirely blank"
    if _row_matches_header(row, header_row):
        return "repeated_header", "row repeats the sheet's own header text"
    if _row_is_subtotal(row):
        return "subtotal", "row looks like a subtotal/total line, not a claim"
    if _row_is_title(row):
        return "title", "row is a section title/banner, not a claim"
    return None, None


def _classify_and_filter_rows(
    sheet_name: str, header_idx: int, header_row: tuple, columns: list[str], candidate_rows: list,
) -> tuple[list[tuple], list[ExcludedRow]]:
    """header_idx is the header's 0-based PHYSICAL row; candidate_rows may
    contain _BlankRun markers, which advance the row counter by their count
    and are recorded as one ledger entry each."""
    kept: list[tuple] = []
    excluded: list[ExcludedRow] = []
    physical = header_idx + 1  # 0-based physical index of the next candidate row
    for row in candidate_rows:
        if _is_blank_run(row):
            excluded.append(ExcludedRow(sheet_name=sheet_name, row_number=physical + 1, reason="blank_run",
                                         detail=f"{row.count} consecutive blank rows (rows {physical + 1}"
                                                f"-{physical + row.count})",
                                         values={}, count=row.count))
            physical += row.count
            continue
        reason, detail = _classify_row(row, header_row)
        if reason is None:
            kept.append(row)
        else:
            values = {columns[i]: ("" if i >= len(row) or row[i] is None else str(row[i]))
                      for i in range(len(columns))}
            excluded.append(ExcludedRow(sheet_name=sheet_name, row_number=physical + 1,
                                         reason=reason, detail=detail, values=values))
        physical += 1
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
        if _is_blank_run(row):
            continue
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
        width = _row_width(row)
        if width > best_width:
            best_idx, best_width = i, width

    if best_idx is None or best_width < MIN_HEADER_MATCHES:
        return None

    following = rows[best_idx + 1: best_idx + 1 + HEADER_SCAN_ROWS]
    has_comparable_data = any(
        _row_width(row) >= max(2, best_width // 2)
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


_AMBIGUOUS = object()  # sentinel: the separator convention cannot be decided from this cell alone


def _parse_amount_cell(text: str, decimal_sep: str | None = None, allow_ambiguous: bool = False):
    """'€900,000.00' -> 900000.0, '£1,234.56' -> 1234.56, '1.234,56' -> 1234.56,
    '(500.00)' -> -500.0, '1.234.567' -> 1234567.0. Returns None for empty or
    unreadable text.

    '1.234' (a single dot followed by exactly three digits) is genuinely
    ambiguous: 1.234 in a UK/US file, 1234 in a European one (forensic P6).
    It is resolved only by `decimal_sep` -- evidence from the *same column*,
    see _column_decimal_separator -- and otherwise returns _AMBIGUOUS when
    allow_ambiguous is set (the column parser turns that into "unparseable",
    never a guessed number) or None. A single comma followed by three digits
    ('1,234') remains thousands grouping unless the column proves a decimal
    comma: a three-decimal money value written with a comma is not a
    convention any market uses."""
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

    n_comma, n_dot = t.count(","), t.count(".")
    if n_comma and n_dot:
        if t.rfind(",") > t.rfind("."):
            t = t.replace(".", "").replace(",", ".")  # comma is the decimal separator (1.234,56)
        else:
            t = t.replace(",", "")  # dot is the decimal separator (1,234.56)
    elif n_comma:
        parts = t.split(",")
        if n_comma == 1 and len(parts[1]) in (1, 2):
            t = t.replace(",", ".")  # 12,5 / 1234,56: decimal comma
        elif n_comma == 1 and len(parts[1]) == 3 and decimal_sep == ",":
            t = t.replace(",", ".")  # column proves a decimal comma
        else:
            t = t.replace(",", "")  # thousands grouping
    elif n_dot > 1:
        t = t.replace(".", "")  # 1.234.567: dots can only be grouping
    elif n_dot == 1:
        frac = t.split(".")[1]
        if len(frac) == 3 and frac.isdigit() and t.split(".")[0].isdigit():
            if decimal_sep == ",":
                t = t.replace(".", "")
            elif decimal_sep != ".":
                return _AMBIGUOUS if allow_ambiguous else None

    try:
        value = float(t)
    except ValueError:
        return None
    return -value if negative else value


_DOT_DECIMAL_EVIDENCE = re.compile(r"\d,\d{3}\.\d|^[-(]?[^\d]*\d+\.\d{1,2}\)?$|\.\d{4,}\)?$")
_COMMA_DECIMAL_EVIDENCE = re.compile(r"\d\.\d{3},\d|^[-(]?[^\d]*\d+,\d{1,2}\)?$")


def _column_decimal_separator(texts: pd.Series, scaled: bool) -> str | None:
    """'.' or ',' when unambiguous cells in the SAME column prove the
    convention; None when there is no evidence or the evidence conflicts. A
    column with a scale suffix ('(USD m)') conventionally carries decimal
    fractions such as 36.686, so a dot is decimal there."""
    dot = comma = False
    for v in texts.dropna().astype(str):
        v = "".join(unicodedata.normalize("NFKC", v).split())
        if not dot and _DOT_DECIMAL_EVIDENCE.search(v):
            dot = True
        if not comma and _COMMA_DECIMAL_EVIDENCE.search(v):
            comma = True
        if dot and comma:
            return None
    if dot:
        return "."
    if comma:
        return ","
    return "." if scaled else None


def _parse_amount_series(series: pd.Series, scaled: bool = False) -> tuple[pd.Series, pd.Series]:
    """Returns (parsed float values, unparseable mask). `series` is
    expected to already have empty strings normalized to NA by the
    caller, so `notna()` reliably means "the source cell had text".
    Ambiguous cells that the column cannot resolve count as unparseable."""
    had_text = series.notna()
    sep = _column_decimal_separator(series, scaled)

    def one(v):
        if pd.isna(v):
            return None
        r = _parse_amount_cell(str(v), decimal_sep=sep, allow_ambiguous=True)
        return None if r is _AMBIGUOUS else r

    parsed = series.map(one)
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


_UNAMBIGUOUS_DATE_FORMATS = ["%Y-%m-%d", "%Y/%m/%d", "%d-%b-%Y", "%Y-%m-%d %H:%M:%S", "%d %b %Y", "%d %B %Y"]
_DAY_FIRST_FORMATS = {"%d/%m/%Y", "%d.%m.%Y"}
_MONTH_FIRST_FORMATS = {"%m/%d/%Y"}


def _best_date_parse(series: pd.Series, notes: list[str] | None = None) -> pd.Series:
    """Pick the single explicit format that parses the most values in the
    column; values it could not parse are then tried ONLY against
    unambiguous formats (ISO, month names), then a flexible parse that keeps
    the chosen day/month order, then Excel serial numbers.

    Forensic P5: previously, if one value failed the winning format, the
    whole column was re-parsed with a month-first flexible parser, silently
    turning 03/04/2024 (3 April) into 4 March for every row. A value already
    parsed is now never re-parsed. When every value is ambiguous (all days
    <= 12) the order chosen is disclosed in `notes`."""
    non_null = series.dropna()
    if non_null.empty:
        return pd.to_datetime(series, errors="coerce")

    target = int(non_null.shape[0])
    best_parsed, best_score, best_fmt = None, -1, None
    for fmt in _DATE_FORMATS:
        parsed = pd.to_datetime(series, format=fmt, errors="coerce")
        score = int(parsed.notna().sum())
        if score > best_score:
            best_score, best_parsed, best_fmt = score, parsed, fmt
        if best_score == target:
            break

    if best_fmt in _DAY_FIRST_FORMATS | _MONTH_FIRST_FORMATS and best_score > 0:
        other = "%m/%d/%Y" if best_fmt in _DAY_FIRST_FORMATS else "%d/%m/%Y"
        alt = pd.to_datetime(series, format=other.replace("/", best_fmt[2]) if best_fmt == "%d.%m.%Y" else other,
                             errors="coerce")
        both = best_parsed.notna() & alt.notna()
        if notes is not None and both.sum() == best_parsed.notna().sum():
            order = "day/month" if best_fmt in _DAY_FIRST_FORMATS else "month/day"
            notes.append(f"every date in this column is ambiguous between day/month and month/day; "
                         f"read as {order} -- confirm with the sender")

    result = best_parsed.copy()
    missing = result.isna() & series.notna()
    for fmt in _UNAMBIGUOUS_DATE_FORMATS:
        if not missing.any():
            break
        p = pd.to_datetime(series[missing], format=fmt, errors="coerce")
        result.loc[p.index[p.notna()]] = p[p.notna()]
        missing = result.isna() & series.notna()
    if missing.any():
        dayfirst = best_fmt not in _MONTH_FIRST_FORMATS
        p = pd.to_datetime(series[missing], format="mixed", dayfirst=dayfirst, errors="coerce")
        result.loc[p.index[p.notna()]] = p[p.notna()]
        missing = result.isna() & series.notna()
    if missing.any():
        serial_parsed = _parse_excel_serial_dates(series[missing])
        if serial_parsed.notna().any():
            result.loc[serial_parsed.index[serial_parsed.notna()]] = serial_parsed[serial_parsed.notna()]
    return result


class MappingConflictError(ValueError):
    """Two source columns were bound to the same canonical field. Resolving
    this by letting the last column win (the old behaviour, forensic P7)
    silently discards data; it must be decided by a person."""


TRANSFORM_RULE_VERSION = "amount-transform/2026-09-24.1"


def apply_mapping(raw: pd.DataFrame, mapping: dict[str, str], sheet_name: str = "") -> pd.DataFrame:
    """mapping: {source_column_name: field_code}. Source columns absent
    from the mapping are dropped; canonical fields absent from the mapping
    come back as all-null columns so downstream code can always rely on
    every field code being present as a column -- validation/report
    consumers check the per-sheet mapping state before treating a null cell
    as "genuinely blank" rather than "column was never mapped".

    Returned DataFrame .attrs:
      "transforms":  one record per amount column -- source header, field,
                     currency read from the header, scale token, multiplier,
                     rule version. Nothing is scaled or assigned a currency
                     without an entry here (auditable, never AI-derived).
      "parse_notes": disclosures (ambiguous date order, mixed currencies).

    Raises MappingConflictError if two source columns target one field."""
    targets: dict[str, list[str]] = {}
    for source_col, code in mapping.items():
        if source_col in raw.columns and code in FIELDS_BY_CODE:
            targets.setdefault(code, []).append(source_col)
    conflicts = {c: cols for c, cols in targets.items() if len(cols) > 1}
    if conflicts:
        detail = "; ".join(f"{c} <- {cols}" for c, cols in conflicts.items())
        raise MappingConflictError(f"sheet {sheet_name!r}: more than one source column bound to a field: {detail}")

    out = pd.DataFrame(index=raw.index)
    unparseable_cols: dict[str, pd.Series] = {}
    transforms: list[dict] = []
    notes: list[str] = []
    column_currencies: set[str] = set()

    for source_col, code in mapping.items():
        if source_col not in raw.columns or code not in FIELDS_BY_CODE:
            continue
        spec = FIELDS_BY_CODE[code]
        series = raw[source_col].astype("string").str.strip()
        series = series.mask(series == "", pd.NA)

        if spec.dtype == "date":
            col_notes: list[str] = []
            out[code] = _best_date_parse(series, col_notes)
            notes.extend(f"{source_col!r}: {n}" for n in col_notes)
        elif spec.dtype == "decimal":
            _, suffix = split_trailing_parenthetical(source_col)
            scale = parse_scale_suffix(suffix)
            parsed, unparseable = _parse_amount_series(series, scaled=bool(scale))
            # TB-003: "Paid (USD m)" states every value in millions. Applied
            # before storage so every consumer sees the true magnitude, and
            # recorded in "transforms" so the multiplier is auditable.
            if scale:
                parsed = parsed * scale
            ccy = parse_currency_suffix(suffix, VALID_CURRENCY_CODES)
            if ccy:
                column_currencies.add(ccy)
            transforms.append({
                "source_column": source_col, "field_code": code, "header_suffix": suffix,
                "currency_from_header": ccy, "scale_multiplier": scale or 1.0,
                "rule": "header-suffix", "rule_version": TRANSFORM_RULE_VERSION,
            })
            out[code] = parsed
            unparseable_cols[code] = unparseable
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

    # Forensic P9: "Paid (GBP)" + "Reserve (EUR)" used to be summed as if one
    # currency. Different header currencies on one sheet make every row's
    # arithmetic NOT_EVALUABLE and no single currency is assigned.
    mixed = len(column_currencies) > 1
    out["_mixed_currency"] = pd.Series(mixed, index=out.index, dtype=bool)
    if mixed:
        notes.append(f"amount columns declare different currencies {sorted(column_currencies)}; "
                     "no currency assigned and arithmetic is not evaluable")
    elif column_currencies and CURRENCY_CODE not in mapping.values() and len(out):
        # The header itself states the currency ("Paid Amount (GBP)") and the
        # sheet has no Currency column: read, not guessed, and recorded.
        (hint,) = tuple(column_currencies)
        out[CURRENCY_CODE] = pd.array([hint] * len(out), dtype="string")
        notes.append(f"currency {hint} taken from amount column headers (no currency column on the sheet)")

    from .schema import SOURCE_SHEET_CODE
    out[SOURCE_SHEET_CODE] = pd.array([sheet_name] * len(out), dtype="string")

    result = out[[f.code for f in FIELDS] + [SOURCE_SHEET_CODE, "_mixed_currency"]
                 + [unparseable_flag_column(c) for c in decimal_codes]]
    result.attrs["transforms"] = transforms
    result.attrs["parse_notes"] = notes
    return result


def _empty_column(dtype: str, length: int, index) -> pd.Series:
    """An all-null column of the right dtype for a field the caller's
    mapping doesn't cover, so pandera can coerce it like any other."""
    if dtype == "date":
        return pd.Series([pd.NaT] * length, index=index, dtype="datetime64[ns]")
    if dtype == "decimal":
        return pd.Series([np.nan] * length, index=index, dtype="float64")
    return pd.Series([pd.NA] * length, index=index, dtype="string")
