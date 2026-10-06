"""P1.7 -- jobs: retries, idempotency keys, wake-ups.

Acceptance:
- the retry limit is JOB_MAX_ATTEMPTS (a setting), stamped on each job;
- a PROCESS job that fails mid-save is retried and ends with exactly the
  results of a clean run: nothing partial, nothing duplicated;
- POST /reports/upload and /reports/{id}/process honour Idempotency-Key:
  a repeat with the same key and the same request replays the first
  response (Idempotent-Replayed: true) and creates nothing; the same key
  with a different request is 422; keys are per organisation; a malformed
  key is 400; a failed request does not burn its key;
- without REDIS_URL, wake-up signals are a no-op and waiting returns at
  once (the worker falls back to polling the database).
"""

from __future__ import annotations

import time
from collections import Counter
from datetime import timedelta
from typing import Any

import pytest
from app.database import set_tenant
from app.models._util import utcnow
from app.models.jobs import Job
from app.models.reports import ClaimRow, Report, ValidationResult
from app.services import job_service, job_signal, persistence_service
from conftest import Api, run_jobs, simple_rows, xlsx_bytes
from sqlalchemy.orm import Session

KEY = {"Idempotency-Key": "upload-7f3c2a"}


def _results(db: Session, rid: str) -> tuple[Counter[str], Counter[tuple[str, str, str]]]:
    db.expire_all()
    rows = Counter(r.claim_reference or "" for r in db.query(ClaimRow).filter_by(report_id=rid))
    vrs = Counter((v.check_type, v.rule or "", v.status) for v in db.query(ValidationResult).filter_by(report_id=rid))
    return rows, vrs


def test_retry_limit_comes_from_settings(api: Api, db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(job_service, "JOB_MAX_ATTEMPTS", 3)
    rid = api.upload("a.xlsx", xlsx_bytes(simple_rows())).json()["id"]
    job = db.query(Job).filter_by(report_id=rid).one()
    assert job.max_attempts == 3
    for attempt in (1, 2):  # two lost workers: still queued again
        claimed = job_service.claim_next(db, f"dead-{attempt}")
        assert claimed is not None
        set_tenant(db, claimed.tenant_id)
        claimed.lease_expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
        job_service.reap_expired(db)
        db.expire_all()
        set_tenant(db, job.tenant_id)
        j = db.get(Job, job.id)
        assert j is not None and j.status == "RETRYING" and j.attempts == attempt
        j.run_after = None
        db.commit()


def test_process_failing_mid_save_is_retried_without_partial_or_duplicate_results(
    api: Api, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    content = xlsx_bytes(simple_rows(12))
    clean_rid, _ = api.full_run("clean.xlsx", content)
    expected = _results(db, clean_rid)

    rid = api.ingest("retry.xlsx", content)
    api.confirm_all(rid)
    real = persistence_service.persist_pipeline_result
    calls = {"n": 0}

    def crash_after_writing(*args: Any, **kwargs: Any) -> None:
        real(*args, **kwargs)  # rows written in the job's transaction ...
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("simulated crash after writing results")  # ... then the job dies

    monkeypatch.setattr(persistence_service, "persist_pipeline_result", crash_after_writing)
    assert api.post(f"/api/v1/reports/{rid}/process").status_code == 202
    run_jobs()  # attempt 1 fails (retryable), attempt 2 is delayed by backoff
    db.expire_all()
    set_tenant(db, api.me["tenant"]["id"])
    job = db.query(Job).filter_by(report_id=rid, kind="PROCESS").one()
    assert job.status == "RETRYING" and job.error_code == "internal_error"
    assert _results(db, rid) == (Counter(), Counter()), "the failed attempt left nothing behind"
    job.run_after = None
    db.commit()
    run_jobs()
    assert api.get(f"/api/v1/reports/{rid}").json()["status"] == "COMPLETE"
    assert calls["n"] == 2
    assert _results(db, rid) == expected


def test_upload_with_idempotency_key_replays_and_creates_nothing(api: Api, db: Session) -> None:
    content = xlsx_bytes(simple_rows())
    first = api.post("/api/v1/reports/upload", files={"file": ("a.xlsx", content)}, headers=KEY)
    assert first.status_code == 202, first.text
    assert "Idempotent-Replayed" not in first.headers
    again = api.post("/api/v1/reports/upload", files={"file": ("a.xlsx", content)}, headers=KEY)
    assert again.status_code == 202
    assert again.headers["Idempotent-Replayed"] == "true"
    assert again.json() == first.json()
    assert db.query(Report).count() == 1
    assert db.query(Job).count() == 1


def test_idempotency_key_reused_for_a_different_request_is_rejected(api: Api) -> None:
    ok = api.post("/api/v1/reports/upload", files={"file": ("a.xlsx", xlsx_bytes(simple_rows(3)))}, headers=KEY)
    assert ok.status_code == 202
    other = api.post("/api/v1/reports/upload", files={"file": ("a.xlsx", xlsx_bytes(simple_rows(4)))}, headers=KEY)
    assert other.status_code == 422
    assert "Idempotency-Key" in other.json()["detail"]


def test_idempotency_keys_are_per_organisation(api: Api, api_b: Api) -> None:
    content = xlsx_bytes(simple_rows())
    a = api.post("/api/v1/reports/upload", files={"file": ("a.xlsx", content)}, headers=KEY)
    b = api_b.post("/api/v1/reports/upload", files={"file": ("a.xlsx", content)}, headers=KEY)
    assert a.status_code == b.status_code == 202
    assert "Idempotent-Replayed" not in b.headers
    assert a.json()["id"] != b.json()["id"]


@pytest.mark.parametrize("key", ["", "x" * 256, "has space", "café"])
def test_malformed_idempotency_key_is_400(api: Api, key: str) -> None:
    r = api.post(
        "/api/v1/reports/upload",
        files={"file": ("a.xlsx", xlsx_bytes(simple_rows()))},
        headers={"Idempotency-Key": key.encode("utf-8")},  # raw bytes, as a misbehaving client would send
    )
    assert r.status_code == 400
    assert "Idempotency-Key" in r.json()["detail"]


def test_failed_request_does_not_burn_its_key(api: Api) -> None:
    bad = api.post("/api/v1/reports/upload", files={"file": ("a.xlsx", b"not a workbook")}, headers=KEY)
    assert bad.status_code >= 400
    good = api.post("/api/v1/reports/upload", files={"file": ("a.xlsx", xlsx_bytes(simple_rows()))}, headers=KEY)
    assert good.status_code == 202 and "Idempotent-Replayed" not in good.headers


def test_process_with_idempotency_key_enqueues_once(api: Api, db: Session) -> None:
    rid = api.ingest("a.xlsx", xlsx_bytes(simple_rows()))
    api.confirm_all(rid)
    key = {"Idempotency-Key": "process-1"}
    first = api.post(f"/api/v1/reports/{rid}/process", headers=key)
    again = api.post(f"/api/v1/reports/{rid}/process", headers=key)  # would be 409 without the key
    assert first.status_code == again.status_code == 202
    assert again.headers["Idempotent-Replayed"] == "true" and again.json() == first.json()
    assert db.query(Job).filter_by(report_id=rid, kind="PROCESS").count() == 1
    other = api.ingest("b.xlsx", xlsx_bytes(simple_rows(4)))
    api.confirm_all(other)
    assert api.post(f"/api/v1/reports/{other}/process", headers=key).status_code == 422


def test_wake_signal_without_redis_is_a_no_op(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(job_signal, "REDIS_URL", "")
    job_signal.notify(db)
    db.commit()
    t0 = time.monotonic()
    assert job_signal.wait(5.0) is False
    assert time.monotonic() - t0 < 0.5


def test_expired_key_is_treated_as_new(api: Api, db: Session) -> None:
    from app.models.idempotency import IdempotencyKey

    content = xlsx_bytes(simple_rows())
    first = api.post("/api/v1/reports/upload", files={"file": ("a.xlsx", content)}, headers=KEY)
    row = db.query(IdempotencyKey).one()
    row.expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    again = api.post("/api/v1/reports/upload", files={"file": ("a.xlsx", content)}, headers=KEY)
    assert again.status_code == 202 and "Idempotent-Replayed" not in again.headers
    assert again.json()["id"] != first.json()["id"]
    db.expire_all()
    assert db.query(IdempotencyKey).count() == 1
