import os
from pydantic_settings import BaseSettings

def normalize_redis_url(url: str) -> str:
    normalized = (url or "").strip()
    if not normalized:
        return "redis://localhost:6379/0"
    if normalized.startswith(("redis://", "rediss://", "unix://")):
        return normalized
    if "://" not in normalized:
        return f"redis://{normalized}"
    return normalized

class Settings(BaseSettings):
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://gripper_app:gripper_secure@localhost:5432/gripper")
    SUPERUSER_DATABASE_URL: str = os.getenv(
        "SUPERUSER_DATABASE_URL",
        os.getenv("DATABASE_URL", "postgresql://gripper_app:gripper_secure@localhost:5432/gripper")
        if "supabase.co" in os.getenv("DATABASE_URL", "")
        else os.getenv(
            "DATABASE_URL",
            "postgresql://gripper_app:gripper_secure@localhost:5432/gripper",
        ).replace("gripper_app:gripper_secure", "civicpulse:civicpulse"),
    )
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "")
    EMBEDDING_MODEL_NAME: str = "BAAI/bge-small-en-v1.5"
    SECRET_KEY: str = os.getenv("SECRET_KEY", "gripper_super_secret_signing_key_2026")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    SEED_DEMO_USER: bool = os.getenv("SEED_DEMO_USER", "true").lower() in ("1", "true", "yes")
    ALLOW_HEADER_AUTH: bool = os.getenv("ALLOW_HEADER_AUTH", "").lower() in ("1", "true", "yes")

    class Config:
        env_file = ".env"

settings = Settings()
settings.REDIS_URL = normalize_redis_url(settings.REDIS_URL)

# Calculate default upload dir if not set in environment
if not settings.UPLOAD_DIR:
    if os.getenv("VERCEL") == "1":
        settings.UPLOAD_DIR = "/tmp/gripper_uploads"
    else:
        backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
        settings.UPLOAD_DIR = os.path.join(backend_dir, "storage", "uploads")

# Ensure the upload directory exists
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
