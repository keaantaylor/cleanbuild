"""Everything the Health Report needs, read once from the database into plain
dataclasses. ``health_report.build_health_report`` takes only these, so it
can be tested (and timed) without a database."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from importlib import metadata

from bordereaux.rules import RULESET_VERSION
from bordereaux.rules import rule as catalogue_rule
from bordereaux.schema import FIELDS_BY_CODE
from openpyxl.utils import get_column_letter
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.audit import AuditLogEntry
from ..models.identity import User
from ..models.jobs import Job
from ..models.reports import ClaimRow, ExcludedRow, Mapping, Report, Sheet, ValidationResult
from ..services.persistence_service import FIELD_TO_COLUMN
from .theme import PRIORITY_WORD, RESULT_WORD


@dataclass
class ReportMeta:
    report_id: str
    file_name: str
    file_kind: str | None
    sender: str | None
    programme: str | None
    uploaded_at: dt.datetime | None
    uploaded_by: str | None
    processed_at: dt.datetime | None
    exported_at: dt.datetime
    exported_by: str
    reporting_periods: list[str] = field(default_factory=list)
    engine_version: str = "unknown"
    ruleset_version: str = RULESET_VERSION


@dataclass
class SheetInfo:
    name: str
    index: int
    status: str  # CONFIRMED | SKIPPED | PENDING_CONFIRMATION
    skip_reason: str | None
    claim_rows: int
    source_rows: int
    excluded_rows: int
    headers: list[str]


@dataclass
class ColumnInfo:
    sheet: str
    letter: str
    source_column: str
    field_code: str | None
    field_name: str | None
    state: str
    confidence: float | None = None
    confirmed_by: str | None = None
    confirmed_at: dt.datetime | None = None
    ai_model: str | None = None
    evidence: str | None = None


@dataclass
class FieldGap:
    """A canonical field that no column on a read sheet was mapped to."""
    sheet: str
    field_code: str
    field_name: str
    required: bool


@dataclass
class ClaimInfo:
    sheet: str | None
    row: int | None
    claim_ref: str | None
    insured: str | None
    policy_ref: str | None
    date_of_loss: dt.date | None
    currency: str | None
    paid: float | None
    reserve: float | None
    fees_paid: float | None
    fees_reserve: float | None
    incurred: float | None


@dataclass
class Issue:
    id: str
    claim_row_id: str
    claim: ClaimInfo
    check_type: str
    rule: str
    label: str
    result: str  # Error | Warning | Couldn't check
    severity: str  # CRITICAL | HIGH | MEDIUM | INFO
    priority: str
    field_code: str | None
    field_name: str | None
    column: str | None
    cell: str | None
    value_found: object
    expected: object
    actual: object
    sentence: str
    fix: str
    owner: str
    status: str  # Open | Queried with sender | Resolved | Accepted
    assignee: str | None
    note: str | None
    match_claim_row_id: str | None = None
    match_confidence: int | None = None
    message: str = ""

    @property
    def sheet(self) -> str | None:
        return self.claim.sheet

    @property
    def row(self) -> int | None:
        return self.claim.row


@dataclass
class AuditEvent:
    seq: int
    at: dt.datetime
    action: str
    entity: str
    actor: str
    before: dict | None
    after: dict | None
    entry_hash: str


@dataclass
class HealthReportData:
    meta: ReportMeta
    summary: dict
    grade: str | None
    score: float | None
    sheets: list[SheetInfo]
    columns: list[ColumnInfo]
    field_gaps: list[FieldGap]
    issues: list[Issue]
    claims: dict[str, ClaimInfo]  # every claim row an issue points at, by id (duplicate partners included)
    audit: list[AuditEvent]

    @property
    def health_view(self) -> dict:
        return self.summary.get("health_view") or {}


def engine_version() -> str:
    try:
        return metadata.version("bordereaux")
    except metadata.PackageNotFoundError:  # pragma: no cover - always installed with the backend
        return "unknown"


def workflow_status(extra: dict) -> str:
    """The Exceptions sheet's Status from the issue's lifecycle in the app."""
    status = extra.get("issue_status") or "DETECTED"
    if status in ("RESOLVED", "AUTO_FIXED"):
        return "Resolved"
    if status == "OVERRIDDEN":
        return "Accepted"
    moved_by_person = any((h or {}).get("actor") not in (None, "system") for h in extra.get("history") or [])
    if status == "REQUIRES_INFORMATION" and moved_by_person:
        return "Queried with sender"
    return "Open"


def _num(v) -> float | None:
    return None if v is None else float(v)


def _plain(v):
    """JSON-stored numbers come back as int/float/str; keep numbers numeric."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    return v


_CLAIM_COLS = (ClaimRow.id, ClaimRow.sheet_id, ClaimRow.source_row_number, ClaimRow.claim_reference,
               ClaimRow.insured_name, ClaimRow.policy_reference, ClaimRow.date_of_loss, ClaimRow.currency,
               ClaimRow.paid_amount, ClaimRow.reserve_amount, ClaimRow.fees_paid_to_date, ClaimRow.fees_reserve,
               ClaimRow.incurred_amount)


def _claim(r, sheet_names: dict[str, str]) -> ClaimInfo:
    return ClaimInfo(sheet=sheet_names.get(r.sheet_id), row=r.source_row_number, claim_ref=r.claim_reference,
                     insured=r.insured_name, policy_ref=r.policy_reference, date_of_loss=r.date_of_loss,
                     currency=r.currency, paid=_num(r.paid_amount), reserve=_num(r.reserve_amount),
                     fees_paid=_num(r.fees_paid_to_date), fees_reserve=_num(r.fees_reserve),
                     incurred=_num(r.incurred_amount))


def collect(db: Session, report: Report, exported_by: str, now: dt.datetime | None = None) -> HealthReportData:
    tid = report.tenant_id
    summary = report.summary if isinstance(report.summary, dict) else {}
    sheets_db = (db.query(Sheet).filter(Sheet.report_id == report.id, Sheet.tenant_id == tid)
                 .order_by(Sheet.sheet_index).all())
    sheet_names = {s.id: s.sheet_name for s in sheets_db}
    by_name = {s.sheet_name: s for s in sheets_db}

    claim_counts: dict[str, int] = {}
    for sid, in db.execute(select(ClaimRow.sheet_id).where(ClaimRow.report_id == report.id)):
        claim_counts[sid] = claim_counts.get(sid, 0) + 1
    excluded: dict[str, int] = {}
    for name, count in db.query(ExcludedRow.sheet_name, ExcludedRow.row_count).filter(
            ExcludedRow.report_id == report.id):
        excluded[name] = excluded.get(name, 0) + (count or 1)
    audit_rows = {a["sheet_name"]: a for a in summary.get("sheet_audit") or []}
    sheets = []
    for s in sheets_db:
        claims = claim_counts.get(s.id, 0)
        a = audit_rows.get(s.sheet_name) or {}
        sheets.append(SheetInfo(
            name=s.sheet_name, index=s.sheet_index, status=s.status, skip_reason=s.skip_reason or a.get("reason"),
            claim_rows=claims, source_rows=claims + excluded.get(s.sheet_name, 0),
            excluded_rows=excluded.get(s.sheet_name, 0),
            headers=[("" if h is None else str(h)) for h in (s.headers or [])]))

    # Columns: every source column of every read sheet, with what it was mapped to.
    mappings = db.query(Mapping).filter(Mapping.report_id == report.id, Mapping.tenant_id == tid).all()
    by_sheet_col: dict[tuple[str, str], Mapping] = {}
    field_gaps: list[FieldGap] = []
    for m in mappings:
        name = sheet_names.get(m.sheet_id)
        if name is None:
            continue
        if m.source_column:
            by_sheet_col[(name, m.source_column)] = m
        elif by_name[name].status == "CONFIRMED":
            spec = FIELDS_BY_CODE.get(m.field_code)
            field_gaps.append(FieldGap(name, m.field_code, m.field_name, bool(spec and spec.required)))
    columns: list[ColumnInfo] = []
    for s in sheets:
        if s.status != "CONFIRMED":
            continue
        for i, h in enumerate(s.headers, start=1):
            if not h.strip():
                continue
            m = by_sheet_col.get((s.name, h))
            columns.append(ColumnInfo(
                sheet=s.name, letter=get_column_letter(i), source_column=h,
                field_code=m.field_code if m else None, field_name=m.field_name if m else None,
                state=m.mapping_state if m else "UNMAPPED", confidence=m.confidence_score if m else None,
                confirmed_by=m.confirmed_by if m else None, confirmed_at=m.confirmed_at if m else None,
                ai_model=m.ai_model if m else None, evidence=m.evidence if m else None))

    # Issues, with the claim row each one is on.
    row_cols = [ClaimRow.id, ClaimRow.sheet_id, ClaimRow.source_row_number] + [
        getattr(ClaimRow, c) for c in sorted(set(FIELD_TO_COLUMN.values()))]
    stmt = (select(ValidationResult.id.label("vr_id"), ValidationResult.check_type, ValidationResult.rule,
                   ValidationResult.status, ValidationResult.severity, ValidationResult.message,
                   ValidationResult.extra, *row_cols)
            .join(ClaimRow, ClaimRow.id == ValidationResult.claim_row_id)
            .where(ValidationResult.report_id == report.id, ValidationResult.tenant_id == tid)
            .order_by(ClaimRow.sheet_id, ClaimRow.row_index, ValidationResult.check_type))
    issues: list[Issue] = []
    claims: dict[str, ClaimInfo] = {}
    partners: set[str] = set()
    for r in db.execute(stmt):
        m = r._mapping
        x = r.extra or {}
        claim = claims.get(r.id)
        if claim is None:
            claim = claims[r.id] = _claim(r, sheet_names)
        rule = r.rule or ""
        cat = catalogue_rule(rule)
        couldnt = r.status == "NOT_EVALUABLE"
        field_code = x.get("field_code")
        spec = FIELDS_BY_CODE.get(field_code or "")
        attr = FIELD_TO_COLUMN.get(field_code or "")
        value = _plain(x["actual"]) if x.get("actual") is not None else (m.get(attr) if attr else None)
        if r.check_type == "MANDATORY_FIELD" and value in (None, ""):
            value = "(blank)"
        issues.append(Issue(
            id=r.vr_id, claim_row_id=r.id, claim=claim, check_type=r.check_type, rule=rule,
            label="Total incurred could not be reconciled" if couldnt else cat.label,
            result=RESULT_WORD.get(r.status, r.status), severity=r.severity,
            priority=PRIORITY_WORD.get(r.severity, r.severity.title()),
            field_code=field_code, field_name=spec.name if spec else None, column=x.get("column"),
            cell=x.get("cell"), value_found=_value(value),
            expected=_plain(x.get("expected")), actual=_plain(x.get("actual")),
            sentence=x.get("sentence") or r.message,
            fix="Map the missing column, or ask the sender for it." if couldnt else cat.fix,
            owner="Sender" if (x.get("owner") or cat.owner) == "sender" else "Us",
            status=workflow_status(x), assignee=x.get("assignee"), note=x.get("note"),
            match_claim_row_id=x.get("match_claim_row_id"), match_confidence=x.get("confidence"),
            message=r.message))
        if x.get("match_claim_row_id"):
            partners.add(x["match_claim_row_id"])
    missing = partners - set(claims)
    if missing:
        ids = list(missing)
        for i in range(0, len(ids), 500):
            for r in db.execute(select(*_CLAIM_COLS).where(ClaimRow.id.in_(ids[i:i + 500]))):
                claims[r.id] = _claim(r, sheet_names)

    users = dict(db.query(User.id, User.display_name).filter(User.id == report.created_by).all()) \
        if report.created_by else {}
    job = (db.query(Job).filter(Job.report_id == report.id, Job.kind == "PROCESS", Job.status == "SUCCEEDED")
           .order_by(Job.finished_at.desc()).first())
    audit = [AuditEvent(e.seq, e.created_at, e.action_type, e.entity_type, e.actor, e.before_value, e.after_value,
                        e.entry_hash)
             for e in db.query(AuditLogEntry).filter(AuditLogEntry.tenant_id == tid,
                                                     AuditLogEntry.report_id == report.id)
             .order_by(AuditLogEntry.seq)]
    meta = ReportMeta(
        report_id=report.id, file_name=report.file_name, file_kind=report.file_kind, sender=report.sender,
        programme=report.programme, uploaded_at=report.created_at,
        uploaded_by=users.get(report.created_by) if report.created_by else None,
        processed_at=(job.finished_at if job and job.finished_at else report.updated_at),
        exported_at=now or dt.datetime.now(dt.UTC), exported_by=exported_by,
        reporting_periods=sorted(str(k) for k in (summary.get("reporting_periods") or {}) if k),
        engine_version=engine_version())
    return HealthReportData(meta=meta, summary=summary, grade=report.grade, score=report.score, sheets=sheets,
                            columns=columns, field_gaps=field_gaps, issues=issues, claims=claims, audit=audit)


def _value(v):
    if v is None or isinstance(v, (dt.date, dt.datetime, int)):
        return v
    if isinstance(v, float):
        return None if v != v else v  # NaN
    if hasattr(v, "is_finite"):  # Decimal
        return float(v)
    return str(v)
