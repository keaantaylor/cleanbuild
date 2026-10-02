"""P1.5 -- immutable original files.

Acceptance:
- originals are stored write-once under a content-addressed key
  (tenants/<tenant>/originals/<sha256>.<kind>) with their SHA-256 recorded;
  storing identical bytes again is idempotent; nothing can overwrite a key;
- the storage interface has no delete/overwrite path at all;
- every read verifies the SHA-256: a tampered original is refused, never parsed;
- deleting a report (or its retention expiring) is a soft delete: the report
  disappears from the API (404, lists, overview) and the audit trail records it,
  but the original stays in storage byte-for-byte.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from app.models.audit import AuditLogEntry
from app.models.reports import Report
from app.services import storage
from app.services.storage import IntegrityError, LocalObjectStore, get_store
from conftest import Api, simple_rows, xlsx_bytes
from sqlalchemy.orm import Session

TENANT = "00000000-0000-4000-8000-000000000001"


def _file(tmp_path: Path, content: bytes, name: str = "src.xlsx") -> Path:
    p = tmp_path / name
    p.write_bytes(content)
    return p


def test_originals_are_content_addressed_and_idempotent(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path / "objects")
    content = b"bordereau bytes v1"
    sha = hashlib.sha256(content).hexdigest()
    obj = store.put_original(TENANT, "xlsx", _file(tmp_path, content))
    assert obj.sha256 == sha and obj.size == len(content)
    assert obj.key == f"tenants/{TENANT}/originals/{sha}.xlsx"
    again = store.put_original(TENANT, "xlsx", _file(tmp_path, content, "copy.xlsx"))
    assert again == obj, "identical bytes map to the same immutable object"
    with store.local_copy(obj.key, sha) as p:
        assert p.read_bytes() == content


def test_storage_has_no_overwrite_path_and_one_retention_delete() -> None:
    """Originals are write-once. The only removal path is delete_source, used by
    the retention purge (retention_service.purge_report) when a report's
    retention period ends or it is deleted."""
    forbidden = ("delete", "remove", "unlink", "purge", "overwrite", "rmtree")
    for cls in (storage.LocalObjectStore, storage.S3ObjectStore, storage.DbObjectStore):
        public = [n for n in dir(cls) if not n.startswith("_")]
        assert [n for n in public if any(w in n.lower() for w in forbidden)] == ["delete_source"], (cls.__name__, public)
    callers = [p for p in Path(storage.__file__).parents[1].rglob("*.py")
               if "delete_source(" in p.read_text(encoding="utf-8") and p.name != "storage.py"]
    assert [p.name for p in callers] == ["retention_service.py"]


def test_tampered_original_is_refused(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path / "objects")
    obj = store.put_original(TENANT, "csv", _file(tmp_path, b"a,b\n1,2\n", "s.csv"))
    stored = tmp_path / "objects" / obj.key
    stored.chmod(0o600)
    stored.write_bytes(b"a,b\n9,9\n")  # someone edits the file on disk
    with pytest.raises(IntegrityError), store.local_copy(obj.key, obj.sha256):
        pass


def test_keys_are_validated(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path / "objects")
    for bad in ("../etc/passwd", f"tenants/{TENANT}/originals/../../x.xlsx", "tenants/x/originals/abc.exe"):
        with pytest.raises(ValueError), store.local_copy(bad, "0" * 64):
            pass


# ---------------------------------------------------------------- API behaviour


def _stored_bytes(report: Report) -> bytes:
    with get_store().local_copy(report.storage_key or "", report.source_sha256 or "") as p:
        return p.read_bytes()


def test_delete_is_soft_and_keeps_the_original(api: Api, db: Session) -> None:
    content = xlsx_bytes(simple_rows())
    rid, _ = api.full_run("a.xlsx", content)
    report = db.get(Report, rid)
    assert report is not None
    assert report.storage_key and report.storage_key.startswith(f"tenants/{report.tenant_id}/originals/")
    assert report.source_sha256 == hashlib.sha256(content).hexdigest()
    before = _stored_bytes(report)

    assert api.delete(f"/api/v1/reports/{rid}").status_code == 204
    assert api.get(f"/api/v1/reports/{rid}").status_code == 404
    assert api.get(f"/api/v1/reports/{rid}/claims").status_code == 404
    assert all(r["id"] != rid for r in api.get("/api/v1/reports").json()["items"])
    ov = api.get("/api/v1/overview").json()
    assert ov["reports"]["total"] == 0, "not counted on the overview"
    assert all(a["report_id"] != rid for a in ov["alerts"]["latest"]), "its alerts are hidden too"
    assert all(a["report_id"] != rid for a in api.get("/api/v1/alerts").json()["items"])
    assert api.delete(f"/api/v1/reports/{rid}").status_code == 404, "already deleted"

    from app.database import get_session_factory, set_tenant

    fresh = get_session_factory()()
    try:
        set_tenant(fresh, report.tenant_id)
        assert fresh.get(Report, rid) is None, "a new session (e.g. a worker) cannot see it"
        kept = fresh.get(Report, rid, execution_options={"include_deleted": True})
        assert kept is not None and kept.deleted_at is not None, "soft delete: the record remains for audit"
        assert _stored_bytes(kept) == before, "the original is untouched"
    finally:
        fresh.close()
    db.expire_all()
    assert db.query(AuditLogEntry).filter_by(report_id=rid, action_type="REPORT_DELETED").count() == 1


def test_retention_expiry_is_soft_and_keeps_the_original(api: Api, db: Session) -> None:
    from datetime import timedelta

    from app.models._util import utcnow
    from app.services import retention_service

    rid, _ = api.full_run("a.xlsx", xlsx_bytes(simple_rows()))
    report = db.get(Report, rid)
    assert report is not None
    report.expires_at = utcnow() - timedelta(days=1)
    db.commit()
    before = _stored_bytes(report)
    assert retention_service.expire_due_reports(db) == 1
    assert api.get(f"/api/v1/reports/{rid}").status_code == 404
    assert retention_service.expire_due_reports(db) == 0, "expiry happens once"
    db.expire_all()
    kept = db.get(Report, rid)
    assert kept is not None and _stored_bytes(kept) == before


def test_same_file_uploaded_twice_shares_one_immutable_original(api: Api, db: Session) -> None:
    content = xlsx_bytes(simple_rows())
    a = api.ingest("first.xlsx", content)
    b = api.ingest("second.xlsx", content)
    ra, rb = db.get(Report, a), db.get(Report, b)
    assert ra is not None and rb is not None
    assert ra.storage_key == rb.storage_key and ra.source_sha256 == rb.source_sha256
