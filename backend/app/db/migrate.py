from __future__ import annotations

import logging
import os
import threading

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from app.core.config import settings
from app.db.session import _engine_kwargs

logger = logging.getLogger(__name__)

_migration_lock = threading.Lock()
_database_ready = False


def _backend_dir() -> str:
    # backend/app/db/migrate.py -> backend/
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))


def run_migrations() -> None:
    db_url = settings.SUPERUSER_DATABASE_URL or settings.DATABASE_URL
    backend_dir = _backend_dir()

    try:
        engine = create_engine(db_url, **_engine_kwargs(db_url))
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    except Exception as exc:
        logger.warning("Could not ensure pgvector extension (%s)", exc)

    cfg = Config(os.path.join(backend_dir, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(backend_dir, "migrations"))
    cfg.set_main_option("sqlalchemy.url", db_url)

    logger.info("Running Alembic migrations")
    command.upgrade(cfg, "head")


def ensure_database_ready() -> None:
    """Run migrations and seed once per process (Vercel cold start)."""
    global _database_ready
    if _database_ready:
        return

    with _migration_lock:
        if _database_ready:
            return
        try:
            run_migrations()
        except Exception as exc:
            logger.exception("Database migration failed: %s", exc)
            raise

        from app.db.seed import seed_default_data

        seed_default_data()
        _database_ready = True
        logger.info("Database migrations and seed completed")
