"""Minimal in-memory rate limiter for the login endpoint.

Fixed-window per client IP. This guards a single instance; for a horizontally
scaled deployment move the counter to Redis (shared, atomic INCR + EXPIRE) so the
limit holds across replicas — see Arquitectura/Justificación.md.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

from app.config import get_settings

settings = get_settings()

_lock = threading.Lock()
_hits: dict[str, deque[float]] = defaultdict(deque)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit_login(request: Request) -> None:
    """FastAPI dependency: raise 429 once the per-IP attempt budget is exceeded."""
    limit = settings.login_rate_limit
    window = settings.login_rate_window_seconds
    key = _client_ip(request)
    now = time.monotonic()

    with _lock:
        bucket = _hits[key]
        while bucket and now - bucket[0] > window:
            bucket.popleft()
        if len(bucket) >= limit:
            retry_after = int(window - (now - bucket[0])) + 1
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many login attempts. Try again later.",
                headers={"Retry-After": str(retry_after)},
            )
        bucket.append(now)
