"""Operational alerts. Quality alerts (coverage, duplicates, ...) are
written when a report is processed; lifecycle alerts (file received,
review needed, report ready, processing failed, export outcome) are raised
here. Every alert names its report, a severity, a plain explanation and is
unread (acknowledged=False) until someone reads it."""

from __future__ import annotations

from sqlalchemy.orm import Session

from ..models.alerts import Alert

# Lifecycle sources (quality sources come from persistence_service).
INBOUND = "INBOUND"
REVIEW_NEEDED = "REVIEW_NEEDED"
REPORT_READY = "REPORT_READY"
PROCESSING_FAILED = "PROCESSING_FAILED"
EXPORT_COMPLETE = "EXPORT_COMPLETE"
EXPORT_FAILED = "EXPORT_FAILED"
QUALITY_SOURCES = ("COVERAGE", "MANDATORY_FAIL", "NOT_EVALUABLE", "DUPLICATE", "MAPPING_COMPLETENESS",
                   "UNMAPPED_COLUMNS", "PERIOD_MISSING")


def raise_alert(db: Session, tenant_id: str, report_id: str, severity: str, source: str, message: str) -> Alert:
    a = Alert(tenant_id=tenant_id, report_id=report_id, severity=severity, source=source, message=message[:1000])
    db.add(a)
    return a
