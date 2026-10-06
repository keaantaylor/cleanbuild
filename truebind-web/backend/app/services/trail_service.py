"""Reconstruct one bordereau from arrival to final approval.

Everything is read from records the system already keeps (report, jobs,
findings, corrections, versions, deliveries, webhooks, the hash-chained audit
log); nothing is inferred. The analysed version (the annotated workbook the
analysis produced) is fingerprinted the first time the trail is built, so it
can be proven later that what a reviewer saw has not changed.
"""

from __future__ import annotations

import hashlib

from bordereaux.rules import RULESET_VERSION
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models.audit import AuditLogEntry
from ..models.channels import WebhookDelivery
from ..models.corrections import Correction, WorkbookVersion
from ..models.deliveries import Delivery
from ..models.jobs import Job
from ..models.reports import Report, ValidationResult
from ..models.memory import InfoRequest
from . import audit_service, deliverables, email_loop, issues
from .storage import derived_key, get_store


def _iso(dt) -> str | None:
    return dt.isoformat() if dt else None


def ensure_analysed(db: Session, report: Report, actor: str) -> WorkbookVersion | None:
    """The analysed version: the annotated workbook, built once and hashed.
    None when the source is no longer available (the trail says so)."""
    v = (db.query(WorkbookVersion).filter(WorkbookVersion.report_id == report.id, WorkbookVersion.kind == "analysed")
         .first())
    if v is not None or report.status != "COMPLETE":
        return v
    try:
        body = deliverables.annotated_workbook(db, report)
    except deliverables.SourceUnavailable:
        return None
    from .corrections_service import _ensure_original  # number 0 is always the original

    _ensure_original(db, report, actor)
    number = (db.query(func.max(WorkbookVersion.number)).filter(WorkbookVersion.report_id == report.id).scalar() or 0) + 1
    sha = hashlib.sha256(body).hexdigest()
    v = WorkbookVersion(tenant_id=report.tenant_id, report_id=report.id, number=number, kind="analysed", sha256=sha,
                        size=len(body), corrections=[], created_by=actor)
    db.add(v)
    db.flush()
    get_store().put_derived(derived_key(report.tenant_id, report.source_sha256 or "0" * 64, f"version-{number}"),
                            body, db=db)
    audit_service.log_action(db, report.tenant_id, report.id, "VERSION_CREATED", "WORKBOOK_VERSION", v.id,
                             after={"number": number, "kind": "analysed", "sha256": sha}, actor=actor)
    return v


def build(db: Session, report: Report, actor: str) -> dict:
    analysed = ensure_analysed(db, report, actor)
    audit = (db.query(AuditLogEntry).filter(AuditLogEntry.tenant_id == report.tenant_id,
                                            AuditLogEntry.report_id == report.id)
             .order_by(AuditLogEntry.seq).all())
    uploaded = next((e for e in audit if e.action_type == "REPORT_UPLOADED"), None)
    jobs = db.query(Job).filter(Job.report_id == report.id, Job.tenant_id == report.tenant_id).order_by(Job.created_at)
    vrs = db.query(ValidationResult).filter(ValidationResult.report_id == report.id).all()
    by_status: dict[str, int] = {}
    by_rule: dict[str, int] = {}
    rulesets: set[str] = set()
    for vr in vrs:
        x = vr.extra or {}
        st = x.get("issue_status") or issues.initial_status(vr.status, vr.rule or "")
        by_status[st] = by_status.get(st, 0) + 1
        by_rule[vr.rule or "?"] = by_rule.get(vr.rule or "?", 0) + 1
        if x.get("ruleset_version"):
            rulesets.add(x["ruleset_version"])
    corrections = (db.query(Correction).filter(Correction.report_id == report.id)
                   .order_by(Correction.created_at, Correction.id).all())
    versions = (db.query(WorkbookVersion).filter(WorkbookVersion.report_id == report.id)
                .order_by(WorkbookVersion.number).all())
    approved = [v for v in versions if v.kind == "approved"]
    deliveries = db.query(Delivery).filter(Delivery.report_id == report.id).order_by(Delivery.created_at).all()
    hooks = [w for w in db.query(WebhookDelivery).filter(WebhookDelivery.tenant_id == report.tenant_id)
             .order_by(WebhookDelivery.created_at.desc()).limit(1000)
             if (w.payload or {}).get("report_id") == report.id
             or ((w.payload or {}).get("data") or {}).get("report_id") == report.id]
    chain_ok, bad_seq = audit_service.verify_chain(db, report.tenant_id)
    last_recheck = next((e.after_value for e in reversed(audit) if e.action_type == "CORRECTIONS_RECHECKED"), None)
    open_issues = sum(n for s, n in by_status.items() if s not in issues.CLOSED)
    return {
        "report_id": report.id,
        "arrival": {"file_name": report.file_name, "sha256": report.source_sha256, "size": report.file_size_bytes,
                    "channel": report.source_channel, "sender": report.sender, "programme": report.programme,
                    "received_at": _iso(report.created_at), "received_by": uploaded.actor if uploaded else None},
        "processing": [{"id": j.id, "kind": j.kind, "status": j.status, "attempts": j.attempts,
                        "queued_at": _iso(j.created_at), "started_at": _iso(j.started_at),
                        "finished_at": _iso(j.finished_at), "error_code": j.error_code} for j in jobs],
        "analysis": {"status": report.status, "rows": report.rows_processed, "grade": report.grade,
                     "ruleset_versions": sorted(rulesets) or [RULESET_VERSION], "findings": len(vrs),
                     "findings_by_rule": dict(sorted(by_rule.items(), key=lambda kv: -kv[1])),
                     "analysed_version_sha256": analysed.sha256 if analysed else None},
        "issues": {"total": len(vrs), "open": open_issues, "by_status": by_status},
        "corrections": [{"id": c.id, "sheet": c.sheet_name, "cell": c.cell, "before": c.before_value,
                         "after": c.after_value, "why": c.reason, "rule": c.rule, "evidence": c.evidence,
                         "policy": c.policy, "policy_reason": c.policy_reason, "source": c.source,
                         "proposed_by": c.proposed_by, "proposed_at": _iso(c.created_at), "status": c.status,
                         "approval": c.approval, "decided_by": c.decided_by, "decided_at": _iso(c.decided_at),
                         "result": c.result} for c in corrections],
        "versions": [{"id": v.id, "number": v.number, "kind": v.kind, "sha256": v.sha256, "size": v.size,
                      "corrections": len(v.corrections or []), "based_on": v.based_on, "created_by": v.created_by,
                      "created_at": _iso(v.created_at)} for v in versions],
        "emails_and_external_writes": [
            *({"type": "delivery", "kind": d.kind, "channel": d.channel, "destination": d.destination,
               "file_name": d.file_name, "status": d.status, "at": _iso(d.created_at), "by": d.created_by}
              for d in deliveries),
            *({"type": "webhook", "event": w.event_type, "message_id": w.message_id, "status": w.status,
               "attempts": w.attempts, "at": _iso(w.created_at)} for w in hooks)],
        "information_requests": [email_loop.out(r) for r in db.query(InfoRequest).filter(
            InfoRequest.tenant_id == report.tenant_id,
            (InfoRequest.report_id == report.id) | (InfoRequest.reply_report_id == report.id))
            .order_by(InfoRequest.number)],
        "final_verification": {
            "approved_version": ({"number": approved[-1].number, "sha256": approved[-1].sha256,
                                  "approved_by": approved[-1].created_by, "at": _iso(approved[-1].created_at)}
                                 if approved else None),
            "last_recheck": last_recheck, "open_issues": open_issues,
            "unverified_corrections": sum(1 for c in corrections if c.status == "APPROVED" and not c.result),
            "audit_chain_intact": chain_ok, "audit_chain_first_bad_seq": bad_seq,
            "source_unchanged": _source_intact(db, report)},
        "audit": [{"seq": e.seq, "action": e.action_type, "entity": e.entity_type, "entity_id": e.entity_id,
                   "actor": e.actor, "at": _iso(e.created_at), "hash": e.entry_hash} for e in audit],
    }


def _source_intact(db: Session, report: Report) -> bool | None:
    """The stored original still hashes to the SHA-256 recorded at arrival."""
    try:
        with get_store().local_copy(report.storage_key or "", report.source_sha256 or "", db=db):
            return True
    except FileNotFoundError:
        return None
    except Exception:  # noqa: BLE001 -- the store raises IntegrityError on a hash mismatch
        return False
