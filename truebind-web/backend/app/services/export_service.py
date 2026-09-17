"""Export endpoints reuse bordereaux/report.py's reportlab PDF builder and
plain CSV writers -- no re-implementation of layout code."""

from __future__ import annotations

import csv
import io

from sqlalchemy.orm import Session

from ..models.audit import AuditLogEntry
from ..models.reports import ClaimRow


def audit_log_csv(db: Session, report_id: str) -> str:
    rows = db.query(AuditLogEntry).filter_by(report_id=report_id).order_by(AuditLogEntry.created_at).all()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["timestamp", "action_type", "entity_type", "entity_id", "actor", "before", "after"])
    for r in rows:
        writer.writerow([r.created_at.isoformat(), r.action_type, r.entity_type, r.entity_id, r.actor,
                          r.before_value, r.after_value])
    return buf.getvalue()


def claims_by_status_csv(db: Session, report_id: str) -> str:
    rows = db.query(ClaimRow).filter_by(report_id=report_id).all()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["claim_reference", "insured_name", "claim_status", "date_of_loss", "date_notified",
                      "policy_reference", "paid_amount", "reserve_amount", "incurred_amount", "currency"])
    for r in sorted(rows, key=lambda r: (r.claim_status or "", r.claim_reference or "")):
        writer.writerow([r.claim_reference, r.insured_name, r.claim_status, r.date_of_loss, r.date_notified,
                          r.policy_reference, r.paid_amount, r.reserve_amount, r.incurred_amount, r.currency])
    return buf.getvalue()
