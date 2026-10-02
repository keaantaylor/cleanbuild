"""STORAGE_BACKEND=db (the production default): originals and the parse cache
live in the database, so a host restart that wipes the local disk can no
longer fail a job with "source_missing"; tampering is still detected; and the
PROCESS job reuses the INGEST parse instead of reading the workbook again."""

from __future__ import annotations

import os
import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from conftest import Api, run_jobs, simple_rows, xlsx_bytes

from app.database import get_session_factory, set_tenant
from app.models.blobs import StoredBlob
from app.models.jobs import Job
from app.models.reports import Report
from app.services import parse_cache, storage
from app.settings import get_settings


@pytest.fixture
def db_store(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("STORAGE_BACKEND", "db")
    get_settings.cache_clear()
    storage.reset_store()
    yield
    monkeypatch.undo()
    get_settings.cache_clear()
    storage.reset_store()


def _session(tenant_id: str):
    s = get_session_factory()()
    set_tenant(s, tenant_id)
    return s


def _upload_and_ingest(api: Api) -> str:
    r = api.upload("claims.xlsx", xlsx_bytes(simple_rows(6)))
    assert r.status_code == 202, r.text
    run_jobs()
    return r.json()["id"]


def test_settings_default_to_db_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    from test_settings import PROD_OK, _settings

    assert _settings(monkeypatch, **PROD_OK).storage_backend == "db"
    assert _settings(monkeypatch).storage_backend == "local"


def test_original_survives_a_wiped_disk_and_processing_reuses_the_parse(db_store, api: Api) -> None:
    rid = _upload_and_ingest(api)
    tid = api.me["tenant"]["id"]
    with _session(tid) as s:
        report = s.get(Report, rid)
        assert s.get(StoredBlob, report.storage_key) is not None, "the original is stored in the database"
    # Simulate a restart on a host with an ephemeral disk.
    shutil.rmtree(Path(os.environ["TRUEBIND_STORAGE_DIR"]), ignore_errors=True)
    api.confirm_all(rid)
    assert api.post(f"/api/v1/reports/{rid}/process").status_code in (200, 202)
    run_jobs()
    assert api.get(f"/api/v1/reports/{rid}").json()["status"] == "COMPLETE"
    with _session(tid) as s:
        proc = s.query(Job).filter_by(report_id=rid, kind="PROCESS").one()
        assert proc.metrics["parse_cached"] is True, "PROCESS reused the INGEST parse"


def test_corrupt_parse_cache_falls_back_to_the_original(db_store, api: Api) -> None:
    rid = _upload_and_ingest(api)
    tid = api.me["tenant"]["id"]
    with _session(tid) as s:
        report = s.get(Report, rid)
        key = storage.derived_key(tid, report.source_sha256, parse_cache.FORMAT)
        s.get(StoredBlob, key).content = b"not gzip"
        s.commit()
    api.confirm_all(rid)
    api.post(f"/api/v1/reports/{rid}/process")
    run_jobs()
    assert api.get(f"/api/v1/reports/{rid}").json()["status"] == "COMPLETE"
    with _session(tid) as s:
        assert s.query(Job).filter_by(report_id=rid, kind="PROCESS").one().metrics["parse_cached"] is False


def test_tampered_original_is_refused(db_store, api: Api) -> None:
    rid = _upload_and_ingest(api)
    tid = api.me["tenant"]["id"]
    with _session(tid) as s:
        report = s.get(Report, rid)
        s.get(StoredBlob, report.storage_key).content = b"not the original"
        # Drop the parse cache too, so PROCESS has to read the (tampered) original.
        s.query(StoredBlob).filter(StoredBlob.key.like(f"tenants/{tid}/derived/%")).delete(synchronize_session=False)
        s.commit()
    api.confirm_all(rid)
    api.post(f"/api/v1/reports/{rid}/process")
    run_jobs()
    rep = api.get(f"/api/v1/reports/{rid}").json()
    assert rep["status"] == "FAILED"
    with _session(tid) as s:
        assert s.query(Job).filter_by(report_id=rid, kind="PROCESS").one().error_code == "source_tampered"


def test_originals_stored_on_disk_before_the_switch_still_load(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    rid = _upload_and_ingest(api)  # written by the local-disk backend
    monkeypatch.setenv("STORAGE_BACKEND", "db")
    get_settings.cache_clear()
    storage.reset_store()
    try:
        api.confirm_all(rid)
        api.post(f"/api/v1/reports/{rid}/process")
        run_jobs()
        assert api.get(f"/api/v1/reports/{rid}").json()["status"] == "COMPLETE"
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()
        storage.reset_store()


def test_derived_keys_cannot_escape_their_tenant() -> None:
    tid = "00000000-0000-4000-8000-000000000000"
    for bad in ("../../etc/passwd", f"tenants/{tid}/derived/../../x.json.gz", f"tenants/{tid}/originals/x.json.gz"):
        with pytest.raises(ValueError):
            storage.check_derived_key(bad)
    with pytest.raises(ValueError):
        storage.derived_key(tid, "a" * 64, "../evil")


def test_purge_removes_the_original_and_parse_cache_from_the_database(db_store, api: Api) -> None:
    from app.services import retention_service

    rid = _upload_and_ingest(api)
    tid = api.me["tenant"]["id"]
    with _session(tid) as s:
        assert s.query(StoredBlob).filter(StoredBlob.tenant_id == tid).count() >= 2, "original + parse cache"
    assert api.delete(f"/api/v1/reports/{rid}").status_code in (200, 204)
    s = get_session_factory()()
    try:
        assert retention_service.purge_deleted_reports(s) == 1
    finally:
        s.close()
    with _session(tid) as s:
        assert s.query(StoredBlob).filter(StoredBlob.tenant_id == tid).count() == 0
