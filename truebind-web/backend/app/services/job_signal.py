"""Job wake-ups over Redis: an optimisation, never a source of truth.

The queue itself lives in PostgreSQL (job_service); a worker always finds
work by claiming from the database. When REDIS_URL is set, enqueueing a job
also pushes a wake-up token once the enqueuing transaction commits, and an
idle worker blocks on BLPOP instead of polling the database, so a job starts
at once and idle workers stop hammering the database. Without Redis (or while
it is unreachable) nothing changes: the worker polls as before.

- notify(db): remember that this session's transaction queued work; the
  token is pushed after COMMIT only (a rolled-back enqueue sends nothing).
- wait(timeout_s): block until a token arrives or the timeout passes;
  returns False at once when Redis is not configured or not reachable.
The token list is trimmed to MAX_BACKLOG so it can never grow unbounded.
"""

from __future__ import annotations

import logging
import time

import redis
from sqlalchemy import event
from sqlalchemy.orm import Session

from ..config import REDIS_URL

log = logging.getLogger("truebind.jobs")

WAKE_KEY = "truebind:jobs:wake"
MAX_BACKLOG = 100
MAX_WAIT_S = 25.0
_PENDING = "truebind_job_wake_pending"
_HOOKED = "truebind_job_wake_hooked"
_RETRY_AFTER_S = 30.0  # after a Redis failure, do not slow every enqueue down retrying it

_client: redis.Redis[bytes] | None = None
_down_until = 0.0


def _redis() -> redis.Redis[bytes] | None:
    global _client
    if not REDIS_URL or time.monotonic() < _down_until:
        return None
    if _client is None:
        _client = redis.Redis.from_url(
            REDIS_URL, socket_connect_timeout=0.5, socket_timeout=MAX_WAIT_S + 5, health_check_interval=30
        )
    return _client


def _mark_down(exc: Exception) -> None:
    global _down_until
    _down_until = time.monotonic() + _RETRY_AFTER_S
    log.warning("job wake-ups unavailable (%s); falling back to polling", type(exc).__name__)


def reset() -> None:
    """Forget the client and any back-off (tests, reconfiguration)."""
    global _client, _down_until
    _client, _down_until = None, 0.0


def notify(db: Session) -> None:
    if not REDIS_URL:
        return
    db.info[_PENDING] = True
    if not db.info.get(_HOOKED):
        event.listen(db, "after_commit", _after_commit)
        event.listen(db, "after_rollback", _after_rollback)
        db.info[_HOOKED] = True


def _after_commit(session: Session) -> None:
    if not session.info.pop(_PENDING, False):
        return
    client = _redis()
    if client is None:
        return
    try:
        pipe = client.pipeline()
        pipe.lpush(WAKE_KEY, "1")
        pipe.ltrim(WAKE_KEY, 0, MAX_BACKLOG - 1)
        pipe.execute()
    except redis.RedisError as exc:
        _mark_down(exc)


def _after_rollback(session: Session) -> None:
    session.info.pop(_PENDING, None)


def wait(timeout_s: float) -> bool:
    """True if a wake-up arrived within timeout_s; False on timeout, or at
    once when Redis is not configured or not reachable."""
    client = _redis()
    if client is None:
        return False
    try:
        got = client.blpop([WAKE_KEY], timeout=min(max(timeout_s, 0.1), MAX_WAIT_S))
    except redis.RedisError as exc:
        _mark_down(exc)
        return False
    return got is not None
