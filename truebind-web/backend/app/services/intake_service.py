"""One way in for every file, whatever the channel (web upload, API,
e-mail): the same file gate, the same immutable original, the same report
row, audit entry, INGEST job and inbound alert.

inspect(): the file gate (type, signature, zip-bomb, size and shape limits);
a rejection is audited with its channel and returned, never raised past the
caller. create_report(): store the original (content-addressed, write once)
and create the report + INGEST job in the caller's transaction.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from ..models._util import new_uuid, utcnow
from ..models.identity import Tenant
from ..models.reports import Report
from ..security.file_guard import Verdict, inspect_upload
from . import alert_service, audit_service, job_service
from .storage import get_store, sha256_file


def inspect(
    db: Session,
    *,
    tenant_id: str,
    path: Path,
    display_name: str,
    size: int,
    channel: str,
    actor: str,
    actor_user_id: str | None,
    sender: str | None = None,
) -> Verdict:
    verdict = inspect_upload(path, display_name)
    if not verdict.accepted:
        audit_service.log_action(
            db,
            tenant_id,
            None,
            "UPLOAD_REJECTED",
            "REPORT",
            new_uuid(),
            after={
                "file_name": display_name,
                "size": size,
                "sha256": sha256_file(path),
                "code": verdict.code,
                "channel": channel,
                "sender": sender,
            },
            actor=actor,
            actor_user_id=actor_user_id,
        )
    return verdict


def create_report(
    db: Session,
    *,
    tenant: Tenant,
    path: Path,
    verdict: Verdict,
    display_name: str,
    size: int,
    channel: str,
    actor: str,
    actor_user_id: str | None,
    sender: str | None = None,
    programme: str | None = None,
) -> Report:
    kind = verdict.kind
    if kind is None:  # an accepted verdict always names its kind
        raise ValueError("unsupported file type")
    stored = get_store().put_original(tenant.id, kind, path, db=db)
    report = Report(
        tenant_id=tenant.id,
        created_by=actor_user_id,
        file_name=display_name,
        file_size_bytes=size,
        file_kind=kind,
        status="UPLOADED",
        ingest_notes={"file_notes": verdict.notes},
        expires_at=utcnow() + timedelta(days=tenant.retention_days),
        updated_at=utcnow(),
        source_channel=channel,
        sender=(sender or "").strip() or None,
        programme=(programme or "").strip() or None,
    )
    db.add(report)
    db.flush()
    report.source_sha256 = stored.sha256
    report.storage_key = stored.key
    audit_service.log_action(
        db,
        tenant.id,
        report.id,
        "REPORT_UPLOADED",
        "REPORT",
        report.id,
        after={
            "file_name": display_name,
            "size": size,
            "sha256": report.source_sha256,
            "kind": kind,
            "notes": verdict.notes,
            "channel": channel,
            "sender": report.sender,
        },
        actor=actor,
        actor_user_id=actor_user_id,
    )
    job_service.enqueue(db, report, "INGEST", actor=actor, actor_user_id=actor_user_id)
    via = {"upload": "", "email": " by e-mail"}.get(channel, f" via {channel}")
    alert_service.raise_alert(
        db,
        tenant.id,
        report.id,
        "INFO",
        alert_service.INBOUND,
        f"New file received{via}: {display_name}"
        + (f" from {report.sender}" if report.sender else "")
        + f" ({size // 1024 or 1} KB, {kind}).",
    )
    return report
