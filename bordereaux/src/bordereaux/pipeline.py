"""High-level orchestration shared by the CLI script and the Streamlit
app: load a raw file (one sheet or a whole multi-sheet workbook), propose
a mapping per sheet, ingest against confirmed mappings, validate, dedupe,
and build the health report. Kept UI-free so both entry points reuse
exactly the same logic (Section 6: every mapping decision logged the same
way regardless of front end; fix spec 3.4: the UI and the report read the
same mapping-outcome objects, never two separately-derived ones)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter

import pandas as pd

from . import dedupe, export, ingest, report, validation
from .ingest import SheetData
from .mapping import AIMapper, MappingBatchResult, MappingSuggestion, build_mapping, derive_field_state
import pandera.errors as pa_errors

from .pandera_schema import CANONICAL_SCHEMA
from .schema import FIELDS, SOURCE_SHEET_CODE


@dataclass
class ProcessResult:
    canonical: pd.DataFrame
    exceptions: pd.DataFrame
    duplicates: pd.DataFrame
    health: "report.HealthReport"
    suggestions: list[MappingSuggestion]


def validate_schema_lazily(canonical: pd.DataFrame) -> list[tuple[int, str, str]]:
    """Pandera in LAZY mode: every failing cell is collected instead of the
    first one raising and aborting the whole workbook. Returns
    (row_index, rule, detail) findings for exactly the failing rows; every
    other row carries on through validation untouched. A failure without a
    row index (a whole-column problem) is attached to no row but still
    reported, via the first row, so it can never vanish."""
    try:
        CANONICAL_SCHEMA.validate(canonical, lazy=True)
        return []
    except pa_errors.SchemaErrors as exc:
        out = []
        seen: set = set()  # one finding per failing cell (pandera may report coercion + dtype for one cell)
        fc = exc.failure_cases
        for _, f in fc.iterrows():
            idx = f.get("index")
            col, check, case = f.get("column"), f.get("check"), f.get("failure_case")
            cell = (None if idx is None or pd.isna(idx) else int(idx), col)
            if cell in seen:
                continue
            seen.add(cell)
            detail = f"{col}: value {case!r} failed schema check {check}"
            if idx is None or pd.isna(idx):
                if len(canonical):
                    out.append((int(canonical.index[0]), "schema_violation", detail + " (whole column)"))
            else:
                out.append((int(idx), "schema_violation", detail))
        return out


def propose_mapping(raw: pd.DataFrame, ai_mapper: AIMapper | None = None) -> MappingBatchResult:
    return build_mapping(list(raw.columns), ai_mapper=ai_mapper)


def run_pipeline(raw: pd.DataFrame, confirmed_mapping: dict[str, str],
                  source_name: str = "") -> ProcessResult:
    canonical = ingest.apply_mapping(raw, confirmed_mapping, sheet_name=source_name)
    schema_failures = validate_schema_lazily(canonical)

    validation_result = validation.add_row_findings(validation.validate(canonical), schema_failures)
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
    stage_timings: dict[str, float] = field(default_factory=dict)  # seconds, wall clock, per stage
    # Same claim re-reported with a later period / moved amounts (never a duplicate).
    developments: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=dedupe.DUPLICATE_COLUMNS))


def load_workbook(path: str | Path, source_stem: str | None = None,
                  limits: "ingest.ReadLimits | None" = None) -> list[SheetData]:
    return ingest.load_workbook_sheets(path, source_stem=source_stem, limits=limits)


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


def _source_column_count(s: SheetData) -> int:
    return sum(1 for c in s.raw.columns if not str(c).startswith("__blank_col_"))


def _build_sheet_audit_record(s: SheetData, field_state: dict[str, str]) -> report.SheetAuditRecord:
    mapped_field_codes = [code for code, state in field_state.items() if state != "unmapped"]
    unmapped_field_codes = [code for code, state in field_state.items() if state == "unmapped"]
    status, reason = report.classify_sheet_status(s.skipped, s.skip_reason, mapped_field_codes,
                                                   source_column_count=_source_column_count(s))
    return report.SheetAuditRecord(
        sheet_name=s.sheet_name,
        is_empty=s.skipped,
        header_row_index=s.header_row_index if not s.skipped else None,
        source_row_count=len(s.raw) if not s.skipped else max(s.raw_row_count - 1, 0),
        rows_processed=len(s.raw) if not s.skipped else 0,
        rows_rejected=s.excluded_row_count,
        fields_mapped=len(mapped_field_codes),
        fields_total=len(FIELDS),
        mapped_field_codes=sorted(mapped_field_codes),
        unmapped_field_codes=sorted(unmapped_field_codes),
        status=status,
        reason=reason,
    )


def _build_reconciliation(
    sheets: list[SheetData],
    sheet_audit: list[report.SheetAuditRecord],
    canonical: pd.DataFrame,
    duplicates: pd.DataFrame,
    validation_result: validation.ValidationResult,
) -> report.ReconciliationSummary:
    """Section 5: computed via two independent paths on purpose. source_
    data_rows comes straight from each sheet's own kept + excluded row
    counts, before mapping ever runs; mapped/unmapped/rejected are
    aggregated the other direction, from the per-sheet audit records
    that already drove the canonical model. Under the current
    architecture these agree by construction (see ReconciliationSummary.
    reconciles) -- if a future change ever broke that invariant, this
    would surface a real mismatch instead of the two totals silently
    drifting apart."""
    source_data_rows = sum(len(s.raw) + s.excluded_row_count for s in sheets if not s.skipped)
    skipped_sheet_rows = sum(rec.source_row_count for rec in sheet_audit if rec.status in ("empty", "error"))

    mapped_rows = sum(rec.rows_processed for rec in sheet_audit if rec.status in ("mapped", "partial"))
    unmapped_rows = sum(rec.rows_processed for rec in sheet_audit if rec.status == "unmapped")
    rejected_rows = sum(rec.rows_rejected for rec in sheet_audit)
    non_claim_summary_rows = sum(rec.rows_processed for rec in sheet_audit if rec.status == "non_claim_summary")

    dup_row_positions: set = set()
    if not duplicates.empty:
        dup_row_positions = set(duplicates["row_index_a"]) | set(duplicates["row_index_b"])

    exception_row_positions: set = set()
    if not validation_result.exceptions.empty:
        exception_row_positions = set(validation_result.exceptions["row_index"])

    unmapped_sheet_names = {rec.sheet_name for rec in sheet_audit if rec.status == "unmapped"}
    unmapped_row_positions: set = set()
    if unmapped_sheet_names and SOURCE_SHEET_CODE in canonical.columns:
        unmapped_row_positions = set(canonical.index[canonical[SOURCE_SHEET_CODE].isin(unmapped_sheet_names)])

    rows_requiring_review = len(exception_row_positions | dup_row_positions | unmapped_row_positions)

    return report.ReconciliationSummary(
        source_worksheets=len(sheets),
        source_data_rows=source_data_rows,
        skipped_sheet_rows=skipped_sheet_rows,
        mapped_rows=mapped_rows,
        unmapped_rows=unmapped_rows,
        rejected_rows=rejected_rows,
        duplicate_rows=len(dup_row_positions),
        exported_rows=len(canonical),
        rows_requiring_review=rows_requiring_review,
        non_claim_summary_rows=non_claim_summary_rows,
    )


def run_workbook_pipeline(
    sheets: list[SheetData],
    confirmed_mappings: dict[str, dict[str, str]],
    proposals: list[SheetMappingProposal],
    source_name: str = "",
) -> WorkbookProcessResult:
    """confirmed_mappings: {sheet_name: {source_column: field_code}},
    one entry per non-skipped sheet, after human confirmation."""
    proposal_by_sheet = {p.sheet.sheet_name: p for p in proposals}
    stage_timings: dict[str, float] = {}
    _t = perf_counter()

    canonical_parts = []
    sheet_field_state: dict[str, dict[str, str]] = {}
    non_claim_summary_sheet_names: set[str] = set()
    sheet_transforms: dict[str, list[dict]] = {}
    sheet_notes: dict[str, list[str]] = {s.sheet_name: list(s.notes) for s in sheets}
    unmapped_source_columns: dict[str, list[str]] = {}
    for s in sheets:
        if s.skipped:
            continue
        confirmed = confirmed_mappings.get(s.sheet_name, {})

        proposal = proposal_by_sheet.get(s.sheet_name)
        suggestions = proposal.mapping.suggestions if proposal else []
        field_state = derive_field_state(suggestions, confirmed)
        sheet_field_state[s.sheet_name] = field_state

        # TB-001: a sheet binding only monetary columns, with no claim
        # reference (or insured name + date), is a summary/aggregate tab,
        # not a claims register -- its rows must never be emitted as
        # claims. Recorded via sheet_audit below, never silently dropped.
        mapped_codes = [code for code, state in field_state.items() if state != "unmapped"]
        status, _ = report.classify_sheet_status(False, None, mapped_codes,
                                                  source_column_count=_source_column_count(s))
        if status == "non_claim_summary":
            non_claim_summary_sheet_names.add(s.sheet_name)
            continue

        part = ingest.apply_mapping(s.raw, confirmed, sheet_name=s.sheet_name)
        # Reverse pass: source columns no canonical field claimed. Named in
        # coverage and kept per row -- never silently dropped.
        mapped_cols = {c for c, code in confirmed.items() if code}
        unclaimed = [c for c in s.raw.columns if c not in mapped_cols and not str(c).startswith("__blank_col_")]
        unmapped_source_columns[s.sheet_name] = [str(c) for c in unclaimed]
        if unclaimed:
            raw_vals = s.raw[unclaimed].astype("object").where(s.raw[unclaimed].notna(), None)
            part["_unmapped_values"] = [
                {str(k): (v if isinstance(v, (str, int, float, bool)) or v is None else str(v))
                 for k, v in row.items() if v is not None and str(v).strip() != ""}
                for row in raw_vals.to_dict("records")]
        else:
            part["_unmapped_values"] = [{} for _ in range(len(part))]
        # Lineage: the 1-based source row of every canonical row.
        part["_source_row"] = pd.array(
            s.source_row_numbers if len(s.source_row_numbers) == len(part) else [pd.NA] * len(part),
            dtype="Int64")
        sheet_transforms[s.sheet_name] = part.attrs.get("transforms", [])
        sheet_notes[s.sheet_name] = list(s.notes) + list(part.attrs.get("parse_notes", []))
        canonical_parts.append(part)

    if canonical_parts:
        canonical = pd.concat(canonical_parts, ignore_index=True)
    else:
        canonical = pd.DataFrame(columns=[f.code for f in FIELDS] + [SOURCE_SHEET_CODE, "_mixed_currency"])
    schema_failures = validate_schema_lazily(canonical)
    stage_timings["mapping"], _t = perf_counter() - _t, perf_counter()

    validation_result = validation.validate(canonical, sheet_field_state=sheet_field_state)
    validation_result = validation.add_row_findings(validation_result, schema_failures)
    stage_timings["validation"], _t = perf_counter() - _t, perf_counter()

    duplicates = dedupe.find_duplicates(canonical)
    developments = dedupe.find_developments(canonical)
    stage_timings["dedupe"], _t = perf_counter() - _t, perf_counter()

    skipped_sheets = [(s.sheet_name, s.skip_reason or "skipped") for s in sheets if s.skipped]
    # TB-001: a non-claim-summary sheet's rows are deliberately excluded
    # from the claim set -- they must not count against coverage as if
    # they were unassessed data, or a correctly-recognised dashboard tab
    # would make every workbook containing one look "not fully covered".
    rows_total = sum(
        len(s.raw) if not s.skipped else max(s.raw_row_count - 1, 0)
        for s in sheets if s.sheet_name not in non_claim_summary_sheet_names
    )
    excluded_rows = [er for s in sheets for er in s.excluded_rows]

    sheet_audit = [_build_sheet_audit_record(s, sheet_field_state.get(s.sheet_name, {})) for s in sheets]

    coverage = report.WorkbookCoverage(
        sheets_total=len(sheets),
        sheets_processed=sum(1 for s in sheets if not s.skipped),
        skipped_sheets=skipped_sheets,
        rows_total=rows_total,
        rows_assessed=len(canonical),
        sheet_field_state=sheet_field_state,
        excluded_rows=excluded_rows,
        sheet_audit=sheet_audit,
        sheet_transforms=sheet_transforms,
        sheet_notes=sheet_notes,
        unmapped_source_columns=unmapped_source_columns,
    )
    coverage.reconciliation = _build_reconciliation(sheets, sheet_audit, canonical, duplicates, validation_result)

    health = report.build_health_report(
        canonical, validation_result, duplicates, source_name=source_name, coverage=coverage,
    )
    stage_timings["report"] = perf_counter() - _t

    return WorkbookProcessResult(
        canonical=canonical,
        validation_result=validation_result,
        duplicates=duplicates,
        health=health,
        coverage=coverage,
        stage_timings=stage_timings,
        developments=developments,
    )


def process_workbook_path(
    path: str | Path,
    confirmed_mappings: dict[str, dict[str, str]],
    proposals: list[SheetMappingProposal],
) -> WorkbookProcessResult:
    sheets = load_workbook(path)
    return run_workbook_pipeline(sheets, confirmed_mappings, proposals, source_name=Path(path).name)


def write_workbook_outputs(
    result: WorkbookProcessResult, out_dir: str | Path, stem: str, sheets: list[SheetData] | None = None,
) -> dict[str, Path]:
    """sheets: the same list passed to run_workbook_pipeline, so a
    sheet whose SheetAuditRecord.status is "unmapped" gets its original
    (raw, unmapped) headers and values written to their own tab in the
    health report -- see report.write_health_report_excel. Optional so
    existing callers that don't have it handy keep working; they just
    don't get that recovery tab (the sheet's rows still show up in "Full
    data" and the coverage/reconciliation numbers either way)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    segregated_path = out_dir / f"{stem}_segregated.xlsx"
    export.write_segregated_export(result.canonical, segregated_path)

    unmapped_sheet_raw = None
    if sheets:
        unmapped_names = {rec.sheet_name for rec in result.coverage.sheet_audit if rec.status == "unmapped"}
        unmapped_sheet_raw = {s.sheet_name: s.raw for s in sheets if s.sheet_name in unmapped_names}

    health_path = out_dir / f"{stem}_health_report.xlsx"
    report.write_health_report_excel(result.health, result.validation_result.exceptions, result.duplicates,
                                      result.canonical, health_path, unmapped_sheet_raw=unmapped_sheet_raw)

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
