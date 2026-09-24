"""Durable processing jobs. The HTTP API only enqueues; a separate worker
process (app/worker.py) claims jobs with a time-limited lease, heartbeats
while working, and records a terminal state. A job whose lease expires
(worker crashed or was killed) is re-queued or failed by the reaper -- no
job can stay RUNNING forever. See AI/ARCHITECTURE/TRUEBIND_JOB_SYSTEM.md."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ._util import created_at_col, uuid_pk

JOB_KINDS = ("INGEST", "PROCESS")
JOB_STATUSES = ("QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED")
TERMINAL_JOB_STATUSES = ("SUCCEEDED", "FAILED", "CANCELLED")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = uuid_pk()
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default="QUEUED", index=True)
    stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=2)
    run_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_owner: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = created_at_col()
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)  # customer-safe
    error_detail: Mapped[str | None] = mapped_column(String(4000), nullable=True)  # internal only, never returned
    metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # stage timings, rows, peak RSS


class WorkerHeartbeat(Base):
    """One row per worker process, refreshed every few seconds while it is
    alive. Lets the API tell "queued, a worker will pick it up" apart from
    "queued, and nothing is processing jobs" -- the difference between a
    short wait and an upload that would otherwise sit forever. Not tenant
    data (no RLS): it holds no customer information."""
    __tablename__ = "worker_heartbeats"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    hostname: Mapped[str] = mapped_column(String(255))
    pid: Mapped[int] = mapped_column(Integer)
    mode: Mapped[str] = mapped_column(String(16))  # embedded | standalone
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    current_job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
