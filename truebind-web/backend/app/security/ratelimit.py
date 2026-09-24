"""Fixed-window in-memory rate limiter.

Scope and limits (documented in AI/ENGINEERING/BACKEND_SECURITY.md): this is
per API process. Behind several API replicas the effective limit multiplies
by the replica count; a shared store (Redis/Postgres) is required before
horizontal scaling. Failed-login lockout is ALSO enforced in the database
(users.failed_logins / locked_until), which is replica-safe."""

from __future__ import annotations

import threading
import time
from collections import defaultdict

from fastapi import HTTPException, Request


class RateLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._hits: dict[tuple[str, str], list[float]] = defaultdict(list)

    def check(self, bucket: str, key: str, limit: int, window_s: float) -> None:
        now = time.monotonic()
        with self._lock:
            hits = self._hits[(bucket, key)]
            cutoff = now - window_s
            while hits and hits[0] < cutoff:
                hits.pop(0)
            if len(hits) >= limit:
                retry = int(window_s - (now - hits[0])) + 1
                raise HTTPException(status_code=429, detail="Too many requests. Please wait and try again.",
                                    headers={"Retry-After": str(retry)})
            hits.append(now)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"
