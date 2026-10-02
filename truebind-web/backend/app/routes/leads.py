"""Website enquiries: the public forms on truebind.ie post here.

POST /api/v1/leads            public; rate-limited per IP; bot honeypot
POST /api/v1/leads/health-check  public: a Health Check request with the visitor's
                              file (.xlsx/.xls/.csv, 10 MB max, explicit consent);
                              checked like an app upload, stored, emailed to
                              LEADS_NOTIFY_EMAIL, deleted after LEAD_FILE_RETENTION_DAYS
GET  /api/v1/leads/{id}/file  operators only
GET  /api/v1/leads            signed-in operators in LEADS_ADMIN_EMAILS only
GET  /api/v1/leads/export.csv same, as CSV

Submissions are always stored first, so nothing is lost; an email
notification is sent afterwards only when LEADS_NOTIFY_EMAIL and SMTP are
configured."""

from __future__ import annotations

import csv
import hashlib
import io
import logging
import os
import smtplib
import tempfile
from email.message import EmailMessage
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel, EmailStr, Field, TypeAdapter, ValidationError
from sqlalchemy.orm import Session

from .. import config
from ..database import get_db
from ..models.identity import User
from ..models._util import utcnow
from ..models.leads import Lead, LeadFile
from ..security.auth import Context, get_context
from ..security.file_guard import inspect_upload, safe_display_name
from ..security.ratelimit import client_ip, limiter
from ..settings import get_settings

router = APIRouter(prefix="/api/v1/leads", tags=["leads"])
logger = logging.getLogger("truebind.leads")


class LeadIn(BaseModel):
    kind: Literal["demo", "health", "contact", "updates"]
    email: EmailStr
    name: str | None = Field(default=None, max_length=200)
    company: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=2000)
    page: str | None = Field(default=None, max_length=300)
    attribution: dict[str, str] | None = None
    # Honeypot: hidden from people, filled in by bots. Must stay empty.
    website: str | None = Field(default=None, max_length=200)


class LeadOut(BaseModel):
    id: str
    kind: str
    name: str | None
    email: str
    company: str | None
    note: str | None
    page: str | None
    attribution: dict[str, str] | None
    created_at: str
    file_name: str | None = None
    file_size: int | None = None
    consent_at: str | None = None


_ATTR_KEYS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "referrer", "landing_page"}


def _clean(v: str | None) -> str | None:
    v = (v or "").strip()
    return v or None


def _notify(lead_id: str, kind: str, email: str, name: str | None, company: str | None, note: str | None,
            attachment: tuple[str, bytes] | None = None) -> None:
    to = get_settings().leads_notify_email.strip()
    if not to or not config.SMTP_HOST:
        return
    msg = EmailMessage()
    msg["Subject"] = f"New TrueBind enquiry ({kind}): {company or email}"
    msg["From"], msg["To"] = config.SMTP_FROM, to
    msg["Reply-To"] = email
    msg.set_content(f"Kind: {kind}\nName: {name or '-'}\nCompany: {company or '-'}\nEmail: {email}\n\n{note or ''}\n\nRef: {lead_id}")
    if attachment is not None:
        msg.add_attachment(attachment[1], maintype="application", subtype="octet-stream", filename=attachment[0])
    try:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=20) as smtp:
            if config.SMTP_STARTTLS:
                smtp.starttls()
            if config.SMTP_USER:
                smtp.login(config.SMTP_USER, config.SMTP_PASSWORD or "")
            smtp.send_message(msg)
    except (smtplib.SMTPException, OSError):
        # The enquiry is already stored; a failed notification loses nothing.
        logger.exception("lead %s stored but the notification email failed", lead_id)


@router.post("", status_code=201)
def create_lead(body: LeadIn, request: Request, background: BackgroundTasks, db: Session = Depends(get_db)) -> dict[str, str]:
    limiter.check("leads-ip", client_ip(request), limit=10, window_s=3600)
    if body.website:
        # Looks like a bot: answer as if accepted, store nothing.
        return {"status": "received"}
    attribution = {k: str(v)[:300] for k, v in (body.attribution or {}).items() if k in _ATTR_KEYS and v} or None
    lead = Lead(kind=body.kind, email=str(body.email).lower(), name=_clean(body.name), company=_clean(body.company),
                note=_clean(body.note), page=_clean(body.page), attribution=attribution)
    db.add(lead)
    db.commit()
    background.add_task(_notify, lead.id, lead.kind, lead.email, lead.name, lead.company, lead.note)
    return {"status": "received"}


HEALTH_CHECK_MAX_BYTES = 10 * 1024 * 1024
_EMAIL = TypeAdapter(EmailStr)


@router.post("/health-check", status_code=201)
async def health_check(request: Request, background: BackgroundTasks,
                       email: str = Form(..., max_length=320), name: str | None = Form(default=None, max_length=200),
                       company: str | None = Form(default=None, max_length=200),
                       note: str | None = Form(default=None, max_length=2000),
                       consent: bool = Form(default=False), page: str | None = Form(default=None, max_length=300),
                       website: str | None = Form(default=None, max_length=200),
                       file: UploadFile = File(...), db: Session = Depends(get_db)) -> dict[str, str]:
    """A free Health Check request: the visitor's bordereau, checked like an app
    upload (type, signature, zip safety), stored apart from the lead and emailed
    to the notification address."""
    limiter.check("leads-health-ip", client_ip(request), limit=5, window_s=3600)
    if website:
        return {"status": "received"}
    try:
        clean_email = str(_EMAIL.validate_python(email)).lower()
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail="Enter a valid work email address.") from exc
    if not consent:
        raise HTTPException(status_code=422, detail="Please confirm we may read the file to prepare your Health Check.")
    display = safe_display_name(file.filename)
    data = await file.read(HEALTH_CHECK_MAX_BYTES + 1)
    if len(data) > HEALTH_CHECK_MAX_BYTES:
        raise HTTPException(status_code=413, detail="The file is larger than 10 MB. Send a smaller extract.")
    fd, tmp_name = tempfile.mkstemp(suffix=Path(display).suffix.lower()[:8])
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        verdict = inspect_upload(Path(tmp_name), display)
    finally:
        Path(tmp_name).unlink(missing_ok=True)
    if not verdict.accepted or verdict.kind not in ("xlsx", "xls", "csv"):
        raise HTTPException(status_code=422, detail=verdict.reason or "Send an .xlsx, .xls or .csv file.")
    lead = Lead(kind="health", email=clean_email, name=_clean(name), company=_clean(company), note=_clean(note),
                page=_clean(page), consent_at=utcnow(), file_name=display[:255], file_size=len(data),
                file_sha256=hashlib.sha256(data).hexdigest())
    db.add(lead)
    db.flush()
    db.add(LeadFile(lead_id=lead.id, content=data))
    db.commit()
    background.add_task(_notify, lead.id, lead.kind, lead.email, lead.name, lead.company, lead.note, (display, data))
    return {"status": "received"}


def _operator(ctx: Context = Depends(get_context), db: Session = Depends(get_db)) -> Context:
    allowed = {e.strip().lower() for e in get_settings().leads_admin_emails.split(",") if e.strip()}
    user = db.get(User, ctx.user_id)
    if user is None or user.email.lower() not in allowed:
        raise HTTPException(status_code=403, detail="Only TrueBind operators can see website enquiries.")
    return ctx


def _rows(db: Session) -> list[Lead]:
    return db.query(Lead).order_by(Lead.created_at.desc()).limit(5000).all()


@router.get("", response_model=list[LeadOut])
def list_leads(_: Context = Depends(_operator), db: Session = Depends(get_db)) -> list[LeadOut]:
    return [LeadOut(id=x.id, kind=x.kind, name=x.name, email=x.email, company=x.company, note=x.note, page=x.page,
                    attribution=x.attribution, created_at=x.created_at.isoformat(), file_name=x.file_name,
                    file_size=x.file_size, consent_at=x.consent_at.isoformat() if x.consent_at else None)
            for x in _rows(db)]


@router.get("/export.csv")
def export_leads(_: Context = Depends(_operator), db: Session = Depends(get_db)) -> Response:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["created_at", "kind", "name", "email", "company", "note", "page", *sorted(_ATTR_KEYS)])
    for x in _rows(db):
        a = x.attribution or {}
        cells = [x.created_at.isoformat(), x.kind, x.name, x.email, x.company, x.note, x.page, *(a.get(k, "") for k in sorted(_ATTR_KEYS))]
        # Neutralise spreadsheet formulas in visitor-supplied text (CSV injection).
        w.writerow([("'" + c) if isinstance(c, str) and c[:1] in ("=", "+", "-", "@") else c for c in cells])
    return Response(buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="truebind_enquiries.csv"'})


@router.get("/{lead_id}/file")
def lead_file(lead_id: str, _: Context = Depends(_operator), db: Session = Depends(get_db)) -> Response:
    lead = db.get(Lead, lead_id)
    stored = db.get(LeadFile, lead_id) if lead is not None else None
    if lead is None or stored is None:
        raise HTTPException(status_code=404, detail="No file is stored for this enquiry (it may have been deleted).")
    name = (lead.file_name or "health-check").replace('"', "")
    return Response(bytes(stored.content), media_type="application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})
