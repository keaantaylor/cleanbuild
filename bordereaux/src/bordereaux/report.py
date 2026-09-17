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

import pandas as pd

from . import schema
from .ingest import EXCLUDED_ROW_REASON_LABELS, ExcludedRow
from .validation import ValidationResult

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
            counts[er.reason] = counts.get(er.reason, 0) + 1
        return counts


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
        return self.coverage.fully_covered and not self.unmapped_required_fields


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
    return line


def _reliability_caveat(health: HealthReport) -> str | None:
    if health.score_reliable:
        return None
    reasons = []
    if not health.coverage.fully_covered:
        reasons.append("not every sheet/row was assessed")
    if health.unmapped_required_fields:
        reasons.append(f"required field(s) left unmapped: {', '.join(health.unmapped_required_fields)}")
    return "Score not fully reliable — " + "; ".join(reasons) + ". See coverage note above."


def write_health_report_excel(health: HealthReport, exceptions: pd.DataFrame,
                               duplicates: pd.DataFrame, canonical: pd.DataFrame,
                               out_path: str | Path) -> None:
    """One workbook: a readable Summary sheet, plus full row-level detail
    (exceptions, duplicates, and the underlying data) for anyone who wants
    to dig in."""
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

    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        summary_df.to_excel(writer, sheet_name="Summary", index=False)
        completeness_df.to_excel(writer, sheet_name="Field completeness", index=False)
        exceptions.to_excel(writer, sheet_name="Exceptions", index=False)
        duplicates.to_excel(writer, sheet_name="Possible duplicates", index=False)
        excluded_df.to_excel(writer, sheet_name="Excluded rows", index=False)
        canonical_display.to_excel(writer, sheet_name="Full data", index=False)

    _autosize_columns(out_path)


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
