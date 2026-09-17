"""Bridges a completed pipeline run into the database: reports, leakage
flags and audit entries all need to survive between sessions and be
queryable by the new dashboards, not live only in Streamlit session state
for the duration of one upload."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pandas as pd
from sqlalchemy.orm import Session

from . import schema
from .db.models import ExceptionRecord, LeakageFlag, Report
from .report import HealthReport


def ensure_schema() -> None:
    """Apply any pending Alembic migrations. Safe to call on every app
    startup -- a no-op once the schema is current."""
    from alembic import command
    from alembic.config import Config

    repo_root = Path(__file__).resolve().parent.parent.parent
    cfg = Config(str(repo_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(repo_root / "alembic"))
    command.upgrade(cfg, "head")


def _health_to_json(health: HealthReport) -> str:
    return json.dumps(dataclasses.asdict(health), default=str)


def persist_report(
    session: Session,
    health: HealthReport,
    source_name: str,
    uploaded_by: str | None = None,
    export_paths: dict[str, Path] | None = None,
) -> Report:
    export_paths = export_paths or {}
    report = Report(
        source_name=source_name,
        uploaded_by=uploaded_by,
        sheets_total=health.coverage.sheets_total,
        sheets_processed=health.coverage.sheets_processed,
        rows_total=health.coverage.rows_total,
        rows_assessed=health.coverage.rows_assessed,
        grade=health.grade,
        composite_score=health.composite_score,
        score_reliable=health.score_reliable,
        summary_json=_health_to_json(health),
        segregated_export_path=str(export_paths.get("segregated", "")) or None,
        health_report_xlsx_path=str(export_paths.get("health", "")) or None,
        health_report_pdf_path=str(export_paths.get("health_pdf", "")) or None,
    )
    session.add(report)
    session.flush()  # assign report.id without requiring a full commit yet
    return report


def _sheet_local_rows(canonical: pd.DataFrame) -> pd.Series:
    """1-indexed position of each row within its own sheet -- the same
    (sheet, row) addressing scheme the boundary-fixture regression test
    uses, so persisted flags/exceptions read back in human terms."""
    return canonical.groupby(schema.SOURCE_SHEET_CODE).cumcount() + 1


def persist_exceptions(session: Session, report_id: str, canonical: pd.DataFrame,
                        exceptions: pd.DataFrame) -> list[ExceptionRecord]:
    if exceptions.empty:
        return []
    sheet_local_row = _sheet_local_rows(canonical)
    rows = []
    for _, exc in exceptions.iterrows():
        idx = exc["row_index"]
        rec = ExceptionRecord(
            report_id=report_id,
            sheet=canonical.at[idx, schema.SOURCE_SHEET_CODE] if idx in canonical.index else None,
            row=int(sheet_local_row.at[idx]) if idx in sheet_local_row.index else None,
            claim_ref=exc["claim_ref"],
            rule=exc["rule"],
            detail=exc["detail"],
        )
        session.add(rec)
        rows.append(rec)
    session.flush()
    return rows


def persist_leakage_flags(session: Session, report_id: str, canonical: pd.DataFrame,
                           leakage_flags: pd.DataFrame) -> list[LeakageFlag]:
    if leakage_flags.empty:
        return []
    sheet_local_row = _sheet_local_rows(canonical)
    rows = []
    for _, f in leakage_flags.iterrows():
        a, b = f["row_index_a"], f["row_index_b"]
        row = LeakageFlag(
            report_id=report_id,
            confidence=f["confidence"],
            sheet_a=canonical.at[a, schema.SOURCE_SHEET_CODE], row_a=int(sheet_local_row.at[a]),
            claim_ref_a=f["claim_ref_a"], insured_name_a=f["insured_name_a"], amount_a=f["amount_a"],
            sheet_b=canonical.at[b, schema.SOURCE_SHEET_CODE], row_b=int(sheet_local_row.at[b]),
            claim_ref_b=f["claim_ref_b"], insured_name_b=f["insured_name_b"], amount_b=f["amount_b"],
            matched_fields=json.dumps(f["matched_fields"]),
            amount_exposure=f["amount_exposure"],
            detail=f["detail"],
        )
        session.add(row)
        rows.append(row)
    session.flush()
    return rows
