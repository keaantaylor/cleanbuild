from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
    file_name: str
    file_size_bytes: int
    sheet_count_total: int
    rows_processed: int
    rows_total: int
    coverage_pct: float | None
    grade: str | None
    score: float | None
    status: str
    processing_error: str | None = None


class SheetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    sheet_name: str
    sheet_index: int
    header_row_index: int | None
    row_count: int
    status: str
    skip_reason: str | None
    # Section 9/11: a sheet with 0 mapped fields ("unmapped") is never the
    # same status as a genuinely empty sheet ("empty") -- see
    # persistence_service.sheet_mapping_status.
    mapping_status: str = "mapped"
    fields_mapped: int = 0
    fields_total: int = 0


class MappingFieldOut(BaseModel):
    field_code: str
    field_name: str
    source_column: str | None
    mapping_state: str
    confidence_score: float | None
    sample_values: list[str] = []
    confirmed: bool


class MappingConfirmRequest(BaseModel):
    # {field_code: source_column_or_null}
    mappings: dict[str, str | None]
    actor: str | None = None


class ValidationResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    claim_row_id: str
    check_type: str
    status: str
    severity: str
    message: str
    delta: float | None


class ExceptionRowOut(BaseModel):
    claim_row_id: str
    claim_reference: str | None
    sheet_name: str | None
    row_index: int
    amount: float | None
    check_type: str
    status: str
    severity: str
    message: str
    validation_result_id: str


class ExcludedRowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    sheet_name: str
    row_number: int
    reason: str
    detail: str
    values: dict


class DuplicatePairOut(BaseModel):
    validation_result_id: str
    match_type: str
    row_a: dict
    row_b: dict
    detail: str
    review_status: str | None = None


class ObligationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    report_id: str
    claim_row_id: str | None
    owner: str | None
    deadline: date | None
    status: str
    note: str | None
    created_by: str | None
    created_at: datetime
    resolved_at: datetime | None


class ObligationCreateRequest(BaseModel):
    claim_row_id: str | None = None
    owner: str | None = None
    deadline: date | None = None
    note: str | None = None
    created_by: str | None = None


class ObligationUpdateRequest(BaseModel):
    owner: str | None = None
    deadline: date | None = None
    status: str | None = None
    note: str | None = None


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    report_id: str
    severity: str
    source: str
    message: str
    acknowledged: bool
    created_at: datetime


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    report_id: str
    action_type: str
    entity_type: str
    entity_id: str
    actor: str
    before_value: dict | None
    after_value: dict | None
    created_at: datetime


class TemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    sender_identifier: str | None
    field_mappings: dict
    is_standard: bool
    is_deletable: bool
    created_by: str | None
    created_at: datetime


class TemplateCreateRequest(BaseModel):
    name: str
    sender_identifier: str | None = None
    field_mappings: dict
    created_by: str | None = None


class FieldCompletenessOut(BaseModel):
    field_code: str
    field_name: str
    present: int
    denominator: int
    never_mapped: bool


class SheetCoverageOut(BaseModel):
    sheet_name: str
    status: str
    row_count: int
    skip_reason: str | None


class ReconciliationOut(BaseModel):
    """Section 5: the row-count reconciliation every upload must be able
    to answer. reconciles is False only if a genuine discrepancy was
    found between two independently-computed totals -- see
    persistence_service.compute_report_summary."""
    source_worksheets: int
    source_data_rows: int
    mapped_rows: int
    unmapped_rows: int
    rejected_rows: int
    duplicate_rows: int
    exported_rows: int
    rows_requiring_review: int
    reconciles: bool


class ExceptionSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    report_id: str
    narrative_status: str
    aggregate: dict
    narrative: dict | None
    narrative_model: str | None
    narrative_error: str | None
    narrative_warning: str | None
    created_at: datetime
    completed_at: datetime | None


class ReportSummaryOut(BaseModel):
    report: ReportOut
    sheets_total: int
    sheets_processed: int
    missing_mandatory_rows: int
    arithmetic_mismatches: int
    arithmetic_not_evaluable: int
    exact_duplicates: int
    probable_duplicates: int
    field_completeness: list[FieldCompletenessOut]
    missing_mandatory_by_sheet: dict[str, int]
    not_evaluable_by_reason: dict[str, int] = {}
    excluded_row_counts: dict[str, int] = {}
    skipped_sheets: list[dict] = []
    unmapped_sheets: list[dict] = []
    reconciliation: ReconciliationOut
    
