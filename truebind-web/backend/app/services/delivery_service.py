"""Outbound deliveries: record every output and, for e-mail, actually send
it when SMTP is configured. A delivery that cannot be made is recorded as
FAILED / NOT_CONFIGURED with a customer-safe reason -- never silently
dropped, never reported as sent."""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from sqlalchemy.orm import Session

from .. import config
from ..models._util import utcnow
from ..models.deliveries import Delivery
from ..models.reports import Report
from . import alert_service, audit_service, export_service

log = logging.getLogger("truebind.delivery")


def email_configured() -> bool:
    return bool(config.SMTP_HOST)


def record(db: Session, tenant_id: str, report_id: str, kind: str, channel: str, destination: str | None,
           file_name: str, size_bytes: int | None, status: str, error: str | None, actor: str | None) -> Delivery:
    d = Delivery(tenant_id=tenant_id, report_id=report_id, kind=kind, channel=channel, destination=destination,
                 file_name=file_name, size_bytes=size_bytes, status=status, error=error, created_by=actor,
                 completed_at=utcnow())
    db.add(d)
    db.flush()
    return d


def send_email(db: Session, tenant_id: str, report: Report, kind: str, recipient: str, actor: str,
               actor_user_id: str | None) -> Delivery:
    name = export_service.file_name(report, kind)
    if not email_configured():
        d = record(db, tenant_id, report.id, kind, "email", recipient, name, None, "NOT_CONFIGURED",
                   "E-mail delivery is not configured on this server (no SMTP settings).", actor)
    else:
        try:
            header, rows = export_service.export_rows(db, tenant_id, report, kind)
            data = export_service.render_csv(header, rows, max_bytes=config.MAX_EMAIL_ATTACHMENT_BYTES)
            msg = EmailMessage()
            msg["From"], msg["To"] = config.SMTP_FROM, recipient
            msg["Subject"] = f"TrueBind: {export_service.KINDS[kind]} for {report.file_name}"
            msg.set_content(f"Attached: {export_service.KINDS[kind]} export for {report.file_name}, "
                            f"sent from TrueBind by {actor}.")
            msg.add_attachment(data, maintype="text", subtype="csv", filename=name)
            with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=20) as smtp:
                if config.SMTP_STARTTLS:
                    smtp.starttls()
                if config.SMTP_USER:
                    smtp.login(config.SMTP_USER, config.SMTP_PASSWORD or "")
                smtp.send_message(msg)
            d = record(db, tenant_id, report.id, kind, "email", recipient, name, len(data), "DELIVERED", None, actor)
        except ValueError:
            d = record(db, tenant_id, report.id, kind, "email", recipient, name, None, "FAILED",
                       "The file is larger than the e-mail attachment limit. Download it instead.", actor)
        except (smtplib.SMTPException, OSError) as exc:
            log.warning("e-mail delivery failed: %s", type(exc).__name__)
            d = record(db, tenant_id, report.id, kind, "email", recipient, name, None, "FAILED",
                       "The mail server did not accept the message. Try again or download the file.", actor)
    ok = d.status == "DELIVERED"
    alert_service.raise_alert(db, tenant_id, report.id, "INFO" if ok else "MEDIUM",
                              alert_service.EXPORT_COMPLETE if ok else alert_service.EXPORT_FAILED,
                              f"{export_service.KINDS[kind].capitalize()} export for {report.file_name} "
                              + (f"sent to {recipient}." if ok else f"was not sent to {recipient}: {d.error}"))
    audit_service.log_action(db, tenant_id, report.id, "EXPORT_GENERATED", "REPORT", report.id,
                             after={"export": kind, "channel": "email", "recipient": recipient, "status": d.status},
                             actor=actor, actor_user_id=actor_user_id)
    return d
