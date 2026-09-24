"""API contracts. Request models forbid unknown fields (a tampered body with
an extra `tenant_id`, `actor` or `status` is rejected, not silently
ignored) and bound every string. Response models expose only what the UI
needs: no storage keys, internal error detail, hashes of secrets or tenant
ids of other tenants."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

T = TypeVar("T")
# All timestamps are stored in UTC; SQLite hands them back naive. Always
# serialise with an explicit offset so clients never guess the zone.
UtcDatetime = Annotated[datetime, AfterValidator(lambda d: d if d.tzinfo else d.replace(tzinfo=timezone.utc))]
# Shape check only (no extra dependency); the address is normalised to lower case.
Email = Annotated[str, Field(min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")]


class _Req(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


# ---------------------------------------------------------------- auth

class SignupRequest(_Req):
    email: Email
    password: str = Field(min_length=1, max_length=256)
    display_name: str = Field(min_length=1, max_length=200)
    organisation: str = Field(min_length=1, max_length=200)


class LoginRequest(_Req):
    email: Email
    password: str = Field(min_length=1, max_length=256)


class UserOut(BaseModel):
    id: str
    email: str
    display_name: str


class TenantOut(BaseModel):
    id: str
    name: str
    retention_days: int


class MeOut(BaseModel):
    user: UserOut
    tenant: TenantOut
    role: str
    can_write: bool
    csrf_token: str


# ---------------------------------------------------------------- reports

class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: str
    status: str
    stage: str | None
    attempts: int
    max_attempts: int
    error_code: str | None
    error_message: str | None
    created_at: UtcDatetime
    started_at: UtcDatetime | None
    finished_at: UtcDatetime | None
    heartbeat_at: UtcDatetime | None


class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: UtcDatetime
    updated_at: UtcDatetime | None = None
    expires_at: UtcDatetime | None = None
    file_name: str
    file_kind: str | None = None
    file_size_bytes: int
    source_sha256: str | None = None
    sheet_count_total: int
    rows_processed: int
    rows_total: int
    coverage_pct: float | None
    grade: str | None
    score: float | None
    status: str
    error_code: str | None = None
    processing_error: str | None = None
    ingest_notes: dict | None = None
    job: JobOut | None = None


class ReportSummaryOut(BaseModel):
    report: ReportOut
    summary: dict | None


class SheetOut(BaseModel):
    id: str
    sheet_name: str
    sheet_index: int
    header_row_index: int | None
    row_count: int
    source_column_count: int
    status: str
    skip_reason: str | None
    hidden: bool
    notes: list[str]
    trailing_blank_rows: int
    mapping_status: str
    fields_mapped: int
    fields_total: int
    needs_review: int


class MappingFieldOut(BaseModel):
    field_code: str
    field_name: str
    required: bool
    source_column: str | None
    mapping_state: str
    review_state: str
    evidence: str | None
    rule_version: str | None
    ai_model: str | None
    confidence_score: float | None
    sample_values: list[str]
    confirmed: bool


class SheetMappingOut(BaseModel):
    sheet: SheetOut
    headers: list[str]
    fields: list[MappingFieldOut]


class MappingConfirmRequest(_Req):
    # {field_code: source_column_or_null}; validated against THIS sheet's headers
    mappings: dict[str, str | None] = Field(max_length=100)


class ExceptionRowOut(BaseModel):
    validation_result_id: str
    claim_row_id: str
    claim_reference: str | None
    sheet_name: str | None
    source_row_number: int | None
    row_index: int
    currency: str | None
    amount: float | None
    check_type: str
    rule: str | None
    status: str
    severity: str
    message: str


class ExcludedRowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    sheet_name: str
    row_number: int
    row_count: int
    reason: str
    detail: str
    values: dict


class ClaimRowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    sheet_id: str
    source_row_number: int | None
    claim_reference: str | None
    insured_name: str | None
    claim_status: str | None
    date_of_loss: date | None
    reporting_period: str | None
    currency: str | None
    paid_amount: float | None
    reserve_amount: float | None
    incurred_amount: float | None


class DuplicatePairOut(BaseModel):
    validation_result_id: str
    match_type: str
    status: str
    row_a: dict
    row_b: dict
    detail: str
    review_status: str | None = None


class DuplicateReviewRequest(_Req):
    review_status: Literal["not_duplicate", "flagged_for_sender", "confirmed_duplicate"]


# ---------------------------------------------------------------- obligations / alerts / audit / templates

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
    created_at: UtcDatetime
    resolved_at: UtcDatetime | None


class ObligationCreateRequest(_Req):
    claim_row_id: str | None = Field(default=None, max_length=36)
    owner: str | None = Field(default=None, max_length=255)
    deadline: date | None = None
    note: str | None = Field(default=None, max_length=2000)


class ObligationUpdateRequest(_Req):
    owner: str | None = Field(default=None, max_length=255)
    deadline: date | None = None
    status: Literal["OPEN", "IN_PROGRESS", "RESOLVED"] | None = None
    note: str | None = Field(default=None, max_length=2000)


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    report_id: str
    severity: str
    source: str
    message: str
    acknowledged: bool
    created_at: UtcDatetime


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    seq: int
    report_id: str | None
    action_type: str
    entity_type: str
    entity_id: str
    actor: str
    before_value: dict | None
    after_value: dict | None
    created_at: UtcDatetime
    entry_hash: str


class AuditVerifyOut(BaseModel):
    intact: bool
    entries: int
    first_bad_seq: int | None


class TemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    sender_identifier: str | None
    field_mappings: dict
    is_standard: bool
    is_deletable: bool
    created_by: str | None
    created_at: UtcDatetime


class TemplateCreateRequest(_Req):
    name: str = Field(min_length=1, max_length=255)
    sender_identifier: str | None = Field(default=None, max_length=255)
    field_mappings: dict[str, str] = Field(max_length=200)


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
    created_at: UtcDatetime
    completed_at: UtcDatetime | None
