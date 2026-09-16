"""Phase 5: completeness / health report.

Produces the sales artifact from the brief: a one-page grade (1-5) a
non-technical claims handler can read in under two minutes, backed by
full row-level detail for anyone who wants to dig in.

Scoring: the brief doesn't specify an exact formula, only that this
should "mirror industry-standard scoring logic" (per-field completeness
scored against an agreed skeleton, the GreenKite-style approach the brief
is built around). The composite score implemented here is:

    composite = average field completeness %
                - 1.5 x (% of rows with at least one validation exception)
                - 1.0 x (% of rows flagged as a duplicate)

clipped to [0, 100] and banded into a 1-5 grade. Exceptions are weighted
more heavily than duplicate flags because they represent data that is
actively wrong (arithmetic doesn't tie out, dates don't make sense),
whereas a duplicate flag is a "check this" signal, not necessarily an
error. This is a documented heuristic, not a standards body's formula --
tune the weights once real client bordereaux give a feel for what "good"
looks like in practice.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from . import schema

GRADE_LABELS = {5: "Excellent", 4: "Good", 3: "Fair", 2: "Poor", 1: "Very poor"}
EXCEPTION_WEIGHT = 1.5
DUPLICATE_WEIGHT = 1.0


@dataclass
class FieldCompleteness:
    code: str
    name: str
    required: bool
    present: int
    total: int

    @property
    def pct(self) -> float:
        return 100.0 * self.present / self.total if self.total else 0.0


@dataclass
class HealthReport:
    source_name: str
    total_claims: int
    field_completeness: list[FieldCompleteness]
    arithmetic_exceptions: int
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


def build_health_report(canonical: pd.DataFrame, exceptions: pd.DataFrame,
                         duplicates: pd.DataFrame, source_name: str = "") -> HealthReport:
    total = len(canonical)

    field_stats = [
        FieldCompleteness(f.code, f.name, f.required, int(canonical[f.code].notna().sum()), total)
        for f in schema.FIELDS
    ]
    overall_completeness = sum(fs.pct for fs in field_stats) / len(field_stats) if field_stats else 0.0

    arithmetic = int((exceptions["rule"] == "arithmetic_mismatch").sum()) if not exceptions.empty else 0
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
        arithmetic_exceptions=arithmetic,
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
    )


def write_health_report_excel(health: HealthReport, exceptions: pd.DataFrame,
                               duplicates: pd.DataFrame, canonical: pd.DataFrame,
                               out_path: str | Path) -> None:
    """One workbook: a readable Summary sheet, plus full row-level detail
    (exceptions, duplicates, and the underlying data) for anyone who wants
    to dig in."""
    out_path = Path(out_path)

    summary_rows = [
        ["Source file", health.source_name],
        ["Total claims", health.total_claims],
        ["Overall grade", f"{health.grade} / 5 — {health.grade_label}"],
        ["Composite score", f"{health.composite_score:.1f} / 100"],
        ["Average field completeness", f"{health.overall_completeness_pct:.1f}%"],
        ["Rows with at least one exception", f"{health.exception_rate_pct:.1f}%"],
        ["Rows flagged as possible duplicates", f"{health.duplicate_rate_pct:.1f}%"],
        ["", ""],
        ["Arithmetic mismatches (paid + reserve != incurred)", health.arithmetic_exceptions],
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
            "Required": "Yes" if fs.required else "Conditional",
            "Present": fs.present,
            "Total rows": fs.total,
            "Completeness %": round(fs.pct, 1),
        }
        for fs in health.field_completeness
    ])

    display_columns = {f.code: f"{f.code} - {f.name}" for f in schema.FIELDS}
    canonical_display = canonical.rename(columns=display_columns)

    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        summary_df.to_excel(writer, sheet_name="Summary", index=False)
        completeness_df.to_excel(writer, sheet_name="Field completeness", index=False)
        exceptions.to_excel(writer, sheet_name="Exceptions", index=False)
        duplicates.to_excel(writer, sheet_name="Possible duplicates", index=False)
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
        Spacer(1, 10),
    ]

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
        ["Arithmetic mismatches", str(health.arithmetic_exceptions)],
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
    field_data = [["Field", "Required", "Completeness"]]
    for fs in health.field_completeness:
        field_data.append([fs.name, "Yes" if fs.required else "Conditional", f"{fs.pct:.0f}%"])
    field_table = Table(field_data, colWidths=[8 * cm, 3.5 * cm, 3.5 * cm])
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
        "shows how often each field was actually populated; exceptions are rows where the "
        "numbers or dates don't add up; duplicate flags are claims that may have been "
        "reported more than once and should be reviewed before use. This report prepares "
        "data for human review and does not make any claims decisions itself.",
        styles["Normal"],
    ))

    doc.build(story)
