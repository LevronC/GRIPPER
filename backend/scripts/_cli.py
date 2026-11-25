"""Shared helpers for owner-connection CLI scripts."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
# Scripts never sign tokens; this only satisfies the config import guard.
os.environ.setdefault("SECRET_KEY", "cli-placeholder-" + "x" * 32)

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

from app.core.database_url import normalize_database_url  # noqa: E402

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "host.docker.internal", "postgres", "db"}


def owner_engine():
    url = os.environ.get("MIGRATION_DATABASE_URL") or os.environ.get("SUPERUSER_DATABASE_URL")
    if not url:
        sys.exit("MIGRATION_DATABASE_URL (owner connection) is required.")
    return create_engine(normalize_database_url(url))


def refuse_unless_local_development(allow_remote: bool = False) -> None:
    """
    Guard for scripts that create demo data. Refuses when:
      * ENVIRONMENT is production, or running on Vercel;
      * ENVIRONMENT is not development/test;
      * the database host is not local, unless --allow-remote-db was passed
        (still never permitted in production).
    """
    env = os.environ.get("ENVIRONMENT", "development").lower()
    if env == "production" or os.environ.get("VERCEL") == "1":
        sys.exit("Refusing to run: ENVIRONMENT=production (or VERCEL=1). Demo data is never created in production.")
    if env not in ("development", "test"):
        sys.exit(f"Refusing to run: ENVIRONMENT={env!r}; expected development or test.")
    url = os.environ.get("MIGRATION_DATABASE_URL") or os.environ.get("SUPERUSER_DATABASE_URL") or ""
    host = make_url(normalize_database_url(url)).host or ""
    if host not in LOCAL_HOSTS and not allow_remote:
        sys.exit(f"Refusing to run against non-local database host {host!r}. Pass --allow-remote-db to override.")
