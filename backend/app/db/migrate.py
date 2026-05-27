from __future__ import annotations

import logging
import os

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from app.core.config import settings
from app.db.session import _engine_kwargs

logger = logging.getLogger(__name__)


def run_migrations() -> None:
    db_url = settings.SUPERUSER_DATABASE_URL or settings.DATABASE_URL
    backend_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))

    try:
        engine = create_engine(db_url, **_engine_kwargs(db_url))
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    except Exception as exc:
        logger.warning("Could not ensure pgvector extension (%s)", exc)

    cfg = Config(os.path.join(backend_dir, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(backend_dir, "migrations"))
    cfg.set_main_option("sqlalchemy.url", db_url)

    logger.info("Running Alembic migrations against production database")
    command.upgrade(cfg, "head")
