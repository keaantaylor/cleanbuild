"""P7 One-click audit pack: everything an auditor needs for one report, in a ZIP.

Contents (fixed order, fixed timestamps inside the archive):
  README.txt           what the pack is, the coverage statement, how to verify it
  report.json          report metadata, health summary and coverage statement
  original/<file>      the uploaded file, byte for byte (its SHA-256 is checked first)
  mapping.csv          every mapping decision: state, AI model, who confirmed it and when
  claims.csv           the extracted rows with their check results
  exceptions.csv       every failed or not-evaluable check
  checks.json          each check module's run: state, per-rule coverage, configuration
  findings.csv         every module finding, with its decision
  audit_trail.json     the report's audit entries with their hashes, plus the
                       whole organisation chain's verification result
  manifest.json        SHA-256 and size of every file above
The pack is built from stored data only; building it writes an audit event.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from ..models.audit import AuditLogEntry
from ..models.modules import Finding, ModuleRun
from ..models.reports import Mapping, Report, Sheet
from . import audit_service, export_service
from .storage import get_store

PACK_VERSION = "1"


class PackIntegrityError(RuntimeError):
    """The stored original no longer matches the SHA-256 recorded at upload."""


def _json(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, default=str, ensure_ascii=False) + "\n").encode("utf-8")


def _csv(header: list[str], rows: Any) -> bytes:
    return export_service.render_csv(header, rows)


def _original(report: Report) -> bytes:
    from .storage import IntegrityError

    try:
        with get_store().local_copy(report.storage_key or "", report.source_sha256 or "") as path:
            data = path.read_bytes()
    except IntegrityError as exc:
        raise PackIntegrityError("the stored original does not match its recorded SHA-256") from exc
    if hashlib.sha256(data).hexdigest() != report.source_sha256:
        raise PackIntegrityError("the stored original does not match its recorded SHA-256")
    return data


def _safe_name(name: str) -> str:
    keep = "".join(c if c.isalnum() or c in "._- " else "_" for c in name).strip(" .")
    return keep[:120] or "original"


def build(db: Session, report: Report, coverage_statement: str, generated_by: str, now: datetime) -> bytes:
    tid = report.tenant_id
    sheets = {s.id: s.sheet_name for s in db.query(Sheet).filter(Sheet.report_id == report.id, Sheet.tenant_id == tid)}
    mappings = (
        db.query(Mapping)
        .filter(Mapping.report_id == report.id, Mapping.tenant_id == tid)
        .order_by(Mapping.sheet_id, Mapping.field_code)
        .all()
    )
    runs = (
        db.query(ModuleRun)
        .filter(ModuleRun.report_id == report.id, ModuleRun.tenant_id == tid)
        .order_by(ModuleRun.module)
        .all()
    )
    findings = (
        db.query(Finding)
        .filter(Finding.report_id == report.id, Finding.tenant_id == tid)
        .order_by(Finding.module, Finding.sheet_name, Finding.row_number, Finding.rule_code)
        .all()
    )
    entries = (
        db.query(AuditLogEntry)
        .filter(AuditLogEntry.tenant_id == tid, AuditLogEntry.report_id == report.id)
        .order_by(AuditLogEntry.seq)
        .all()
    )
    intact, first_bad = audit_service.verify_chain(db, tid)

    files: list[tuple[str, bytes]] = []
    files.append(
        (
            "report.json",
            _json(
                {
                    "report_id": report.id,
                    "file_name": report.file_name,
                    "source_sha256": report.source_sha256,
                    "file_size_bytes": report.file_size_bytes,
                    "source_channel": report.source_channel,
                    "sender": report.sender,
                    "programme": report.programme,
                    "uploaded_at": report.created_at,
                    "status": report.status,
                    "rows_processed": report.rows_processed,
                    "rows_total": report.rows_total,
                    "grade": report.grade,
                    "score": report.score,
                    "coverage_statement": coverage_statement,
                    "summary": report.summary,
                }
            ),
        )
    )
    files.append((f"original/{_safe_name(report.file_name)}", _original(report)))
    files.append(
        (
            "mapping.csv",
            _csv(
                [
                    "sheet_name",
                    "field_code",
                    "field_name",
                    "source_column",
                    "mapping_state",
                    "review_state",
                    "ai_model",
                    "confidence",
                    "confirmed_by",
                    "confirmed_at",
                ],
                (
                    [
                        sheets.get(m.sheet_id),
                        m.field_code,
                        m.field_name,
                        m.source_column,
                        m.mapping_state,
                        m.review_state,
                        m.ai_model,
                        m.confidence_score,
                        m.confirmed_by,
                        m.confirmed_at,
                    ]
                    for m in mappings
                ),
            ),
        )
    )
    for kind, name in (("claims_csv", "claims.csv"), ("exceptions_csv", "exceptions.csv")):
        header, rows = export_service.export_rows(db, tid, report, kind)
        files.append((name, _csv(header, rows)))
    files.append(
        (
            "checks.json",
            _json(
                [
                    {
                        "module": r.module,
                        "state": r.state,
                        "reason": r.reason,
                        "rules": r.rules,
                        "config": r.config,
                        "finding_count": r.finding_count,
                        "ran_at": r.ran_at,
                        "ran_by": r.ran_by,
                    }
                    for r in runs
                ]
            ),
        )
    )
    files.append(
        (
            "findings.csv",
            _csv(
                [
                    "module",
                    "rule_code",
                    "status",
                    "severity",
                    "title",
                    "explanation",
                    "sheet_name",
                    "row_number",
                    "source_column",
                    "claim_reference",
                    "amount",
                    "currency",
                    "disposition",
                    "disposition_note",
                    "disposed_by",
                    "disposed_at",
                ],
                (
                    [
                        f.module,
                        f.rule_code,
                        f.status,
                        f.severity,
                        f.title,
                        f.explanation,
                        f.sheet_name,
                        f.row_number,
                        f.source_column,
                        f.claim_reference,
                        str(f.amount) if f.amount is not None else None,
                        f.currency,
                        f.disposition,
                        f.disposition_note,
                        f.disposed_by,
                        f.disposed_at,
                    ]
                    for f in findings
                ),
            ),
        )
    )
    files.append(
        (
            "audit_trail.json",
            _json(
                {
                    "organisation_chain_intact": intact,
                    "first_broken_seq": first_bad,
                    "entries": [
                        {
                            "seq": e.seq,
                            "timestamp": e.created_at,
                            "action_type": e.action_type,
                            "entity_type": e.entity_type,
                            "entity_id": e.entity_id,
                            "actor": e.actor,
                            "before": e.before_value,
                            "after": e.after_value,
                            "prev_hash": e.prev_hash,
                            "entry_hash": e.entry_hash,
                        }
                        for e in entries
                    ],
                }
            ),
        )
    )
    readme = (
        f"TrueBind audit pack (format {PACK_VERSION})\n"
        f"Report: {report.file_name} ({report.id})\n"
        f"Generated: {now.isoformat()} by {generated_by}\n\n"
        f"Coverage: {coverage_statement}\n\n"
        "Every file in this pack is listed in manifest.json with its SHA-256. The original upload is under\n"
        "original/ and matches the source_sha256 in report.json. audit_trail.json holds this report's\n"
        "hash-chained audit entries and whether the organisation's whole chain verified intact when the pack\n"
        "was built. Amounts are exact decimals as text; currencies are ISO 4217 codes.\n"
    )
    files.insert(0, ("README.txt", readme.encode("utf-8")))
    manifest = {
        "pack_version": PACK_VERSION,
        "report_id": report.id,
        "generated_at": now,
        "generated_by": generated_by,
        "files": [{"path": p, "sha256": hashlib.sha256(b).hexdigest(), "bytes": len(b)} for p, b in files],
    }
    files.append(("manifest.json", _json(manifest)))

    buf = io.BytesIO()
    stamp = (now.year, now.month, now.day, now.hour, now.minute, now.second)
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for path, body in files:
            info = zipfile.ZipInfo(path, date_time=stamp)
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, body)
    return buf.getvalue()
