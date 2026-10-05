"""Corrections and workbook versions. The uploaded file is never modified.

- A correction records one cell: before (read from the stored original, never
  from the client), after, reason, rule, who proposed it and who decided it.
- A corrected version is built from the original plus every APPROVED
  correction, deterministically: same original and same corrections give the
  same bytes and the same SHA-256 (fixed zip timestamps and document dates).
- An approved version records that a person approved a specific corrected
  version for submission.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import io
import re
import zipfile

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models._util import utcnow
from ..models.corrections import Correction, WorkbookVersion
from ..models.reports import Report, Sheet, ValidationResult
from . import audit_service, deliverables, grid_view, issues
from .storage import derived_key, get_store

CELL = re.compile(r"^([A-Z]{1,3})([1-9][0-9]{0,6})$")
_NUM = re.compile(r"^-?\d+(\.\d+)?$")
_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")
FIXED_TS = (1980, 1, 1, 0, 0, 0)


class CorrectionError(ValueError):
    pass


def _col_index(letters: str) -> int:
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n


def original_value(db: Session, report: Report, sheet_name: str, cell: str) -> str | None:
    m = CELL.match(cell)
    if not m:
        raise CorrectionError("Give the cell as a reference such as F14.")
    names = [s.sheet_name for s in db.query(Sheet).filter(Sheet.report_id == report.id, Sheet.status == "CONFIRMED")]
    if sheet_name not in names:
        raise CorrectionError("Corrections are made on a confirmed claims sheet.")
    values = grid_view._cached_values(db, report, names).get(sheet_name, [])
    row, col = int(m.group(2)), _col_index(m.group(1))
    if row > len(values):
        raise CorrectionError(f"{sheet_name} has no row {row}.")
    cells = values[row - 1]
    return cells[col - 1] if col - 1 < len(cells) else None


def propose(db: Session, report: Report, sheet_name: str, cell: str, after: str | None, reason: str, actor: str,
            issue_id: str | None = None, rule: str | None = None, source: str = "manual") -> Correction:
    cell = cell.strip().upper()
    if not reason.strip():
        raise CorrectionError("Give a reason for the correction.")
    if issue_id is not None and db.query(ValidationResult).filter(ValidationResult.id == issue_id,
                                                                  ValidationResult.report_id == report.id).first() is None:
        raise CorrectionError("That issue is not part of this report.")
    before = original_value(db, report, sheet_name, cell)
    pending = (db.query(Correction).filter(Correction.report_id == report.id, Correction.sheet_name == sheet_name,
                                           Correction.cell == cell, Correction.status == "PROPOSED").first())
    if pending is not None:
        raise CorrectionError(f"{sheet_name}!{cell} already has a correction waiting for a decision.")
    c = Correction(tenant_id=report.tenant_id, report_id=report.id, issue_id=issue_id, sheet_name=sheet_name, cell=cell,
                   before_value=before, after_value=after, reason=reason.strip()[:2000], rule=rule, source=source,
                   status="PROPOSED", proposed_by=actor)
    db.add(c)
    db.flush()
    audit_service.log_action(db, report.tenant_id, report.id, "CORRECTION_PROPOSED", "CORRECTION", c.id,
                             after={"sheet": sheet_name, "cell": cell, "before": before, "after": after,
                                    "reason": c.reason, "rule": rule, "source": source, "issue_id": issue_id},
                             actor=actor)
    return c


def propose_auto(db: Session, report: Report, actor: str) -> int:
    """Turn the safe, deterministic fixes (corrected-copy rules) into PROPOSED
    corrections linked to their issues. Idempotent: a cell that already has a
    correction is skipped."""
    _, changes = deliverables.corrected_workbook(db, report)
    taken = {(c.sheet_name, c.cell) for c in db.query(Correction).filter(Correction.report_id == report.id,
                                                                         Correction.status != "REJECTED")}
    by_cell = {}
    for vr in db.query(ValidationResult).filter(ValidationResult.report_id == report.id):
        x = vr.extra or {}
        if x.get("cell") and x.get("issue_status") in ("AUTO_FIX_PROPOSED", "DETECTED", "REQUIRES_HUMAN_REVIEW"):
            by_cell.setdefault(x["cell"], vr)
    n = 0
    for ch in changes:
        if (ch.sheet, ch.cell) in taken:
            continue
        vr = by_cell.get(ch.cell)
        after = ch.new.isoformat()[:10] if isinstance(ch.new, (dt.date, dt.datetime)) else (
            None if ch.new is None else str(ch.new))
        propose(db, report, ch.sheet, ch.cell, after, f"Automatic fix: {ch.rule}", actor,
                issue_id=vr.id if vr is not None else None, rule=(vr.rule if vr is not None else None), source="auto")
        n += 1
    return n


def decide(db: Session, report: Report, c: Correction, approve: bool, actor: str, note: str | None) -> Correction:
    if c.status != "PROPOSED":
        raise CorrectionError("This correction has already been decided.")
    c.status = "APPROVED" if approve else "REJECTED"
    c.decided_by, c.decided_at, c.decision_note = actor, utcnow(), (note or None)
    if approve and c.issue_id:
        vr = db.get(ValidationResult, c.issue_id)
        if vr is not None:
            target = "AUTO_FIXED" if c.source == "auto" else "RESOLVED"
            extra = dict(vr.extra or {})
            if extra.get("issue_status") == "DETECTED" and target == "AUTO_FIXED":
                extra = issues.transition(extra, "AUTO_FIX_PROPOSED", actor, "Automatic fix proposed")
            try:
                vr.extra = issues.transition(extra, target, actor,
                                             f"Corrected {c.sheet_name}!{c.cell}: {c.before_value!r} -> {c.after_value!r}")
            except issues.TransitionError:
                pass  # the issue was already closed another way; the correction still stands
    audit_service.log_action(db, report.tenant_id, report.id,
                             "CORRECTION_APPROVED" if approve else "CORRECTION_REJECTED", "CORRECTION", c.id,
                             after={"sheet": c.sheet_name, "cell": c.cell, "before": c.before_value,
                                    "after": c.after_value, "note": note}, actor=actor)
    return c


def _typed(v: str | None):
    if v is None or v == "":
        return None
    if _NUM.match(v):
        return float(v) if "." in v else int(v)
    if _ISO.match(v):
        return dt.date.fromisoformat(v)
    return v


def _deterministic(data: bytes) -> bytes:
    """Re-pack the xlsx zip with fixed timestamps so equal content hashes equally."""
    src = zipfile.ZipFile(io.BytesIO(data))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for info in sorted(src.infolist(), key=lambda i: i.filename):
            zi = zipfile.ZipInfo(info.filename, date_time=FIXED_TS)
            zi.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(zi, src.read(info.filename))
    return out.getvalue()


def _ensure_original(db: Session, report: Report, actor: str) -> WorkbookVersion:
    v = db.query(WorkbookVersion).filter(WorkbookVersion.report_id == report.id, WorkbookVersion.number == 0).first()
    if v is None:
        v = WorkbookVersion(tenant_id=report.tenant_id, report_id=report.id, number=0, kind="original",
                            sha256=report.source_sha256 or "", size=report.file_size_bytes or 0, corrections=[],
                            created_by=actor)
        db.add(v)
        db.flush()
    return v


def build_corrected(db: Session, report: Report, actor: str) -> tuple[WorkbookVersion, bytes]:
    """A corrected version: the original plus every approved correction."""
    _ensure_original(db, report, actor)
    approved = (db.query(Correction).filter(Correction.report_id == report.id, Correction.status == "APPROVED")
                .order_by(Correction.created_at, Correction.id).all())
    if not approved:
        raise CorrectionError("Approve at least one correction first.")
    wb, _ = deliverables.load_original(db, report)
    for c in approved:
        ws = deliverables._ws_for(wb, c.sheet_name)
        if ws is None:
            continue
        val = _typed(c.after_value)
        if isinstance(val, str):
            deliverables.set_text(ws[c.cell], val)
        else:
            ws[c.cell].value = val
            if isinstance(val, dt.date):
                ws[c.cell].number_format = "yyyy-mm-dd"
    stamp = report.created_at.replace(tzinfo=None) if report.created_at else dt.datetime(2026, 1, 1)  # noqa: DTZ001 -- openpyxl document dates are naive
    wb.properties.created = wb.properties.modified = stamp
    buf = io.BytesIO()
    wb.save(buf)
    body = _deterministic(buf.getvalue())
    sha = hashlib.sha256(body).hexdigest()
    ids = [c.id for c in approved]
    last = (db.query(WorkbookVersion).filter(WorkbookVersion.report_id == report.id, WorkbookVersion.kind == "corrected")
            .order_by(WorkbookVersion.number.desc()).first())
    if last is not None and last.sha256 == sha:
        return last, body  # nothing changed since the last corrected version
    number = (db.query(func.max(WorkbookVersion.number)).filter(WorkbookVersion.report_id == report.id).scalar() or 0) + 1
    v = WorkbookVersion(tenant_id=report.tenant_id, report_id=report.id, number=number, kind="corrected", sha256=sha,
                        size=len(body), corrections=ids, created_by=actor)
    db.add(v)
    db.flush()
    get_store().put_derived(_key(report, number), body, db=db)
    audit_service.log_action(db, report.tenant_id, report.id, "VERSION_CREATED", "WORKBOOK_VERSION", v.id,
                             after={"number": number, "kind": "corrected", "sha256": sha, "corrections": len(ids)},
                             actor=actor)
    return v, body


def approve_version(db: Session, report: Report, version: WorkbookVersion, actor: str, note: str | None) -> WorkbookVersion:
    if version.kind != "corrected":
        raise CorrectionError("Only a corrected version can be approved.")
    latest = (db.query(WorkbookVersion).filter(WorkbookVersion.report_id == report.id, WorkbookVersion.kind == "corrected")
              .order_by(WorkbookVersion.number.desc()).first())
    if latest is None or latest.id != version.id:
        raise CorrectionError("Approve the latest corrected version.")
    if db.query(Correction).filter(Correction.report_id == report.id, Correction.status == "PROPOSED").count():
        raise CorrectionError("Decide every proposed correction before approving.")
    number = (db.query(func.max(WorkbookVersion.number)).filter(WorkbookVersion.report_id == report.id).scalar() or 0) + 1
    v = WorkbookVersion(tenant_id=report.tenant_id, report_id=report.id, number=number, kind="approved",
                        sha256=version.sha256, size=version.size, corrections=version.corrections, based_on=version.id,
                        created_by=actor)
    db.add(v)
    db.flush()
    audit_service.log_action(db, report.tenant_id, report.id, "VERSION_APPROVED", "WORKBOOK_VERSION", v.id,
                             after={"number": number, "approves": version.number, "sha256": version.sha256,
                                    "note": note}, actor=actor)
    return v


def _key(report: Report, number: int) -> str:
    return derived_key(report.tenant_id, report.source_sha256 or "0" * 64, f"version-{number}")


def version_bytes(db: Session, report: Report, v: WorkbookVersion) -> bytes:
    if v.kind == "original":
        with deliverables._original_path(db, report) as p:
            return p.read_bytes()
    number = v.number
    if v.kind == "approved" and v.based_on:
        base = db.get(WorkbookVersion, v.based_on)
        number = base.number if base is not None else number
    data = get_store().get_derived(_key(report, number), db=db)
    if data is None:
        raise CorrectionError("This version's file is no longer stored.")
    if hashlib.sha256(data).hexdigest() != v.sha256:
        raise CorrectionError("This version's file does not match its recorded fingerprint.")
    return data
