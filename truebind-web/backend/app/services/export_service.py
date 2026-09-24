"""Output files. One builder per export kind, shared by browser downloads
and outbound deliveries (e-mail), so every channel sends identical,
formula-injection-safe CSV."""

from __future__ import annotations

import csv
import io
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_session_factory, set_tenant
from ..models.audit import AuditLogEntry
from ..models.reports import ClaimRow, Report, Sheet, ValidationResult

KINDS = {"claims_csv": "claims", "exceptions_csv": "exceptions", "audit_csv": "audit"}
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r", "\n")


def csv_safe(v):
    """Neutralise spreadsheet formula injection (OWASP CSV Injection): text
    beginning with a formula trigger is prefixed with a quote. Numbers are
    left as numbers (a negative amount stays numeric)."""
    if v is None:
        return ""
    if isinstance(v, str) and v.startswith(_FORMULA_PREFIXES):
        return "'" + v
    return v


def csv_stream(header: list[str], rows_iter):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    n = 0
    for row in rows_iter:
        w.writerow([csv_safe(v) for v in row])
        n += 1
        if n % 2000 == 0:
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate()
    yield buf.getvalue()


def render_csv(header, rows, max_bytes: int | None = None) -> bytes:
    out = io.BytesIO()
    for chunk in csv_stream(header, rows):
        out.write(chunk.encode("utf-8"))
        if max_bytes is not None and out.tell() > max_bytes:
            raise ValueError("export too large")
    return out.getvalue()


def file_name(report: Report, kind: str) -> str:
    return f"truebind_{report.id}_{KINDS[kind]}.csv"


def _stream_query(tenant_id: str, stmt):
    """Rows read on a session owned by the generator: the request-scoped
    session may be closed before a streamed body is sent."""
    db = get_session_factory()()
    try:
        set_tenant(db, tenant_id)
        yield from db.execute(stmt.execution_options(yield_per=5000))
    finally:
        db.close()


_CLAIM_EXPORT_COLS = [
    ("claim_reference", ClaimRow.claim_reference), ("insured_name", ClaimRow.insured_name),
    ("policy_reference", ClaimRow.policy_reference), ("claim_status", ClaimRow.claim_status),
    ("date_of_loss", ClaimRow.date_of_loss), ("date_notified", ClaimRow.date_notified),
    ("reporting_period", ClaimRow.reporting_period), ("currency", ClaimRow.currency),
    ("paid_this_month", ClaimRow.paid_this_month), ("previously_paid", ClaimRow.previously_paid),
    ("paid_to_date", ClaimRow.paid_amount), ("reserve", ClaimRow.reserve_amount),
    ("fees_paid_this_month", ClaimRow.fees_paid_this_month), ("fees_previously_paid", ClaimRow.fees_previously_paid),
    ("fees_reserve", ClaimRow.fees_reserve), ("fees_paid_to_date", ClaimRow.fees_paid_to_date),
    ("total_incurred_indemnity", ClaimRow.incurred_indemnity), ("total_incurred_incl_fees", ClaimRow.incurred_amount),
]


def export_rows(db: Session, tenant_id: str, report: Report, kind: str):
    """(header, row iterator) for one export kind of one report."""
    sheet_names = dict(db.query(Sheet.id, Sheet.sheet_name).filter(Sheet.report_id == report.id).all())
    if kind == "claims_csv":
        findings: dict[str, list[str]] = {}
        for crid, rule, status in (db.query(ValidationResult.claim_row_id, ValidationResult.rule,
                                            ValidationResult.status)
                                   .filter(ValidationResult.report_id == report.id)):
            findings.setdefault(crid, []).append(f"{rule}:{status}")
        stmt = (select(ClaimRow.id, ClaimRow.sheet_id, ClaimRow.source_row_number,
                       *[c for _, c in _CLAIM_EXPORT_COLS], ClaimRow.unmapped_values)
                .where(ClaimRow.report_id == report.id).order_by(ClaimRow.sheet_id, ClaimRow.row_index))
        header = (["sheet_name", "source_row_number"] + [n for n, _ in _CLAIM_EXPORT_COLS]
                  + ["unmapped_source_values", "findings"])

        def rows():
            for r in _stream_query(tenant_id, stmt):
                extra = json.dumps(r[-1], ensure_ascii=False, sort_keys=True) if r[-1] else ""
                yield [sheet_names.get(r[1]), r[2], *r[3:-1], extra, "; ".join(findings.get(r[0], []))]
        return header, rows()
    if kind == "exceptions_csv":
        stmt = (select(ClaimRow.sheet_id, ClaimRow.source_row_number, ClaimRow.claim_reference,
                       ValidationResult.check_type, ValidationResult.rule, ValidationResult.status,
                       ValidationResult.severity, ValidationResult.message)
                .join(ClaimRow, ClaimRow.id == ValidationResult.claim_row_id)
                .where(ValidationResult.report_id == report.id)
                .order_by(ClaimRow.sheet_id, ClaimRow.row_index))

        def rows():
            for r in _stream_query(tenant_id, stmt):
                yield [sheet_names.get(r[0]), *r[1:]]
        return (["sheet_name", "source_row_number", "claim_reference", "check_type", "rule", "status", "severity",
                 "message"], rows())
    if kind == "audit_csv":
        entries = (db.query(AuditLogEntry).filter(AuditLogEntry.tenant_id == tenant_id,
                                                  AuditLogEntry.report_id == report.id)
                   .order_by(AuditLogEntry.seq).all())
        rows = ([e.seq, e.created_at.isoformat(), e.action_type, e.entity_type, e.entity_id, e.actor,
                 e.before_value, e.after_value, e.entry_hash] for e in entries)
        return (["seq", "timestamp", "action_type", "entity_type", "entity_id", "actor", "before", "after",
                 "entry_hash"], rows)
    raise ValueError(f"unknown export kind {kind!r}")
