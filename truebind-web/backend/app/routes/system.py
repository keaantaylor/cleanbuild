"""Processing-service status for the signed-in tenant: is any worker alive,
and how much of this tenant's work is queued/running. Lets the UI say
"processing service unavailable" instead of showing "queued" forever."""

from __future__ import annotations

from datetime import timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import EMBEDDED_WORKER, WORKER_STALE_S
from ..database import get_db, set_tenant
from ..models._util import utcnow
from ..models.jobs import Job, WorkerHeartbeat
from ..security.auth import Context, get_context
from ..services import job_service

router = APIRouter(prefix="/api/v1/system", tags=["system"])


@router.get("/status")
def processing_status(ctx: Context = Depends(get_context), db: Session = Depends(get_db)) -> dict:
    set_tenant(db, ctx.tenant_id)
    counts = dict(db.query(Job.status, func.count()).filter(Job.tenant_id == ctx.tenant_id,
                                                            Job.status.in_(("QUEUED", "RUNNING")))
                  .group_by(Job.status).all())
    oldest = (db.query(func.min(Job.created_at)).filter(Job.tenant_id == ctx.tenant_id, Job.status == "QUEUED")
              .scalar())
    workers = job_service.live_workers(db)
    last = db.query(func.max(WorkerHeartbeat.last_seen_at)).scalar()

    def age(dt):
        if dt is None:
            return None
        dt = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        return round((utcnow() - dt).total_seconds(), 1)

    return {
        "workers_alive": len(workers),
        "worker_available": bool(workers),
        "worker_modes": sorted({w.mode for w in workers}),
        "last_worker_check_in_s": age(last),
        "embedded_worker_configured": EMBEDDED_WORKER,
        "stale_after_s": WORKER_STALE_S,
        "queued": int(counts.get("QUEUED", 0)),
        "running": int(counts.get("RUNNING", 0)),
        "oldest_queued_s": age(oldest),
    }
