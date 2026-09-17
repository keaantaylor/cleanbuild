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


class SheetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    sheet_name: str
    sheet_index: int
    header_row_index: int | None
    row_count: int
    status: str
    skip_reason: str | None


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
    severity: str
    message: str
    validation_result_id: str


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
