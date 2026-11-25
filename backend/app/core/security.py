from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Union

import bcrypt
import jwt

from app.core.config import settings
from app.core.redis_client import get_redis_client

# bcrypt only uses the first 72 bytes of input and bcrypt>=5 raises beyond that.
PASSWORD_MIN_LENGTH = 12
PASSWORD_MAX_BYTES = 72


def validate_password_policy(password: str) -> str:
    if len(password) < PASSWORD_MIN_LENGTH:
        raise ValueError(f"Password must be at least {PASSWORD_MIN_LENGTH} characters.")
    if len(password.encode("utf-8")) > PASSWORD_MAX_BYTES:
        raise ValueError(f"Password must be at most {PASSWORD_MAX_BYTES} bytes.")
    return password


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


# Used to equalise login timing when the email is unknown.
DUMMY_PASSWORD_HASH = get_password_hash("unused-dummy-password-for-timing")


def create_access_token(
    subject: Union[str, Any], token_version: int = 0, expires_delta: Optional[timedelta] = None
) -> str:
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode = {
        "exp": expire,
        "sub": str(subject),
        "jti": str(uuid.uuid4()),  # supports server-side revocation (logout)
        "ver": int(token_version),  # invalidated by password reset
        "typ": "access",
    }
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def blacklist_token(token_jti: str, expire_seconds: int) -> bool:
    """Store a revoked token id in Redis. Returns False if Redis is unavailable."""
    redis_client = get_redis_client()
    if not redis_client:
        return False
    redis_client.setex(f"token_blacklist:{token_jti}", expire_seconds, "1")
    return True


def is_token_blacklisted(token_jti: str) -> bool:
    redis_client = get_redis_client()
    if not redis_client:
        return False
    return redis_client.exists(f"token_blacklist:{token_jti}") > 0
