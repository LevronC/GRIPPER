"""
Create (or update) the restricted login role the API uses at runtime.

Run AFTER `alembic upgrade head` (which creates the `gripper_runtime` group role),
using the owner/migration connection:

    MIGRATION_DATABASE_URL=postgresql://postgres:...@host/db \
    APP_DB_USER=gripper_app APP_DB_PASSWORD=... \
    python scripts/create_app_role.py

The login role is created NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE and is
granted membership in `gripper_runtime`, which carries all runtime privileges.
Idempotent: re-running changes only the password, then verifies the role has none of
SUPERUSER, BYPASSRLS, CREATEDB or CREATEROLE (PostgreSQL 16+ forbids a non-superuser,
such as Supabase's `postgres`, from naming those attributes in ALTER ROLE). Errors never
print SQL, because the statement contains the password.
"""

from __future__ import annotations

import os
import re
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

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
    try:
        with engine.begin() as conn:
            if not conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = 'gripper_runtime'")).first():
                print("gripper_runtime role missing — run `alembic upgrade head` first.", file=sys.stderr)
                return 1
            exists = conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :u"), {"u": user}).first()
            # Identifiers cannot be bound parameters; `user` is validated above. The
            # password is passed through format('%L') so PostgreSQL quotes it.
            literal = conn.execute(text("SELECT format('%L', CAST(:p AS text))"), {"p": password}).scalar()
            if exists:
                # PostgreSQL 16+ rejects SUPERUSER/BYPASSRLS keywords (even NO...) in ALTER ROLE
                # from a non-superuser such as Supabase's `postgres`. Change only the password;
                # the attributes are verified below instead of re-asserted.
                conn.execute(text(f"ALTER ROLE {user} WITH LOGIN PASSWORD {literal}"))
            else:
                conn.execute(text(
                    f"CREATE ROLE {user} LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE PASSWORD {literal}"
                ))
            conn.execute(text(f"GRANT gripper_runtime TO {user}"))
            unsafe = conn.execute(text(
                "SELECT rolsuper OR rolbypassrls OR rolcreatedb OR rolcreaterole FROM pg_roles WHERE rolname = :u"
            ), {"u": user}).scalar()
            if unsafe:
                raise RuntimeError(f"role {user} has SUPERUSER, BYPASSRLS, CREATEDB or CREATEROLE; refusing")
    except (DBAPIError, RuntimeError) as exc:
        # Never print the SQL: it contains the password literal.
        detail = str(getattr(exc, "orig", exc)).strip().splitlines()
        print(f"{type(getattr(exc, 'orig', exc)).__name__}: {' '.join(detail)[:300]}", file=sys.stderr)
        return 1
    print(f"{'updated password for' if exists else 'created'} role {user} as member of gripper_runtime")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
