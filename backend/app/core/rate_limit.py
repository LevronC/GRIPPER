"""
Fixed-window rate limiting.

Uses Redis (INCR + EXPIRE) when available so limits hold across processes. Without
Redis it falls back to a per-process in-memory counter; on serverless platforms that
limit is per warm instance only, so it slows but does not reliably cap an attacker.
Token endpoints do not depend on rate limiting for safety: tokens carry 256 bits of
entropy. Limits exist to curb credential stuffing and email flooding.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional

from fastapi import HTTPException, Request

from app.core.redis_client import get_redis_client

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_memory: dict[str, tuple[int, float]] = {}


def _hit_memory(key: str, window: int) -> int:
    now = time.monotonic()
    with _lock:
        count, reset_at = _memory.get(key, (0, now + window))
        if now >= reset_at:
            count, reset_at = 0, now + window
        count += 1
        _memory[key] = (count, reset_at)
        return count


def _hit(key: str, window: int) -> int:
    client = get_redis_client()
    if client is not None:
        try:
            pipe = client.pipeline()
            pipe.incr(key)
            pipe.expire(key, window, nx=True)
            return int(pipe.execute()[0])
        except Exception as exc:  # Redis hiccup: degrade to local counting
            logger.warning("Rate limiter falling back to memory (%s)", type(exc).__name__)
    return _hit_memory(key, window)


def client_ip(request: Optional[Request]) -> str:
    if request is None:
        return "unknown"
    # Vercel sets x-forwarded-for; first hop is the client. Not trusted for auth, only for throttling.
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()[:64]
    return request.client.host if request.client else "unknown"


def enforce(bucket: str, identity: str, limit: int, window_seconds: int) -> None:
    key = f"ratelimit:{bucket}:{identity.lower()}"
    if _hit(key, window_seconds) > limit:
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please wait and try again.",
            headers={"Retry-After": str(window_seconds)},
        )


def reset_memory_limits() -> None:  # tests only
    with _lock:
        _memory.clear()
