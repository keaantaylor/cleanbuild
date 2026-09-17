"""Truebind 2.2: one-click Governance Review Pack export.

A single PDF per report (sender/reporting-period), containing exactly
what the redevelopment prompt asks a compliance officer be able to hand
an auditor: the coverage summary, every mapping decision and who
confirmed it, every exception raised and its resolution status, every
obligation and whether it was met by its deadline, and the full audit
log for that period. Reuses report.py's reportlab table/story patterns
rather than reinventing PDF layout.
"""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.orm import Session

from .audit import ACTION_MAPPING_CONFIRMED, ACTION_MAPPING_OVERRIDDEN
from .db.models import AuditLogEntry, ExceptionRecord, LeakageFlag, Obligation, Report


def build_governance_pack(session: Session, report_id: str, out_path: str | Path) -> Path:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    report = session.get(Report, report_id)
    if report is None:
        raise ValueError(f"no report with id {report_id}")
    summary = json.loads(report.summary_json)

    audit_entries = (
        session.query(AuditLogEntry)
        .filter(AuditLogEntry.report_id == report_id)
        .order_by(AuditLogEntry.timestamp)
        .all()
    )
    exceptions = session.query(ExceptionRecord).filter(ExceptionRecord.report_id == report_id).all()
    obligations = session.query(Obligation).filter(Obligation.report_id == report_id).all()
    leakage_flags = session.query(LeakageFlag).filter(LeakageFlag.report_id == report_id).all()

    out_path = Path(out_path)
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(str(out_path), pagesize=A4,
                             topMargin=1.5 * cm, bottomMargin=1.5 * cm,
                             leftMargin=1.6 * cm, rightMargin=1.6 * cm)

    header_style = TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f1f3d")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#dddddd")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f6f9")]),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ])

    story = [
        Paragraph("Governance Review Pack", styles["Title"]),
        Paragraph(report.source_name, styles["Heading3"]),
        Paragraph(f"Uploaded {report.uploaded_at:%Y-%m-%d %H:%M UTC} by {report.uploaded_by or 'unknown'}",
                  styles["Normal"]),
        Spacer(1, 12),
    ]

    story.append(Paragraph("Coverage summary", styles["Heading2"]))
    coverage_rows = [
        ["Assessed rows", f"{report.rows_assessed} of {report.rows_total}"],
        ["Sheets processed", f"{report.sheets_processed} of {report.sheets_total}"],
        ["Grade", f"{report.grade} / 5"],
        ["Composite score", f"{report.composite_score:.1f} / 100"],
        ["Score reliable", "Yes" if report.score_reliable else "No -- see coverage/unmapped-field caveats"],
        ["Arithmetic mismatches", str(summary.get("arithmetic_mismatches", "n/a"))],
        ["Arithmetic not evaluable", str(summary.get("arithmetic_not_evaluable", "n/a"))],
        ["Missing-mandatory-field rows", str(summary.get("missing_mandatory_rows", "n/a"))],
    ]
    story.append(Table(coverage_rows, colWidths=[8 * cm, 9 * cm], style=header_style))
    story.append(Spacer(1, 14))

    story.append(Paragraph("Mapping decisions", styles["Heading2"]))
    mapping_entries = [e for e in audit_entries if e.action_type in (ACTION_MAPPING_CONFIRMED, ACTION_MAPPING_OVERRIDDEN)]
    if mapping_entries:
        mapping_rows = [["Column", "Field code", "Method", "Confirmed by", "When"]]
        for e in mapping_entries:
            before = json.loads(e.before_value) if e.before_value else {}
            mapping_rows.append([
                e.entity_id or "", before.get("suggested_field_code", ""), before.get("method", e.action_type),
                e.actor, e.timestamp.strftime("%Y-%m-%d %H:%M"),
            ])
        story.append(Table(mapping_rows, colWidths=[4.5 * cm, 3 * cm, 3 * cm, 3.5 * cm, 3 * cm], style=header_style))
    else:
        story.append(Paragraph("No mapping decisions logged for this report.", styles["Normal"]))
    story.append(Spacer(1, 14))

    story.append(Paragraph("Exceptions and resolution status", styles["Heading2"]))
    if exceptions:
        exc_rows = [["Sheet", "Row", "Claim ref", "Rule", "Status"]]
        for e in exceptions:
            exc_rows.append([e.sheet or "", str(e.row or ""), e.claim_ref or "", e.rule, e.status])
        story.append(Table(exc_rows, colWidths=[3.5 * cm, 1.5 * cm, 3.5 * cm, 4.5 * cm, 3.5 * cm], style=header_style))
    else:
        story.append(Paragraph("No exceptions raised for this report.", styles["Normal"]))
    story.append(Spacer(1, 14))

    story.append(Paragraph("Leakage flags", styles["Heading2"]))
    if leakage_flags:
        lf_rows = [["Confidence", "Insured", "Exposure", "Status"]]
        for f in leakage_flags:
            lf_rows.append([f.confidence, f.insured_name_a or "", f"{f.amount_exposure:,.2f}", f.status])
        story.append(Table(lf_rows, colWidths=[3 * cm, 6 * cm, 3.5 * cm, 3.5 * cm], style=header_style))
    else:
        story.append(Paragraph("No leakage flags for this report.", styles["Normal"]))
    story.append(Spacer(1, 14))

    story.append(Paragraph("Obligations", styles["Heading2"]))
    if obligations:
        ob_rows = [["Description", "Category", "Due", "Status"]]
        for o in obligations:
            ob_rows.append([o.description, o.category, str(o.due_date or ""), o.status])
        story.append(Table(ob_rows, colWidths=[7 * cm, 3.5 * cm, 2.5 * cm, 3 * cm], style=header_style))
    else:
        story.append(Paragraph("No obligations recorded for this report.", styles["Normal"]))

    story.append(PageBreak())
    story.append(Paragraph("Full audit log", styles["Heading2"]))
    if audit_entries:
        log_rows = [["When", "Actor", "Action", "Entity"]]
        for e in audit_entries:
            log_rows.append([
                e.timestamp.strftime("%Y-%m-%d %H:%M"), e.actor, e.action_type,
                f"{e.entity_type}:{e.entity_id}" if e.entity_id else e.entity_type,
            ])
        story.append(Table(log_rows, colWidths=[3.5 * cm, 3.5 * cm, 4 * cm, 5 * cm], style=header_style))
    else:
        story.append(Paragraph("No audit entries recorded for this report.", styles["Normal"]))

    doc.build(story)
    return out_path
