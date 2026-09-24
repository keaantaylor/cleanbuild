"""Phase 5 (+ fix spec 3.3/3.6/3.7/3.9): completeness / health report.

Produces the sales artifact from the brief: a one-page grade (1-5) a
non-technical claims handler can read in under two minutes, backed by
full row-level detail for anyone who wants to dig in.

Scoring: the brief doesn't specify an exact formula, only that this
should "mirror industry-standard scoring logic" (per-field completeness
scored against an agreed skeleton, the GreenKite-style approach the brief
is built around). The composite score implemented here is:

    composite = average field completeness %
                - 1.0 x (% of rows with at least one validation exception)
                - 0.5 x (% of rows flagged as a duplicate)

clipped to [0, 100] and banded into a 1-5 grade, but ONLY over fields that
were actually mapped somewhere in the file -- a field nobody's sheet ever
had a column for is reported as "not found", not averaged in as a 0%
(fix spec D3/3.3). Coverage (how much of the source file was actually
read and mapped) is tracked and surfaced separately: a file where sheets
were skipped or a required field was never mapped gets a visible caveat
rather than a clean-looking low score that reads as "bad data" when the
real story is "the pipeline didn't see all of it" (fix spec D8/3.9).

Weights: exceptions are penalized twice as heavily as duplicate flags,
because they represent data that is actively wrong (arithmetic doesn't
tie out, a mandatory field is blank) whereas a duplicate flag is a
"check this" signal, not necessarily an error -- but not so heavily that
a file built with realistic, bounded and roughly-independent error rates
per category (a bordereau with a mandatory-field issue on ~20% of rows
and an arithmetic issue on ~12% of a *different* set of rows is messy,
not worthless) collapses toward a near-zero score. That collapse is
itself a defect (fix spec D8): a near-zero score should read as "check
the pipeline", not be indistinguishable from genuinely unusable data.
This is a documented heuristic, not a standards body's formula -- tune
the weights once real client bordereaux give a feel for what "good"
looks like in practice.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import pandas as pd

from . import schema
from .ingest import EXCLUDED_ROW_REASON_LABELS, ExcludedRow
from .validation import ValidationResult

# A sheet's mapping outcome, one of four (never collapsed into a single
# "skipped" bucket -- Section 9/11 of the audit brief): "mapped" (every
# unconditionally-required field found a column), "partial" (some fields
# mapped, at least one required field didn't), "unmapped" (data is
# present and retained, but not one field could be mapped -- see
# ingest._structural_header_row), "empty" (no plausible tabular shape at
# all, or a crash reading the sheet -- see SheetAuditRecord.reason for
# which).
SheetMappingStatus = Literal["mapped", "partial", "unmapped", "empty", "error", "non_claim_summary"]

# TB-001: a sheet is only a claims register if it can identify individual
# claims -- binding only monetary columns (a per-sheet or per-LOB summary/
# dashboard tab, common in real bordereaux) must never be silently
# emitted as claim rows. Requiring Claim Reference, or failing that
# Insured Name plus at least one date, mirrors how a human reviewer would
# tell "this is a claims register" from "this is a rollup of one".
_IDENTITY_DATE_CODES = (schema.LOSS_DATE_CODE, schema.NOTIFIED_DATE_CODE)
_MONETARY_CODES = schema.MONETARY_CODES


def _has_claim_identity(mapped_field_codes: list[str]) -> bool:
    codes = set(mapped_field_codes)
    if schema.CLAIM_REF_CODE in codes:
        return True
    return schema.INSURED_NAME_CODE in codes and bool(codes & set(_IDENTITY_DATE_CODES))

def _looks_like_summary(mapped_field_codes: list[str], source_column_count: int | None) -> bool:
    """TB-001 excluded any sheet with monetary columns but no claim
    identity. Forensic F3: a French-headed claims sheet where only
    "Réserve" happened to match an alias (1 of 10 columns) was excluded as a
    "summary" -- 50% of a workbook's claims disappeared under a grade-5
    report. A sheet is only auto-classified as a summary when the columns we
    recognised make up at least half of its columns (a rollup is mostly
    amounts). Anything else stays in the claim set as "partial", visibly
    needing mapping review. Without a column count (legacy callers), keep the
    original TB-001 behaviour."""
    if source_column_count is None or source_column_count <= 0:
        return True
    return len(set(mapped_field_codes)) * 2 >= source_column_count


GRADE_LABELS = {5: "Excellent", 4: "Good", 3: "Fair", 2: "Poor", 1: "Very poor"}
EXCEPTION_WEIGHT = 1.0
DUPLICATE_WEIGHT = 0.5

REQUIREMENT_LABELS = {
    "required": "Required",
    "optional": "Optional",
    "conditional_pair": "Conditional pair",
    "reconciled": "Reconciled (not standalone-required)",
}


@dataclass
class WorkbookCoverage:
    """What fraction of the source file the pipeline actually read and
    mapped -- the fix spec 3.9 "assessed N of M rows across K of J
    sheets" line, plus the per-sheet mapping state fix spec 3.3 needs to
    tell "unmapped" apart from "mapped but blank"."""
    sheets_total: int
    sheets_processed: int
    skipped_sheets: list[tuple[str, str]]  # (sheet_name, reason)
    rows_total: int
    rows_assessed: int
    sheet_field_state: dict[str, dict[str, str]] = field(default_factory=dict)
    excluded_rows: list[ExcludedRow] = field(default_factory=list)
    sheet_audit: list[SheetAuditRecord] = field(default_factory=list)
    reconciliation: "ReconciliationSummary | None" = None
    sheet_transforms: dict[str, list[dict]] = field(default_factory=dict)  # amount-column currency/scale audit
    sheet_notes: dict[str, list[str]] = field(default_factory=dict)  # read/parse disclosures per sheet

    @staticmethod
    def single_sheet(row_count: int, sheet_name: str = "") -> "WorkbookCoverage":
        """Coverage for the simple single-DataFrame call path (one file,
        already-resolved mapping, nothing skipped)."""
        return WorkbookCoverage(
            sheets_total=1, sheets_processed=1, skipped_sheets=[],
            rows_total=row_count, rows_assessed=row_count,
            sheet_field_state={},
        )

    @property
    def fully_covered(self) -> bool:
        return self.sheets_processed == self.sheets_total and self.rows_assessed == self.rows_total

    @property
    def excluded_row_counts(self) -> dict[str, int]:
        """{reason: count} -- e.g. {"blank": 2, "repeated_header": 1}."""
        counts: dict[str, int] = {}
        for er in self.excluded_rows:
            counts[er.reason] = counts.get(er.reason, 0) + er.count
        return counts

    @property
    def unmapped_data_sheets(self) -> list[str]:
        """Sheet names that were retained -- not skipped; their rows are
        in canonical/rows_assessed like any other sheet -- but whose
        confirmed mapping left every single canonical field unmapped. The
        data was never dropped, but nothing about it could be validated
        or scored, and that must be a visible, explained fact rather than
        something a reviewer has to infer from an otherwise-unremarkable
        low completeness number. General mechanism: driven entirely by
        sheet_field_state, which every non-skipped sheet already
        populates -- no per-file or per-sheet-name special-casing."""
        return sorted(
            name for name, state in self.sheet_field_state.items()
            if state and all(v == "unmapped" for v in state.values())
        )

    @property
    def non_claim_summary_sheets(self) -> list[str]:
        """TB-001: sheets recognised as summary/aggregate data (monetary
        columns bound, no claim identity) and therefore excluded from the
        claim set entirely -- never silently dropped, always named here
        so a reviewer sees that TrueBlind understood the sheet and chose
        not to count it, rather than inferring an inflated total or a
        missing sheet."""
        return sorted(rec.sheet_name for rec in self.sheet_audit if rec.status == "non_claim_summary")


@dataclass
class SheetAuditRecord:
    """Answers, for one worksheet, every question Section 10 of the audit
    brief asks: was it detected, was it empty, which row was the header,
    how many source rows existed, how many fields mapped (and which),
    why it landed in its final status, and how many of its rows were
    processed vs. rejected before mapping. Built once per sheet from the
    same SheetData / sheet_field_state every other consumer already
    reads -- classification is entirely general (driven by field counts
    and schema.REQUIRED_CODES), never a per-file or per-sheet-name
    special case."""
    sheet_name: str
    is_empty: bool
    header_row_index: int | None
    source_row_count: int
    rows_processed: int
    rows_rejected: int
    fields_mapped: int
    fields_total: int
    mapped_field_codes: list[str]
    unmapped_field_codes: list[str]
    status: SheetMappingStatus
    reason: str

    @property
    def requires_review(self) -> bool:
        return self.status in ("unmapped", "partial", "error")


def classify_sheet_status(
    skipped: bool, skip_reason: str | None, mapped_field_codes: list[str],
    source_column_count: int | None = None,
) -> tuple[SheetMappingStatus, str]:
    """The general mechanism behind SheetAuditRecord.status -- a sheet
    with 0 mapped fields is explicitly NOT the same thing as an empty
    sheet (Section 9), and a sheet missing some but not all required
    fields is its own "partial" state rather than being silently folded
    into either "mapped" or "unmapped"."""
    if skipped:
        is_crash = bool(skip_reason and skip_reason.startswith("error while reading"))
        return ("error" if is_crash else "empty"), (skip_reason or "sheet contained no tabular data")
    if not mapped_field_codes:
        return "unmapped", "no recognized business fields were detected in the header row"
    if (not _has_claim_identity(mapped_field_codes) and set(mapped_field_codes) & set(_MONETARY_CODES)
            and _looks_like_summary(mapped_field_codes, source_column_count)):
        return "non_claim_summary", (
            "binds only monetary column(s) with no claim reference (or insured name + date) -- "
            "recognised as a summary/aggregate sheet, not a claims register, and excluded from the claim set"
        )
    if all(code in mapped_field_codes for code in schema.REQUIRED_CODES):
        return "mapped", "every unconditionally-required field was mapped"
    missing = [schema.FIELDS_BY_CODE[c].name for c in schema.REQUIRED_CODES if c not in mapped_field_codes]
    return "partial", f"{len(mapped_field_codes)} field(s) mapped, but still missing: {', '.join(missing)}"


@dataclass
class ReconciliationSummary:
    """Section 5's row-count reconciliation, computed from two
    independent sources so a real discrepancy is actually catchable: the
    per-sheet SheetAuditRecords give source_data_rows directly from the
    raw sheet data (rows kept + rows rejected, before mapping ever runs),
    while mapped/unmapped/rejected are aggregated from the same records
    the other direction. Under the current architecture these must
    agree by construction (see reconciles/discrepancy) -- if a future
    change ever breaks that invariant, this is what would catch it,
    rather than the two numbers silently drifting apart."""
    source_worksheets: int
    source_data_rows: int
    skipped_sheet_rows: int  # rows on sheets classified empty/error -- never a real claim, reported separately, never silently folded into any total above
    mapped_rows: int
    unmapped_rows: int
    rejected_rows: int
    duplicate_rows: int
    exported_rows: int
    rows_requiring_review: int
    non_claim_summary_rows: int = 0  # TB-001: rows on recognised-but-excluded summary sheets

    @property
    def discrepancy(self) -> int:
        return self.source_data_rows - (
            self.mapped_rows + self.unmapped_rows + self.rejected_rows + self.non_claim_summary_rows
        )

    @property
    def reconciles(self) -> bool:
        return self.discrepancy == 0

    def as_lines(self) -> list[str]:
        lines = [
            f"Source worksheets: {self.source_worksheets}",
            f"Source data rows: {self.source_data_rows}",
            f"Mapped rows: {self.mapped_rows}",
            f"Unmapped rows: {self.unmapped_rows}",
            f"Duplicate rows: {self.duplicate_rows}",
            f"Rejected rows: {self.rejected_rows}",
            f"Exported rows: {self.exported_rows}",
            f"Rows requiring review: {self.rows_requiring_review}",
        ]
        if self.non_claim_summary_rows:
            lines.append(
                f"(Excluded from the above: {self.non_claim_summary_rows} row(s) on sheet(s) "
                "recognised as summaries/aggregates, not claims)"
            )
        if self.skipped_sheet_rows:
            lines.append(f"(Excluded from the above: {self.skipped_sheet_rows} row(s) on empty/unreadable sheets)")
        if not self.reconciles:
            lines.append(
                f"RECONCILIATION MISMATCH: source data rows ({self.source_data_rows}) != "
                f"mapped + unmapped + rejected ({self.mapped_rows + self.unmapped_rows + self.rejected_rows}), "
                f"difference of {self.discrepancy}"
            )
        return lines


@dataclass
class FieldCompleteness:
    code: str
    name: str
    requirement: str  # schema.Requirement
    present: int
    denominator: int  # rows where this field was actually mapped to a source column
    total: int  # rows assessed file-wide, for reference

    @property
    def never_mapped(self) -> bool:
        return self.denominator == 0

    @property
    def pct(self) -> float | None:
        if self.denominator == 0:
            return None
        return 100.0 * self.present / self.denominator


@dataclass
class HealthReport:
    source_name: str
    total_claims: int
    field_completeness: list[FieldCompleteness]
    arithmetic_mismatches: int
    arithmetic_not_evaluable: int
    missing_mandatory_rows: int
    date_exceptions: int
    currency_exceptions: int
    exact_duplicates: int
    probable_duplicates: int
    period_unknown_repeats: int  # same ref on different sheets with no reporting period: review
    overall_completeness_pct: float
    exception_rate_pct: float
    duplicate_rate_pct: float
    composite_score: float
    grade: int
    grade_label: str
    coverage: WorkbookCoverage
    unmapped_required_fields: list[str]

    @property
    def score_reliable(self) -> bool:
        # A score is only presented as reliable when every sheet was read and
        # bound well enough to be assessed: a "partial" sheet (required fields
        # unmapped) contributes rows the checks cannot see (forensic F3).
        return (
            self.coverage.fully_covered
            and not self.unmapped_required_fields
            and not self.coverage.unmapped_data_sheets
            and not any(rec.requires_review for rec in self.coverage.sheet_audit)
        )


def _grade_from_composite(score: float) -> int:
    if score >= 90:
        return 5
    if score >= 75:
        return 4
    if score >= 55:
        return 3
    if score >= 35:
        return 2
    return 1


def _mapped_mask(df: pd.DataFrame, field_code: str, sheet_field_state: dict[str, dict[str, str]]) -> pd.Series:
    if not sheet_field_state or schema.SOURCE_SHEET_CODE not in df.columns:
        return pd.Series(True, index=df.index)

    def is_mapped(sheet_name: object) -> bool:
        return sheet_field_state.get(sheet_name, {}).get(field_code) != "unmapped"

    return df[schema.SOURCE_SHEET_CODE].map(is_mapped).fillna(True).astype(bool)


def build_health_report(canonical: pd.DataFrame, validation_result: ValidationResult,
                         duplicates: pd.DataFrame, source_name: str = "",
                         coverage: WorkbookCoverage | None = None) -> HealthReport:
    total = len(canonical)
    coverage = coverage or WorkbookCoverage.single_sheet(total, source_name)
    exceptions = validation_result.exceptions

    field_stats = []
    for f in schema.FIELDS:
        mapped = _mapped_mask(canonical, f.code, coverage.sheet_field_state)
        denominator = int(mapped.sum())
        present = int((canonical[f.code].notna() & mapped).sum())
        field_stats.append(FieldCompleteness(f.code, f.name, f.requirement, present, denominator, total))

    scored_fields = [fs for fs in field_stats if not fs.never_mapped]
    overall_completeness = (
        sum(fs.pct for fs in scored_fields) / len(scored_fields) if scored_fields else 0.0
    )

    unmapped_required_fields = [
        fs.name for fs in field_stats if fs.never_mapped and fs.requirement == "required"
    ]

    missing_mandatory_rows = (
        exceptions.loc[exceptions["rule"] == "missing_mandatory_field", "row_index"].nunique()
        if not exceptions.empty else 0
    )
    date_exceptions = int(exceptions["rule"].isin(["date_order", "date_in_future"]).sum()) if not exceptions.empty else 0
    currency_exceptions = (
        int(exceptions["rule"].isin(["invalid_currency", "currency_inconsistency"]).sum())
        if not exceptions.empty else 0
    )

    exact_dupes = int((duplicates["match_type"] == "exact_duplicate").sum()) if not duplicates.empty else 0
    probable_dupes = int((duplicates["match_type"] == "probable_duplicate").sum()) if not duplicates.empty else 0
    period_unknown = int((duplicates["match_type"] == "repeat_period_unknown").sum()) if not duplicates.empty else 0

    exception_rows = exceptions["row_index"].nunique() if not exceptions.empty else 0
    exception_rate = 100.0 * exception_rows / total if total else 0.0

    dup_rows: set = set()
    if not duplicates.empty:
        dup_rows = set(duplicates["row_index_a"]) | set(duplicates["row_index_b"])
    duplicate_rate = 100.0 * len(dup_rows) / total if total else 0.0

    composite = overall_completeness - (EXCEPTION_WEIGHT * exception_rate) - (DUPLICATE_WEIGHT * duplicate_rate)
    composite = max(0.0, min(100.0, composite))
    grade = _grade_from_composite(composite)

    return HealthReport(
        source_name=source_name,
        total_claims=total,
        field_completeness=field_stats,
        arithmetic_mismatches=validation_result.arithmetic_mismatch_count,
        arithmetic_not_evaluable=validation_result.arithmetic_not_evaluable_count,
        missing_mandatory_rows=int(missing_mandatory_rows),
        date_exceptions=date_exceptions,
        currency_exceptions=currency_exceptions,
        exact_duplicates=exact_dupes,
        probable_duplicates=probable_dupes,
        period_unknown_repeats=period_unknown,
        overall_completeness_pct=overall_completeness,
        exception_rate_pct=exception_rate,
        duplicate_rate_pct=duplicate_rate,
        composite_score=composite,
        grade=grade,
        grade_label=GRADE_LABELS[grade],
        coverage=coverage,
        unmapped_required_fields=unmapped_required_fields,
    )


def _coverage_line(coverage: WorkbookCoverage) -> str:
    line = (f"Assessed {coverage.rows_assessed} of {coverage.rows_total} total rows "
            f"across {coverage.sheets_processed} of {coverage.sheets_total} sheets/tabs in the source file.")
    counts = coverage.excluded_row_counts
    if counts:
        parts = [f"{n} {EXCLUDED_ROW_REASON_LABELS.get(reason, reason)}{'s' if n != 1 else ''}"
                 for reason, n in sorted(counts.items())]
        total_excluded = sum(counts.values())
        line += (f" {total_excluded} additional row{'s' if total_excluded != 1 else ''} excluded before "
                 f"assessment ({', '.join(parts)}) -- not counted as claims, not flagged as errors.")
    unmapped_sheets = coverage.unmapped_data_sheets
    if unmapped_sheets:
        line += (f" {len(unmapped_sheets)} sheet(s) retained with every column unmapped "
                 f"({', '.join(unmapped_sheets)}) -- their rows are counted above, but not evaluable "
                 f"until mapped.")
    ncs_sheets = coverage.non_claim_summary_sheets
    if ncs_sheets:
        line += (f" {len(ncs_sheets)} sheet(s) recognised as summary/aggregate data, not a claims "
                 f"register ({', '.join(ncs_sheets)}) -- excluded from the claim set entirely.")
    return line


def _reliability_caveat(health: HealthReport) -> str | None:
    if health.score_reliable:
        return None
    reasons = []
    if not health.coverage.fully_covered:
        reasons.append("not every sheet/row was assessed")
    if health.unmapped_required_fields:
        reasons.append(f"required field(s) left unmapped: {', '.join(health.unmapped_required_fields)}")
    review = [rec.sheet_name for rec in health.coverage.sheet_audit if rec.status in ("partial", "error")]
    if review:
        reasons.append(f"sheet(s) needing mapping review: {', '.join(review)}")
    if health.coverage.unmapped_data_sheets:
        reasons.append(
            f"sheet(s) retained but entirely unmapped: {', '.join(health.coverage.unmapped_data_sheets)}"
        )
    return "Score not fully reliable — " + "; ".join(reasons) + ". See coverage note above."


def write_health_report_excel(health: HealthReport, exceptions: pd.DataFrame,
                               duplicates: pd.DataFrame, canonical: pd.DataFrame,
                               out_path: str | Path,
                               unmapped_sheet_raw: dict[str, pd.DataFrame] | None = None) -> None:
    """One workbook: a readable Summary sheet, plus full row-level detail
    (exceptions, duplicates, and the underlying data) for anyone who wants
    to dig in.

    unmapped_sheet_raw: {sheet_name: raw DataFrame}, one entry per sheet
    whose SheetAuditRecord.status is "unmapped" -- its ORIGINAL headers
    and values, not the canonical (all-null-for-this-sheet) columns.
    Section 12: an unmapped sheet's rows already appear in "Full data"
    with every canonical field blank; without this, the actual received
    values (what the source file's "ZX_001"-style columns actually said)
    would never appear anywhere in the export at all, silently making
    the data unrecoverable even though the row count is preserved."""
    out_path = Path(out_path)

    summary_rows = [
        ["Source file", health.source_name],
        ["Coverage", _coverage_line(health.coverage)],
    ]
    if health.coverage.skipped_sheets:
        for name, reason in health.coverage.skipped_sheets:
            summary_rows.append([f"  Skipped sheet: {name}", reason])
    caveat = _reliability_caveat(health)
    if caveat:
        summary_rows.append(["Reliability caveat", caveat])
    recon = health.coverage.reconciliation
    if recon:
        summary_rows.append(["", ""])
        summary_rows += [
            ["Source worksheets", recon.source_worksheets],
            ["Source data rows", recon.source_data_rows],
            ["Mapped rows", recon.mapped_rows],
            ["Unmapped rows", recon.unmapped_rows],
            ["Duplicate rows", recon.duplicate_rows],
            ["Rejected rows", recon.rejected_rows],
            ["Exported rows", recon.exported_rows],
            ["Rows requiring review", recon.rows_requiring_review],
        ]
        if recon.skipped_sheet_rows:
            summary_rows.append(
                ["  (excluded from the above)", f"{recon.skipped_sheet_rows} row(s) on empty/unreadable sheets"]
            )
        if not recon.reconciles:
            summary_rows.append(["RECONCILIATION MISMATCH", (
                f"source data rows ({recon.source_data_rows}) != mapped + unmapped + rejected "
                f"({recon.mapped_rows + recon.unmapped_rows + recon.rejected_rows}), "
                f"difference of {recon.discrepancy}"
            )])
    summary_rows += [
        ["", ""],
        ["Total claims assessed", health.total_claims],
        ["Overall grade", f"{health.grade} / 5 — {health.grade_label}"],
        ["Composite score", f"{health.composite_score:.1f} / 100"],
        ["Average field completeness", f"{health.overall_completeness_pct:.1f}%"],
        ["Rows with at least one exception", f"{health.exception_rate_pct:.1f}%"],
        ["Rows flagged as possible duplicates", f"{health.duplicate_rate_pct:.1f}%"],
        ["", ""],
        ["Arithmetic mismatches (paid + reserve != incurred)", health.arithmetic_mismatches],
        ["Arithmetic checks not evaluable (missing/unmapped inputs)", health.arithmetic_not_evaluable],
        ["Rows with a missing mandatory field", health.missing_mandatory_rows],
        ["Date-logic exceptions", health.date_exceptions],
        ["Currency exceptions", health.currency_exceptions],
        ["Certain duplicates (exact claim reference match)", health.exact_duplicates],
        ["Probable duplicates (similar name + nearby loss date)", health.probable_duplicates],
        ["Same claim on several sheets, no reporting period (review)", health.period_unknown_repeats],
    ]
    summary_df = pd.DataFrame(summary_rows, columns=["Metric", "Value"])

    completeness_df = pd.DataFrame([
        {
            "Field code": fs.code,
            "Field name": fs.name,
            "Requirement": REQUIREMENT_LABELS[fs.requirement],
            "Present": fs.present,
            "Mapped rows": fs.denominator,
            "Completeness %": "— (column not found)" if fs.never_mapped else round(fs.pct, 1),
        }
        for fs in health.field_completeness
    ])

    display_columns = {f.code: f"{f.code} - {f.name}" for f in schema.FIELDS}
    canonical_display = canonical.rename(columns=display_columns)

    excluded_df = pd.DataFrame([
        {"Sheet": er.sheet_name, "Row": er.row_number,
         "Reason": EXCLUDED_ROW_REASON_LABELS.get(er.reason, er.reason), "Detail": er.detail}
        for er in health.coverage.excluded_rows
    ], columns=["Sheet", "Row", "Reason", "Detail"])

    sheet_audit_df = pd.DataFrame([
        {
            "Sheet": rec.sheet_name, "Status": rec.status.upper(), "Header row": (
                rec.header_row_index + 1 if rec.header_row_index is not None else "—"
            ),
            "Source rows": rec.source_row_count, "Rows processed": rec.rows_processed,
            "Rows rejected": rec.rows_rejected, "Fields mapped": f"{rec.fields_mapped}/{rec.fields_total}",
            "Reason": rec.reason,
        }
        for rec in health.coverage.sheet_audit
    ], columns=["Sheet", "Status", "Header row", "Source rows", "Rows processed",
                "Rows rejected", "Fields mapped", "Reason"])

    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        summary_df.to_excel(writer, sheet_name="Summary", index=False)
        if not sheet_audit_df.empty:
            sheet_audit_df.to_excel(writer, sheet_name="Sheet audit", index=False)
        completeness_df.to_excel(writer, sheet_name="Field completeness", index=False)
        exceptions.to_excel(writer, sheet_name="Exceptions", index=False)
        duplicates.to_excel(writer, sheet_name="Possible duplicates", index=False)
        excluded_df.to_excel(writer, sheet_name="Excluded rows", index=False)
        canonical_display.to_excel(writer, sheet_name="Full data", index=False)
        for sheet_name, raw_df in (unmapped_sheet_raw or {}).items():
            raw_df.to_excel(writer, sheet_name=_unmapped_sheet_tab_name(sheet_name), index=False)

    _autosize_columns(out_path)


_MAX_EXCEL_SHEET_NAME = 31


def _unmapped_sheet_tab_name(sheet_name: str) -> str:
    """Excel sheet names cap at 31 chars and can't hold '[]:*?/\\' --
    strip the illegal characters and truncate, keeping the tab
    recognizable rather than raising or silently dropping the sheet."""
    prefix = "Unmapped-"
    safe = "".join(c for c in sheet_name if c not in "[]:*?/\\")
    return (prefix + safe)[:_MAX_EXCEL_SHEET_NAME]


def _autosize_columns(path: Path) -> None:
    from openpyxl import load_workbook

    wb = load_workbook(path)
    for ws in wb.worksheets:
        for col_cells in ws.columns:
            length = max((len(str(c.value)) if c.value is not None else 0) for c in col_cells)
            ws.column_dimensions[col_cells[0].column_letter].width = min(max(length + 2, 10), 60)
    wb.save(path)


def write_health_report_pdf(health: HealthReport, out_path: str | Path) -> None:
    """The one-page artifact meant to be handed to a claims manager."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    out_path = Path(out_path)
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(str(out_path), pagesize=A4,
                             topMargin=1.5 * cm, bottomMargin=1.5 * cm,
                             leftMargin=1.8 * cm, rightMargin=1.8 * cm)

    grade_colors = {5: colors.HexColor("#1a7f37"), 4: colors.HexColor("#4c9a2a"),
                    3: colors.HexColor("#d4a017"), 2: colors.HexColor("#d9730d"),
                    1: colors.HexColor("#c0392b")}

    story = [
        Paragraph("Claims Bordereau Data Quality Report", styles["Title"]),
        Paragraph(health.source_name or "(unnamed file)", styles["Heading3"]),
        Spacer(1, 6),
    ]

    coverage_style = styles["Normal"].clone("coverage")
    if not health.coverage.fully_covered:
        coverage_style.textColor = colors.HexColor("#c0392b")
        coverage_style.fontName = "Helvetica-Bold"
    story.append(Paragraph(_coverage_line(health.coverage), coverage_style))

    caveat = _reliability_caveat(health)
    if caveat:
        caveat_style = styles["Normal"].clone("caveat")
        caveat_style.textColor = colors.HexColor("#c0392b")
        caveat_style.fontName = "Helvetica-Bold"
        story.append(Paragraph(caveat, caveat_style))
    story.append(Spacer(1, 10))

    grade_style = styles["Heading1"].clone("grade")
    grade_style.textColor = grade_colors.get(health.grade, colors.black)
    grade_style.fontSize = 32
    story.append(Paragraph(f"Grade: {health.grade} / 5 — {health.grade_label}", grade_style))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        f"Composite score {health.composite_score:.0f}/100, based on {health.total_claims} claims.",
        styles["Normal"],
    ))
    story.append(Spacer(1, 14))

    headline_data = [
        ["Average field completeness", f"{health.overall_completeness_pct:.1f}%"],
        ["Rows with at least one exception", f"{health.exception_rate_pct:.1f}%"],
        ["Rows flagged as possible duplicates", f"{health.duplicate_rate_pct:.1f}%"],
        ["Arithmetic mismatches", str(health.arithmetic_mismatches)],
        ["Arithmetic checks not evaluable", str(health.arithmetic_not_evaluable)],
        ["Missing mandatory fields", str(health.missing_mandatory_rows)],
        ["Certain duplicates", str(health.exact_duplicates)],
        ["Probable duplicates (review)", str(health.probable_duplicates)],
    ]
    headline_table = Table(headline_data, colWidths=[9 * cm, 6 * cm])
    headline_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica"),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
    ]))
    story.append(headline_table)
    story.append(Spacer(1, 16))

    story.append(Paragraph("Field-by-field completeness", styles["Heading2"]))
    field_data = [["Field", "Requirement", "Completeness"]]
    for fs in health.field_completeness:
        completeness_str = "— (column not found)" if fs.never_mapped else f"{fs.pct:.0f}%"
        field_data.append([fs.name, REQUIREMENT_LABELS[fs.requirement], completeness_str])
    field_table = Table(field_data, colWidths=[7 * cm, 4.5 * cm, 3.5 * cm])
    field_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f1f3d")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#dddddd")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f6f9")]),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(field_table)
    story.append(Spacer(1, 14))

    story.append(Paragraph(
        "What this means: this contract's bordereaux were checked against the ten-field "
        "core data set insurers and coverholders typically agree on first. Completeness "
        "shows how often each field was actually populated, among the rows where it was "
        "found at all; exceptions are rows where the numbers or dates don't add up; "
        "duplicate flags are claims that may have been reported more than once and should "
        "be reviewed before use. This report prepares data for human review and does not "
        "make any claims decisions itself.",
        styles["Normal"],
    ))

    doc.build(story)
