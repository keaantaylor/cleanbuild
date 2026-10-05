"""E-mail intake: bordereaux e-mailed to an organisation's inbound address
(<inbound_token>@<INBOUND_EMAIL_DOMAIN>) are ingested like uploads.

Providers: Postmark inbound webhook (JSON, attachments base64) and Amazon
SES receipt rule -> SNS (raw MIME, base64). Both become an InboundMessage;
every attachment then goes through intake_service (same file gate, immutable
original, audit, INGEST job). Provider retries are harmless: each
(message id, attachment) is claimed once through an idempotency key.
Nothing about the organisation is revealed to the sender or the provider.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import logging
import secrets
import tempfile
from dataclasses import dataclass, field
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import getaddresses, parseaddr
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .. import config
from ..database import set_tenant
from ..models.idempotency import IdempotencyKey
from ..models.identity import Tenant
from ..security.file_guard import safe_display_name
from . import email_loop, idempotency, intake_service

log = logging.getLogger("truebind.inbound")

MAX_ATTACHMENTS = 10


@dataclass
class Attachment:
    name: str
    content: bytes


@dataclass
class InboundMessage:
    message_id: str
    sender: str
    recipients: list[str]
    attachments: list[Attachment] = field(default_factory=list)
    # Untrusted: used only to find the request a reply answers ([TB-n] or
    # Message-ID), and stored as text for a person to read. Never interpreted.
    subject: str = ""
    in_reply_to: str = ""
    text: str = ""


@dataclass
class IntakeResult:
    accepted: list[str] = field(default_factory=list)  # report ids
    rejected: list[dict[str, str]] = field(default_factory=list)
    duplicates: int = 0
    routed: bool = False
    reply_to: int | None = None  # the [TB-n] request this e-mail answered


def new_token() -> str:
    return secrets.token_hex(12)


def address_for(token: str | None) -> str | None:
    if not token or not config.INBOUND_EMAIL_DOMAIN:
        return None
    return f"{token}@{config.INBOUND_EMAIL_DOMAIN}"


def from_postmark(payload: dict[str, Any]) -> InboundMessage:
    recipients = [
        a for _n, a in getaddresses([str(payload.get("OriginalRecipient") or ""), str(payload.get("To") or "")])
    ]
    for full in payload.get("ToFull") or []:
        if isinstance(full, dict) and full.get("Email"):
            recipients.append(str(full["Email"]))
    attachments = []
    for a in (payload.get("Attachments") or [])[:MAX_ATTACHMENTS]:
        try:
            content = base64.b64decode(str(a.get("Content") or ""), validate=True)
        except (binascii.Error, ValueError):
            continue
        attachments.append(Attachment(str(a.get("Name") or "attachment"), content))
    headers = {str(h.get("Name") or "").lower(): str(h.get("Value") or "")
               for h in (payload.get("Headers") or []) if isinstance(h, dict)}
    return InboundMessage(
        message_id=str(payload.get("MessageID") or ""),
        sender=parseaddr(str(payload.get("From") or ""))[1],
        recipients=[r for r in recipients if r],
        attachments=attachments,
        subject=str(payload.get("Subject") or "")[:500],
        in_reply_to=" ".join(filter(None, [headers.get("in-reply-to"), headers.get("references")]))[:2000],
        text=str(payload.get("StrippedTextReply") or payload.get("TextBody") or "")[:20000],
    )


def from_mime(raw: bytes, destinations: list[str], message_id: str) -> InboundMessage:
    msg = BytesParser(policy=policy.default).parsebytes(raw)
    attachments = []
    if isinstance(msg, EmailMessage):
        for part in msg.iter_attachments():
            payload = part.get_payload(decode=True)
            if isinstance(payload, bytes):
                attachments.append(Attachment(part.get_filename() or "attachment", payload))
            if len(attachments) >= MAX_ATTACHMENTS:
                break
    text = ""
    if isinstance(msg, EmailMessage):
        body = msg.get_body(preferencelist=("plain",))
        if body is not None:
            try:
                text = str(body.get_content())[:20000]
            except (LookupError, ValueError):
                text = ""
    return InboundMessage(
        message_id=message_id or str(msg.get("Message-ID") or ""),
        sender=parseaddr(str(msg.get("From") or ""))[1],
        recipients=destinations or [a for _n, a in getaddresses([str(msg.get("To") or "")])],
        attachments=attachments,
        subject=str(msg.get("Subject") or "")[:500],
        in_reply_to=" ".join(filter(None, [str(msg.get("In-Reply-To") or ""), str(msg.get("References") or "")]))[:2000],
        text=text,
    )


def resolve_tenant(db: Session, recipients: list[str]) -> Tenant | None:
    domain = config.INBOUND_EMAIL_DOMAIN.lower()
    for r in recipients:
        local, _, dom = r.strip().lower().partition("@")
        if dom == domain and local:
            tenant = db.query(Tenant).filter(Tenant.inbound_token == local).first()
            if tenant is not None:
                return tenant
    return None


def ingest(db: Session, message: InboundMessage, provider: str) -> IntakeResult:
    result = IntakeResult()
    tenant = resolve_tenant(db, message.recipients)
    if tenant is None:
        log.info("inbound e-mail via %s for an unknown address ignored", provider)
        return result
    result.routed = True
    set_tenant(db, tenant.id)
    actor = f"email:{message.sender or 'unknown sender'}"[:255]
    # A reply to an information request updates that request and its issues.
    req = email_loop.match_reply(db, tenant.id, message.sender, message.subject, message.in_reply_to)
    if req is not None and not any(r.get("message_id") == message.message_id[:255] for r in (req.replies or [])):
        email_loop.record_reply(db, req, message.sender, message.message_id, message.text,
                                [safe_display_name(a.name) for a in message.attachments])
        db.commit()
        set_tenant(db, tenant.id)
        result.reply_to = req.number
    for index, att in enumerate(message.attachments):
        display = safe_display_name(att.name)
        with tempfile.NamedTemporaryFile(prefix="in-", delete=False) as fh:
            fh.write(att.content)
            path = Path(fh.name)
        try:
            if len(att.content) > config.MAX_UPLOAD_BYTES:
                result.rejected.append({"file_name": display, "reason": "larger than the upload limit"})
                continue
            verdict = intake_service.inspect(
                db,
                tenant_id=tenant.id,
                path=path,
                display_name=display,
                size=len(att.content),
                channel="email",
                actor=actor,
                actor_user_id=None,
                sender=message.sender,
            )
            if not verdict.accepted:
                result.rejected.append({"file_name": display, "reason": verdict.reason or "rejected"})
                db.commit()
                continue
            key = hashlib.sha256(f"{provider}:{message.message_id}:{index}".encode()).hexdigest()
            try:
                claimed = idempotency.claim(
                    db,
                    tenant_id=tenant.id,
                    user_id=None,
                    scope="inbound.email",
                    key=key,
                    request_fingerprint=hashlib.sha256(att.content).hexdigest(),
                )
            except HTTPException:  # same message id, different content: never overwrite what was received
                result.rejected.append({"file_name": display, "reason": "conflicts with an earlier delivery"})
                db.rollback()
                continue
            if not isinstance(claimed, IdempotencyKey):
                result.duplicates += 1
                db.rollback()
                set_tenant(db, tenant.id)
                continue
            report = intake_service.create_report(
                db,
                tenant=tenant,
                path=path,
                verdict=verdict,
                display_name=display,
                size=len(att.content),
                channel="email",
                actor=actor,
                actor_user_id=None,
                sender=message.sender,
            )
            idempotency.complete(claimed, 202, {"report_id": report.id})
            if req is not None and req.reply_report_id is None:
                email_loop.link_resubmission(db, req, report)
            db.commit()
            set_tenant(db, tenant.id)
            result.accepted.append(report.id)
        finally:
            path.unlink(missing_ok=True)
    return result
