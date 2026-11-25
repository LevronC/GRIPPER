"""
Schema migrations.

Migrations are a deploy step (`alembic upgrade head` with MIGRATION_DATABASE_URL).
They run in-process only when AUTO_MIGRATE=true, and then with the owner connection
(never the runtime connection) under a PostgreSQL advisory lock so concurrent
serverless cold starts cannot run Alembic simultaneously.
"""

from __future__ import annotations

import logging
import os
import threading

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from app.core.config import settings
from app.core.database_url import normalize_database_url

logger = logging.getLogger(__name__)

_migration_lock = threading.Lock()
_database_ready = False
# Arbitrary constant identifying Gripper's migration lock.
_ADVISORY_LOCK_KEY = 7_734_221_001


def _backend_dir() -> str:
    # backend/app/db/migrate.py -> backend/
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))


def _normalize_db_url(url: str) -> str:
    return normalize_database_url(url)


def run_migrations() -> None:
    if not settings.MIGRATION_DATABASE_URL:
        raise RuntimeError("MIGRATION_DATABASE_URL is required to run migrations.")
    db_url = _normalize_db_url(settings.MIGRATION_DATABASE_URL)
    backend_dir = _backend_dir()

    from app.db.session import _engine_kwargs

    engine = create_engine(db_url, **_engine_kwargs(db_url))
    try:
        with engine.connect() as lock_conn:
            lock_conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": _ADVISORY_LOCK_KEY})
            try:
                with engine.begin() as conn:
                    conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                cfg = Config(os.path.join(backend_dir, "alembic.ini"))
                cfg.set_main_option("script_location", os.path.join(backend_dir, "migrations"))
                # ConfigParser treats % as interpolation; URL-encoded passwords need doubling.
                cfg.set_main_option("sqlalchemy.url", db_url.replace("%", "%%"))
                command.upgrade(cfg, "head")
                logger.info("Alembic migrations completed successfully")
            finally:
                lock_conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _ADVISORY_LOCK_KEY})
    finally:
        engine.dispose()


def ensure_database_ready() -> None:
    """Run migrations once per process when AUTO_MIGRATE is enabled; otherwise no-op."""
    global _database_ready
    if _database_ready:
        return
    if not settings.AUTO_MIGRATE or os.getenv("SKIP_DB_BOOTSTRAP", "").lower() in ("1", "true", "yes"):
        _database_ready = True
        return

    with _migration_lock:
        if _database_ready:
            return
        run_migrations()
        _database_ready = True
