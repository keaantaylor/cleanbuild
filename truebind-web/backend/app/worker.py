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

from .config import JOB_LEASE_S, JOB_MEMORY_MB, JOB_TIMEOUT_S, describe_database_url
from .database import get_session_factory, set_tenant
from .models._util import utcnow
from .models.jobs import Job, WorkerHeartbeat
from .services import job_service, retention_service

log = logging.getLogger("truebind.worker")

POLL_S = 0.5
REAP_EVERY_S = 10.0
RETENTION_EVERY_S = 3600.0


def _limit_memory(memory_mb: int) -> None:
    if memory_mb <= 0:
        return
    try:
        import resource  # POSIX only; Windows has no RLIMIT_AS (see README: run the worker on Linux in production)
        limit = memory_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    except (ImportError, ValueError, OSError):  # pragma: no cover
        pass


def _child_entry(conn, memory_mb: int) -> None:
    """Entry point of an isolated child process. It imports the heavy
    modules first and then WAITS for one job id: the parent keeps one such
    child warm, so a claimed job starts in milliseconds instead of paying
    process start + pandas/openpyxl/SQLAlchemy import time. Each child runs
    exactly one job and exits (isolation is unchanged)."""
    _limit_memory(memory_mb)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    from .database import get_session_factory as _factory  # fresh engine in this process
    from .services import job_handlers

    try:
        msg = conn.recv()
    except (EOFError, OSError):
        return
    if not msg:
        return
    job_id, tenant_id = msg
    db = _factory()()
    try:
        job_handlers.execute(db, job_id, tenant_id)
    finally:
        db.close()


def _exit_failure(exitcode: int | None) -> tuple[str, str]:
    sigkill = getattr(signal, "SIGKILL", 9)  # Windows has no SIGKILL constant
    if exitcode is not None and exitcode < 0 and -exitcode == sigkill:
        return "resource_limit", "Processing was stopped because it exceeded the memory allowed for one file."
    return "worker_crash", "The processing worker stopped unexpectedly while handling this file."


REGISTRY_EVERY_S = 5.0
JOIN_TICK_S = 1.0


class Worker:
    def __init__(self, worker_id: str | None = None, timeout_s: int = JOB_TIMEOUT_S,
                 memory_mb: int = JOB_MEMORY_MB, lease_s: int = JOB_LEASE_S, mode: str = "standalone",
                 prewarm: bool = True):
        self.id = worker_id or f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"
        self.timeout_s, self.memory_mb, self.mode, self.prewarm = timeout_s, memory_mb, mode, prewarm
        self.hb_interval = max(1.0, lease_s / 3)
        self.factory = get_session_factory()
        self._stop = threading.Event()
        self._ctx = mp.get_context("spawn")
        self._last_reap = 0.0
        self._last_retention = 0.0
        self._last_registry = 0.0
        self._started_at = utcnow()
        self._warm: tuple | None = None  # (process, parent_conn)

    def stop(self) -> None:
        self._stop.set()

    # ------------------------------------------------------------ liveness registry
    def check_in(self, current_job_id: str | None = None, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_registry < REGISTRY_EVERY_S:
            return
        self._last_registry = now
        db = self.factory()
        try:
            row = db.get(WorkerHeartbeat, self.id)
            if row is None:
                row = WorkerHeartbeat(id=self.id, hostname=socket.gethostname()[:255], pid=os.getpid(),
                                      mode=self.mode, started_at=self._started_at, last_seen_at=utcnow())
                db.add(row)
            row.last_seen_at = utcnow()
            row.current_job_id = current_job_id
            db.commit()
        except Exception:  # noqa: BLE001 -- liveness reporting must never stop processing
            db.rollback()
            log.exception("worker check-in failed")
        finally:
            db.close()

    def check_out(self) -> None:
        db = self.factory()
        try:
            row = db.get(WorkerHeartbeat, self.id)
            if row is not None:
                db.delete(row)
                db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
        finally:
            db.close()

    def housekeeping(self) -> None:
        now = time.monotonic()
        if now - self._last_reap >= REAP_EVERY_S:
            self._last_reap = now
            db = self.factory()
            try:
                n = job_service.reap_expired(db)
                if n:
                    log.warning("recovered %d job(s) from a stopped or unresponsive worker", n)
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

    # ------------------------------------------------------------ child processes
    def _spawn_child(self):
        parent_conn, child_conn = self._ctx.Pipe()
        proc = self._ctx.Process(target=_child_entry, args=(child_conn, self.memory_mb), daemon=True)
        proc.start()
        child_conn.close()
        return proc, parent_conn

    def _take_child(self):
        warm, self._warm = self._warm, None
        if warm is not None and warm[0].is_alive():
            return warm
        if warm is not None:
            warm[0].join(0)
        return self._spawn_child()

    def warm_up(self) -> None:
        if self.prewarm and (self._warm is None or not self._warm[0].is_alive()):
            self._warm = self._spawn_child()

    def discard_warm(self) -> None:
        if self._warm is not None:
            proc, conn = self._warm
            try:
                conn.send(None)
            except (OSError, BrokenPipeError):
                pass
            proc.join(2)
            if proc.is_alive():
                proc.kill()
            self._warm = None

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
        self.check_in(job_id, force=True)
        proc, conn = self._take_child()
        conn.send((job_id, tenant_id))
        self.warm_up()  # the next job's child starts importing now, in parallel
        started = last_hb = time.monotonic()
        outcome = None  # None | "timeout" | "cancel"
        tick = min(JOIN_TICK_S, self.hb_interval)
        while True:
            proc.join(tick)
            if not proc.is_alive():
                break
            self.check_in(job_id)
            now = time.monotonic()
            if now - started > self.timeout_s:
                outcome = "timeout"
            elif now - last_hb >= self.hb_interval:
                last_hb = now
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
        conn.close()
        self._record_abnormal(job_id, tenant_id, outcome, proc.exitcode)
        self.check_in(None, force=True)
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
        log.info("worker %s started (%s, timeout=%ss memory=%sMB, db=%s)", self.id, self.mode, self.timeout_s,
                 self.memory_mb, describe_database_url())
        self.check_in(force=True)
        self.warm_up()
        try:
            while not self._stop.is_set():
                try:
                    self.check_in()
                    self.housekeeping()
                    if not self.run_one():
                        self._stop.wait(POLL_S)
                except Exception:  # noqa: BLE001 -- e.g. DB briefly unavailable: back off, keep going
                    log.exception("worker loop error; backing off")
                    self._stop.wait(5)
        finally:
            self.discard_warm()
            self.check_out()
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
_embedded_thread: threading.Thread | None = None


def start_embedded() -> Worker:
    global _embedded, _embedded_thread
    if _embedded is None:
        _embedded = Worker(mode="embedded")
        _embedded_thread = threading.Thread(target=_embedded.run_forever, name="truebind-worker", daemon=True)
        _embedded_thread.start()
    return _embedded


def stop_embedded(timeout_s: float = 10.0) -> None:
    global _embedded, _embedded_thread
    if _embedded is not None:
        _embedded.stop()
        if _embedded_thread is not None:
            _embedded_thread.join(timeout_s)
    _embedded, _embedded_thread = None, None


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    w = Worker()
    signal.signal(signal.SIGTERM, lambda *_: w.stop())
    signal.signal(signal.SIGINT, lambda *_: w.stop())
    w.run_forever()


if __name__ == "__main__":
    main()
