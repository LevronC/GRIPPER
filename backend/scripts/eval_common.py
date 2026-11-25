"""Shared guards for evaluation scripts. They only touch local databases whose names start with gripper_eval or gripper_bench."""

from __future__ import annotations

import os
import re
import subprocess
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from app.core.database_url import normalize_database_url  # noqa: E402

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "host.docker.internal"}
ALLOWED_PREFIXES = ("gripper_eval", "gripper_bench")
_DB_NAME = re.compile(r"^[a-z][a-z0-9_]{0,62}$")


def require_local_database(url: str, label: str) -> str:
    normalized = normalize_database_url(url)
    parsed = make_url(normalized)
    host = parsed.host or ""
    name = parsed.database or ""
    if host not in LOCAL_HOSTS:
        sys.exit(f"Refusing {label}: host {host!r} is not local.")
    if not _DB_NAME.match(name) or not name.startswith(ALLOWED_PREFIXES):
        sys.exit(
            f"Refusing {label}: database {name!r} must start with "
            + " or ".join(ALLOWED_PREFIXES)
            + "."
        )
    return normalized


def ensure_database(admin_url: str, replace: bool) -> str:
    """Create the target database if needed. Drop it first only when `replace` is set and the name is allowed."""
    admin_url = require_local_database(admin_url, "MIGRATION_DATABASE_URL")
    parsed = make_url(admin_url)
    name = parsed.database
    maintenance = parsed.set(database="postgres")
    engine = create_engine(maintenance, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        exists = conn.execute(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": name}).first()
        if exists and replace:
            conn.execute(text("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = :n AND pid <> pg_backend_pid()"), {"n": name})
            conn.execute(text(f'DROP DATABASE "{name}"'))
            exists = None
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{name}"'))
    engine.dispose()
    owner = create_engine(admin_url)
    with owner.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    owner.dispose()
    return admin_url


def upgrade(admin_url: str) -> None:
    env = os.environ.copy()
    env["MIGRATION_DATABASE_URL"] = admin_url
    backend = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    subprocess.check_call([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=backend, env=env)


def git_revision() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
