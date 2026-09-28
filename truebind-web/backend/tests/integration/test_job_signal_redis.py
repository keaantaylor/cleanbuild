"""P1.7 -- job wake-ups over the compose Redis (TRUEBIND_IT=1).

A wake-up is sent only when the enqueuing transaction commits (never for a
rolled-back enqueue), and a waiting worker returns as soon as it arrives.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator

import pytest
import redis
from app.database import get_session_factory
from app.services import job_signal
from integration_env import IT, service_url

pytestmark = pytest.mark.skipif(not IT, reason="integration: needs docker-compose.test.yml (TRUEBIND_IT=1)")


@pytest.fixture
def wired(monkeypatch: pytest.MonkeyPatch) -> Iterator[redis.Redis[bytes]]:
    url = service_url("REDIS") + "/3"
    monkeypatch.setattr(job_signal, "REDIS_URL", url)
    monkeypatch.setattr(job_signal, "_client", None)
    r = redis.Redis.from_url(url)
    r.delete(job_signal.WAKE_KEY)
    yield r
    r.delete(job_signal.WAKE_KEY)
    job_signal.reset()


def test_wake_is_sent_on_commit_only(wired: redis.Redis[bytes]) -> None:
    db = get_session_factory()()
    try:
        job_signal.notify(db)
        assert wired.llen(job_signal.WAKE_KEY) == 0, "nothing before the commit"
        db.rollback()
        assert wired.llen(job_signal.WAKE_KEY) == 0, "nothing for a rolled-back transaction"
        job_signal.notify(db)
        db.commit()
        assert wired.llen(job_signal.WAKE_KEY) == 1
    finally:
        db.close()


def test_waiting_worker_wakes_immediately(wired: redis.Redis[bytes]) -> None:
    woke: list[float] = []

    def waiter() -> None:
        t0 = time.monotonic()
        if job_signal.wait(10.0):
            woke.append(time.monotonic() - t0)

    t = threading.Thread(target=waiter)
    t.start()
    time.sleep(0.3)
    db = get_session_factory()()
    try:
        job_signal.notify(db)
        db.commit()
    finally:
        db.close()
    t.join(5)
    assert woke and woke[0] < 2.0, woke


def test_wait_times_out_quietly(wired: redis.Redis[bytes]) -> None:
    t0 = time.monotonic()
    assert job_signal.wait(1.0) is False
    assert 0.9 <= time.monotonic() - t0 < 3.0


def test_wake_backlog_is_bounded(wired: redis.Redis[bytes]) -> None:
    db = get_session_factory()()
    try:
        for _ in range(job_signal.MAX_BACKLOG + 50):
            job_signal.notify(db)
            db.commit()
    finally:
        db.close()
    assert wired.llen(job_signal.WAKE_KEY) == job_signal.MAX_BACKLOG
