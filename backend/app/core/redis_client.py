from __future__ import annotations

from typing import Optional

from redis import Redis

from app.core.config import normalize_redis_url

_redis_client: Optional[Redis] = None
_redis_checked = False


def get_redis_client() -> Optional[Redis]:
    global _redis_client, _redis_checked
    if _redis_checked:
        return _redis_client

    _redis_checked = True
    try:
        from app.core.config import settings

        client = Redis.from_url(normalize_redis_url(settings.REDIS_URL))
        client.ping()
        _redis_client = client
    except Exception:
        _redis_client = None
    return _redis_client
