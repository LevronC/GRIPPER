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

    # File storage — local path (dev) or Vercel Blob token (production)
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "")
    BLOB_READ_WRITE_TOKEN: str = os.getenv("BLOB_READ_WRITE_TOKEN", "")

    # Embedding model — local model name, or HuggingFace Inference API key for Vercel
    EMBEDDING_MODEL_NAME: str = "BAAI/bge-small-en-v1.5"
    HF_API_KEY: str = os.getenv("HF_API_KEY", "")

    # JWT settings
    SECRET_KEY: str = os.getenv("SECRET_KEY", "")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # Vercel Cron secret — set in Vercel dashboard, used to authenticate cron invocations
    CRON_SECRET: str = os.getenv("CRON_SECRET", "")

    # Feature flags
    SEED_DEMO_USER: bool = os.getenv("SEED_DEMO_USER", "true").lower() in ("1", "true", "yes")
    ALLOW_HEADER_AUTH: bool = os.getenv("ALLOW_HEADER_AUTH", "").lower() in ("1", "true", "yes")

    # Set to "true" only in local development to print OTP codes to the console.
    # Never enable in production — codes will appear in log aggregators.
    DEBUG_PRINT_CODES: bool = os.getenv("DEBUG_PRINT_CODES", "false").lower() in ("1", "true", "yes")

    # CORS — comma-separated list of allowed origins
    ALLOWED_ORIGINS: str = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173")

    class Config:
        env_file = ".env"


settings = Settings()
settings.REDIS_URL = normalize_redis_url(settings.REDIS_URL)

# ── SECRET_KEY guard ──────────────────────────────────────────────────────────
# Never allow a blank or well-known default key. The application must not start
# without a cryptographically secure key. Generate one with:
#   python -c "import secrets; print(secrets.token_hex(32))"
_KNOWN_INSECURE_KEYS = {
    "",
    "gripper_super_secret_signing_key_2026",
    "change-me-in-production",
    "change-me-generate-with-python-c-import-secrets-print-secrets-token-hex-32",
    "secret",
    "dev",
    "test",
}
if settings.SECRET_KEY in _KNOWN_INSECURE_KEYS:
    raise RuntimeError(
        "SECRET_KEY is not set or is using an insecure default. "
        "Generate a secure key with:\n"
        "  python -c \"import secrets; print(secrets.token_hex(32))\"\n"
        "Then set it as the SECRET_KEY environment variable."
    )

# ── Upload directory ──────────────────────────────────────────────────────────
# On Vercel, local disk writes are ephemeral; Vercel Blob is used instead.
# The UPLOAD_DIR is still needed locally and as a temp scratch area on Vercel.
if not settings.UPLOAD_DIR:
    if os.getenv("VERCEL") == "1":
        settings.UPLOAD_DIR = "/tmp/gripper_uploads"
    else:
        backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
        settings.UPLOAD_DIR = os.path.join(backend_dir, "storage", "uploads")

os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
