"""High-level orchestration shared by the CLI script and the Streamlit
app: load a raw file (one sheet or a whole multi-sheet workbook), propose
a mapping per sheet, ingest against confirmed mappings, validate, dedupe,
and build the health report. Kept UI-free so both entry points reuse
exactly the same logic (Section 6: every mapping decision logged the same
way regardless of front end; fix spec 3.4: the UI and the report read the
same mapping-outcome objects, never two separately-derived ones)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from . import dedupe, export, ingest, report, validation
from .ingest import SheetData
from .mapping import AIMapper, MappingBatchResult, MappingSuggestion, build_mapping, derive_field_state
from .pandera_schema import CANONICAL_SCHEMA
from .schema import FIELDS, SOURCE_SHEET_CODE


@dataclass
class ProcessResult:
    canonical: pd.DataFrame
    exceptions: pd.DataFrame
    duplicates: pd.DataFrame
    health: "report.HealthReport"
    suggestions: list[MappingSuggestion]


def propose_mapping(raw: pd.DataFrame, ai_mapper: AIMapper | None = None) -> MappingBatchResult:
    return build_mapping(list(raw.columns), ai_mapper=ai_mapper)


def run_pipeline(raw: pd.DataFrame, confirmed_mapping: dict[str, str],
                  source_name: str = "") -> ProcessResult:
    canonical = ingest.apply_mapping(raw, confirmed_mapping, sheet_name=source_name)
    CANONICAL_SCHEMA.validate(canonical)

    validation_result = validation.validate(canonical)
    duplicates = dedupe.find_duplicates(canonical)
    health = report.build_health_report(canonical, validation_result, duplicates, source_name=source_name)

    return ProcessResult(
        canonical=canonical,
        exceptions=validation_result.exceptions,
        duplicates=duplicates,
        health=health,
        suggestions=[],
    )


def process_path(path: str | Path, confirmed_mapping: dict[str, str]) -> ProcessResult:
    raw = ingest.load_raw(path)
    return run_pipeline(raw, confirmed_mapping, source_name=Path(path).name)


# --------------------------------------------------------------------
# Multi-sheet workbook path (fix spec 3.1-3.4, 3.9)
# --------------------------------------------------------------------

@dataclass
class SheetMappingProposal:
    sheet: SheetData
    mapping: MappingBatchResult


@dataclass
class WorkbookProcessResult:
    canonical: pd.DataFrame
    validation_result: validation.ValidationResult
    duplicates: pd.DataFrame
    health: "report.HealthReport"
    coverage: "report.WorkbookCoverage"


def load_workbook(path: str | Path, display_name: str | None = None) -> list[SheetData]:
    return ingest.load_workbook_sheets(path, display_name=display_name)


def propose_mapping_for_workbook(
    sheets: list[SheetData], ai_mapper: AIMapper | None = None,
) -> list[SheetMappingProposal]:
    """One mapping proposal per non-skipped sheet. Skipped sheets (fix
    spec 3.1: no mappable header row, or genuinely empty) are left out --
    callers surface them via WorkbookCoverage.skipped_sheets instead of
    silently dropping or silently counting them as claims."""
    return [
        SheetMappingProposal(s, build_mapping(list(s.raw.columns), ai_mapper=ai_mapper))
        for s in sheets if not s.skipped
    ]


def run_workbook_pipeline(
    sheets: list[SheetData],
    confirmed_mappings: dict[str, dict[str, str]],
    proposals: list[SheetMappingProposal],
    source_name: str = "",
) -> WorkbookProcessResult:
    """confirmed_mappings: {sheet_name: {source_column: field_code}},
    one entry per non-skipped sheet, after human confirmation."""
    proposal_by_sheet = {p.sheet.sheet_name: p for p in proposals}

    canonical_parts = []
    sheet_field_state: dict[str, dict[str, str]] = {}
    for s in sheets:
        if s.skipped:
            continue
        confirmed = confirmed_mappings.get(s.sheet_name, {})
        canonical_parts.append(ingest.apply_mapping(s.raw, confirmed, sheet_name=s.sheet_name))

        proposal = proposal_by_sheet.get(s.sheet_name)
        suggestions = proposal.mapping.suggestions if proposal else []
        sheet_field_state[s.sheet_name] = derive_field_state(suggestions, confirmed)

    if canonical_parts:
        canonical = pd.concat(canonical_parts, ignore_index=True)
    else:
        canonical = pd.DataFrame(columns=[f.code for f in FIELDS] + [SOURCE_SHEET_CODE])
    CANONICAL_SCHEMA.validate(canonical)

    validation_result = validation.validate(canonical, sheet_field_state=sheet_field_state)
    duplicates = dedupe.find_duplicates(canonical)

    skipped_sheets = [(s.sheet_name, s.skip_reason or "skipped") for s in sheets if s.skipped]
    rows_total = sum(
        len(s.raw) if not s.skipped else max(s.raw_row_count - 1, 0)
        for s in sheets
    )
    coverage = report.WorkbookCoverage(
        sheets_total=len(sheets),
        sheets_processed=sum(1 for s in sheets if not s.skipped),
        skipped_sheets=skipped_sheets,
        rows_total=rows_total,
        rows_assessed=len(canonical),
        sheet_field_state=sheet_field_state,
    )

    health = report.build_health_report(
        canonical, validation_result, duplicates, source_name=source_name, coverage=coverage,
    )

    return WorkbookProcessResult(
        canonical=canonical,
        validation_result=validation_result,
        duplicates=duplicates,
        health=health,
        coverage=coverage,
    )


def process_workbook_path(
    path: str | Path,
    confirmed_mappings: dict[str, dict[str, str]],
    proposals: list[SheetMappingProposal],
) -> WorkbookProcessResult:
    sheets = load_workbook(path)
    return run_workbook_pipeline(sheets, confirmed_mappings, proposals, source_name=Path(path).name)


def write_workbook_outputs(result: WorkbookProcessResult, out_dir: str | Path, stem: str) -> dict[str, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    segregated_path = out_dir / f"{stem}_segregated.xlsx"
    export.write_segregated_export(result.canonical, segregated_path)

    health_path = out_dir / f"{stem}_health_report.xlsx"
    report.write_health_report_excel(result.health, result.validation_result.exceptions, result.duplicates,
                                      result.canonical, health_path)

    health_pdf_path = out_dir / f"{stem}_health_report.pdf"
    report.write_health_report_pdf(result.health, health_pdf_path)

    return {"segregated": segregated_path, "health": health_path, "health_pdf": health_pdf_path}


def write_outputs(result: ProcessResult, out_dir: str | Path, stem: str) -> dict[str, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    segregated_path = out_dir / f"{stem}_segregated.xlsx"
    export.write_segregated_export(result.canonical, segregated_path)

    health_path = out_dir / f"{stem}_health_report.xlsx"
    report.write_health_report_excel(result.health, result.exceptions, result.duplicates,
                                      result.canonical, health_path)

    health_pdf_path = out_dir / f"{stem}_health_report.pdf"
    report.write_health_report_pdf(result.health, health_pdf_path)

    return {"segregated": segregated_path, "health": health_path, "health_pdf": health_pdf_path}
