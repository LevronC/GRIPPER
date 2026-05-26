from __future__ import annotations

from typing import Optional

from redis import Redis

from app.core.config import settings


def normalize_redis_url(url: str) -> str:
    normalized = (url or "").strip()
    if not normalized:
        return "redis://localhost:6379/0"
    if normalized.startswith(("redis://", "rediss://", "unix://")):
        return normalized
    if "://" not in normalized:
        return f"redis://{normalized}"
    return normalized


_redis_client: Optional[Redis] = None
_redis_checked = False


def get_redis_client() -> Optional[Redis]:
    global _redis_client, _redis_checked
    if _redis_checked:
        return _redis_client

    _redis_checked = True
    try:
        client = Redis.from_url(normalize_redis_url(settings.REDIS_URL))
        client.ping()
        _redis_client = client
    except Exception:
        _redis_client = None
    return _redis_client
