from __future__ import annotations

import logging
from typing import Optional

from redis import Redis
from redis.exceptions import RedisError

from app.core.config import normalize_redis_url

logger = logging.getLogger(__name__)

_redis_client: Optional[Redis] = None
_redis_checked = False


def get_redis_client() -> Optional[Redis]:
    """
    Returns a Redis client if one can be established, otherwise returns None.

    Failures are non-fatal: on Vercel, Redis is optional — document ingestion
    falls back to the Vercel Cron job when Redis is unavailable.

    Uses a 3-second socket timeout so a misconfigured or unreachable Redis URL
    fails fast rather than blocking a serverless function invocation.
    """
    global _redis_client, _redis_checked
    if _redis_checked:
        return _redis_client

    _redis_checked = True
    try:
        from app.core.config import settings

        client = Redis.from_url(
            normalize_redis_url(settings.REDIS_URL),
            socket_connect_timeout=3,
            socket_timeout=3,
        )
        client.ping()
        _redis_client = client
        logger.info("Redis connection established")
    except RedisError as exc:
        logger.warning("Redis unavailable (%s) — background jobs will use cron fallback", exc)
        _redis_client = None
    except Exception as exc:
        logger.warning("Redis connection failed (%s) — background jobs will use cron fallback", exc)
        _redis_client = None

    return _redis_client
