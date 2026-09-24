"""Job system: atomic claim, leases, reaper, retries, cancellation, AI cost
cap, and the real isolated child-process worker (timeout, memory limit,
crash recovery)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.database import set_tenant
from app.models._util import utcnow
from app.models.jobs import Job
from app.models.reports import Report
from app.services import job_service
from app.worker import Worker
from conftest import run_jobs, simple_rows, xlsx_bytes


def _queued(api, db) -> tuple[str, Job]:
    r = api.upload("a.xlsx", xlsx_bytes(simple_rows()))
    rid = r.json()["id"]
    return rid, db.query(Job).filter_by(report_id=rid).one()


def test_claim_is_exclusive(api, db):
    rid, job = _queued(api, db)
    first = job_service.claim_next(db, "w1")
    second = job_service.claim_next(db, "w2")
    assert first is not None and first.id == job.id and first.lease_owner == "w1"
    assert second is None


def test_expired_lease_is_requeued_then_failed_never_stuck(api, db):
    rid, job = _queued(api, db)
    claimed = job_service.claim_next(db, "dead-worker")
    set_tenant(db, claimed.tenant_id)
    claimed.lease_expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    assert job_service.reap_expired(db) == 1
    db.expire_all()
    set_tenant(db, job.tenant_id)
    j = db.get(Job, job.id)
    assert j.status == "QUEUED" and j.error_code == "worker_lost" and j.attempts == 1
    assert db.get(Report, rid).status == "QUEUED"
    # second loss exhausts max_attempts (2) -> FAILED with a safe message
    j.run_after = None
    db.commit()
    claimed = job_service.claim_next(db, "dead-again")
    set_tenant(db, claimed.tenant_id)
    claimed.lease_expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    job_service.reap_expired(db)
    db.expire_all()
    set_tenant(db, job.tenant_id)
    assert db.get(Job, job.id).status == "FAILED"
    report = api.get(f"/api/v1/reports/{rid}").json()
    assert report["status"] == "FAILED" and report["error_code"] == "worker_lost"
    assert "lease expired" not in str(report), "internal detail is not exposed"


def test_heartbeat_extends_lease_and_reports_cancel(api, db):
    rid, job = _queued(api, db)
    claimed = job_service.claim_next(db, "w1")
    before = claimed.lease_expires_at
    assert job_service.heartbeat(db, claimed.id, "w1") == "ok"
    set_tenant(db, job.tenant_id)
    assert db.get(Job, job.id).lease_expires_at >= before
    assert job_service.heartbeat(db, claimed.id, "someone-else") == "gone"
    assert api.post(f"/api/v1/reports/{rid}/cancel").status_code == 200
    assert job_service.heartbeat(db, claimed.id, "w1") == "cancel"


def test_cancel_queued_job(api, db):
    rid, _ = _queued(api, db)
    r = api.post(f"/api/v1/reports/{rid}/cancel")
    assert r.status_code == 200 and r.json()["status"] == "CANCELLED"
    assert run_jobs() == 0
    assert api.post(f"/api/v1/reports/{rid}/cancel").status_code == 409


def test_per_tenant_concurrency_limit(api, db, monkeypatch):
    monkeypatch.setattr(job_service, "MAX_CONCURRENT_JOBS_PER_TENANT", 1)
    _queued(api, db)
    _queued(api, db)
    assert job_service.claim_next(db, "w1") is not None
    assert job_service.claim_next(db, "w2") is None, "tenant already has its one running job"


def test_ai_mapping_calls_are_capped_per_report(api, db, monkeypatch):
    from bordereaux import mapping as mapping_mod
    import app.services.job_handlers as jh

    calls = []

    class FakeMapper:
        model = "fake-model"
        last_usage = {"input_tokens": 10, "output_tokens": 5}

        def propose(self, headers):
            calls.append(list(headers))
            return {}

    monkeypatch.setattr(mapping_mod, "ai_mapping_available", lambda: True)
    monkeypatch.setattr(mapping_mod, "ClaudeAIMapper", FakeMapper)
    monkeypatch.setattr(jh, "AI_MAX_CALLS_PER_REPORT", 2)
    odd = [["Claim Reference", "Insured Name", "Mystery Col"], ["C1", "Acme", "x"]]
    content = xlsx_bytes(odd, extra_sheets={f"S{i}": odd for i in range(4)})
    rid = api.ingest("ai.xlsx", content)
    notes = api.get(f"/api/v1/reports/{rid}").json()["ingest_notes"]
    assert len(calls) == 2 and notes["ai_calls"] == 2 and notes["ai_capped"] is True
    assert notes["ai_input_tokens"] == 20
    assert all("x" not in h for c in calls for h in c), "only headers are sent, never cell values"


# ---------------------------------------------------------------- real child-process worker

@pytest.mark.slow
def test_worker_runs_job_in_child_process(api, db):
    rid, _ = _queued(api, db)
    assert Worker(worker_id="t-worker", timeout_s=120, memory_mb=0).run_one() is True
    assert api.get(f"/api/v1/reports/{rid}").json()["status"] == "WAITING_FOR_REVIEW"


@pytest.mark.slow
def test_worker_kills_job_that_exceeds_timeout(api, db):
    rid, job = _queued(api, db)
    w = Worker(worker_id="t-worker", timeout_s=0, memory_mb=0)
    w.hb_interval = 0.05
    w.run_one()
    report = api.get(f"/api/v1/reports/{rid}").json()
    assert report["status"] == "FAILED" and report["error_code"] == "timeout"


@pytest.mark.slow
def test_worker_survives_child_that_exceeds_memory(api, db):
    rid, job = _queued(api, db)
    Worker(worker_id="t-worker", timeout_s=120, memory_mb=64).run_one()
    set_tenant(db, job.tenant_id)
    db.expire_all()
    j = db.get(Job, job.id)
    assert j.status in ("FAILED", "QUEUED"), j.status
    assert j.error_code in ("resource_limit", "worker_crash", "internal_error"), j.error_code
    # the parent (this process) is unaffected and the report is not stuck
    assert api.get(f"/api/v1/reports/{rid}").json()["status"] in ("FAILED", "QUEUED")


# ---------------------------------------------------------------- worker liveness (queued-forever regression)

def test_status_reports_no_worker_so_ui_never_waits_forever(api, db):
    _queued(api, db)
    s = api.get("/api/v1/system/status").json()
    assert s["worker_available"] is False and s["workers_alive"] == 0
    assert s["queued"] == 1 and s["oldest_queued_s"] is not None


def test_status_sees_a_checked_in_worker(api):
    w = Worker(worker_id="status-worker", prewarm=False)
    w.check_in(force=True)
    s = api.get("/api/v1/system/status").json()
    assert s["worker_available"] is True and s["workers_alive"] == 1
    w.check_out()
    assert api.get("/api/v1/system/status").json()["worker_available"] is False


def test_jobs_of_a_dead_worker_are_recovered_before_lease_expiry(api, db):
    from app.models.jobs import WorkerHeartbeat
    rid, job = _queued(api, db)
    claimed = job_service.claim_next(db, "dead-worker")
    assert claimed.lease_expires_at is not None  # lease still valid for ~60s
    db.add(WorkerHeartbeat(id="dead-worker", hostname="h", pid=1, mode="standalone",
                           started_at=utcnow() - timedelta(minutes=5), last_seen_at=utcnow() - timedelta(minutes=2)))
    db.commit()
    assert job_service.reap_expired(db) == 1
    report = api.get(f"/api/v1/reports/{rid}").json()
    assert report["status"] == "QUEUED" and report["job"]["error_code"] == "worker_lost"
    assert "queued again automatically" in report["job"]["error_message"]


@pytest.mark.slow
def test_prewarmed_child_runs_job_and_worker_loop_checks_in(api, db):
    rid, _ = _queued(api, db)
    w = Worker(worker_id="warm-worker", timeout_s=120, memory_mb=0)
    w.warm_up()
    assert w.run_one() is True
    w.discard_warm()
    assert api.get(f"/api/v1/reports/{rid}").json()["status"] == "WAITING_FOR_REVIEW"


def test_same_host_worker_with_dead_pid_is_recovered_immediately(api, db):
    import os
    import socket
    from app.models.jobs import WorkerHeartbeat
    if os.name != "posix":
        pytest.skip("POSIX pid probe")
    rid, _ = _queued(api, db)
    job_service.claim_next(db, "crashed-local")
    db.add(WorkerHeartbeat(id="crashed-local", hostname=socket.gethostname()[:255], pid=2 ** 22 + 7,
                           mode="embedded", started_at=utcnow(), last_seen_at=utcnow()))  # fresh check-in, dead pid
    db.commit()
    w = Worker(worker_id="restarted", prewarm=False)
    w.housekeeping()
    assert api.get(f"/api/v1/reports/{rid}").json()["status"] == "QUEUED"


def test_slow_ai_is_bounded_by_a_time_budget(api, db, monkeypatch):
    import time
    from bordereaux import mapping as mapping_mod
    import app.services.job_handlers as jh

    class SlowMapper:
        model = "slow-model"
        last_usage = None

        def propose(self, headers):
            time.sleep(0.4)
            return {}

    monkeypatch.setattr(mapping_mod, "ai_mapping_available", lambda: True)
    monkeypatch.setattr(mapping_mod, "ClaudeAIMapper", SlowMapper)
    monkeypatch.setattr(jh, "AI_TIME_BUDGET_S", 0.5)
    odd = [["Claim Reference", "Insured Name", "Mystery Col"], ["C1", "Acme", "x"]]
    t = time.perf_counter()
    rid = api.ingest("slow.xlsx", xlsx_bytes(odd, extra_sheets={f"S{i}": odd for i in range(6)}))
    elapsed = time.perf_counter() - t
    notes = api.get(f"/api/v1/reports/{rid}").json()["ingest_notes"]
    assert notes["ai_capped"] is True and notes["ai_cap_reason"] == "time budget"
    assert notes["ai_calls"] <= 2 and elapsed < 3, "7 sheets x 0.4s would take 2.8s+ without the budget"
    assert api.get(f"/api/v1/reports/{rid}").json()["status"] == "WAITING_FOR_REVIEW"


def test_failing_ai_degrades_to_deterministic_mapping(api, db, monkeypatch):
    from bordereaux import mapping as mapping_mod

    class BrokenMapper:
        model = "broken"
        last_usage = None

        def propose(self, headers):
            raise TimeoutError("provider timed out")

    monkeypatch.setattr(mapping_mod, "ai_mapping_available", lambda: True)
    monkeypatch.setattr(mapping_mod, "ClaudeAIMapper", BrokenMapper)
    rid = api.ingest("a.xlsx", xlsx_bytes([["Claim Reference", "Insured Name", "Mystery Col"], ["C1", "Acme", "x"]]))
    r = api.get(f"/api/v1/reports/{rid}").json()
    assert r["status"] == "WAITING_FOR_REVIEW"
    sheet = api.get(f"/api/v1/reports/{rid}/sheets").json()[0]
    fields = {f["field_code"]: f for f in api.get(f"/api/v1/reports/{rid}/sheets/{sheet['id']}/mapping").json()["fields"]}
    assert fields["CR0104M"]["source_column"] == "Claim Reference"
