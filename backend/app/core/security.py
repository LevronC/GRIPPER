from datetime import datetime, timedelta
from typing import Any, Union
import uuid
from jose import jwt
import bcrypt

from app.core.config import settings
from app.core.redis_client import get_redis_client

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except Exception:
        return False

def get_password_hash(password: str) -> str:
    # bcrypt requires bytes
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')

def create_access_token(subject: Union[str, Any], expires_delta: timedelta = None) -> str:
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    # Generate unique JTI for this token to support server-side revocation
    token_jti = str(uuid.uuid4())
    to_encode = {
        "exp": expire, 
        "sub": str(subject),
        "jti": token_jti
    }
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def blacklist_token(token_jti: str, expire_seconds: int):
    """
    Store blacklisted token ID in Redis with expiration.
    """
    redis_client = get_redis_client()
    if not redis_client:
        return
    redis_client.setex(f"token_blacklist:{token_jti}", expire_seconds, "1")

def is_token_blacklisted(token_jti: str) -> bool:
    """
    Check if a token ID exists in the Redis blacklist.
    """
    redis_client = get_redis_client()
    if not redis_client:
        return False
    return redis_client.exists(f"token_blacklist:{token_jti}") > 0
