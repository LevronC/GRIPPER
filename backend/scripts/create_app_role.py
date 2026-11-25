"""
Create (or update) the restricted login role the API uses at runtime.

Run AFTER `alembic upgrade head` (which creates the `gripper_runtime` group role),
using the owner/migration connection:

    MIGRATION_DATABASE_URL=postgresql://postgres:...@host/db \
    APP_DB_USER=gripper_app APP_DB_PASSWORD=... \
    python scripts/create_app_role.py

The login role is created NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE and is
granted membership in `gripper_runtime`, which carries all runtime privileges.
Idempotent: re-running updates the password and re-asserts the attributes.
"""

from __future__ import annotations

import os
import re
import sys

from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from app.core.database_url import normalize_database_url  # noqa: E402

_IDENT = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def main() -> int:
    url = os.environ.get("MIGRATION_DATABASE_URL") or os.environ.get("SUPERUSER_DATABASE_URL")
    user = os.environ.get("APP_DB_USER", "gripper_app")
    password = os.environ.get("APP_DB_PASSWORD")
    if not url or not password:
        print("MIGRATION_DATABASE_URL and APP_DB_PASSWORD are required.", file=sys.stderr)
        return 2
    if not _IDENT.match(user):
        print("APP_DB_USER must be a simple lowercase identifier.", file=sys.stderr)
        return 2

    engine = create_engine(normalize_database_url(url))
    with engine.begin() as conn:
        if not conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = 'gripper_runtime'")).first():
            print("gripper_runtime role missing — run `alembic upgrade head` first.", file=sys.stderr)
            return 1
        exists = conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :u"), {"u": user}).first()
        verb = "ALTER" if exists else "CREATE"
        # Identifiers cannot be bound parameters; `user` is validated above. The
        # password is passed through format('%L') so PostgreSQL quotes it.
        literal = conn.execute(text("SELECT format('%L', CAST(:p AS text))"), {"p": password}).scalar()
        conn.execute(
            text(
                f"{verb} ROLE {user} LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE "
                f"PASSWORD {literal}"
            )
        )
        conn.execute(text(f"GRANT gripper_runtime TO {user}"))
    print(f"{'updated' if exists else 'created'} role {user} as member of gripper_runtime")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
