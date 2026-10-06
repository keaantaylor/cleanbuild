"""The e-mail loop: information request -> reply -> resubmission -> verification.

- A request is written by code from the issues it asks about (cells, expected,
  actual), never by AI, and carries a reference: [TB-<number>].
- A reply is matched to its request by that reference (subject) or by the
  request's Message-ID (In-Reply-To / References), only inside the
  organisation the inbound address belongs to, and only when it comes from
  the address the request was sent to. Anything else is ordinary intake.
- The reply's text is stored as untrusted data and shown to a person; it is
  never interpreted. Nothing in an e-mail can approve, override or change a
  value. Linked issues move to "a person reviews the reply".
- A workbook attached to the reply is processed like any submission; when it
  completes, each linked issue is checked again in the new file: closed if the
  rule no longer fires for that claim and field, kept open otherwise.
"""

from __future__ import annotations

import re
import smtplib
from email.message import EmailMessage
from email.utils import make_msgid

from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import config
from ..models._util import utcnow
from ..models.memory import InfoRequest
from ..models.reports import ClaimRow, Report, Sheet, ValidationResult
from . import audit_service, issues

REF = re.compile(r"\[TB-(\d{1,9})\]")
MAX_REPLY_TEXT = 4000
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _fmt(v) -> str:
    if isinstance(v, (int, float)):
        return f"{v:,.2f}"
    return "-" if v is None else str(v)


def compose(report: Report, label: str, items: list[tuple[ValidationResult, ClaimRow, str]], number: int) -> tuple[str, str]:
    subject = f"[TB-{number}] {report.file_name}: {label} ({len(items)} row{'s' if len(items) != 1 else ''})"
    lines = ["Hello,", "", f"Reviewing {report.file_name} we found: {label}.", "",
             "Cell | Claim | Expected | Reported", "-----|-------|----------|---------"]
    for vr, row, sheet in items[:200]:
        x = vr.extra or {}
        lines.append(f"{sheet}!{x.get('cell') or '?'} | {row.claim_reference or '-'} | {_fmt(x.get('expected'))} | "
                     f"{_fmt(x.get('actual'))}")
    if len(items) > 200:
        lines.append(f"... and {len(items) - 200} more rows.")
    lines += ["", "Please reply to this e-mail with the correct figures, or attach a corrected file.",
              f"Keep [TB-{number}] in the subject so your reply is matched to this request.", "", "Thank you."]
    return subject[:500], "\n".join(lines)


def create_request(db: Session, report: Report, root_cause: str, issue_ids: list[str], to: str | None,
                   actor: str, actor_user_id: str | None) -> InfoRequest:
    rows = (db.query(ValidationResult, ClaimRow, Sheet.sheet_name)
            .join(ClaimRow, ClaimRow.id == ValidationResult.claim_row_id)
            .join(Sheet, Sheet.id == ClaimRow.sheet_id)
            .filter(ValidationResult.report_id == report.id, ValidationResult.id.in_(issue_ids or [""]))
            .order_by(Sheet.sheet_name, ClaimRow.row_index).all())
    from bordereaux.rules import rule as catalogue_rule

    label = catalogue_rule(rows[0][0].rule or "").label if rows else root_cause
    number = (db.query(func.max(InfoRequest.number)).filter(InfoRequest.tenant_id == report.tenant_id).scalar() or 0) + 1
    subject, body = compose(report, label, rows, number)
    address = (to or "").strip() or ((report.sender or "").strip() if _EMAIL.match((report.sender or "").strip()) else "")
    req = InfoRequest(tenant_id=report.tenant_id, report_id=report.id, number=number, root_cause=root_cause,
                      issue_ids=[vr.id for vr, _, _ in rows], to_address=address or None, subject=subject, body=body,
                      status="OPEN", created_by=actor, delivery="NO_ADDRESS")
    if address and not _EMAIL.match(address):
        raise ValueError("That is not an e-mail address.")
    if address:
        req.message_id = make_msgid(domain=(config.INBOUND_EMAIL_DOMAIN or "truebind.local"))
        req.delivery, req.delivery_error = _send(address, subject, body, req.message_id)
    db.add(req)
    db.flush()
    audit_service.log_action(db, report.tenant_id, report.id, "INFO_REQUEST_SENT", "INFO_REQUEST", req.id,
                             after={"number": number, "root_cause": root_cause, "issues": len(req.issue_ids),
                                    "to": req.to_address, "delivery": req.delivery}, actor=actor,
                             actor_user_id=actor_user_id)
    return req


def _send(to: str, subject: str, body: str, message_id: str) -> tuple[str, str | None]:
    if not config.SMTP_HOST:
        return "NOT_CONFIGURED", "E-mail is not configured on this server; send the text yourself."
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"], msg["Message-ID"] = config.SMTP_FROM, to, subject, message_id
    # Replies go to the organisation's inbound address when one exists.
    msg.set_content(body)
    try:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=20) as smtp:
            if config.SMTP_STARTTLS:
                smtp.starttls()
            if config.SMTP_USER:
                smtp.login(config.SMTP_USER, config.SMTP_PASSWORD or "")
            smtp.send_message(msg)
        return "SENT", None
    except (smtplib.SMTPException, OSError):
        return "FAILED", "The mail server did not accept the message."


def match_reply(db: Session, tenant_id: str, sender: str, subject: str, in_reply_to: str) -> InfoRequest | None:
    """The open request this e-mail answers, or None. Decided only by the
    reference / Message-ID and the sender address, within one organisation."""
    req = None
    m = REF.search(subject or "")
    if m:
        req = db.query(InfoRequest).filter(InfoRequest.tenant_id == tenant_id,
                                           InfoRequest.number == int(m.group(1))).first()
    if req is None and in_reply_to:
        ids = [t for t in re.findall(r"<[^>]+>", in_reply_to)] or [in_reply_to.strip()]
        req = db.query(InfoRequest).filter(InfoRequest.tenant_id == tenant_id, InfoRequest.message_id.in_(ids)).first()
    if req is None:
        return None
    if not req.to_address or req.to_address.lower() != (sender or "").strip().lower():
        audit_service.log_action(db, tenant_id, req.report_id, "INBOUND_REPLY_UNMATCHED", "INFO_REQUEST", req.id,
                                 after={"reason": "sender is not the address the request was sent to",
                                        "from": (sender or "")[:320]}, actor=f"email:{sender or 'unknown'}"[:255])
        return None
    return req


def record_reply(db: Session, req: InfoRequest, sender: str, message_id: str, text: str,
                 attachments: list[str]) -> None:
    excerpt = (text or "").strip()[:MAX_REPLY_TEXT]
    reply = {"at": utcnow().isoformat(), "from": sender, "message_id": message_id[:255], "text": excerpt,
             "attachments": attachments[:10]}
    req.replies = [*(req.replies or []), reply]
    if req.status == "OPEN":
        req.status = "ANSWERED"
    actor = f"email:{sender}"[:255]
    for vr in db.query(ValidationResult).filter(ValidationResult.report_id == req.report_id,
                                                ValidationResult.id.in_(req.issue_ids or [""])):
        x = dict(vr.extra or {})
        x.setdefault("issue_status", issues.initial_status(vr.status, vr.rule or ""))
        note = f"Sender replied to [TB-{req.number}]" + (f" with {', '.join(attachments)}" if attachments else "")
        try:
            vr.extra = issues.transition(x, "REQUIRES_HUMAN_REVIEW", actor, note)
        except issues.TransitionError:
            hist = list(x.get("history") or [])
            hist.append({"at": reply["at"], "status": x["issue_status"], "actor": actor, "note": note})
            vr.extra = {**x, "history": hist}
    audit_service.log_action(db, req.tenant_id, req.report_id, "INBOUND_REPLY_MATCHED", "INFO_REQUEST", req.id,
                             after={"number": req.number, "from": sender, "attachments": attachments,
                                    "chars": len(excerpt)}, actor=actor)


def link_resubmission(db: Session, req: InfoRequest, new_report: Report) -> None:
    original = db.get(Report, req.report_id)
    req.reply_report_id = new_report.id
    if original is not None and original.sender:
        new_report.sender = original.sender  # the same counterparty, whatever address it came from


def verify_resubmission(db: Session, new_report: Report) -> list[InfoRequest]:
    """After a reply's workbook is processed: close each linked issue whose
    rule no longer fires for the same claim and field in the new file."""
    reqs = db.query(InfoRequest).filter(InfoRequest.tenant_id == new_report.tenant_id,
                                        InfoRequest.reply_report_id == new_report.id).all()
    if not reqs:
        return []
    now = {(vr.rule, (ref or "").strip().upper(), (vr.extra or {}).get("field_code"))
           for vr, ref in db.query(ValidationResult, ClaimRow.claim_reference)
           .join(ClaimRow, ClaimRow.id == ValidationResult.claim_row_id)
           .filter(ValidationResult.report_id == new_report.id)}
    refs_now = {(ref or "").strip().upper() for (ref,) in db.query(ClaimRow.claim_reference)
                .filter(ClaimRow.report_id == new_report.id)}
    for req in reqs:
        resolved, still, missing = [], [], []
        for vr, ref in (db.query(ValidationResult, ClaimRow.claim_reference)
                        .join(ClaimRow, ClaimRow.id == ValidationResult.claim_row_id)
                        .filter(ValidationResult.report_id == req.report_id,
                                ValidationResult.id.in_(req.issue_ids or [""]))):
            key = (vr.rule, (ref or "").strip().upper(), (vr.extra or {}).get("field_code"))
            x = dict(vr.extra or {})
            if key[1] not in refs_now:
                missing.append(vr.id)  # the claim is not in the new file: cannot say it is fixed
                continue
            if key in now:
                still.append(vr.id)
                note = f"Still fails in resubmission {new_report.file_name} ([TB-{req.number}])"
                target = "DETECTED"
            else:
                resolved.append(vr.id)
                note = (f"Resolved by resubmission {new_report.file_name} ([TB-{req.number}]): "
                        f"{vr.rule} no longer fires for claim {ref}")
                target = "RESOLVED"
            try:
                vr.extra = issues.transition(x, target, "system", note)
            except issues.TransitionError:
                pass
        req.resolution = {"report_id": new_report.id, "file_name": new_report.file_name, "resolved": len(resolved),
                          "still_failing": len(still), "not_in_file": len(missing), "at": utcnow().isoformat()}
        req.status = "RESOLVED" if resolved and not still and not missing else "ANSWERED"
        audit_service.log_action(db, req.tenant_id, req.report_id, "RESUBMISSION_VERIFIED", "INFO_REQUEST", req.id,
                                 after=req.resolution, actor="system")
    return reqs


def out(req: InfoRequest) -> dict:
    return {"id": req.id, "number": req.number, "reference": f"TB-{req.number}", "report_id": req.report_id,
            "root_cause": req.root_cause, "issues": len(req.issue_ids or []), "to": req.to_address,
            "subject": req.subject, "body": req.body, "delivery": req.delivery, "delivery_error": req.delivery_error,
            "status": req.status, "replies": req.replies or [], "reply_report_id": req.reply_report_id,
            "resolution": req.resolution, "created_by": req.created_by, "created_at": req.created_at.isoformat()}
