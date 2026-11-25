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


def _bool_env(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes")


def _default_environment() -> str:
    explicit = os.getenv("ENVIRONMENT", "").strip().lower()
    if explicit:
        return explicit
    # Vercel deployments are production unless explicitly configured otherwise.
    return "production" if os.getenv("VERCEL") == "1" else "development"


class Settings(BaseSettings):
    # development | test | production
    ENVIRONMENT: str = _default_environment()

    # Runtime connection. MUST use a restricted role (NOSUPERUSER, NOBYPASSRLS,
    # not the table owner) that is a member of `gripper_runtime`. See docs/DATABASE_SECURITY.md.
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", "postgresql://gripper_app:gripper_app_dev@localhost:5432/gripper"
    )
    # Owner / DDL connection. Used ONLY by migrations and administrative CLI
    # commands, never by request handlers. SUPERUSER_DATABASE_URL is accepted as a
    # deprecated alias.
    MIGRATION_DATABASE_URL: str = os.getenv(
        "MIGRATION_DATABASE_URL", os.getenv("SUPERUSER_DATABASE_URL", "")
    )
    # Run Alembic on API cold start. Off by default: migrations are a deploy step.
    # Requires MIGRATION_DATABASE_URL.
    AUTO_MIGRATE: bool = _bool_env("AUTO_MIGRATE")
    # enforce: refuse to serve DB-backed requests if the runtime role can bypass RLS.
    # warn: log only (intended for isolated tests that deliberately use a privileged role).
    DB_ROLE_SAFETY: str = os.getenv("DB_ROLE_SAFETY", "enforce").strip().lower()

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

    # Shared secret for the manual ingestion-retry endpoint (/cron/process-documents)
    CRON_SECRET: str = os.getenv("CRON_SECRET", "")

    # Feature flags
    SEED_DEMO_USER: bool = _bool_env("SEED_DEMO_USER", "true")

    # Set to "true" only in local development to print OTP codes to the console.
    # Never enable in production — codes will appear in log aggregators.
    DEBUG_PRINT_CODES: bool = _bool_env("DEBUG_PRINT_CODES")

    # CORS — comma-separated list of allowed origins
    ALLOWED_ORIGINS: str = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173")

    class Config:
        env_file = ".env"
        extra = "ignore"

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"


settings = Settings()
settings.REDIS_URL = normalize_redis_url(settings.REDIS_URL)

# ── SECRET_KEY guard ──────────────────────────────────────────────────────────
# Never allow a blank, short, or well-known default key. Generate one with:
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
if settings.SECRET_KEY in _KNOWN_INSECURE_KEYS or len(settings.SECRET_KEY) < 32:
    raise RuntimeError(
        "SECRET_KEY is not set, shorter than 32 characters, or a known insecure default. "
        "Generate a secure key with:\n"
        "  python -c \"import secrets; print(secrets.token_hex(32))\"\n"
        "Then set it as the SECRET_KEY environment variable."
    )

if settings.DB_ROLE_SAFETY not in ("enforce", "warn"):
    raise RuntimeError("DB_ROLE_SAFETY must be 'enforce' or 'warn'.")
if settings.is_production and settings.DB_ROLE_SAFETY != "enforce":
    raise RuntimeError("DB_ROLE_SAFETY=warn is not permitted when ENVIRONMENT=production.")

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
