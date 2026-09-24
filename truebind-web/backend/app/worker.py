"""TrueBind job worker: `python -m app.worker`.

The parent loop claims one job at a time and runs it in a fresh CHILD
process (multiprocessing "spawn") with:
- an address-space limit (RLIMIT_AS = JOB_MEMORY_MB), so a decompression
  bomb or pathological workbook kills only that child, never the API;
- a wall-clock timeout (JOB_TIMEOUT_S), after which the child is killed;
- a heartbeat from the parent every JOB_LEASE_S/3 seconds that extends the
  lease and notices cancellation requests.
If the child dies without recording an outcome (OOM kill, segfault in a
parser), the parent records FAILED with a stable code. If the PARENT dies,
the lease expires and any other worker's reaper re-queues or fails the job.

Run N copies for N-way parallelism; claims are atomic. For local
development, TRUEBIND_EMBEDDED_WORKER=1 starts this loop on a thread inside
the API process (children are still separate processes)."""

from __future__ import annotations

import logging
import multiprocessing as mp
import os
import signal
import socket
import threading
import time
import uuid

from .config import JOB_LEASE_S, JOB_MEMORY_MB, JOB_TIMEOUT_S
from .database import get_session_factory, set_tenant
from .models.jobs import Job
from .services import job_service, retention_service

log = logging.getLogger("truebind.worker")

POLL_S = 1.0
REAP_EVERY_S = 30.0
RETENTION_EVERY_S = 3600.0


def _child_main(job_id: str, tenant_id: str, memory_mb: int) -> None:
    """Entry point of the isolated child process."""
    if memory_mb > 0:
        try:
            import resource
            limit = memory_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
        except (ImportError, ValueError, OSError):  # pragma: no cover -- non-Linux dev boxes
            pass
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    from .database import get_session_factory as _factory  # fresh engine in this process
    from .services import job_handlers

    db = _factory()()
    try:
        job_handlers.execute(db, job_id, tenant_id)
    finally:
        db.close()


def _exit_failure(exitcode: int | None) -> tuple[str, str]:
    if exitcode is not None and exitcode < 0 and -exitcode == signal.SIGKILL:
        return "resource_limit", "Processing was stopped because it exceeded the memory allowed for one file."
    return "worker_crash", "Processing stopped unexpectedly while reading this file."


class Worker:
    def __init__(self, worker_id: str | None = None, timeout_s: int = JOB_TIMEOUT_S,
                 memory_mb: int = JOB_MEMORY_MB, lease_s: int = JOB_LEASE_S):
        self.id = worker_id or f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"
        self.timeout_s, self.memory_mb = timeout_s, memory_mb
        self.hb_interval = max(1.0, lease_s / 3)
        self.factory = get_session_factory()
        self._stop = threading.Event()
        self._ctx = mp.get_context("spawn")
        self._last_reap = 0.0
        self._last_retention = 0.0

    def stop(self) -> None:
        self._stop.set()

    def housekeeping(self) -> None:
        now = time.monotonic()
        if now - self._last_reap >= REAP_EVERY_S:
            self._last_reap = now
            db = self.factory()
            try:
                n = job_service.reap_expired(db)
                if n:
                    log.warning("reaped %d job(s) with expired leases", n)
            finally:
                db.close()
        if now - self._last_retention >= RETENTION_EVERY_S:
            self._last_retention = now
            db = self.factory()
            try:
                retention_service.expire_due_reports(db)
            except Exception:  # noqa: BLE001 -- housekeeping must not stop the worker
                log.exception("retention sweep failed")
            finally:
                db.close()

    def run_one(self) -> bool:
        """Claim and run one job. Returns False when the queue is empty."""
        db = self.factory()
        try:
            job = job_service.claim_next(db, self.id)
            if job is None:
                return False
            job_id, tenant_id, kind = job.id, job.tenant_id, job.kind
        finally:
            db.close()
        log.info("job %s (%s) claimed by %s", job_id, kind, self.id)
        proc = self._ctx.Process(target=_child_main, args=(job_id, tenant_id, self.memory_mb), daemon=True)
        proc.start()
        started = time.monotonic()
        outcome = None  # None | "timeout" | "cancel"
        while True:
            proc.join(self.hb_interval)
            if not proc.is_alive():
                break
            if time.monotonic() - started > self.timeout_s:
                outcome = "timeout"
            else:
                db = self.factory()
                try:
                    state = job_service.heartbeat(db, job_id, self.id)
                finally:
                    db.close()
                if state == "cancel":
                    outcome = "cancel"
                elif state == "gone":
                    proc.join(10)  # the child recorded an outcome and is exiting
                    if not proc.is_alive():
                        break
            if outcome:
                proc.kill()
                proc.join(10)
                break
        self._record_abnormal(job_id, tenant_id, outcome, proc.exitcode)
        return True

    def _record_abnormal(self, job_id: str, tenant_id: str, outcome: str | None, exitcode: int | None) -> None:
        """If the child did not record a terminal outcome itself, record one."""
        db = self.factory()
        try:
            set_tenant(db, tenant_id)
            job = db.get(Job, job_id)
            if job is None or job.status != "RUNNING" or job.lease_owner != self.id:
                return
            if outcome == "cancel":
                job_service.finish(db, job, ok=False, code="cancelled")
            elif outcome == "timeout":
                job_service.finish(db, job, ok=False, code="timeout",
                                   message=f"Processing took longer than the {self.timeout_s}s limit and was stopped.",
                                   detail=f"killed after {self.timeout_s}s by {self.id}")
            else:
                code, message = _exit_failure(exitcode)
                job_service.finish(db, job, ok=False, code=code, message=message,
                                   detail=f"child exit code {exitcode}", retryable=code == "worker_crash")
            log.warning("job %s ended abnormally: outcome=%s exitcode=%s", job_id, outcome, exitcode)
        finally:
            db.close()

    def run_forever(self) -> None:
        log.info("worker %s started (timeout=%ss memory=%sMB)", self.id, self.timeout_s, self.memory_mb)
        while not self._stop.is_set():
            try:
                self.housekeeping()
                if not self.run_one():
                    self._stop.wait(POLL_S)
            except Exception:  # noqa: BLE001 -- e.g. DB briefly unavailable: back off, keep going
                log.exception("worker loop error; backing off")
                self._stop.wait(5)
        log.info("worker %s stopped", self.id)


def run_pending_jobs_inline(max_jobs: int = 100) -> int:
    """Test/dev helper: run queued jobs in THIS process, no child and no
    resource limits. Returns the number of jobs run."""
    from .services import job_handlers

    factory = get_session_factory()
    worker_id = f"inline:{os.getpid()}"
    ran = 0
    while ran < max_jobs:
        db = factory()
        try:
            job = job_service.claim_next(db, worker_id)
            if job is None:
                return ran
            job_id, tenant_id = job.id, job.tenant_id
        finally:
            db.close()
        db = factory()
        try:
            job_handlers.execute(db, job_id, tenant_id)
        finally:
            db.close()
        ran += 1
    return ran


_embedded: Worker | None = None


def start_embedded() -> Worker:
    global _embedded
    if _embedded is None:
        _embedded = Worker()
        threading.Thread(target=_embedded.run_forever, name="truebind-worker", daemon=True).start()
    return _embedded


def stop_embedded() -> None:
    if _embedded is not None:
        _embedded.stop()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    w = Worker()
    signal.signal(signal.SIGTERM, lambda *_: w.stop())
    signal.signal(signal.SIGINT, lambda *_: w.stop())
    w.run_forever()


if __name__ == "__main__":
    main()
