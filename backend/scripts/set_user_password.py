"""
Set an existing user's password without email (owner connection). Operator action.

    MIGRATION_DATABASE_URL=... python scripts/set_user_password.py --email person@example.edu

For when email delivery is not configured, so the self-service reset cannot send a
link. The password is read from NEW_PASSWORD or prompted for (twice); it is never
printed. The account is marked verified, and token_version is incremented, so every
existing session for that user ends. The user's role and institution are unchanged.

Exit codes: 0 password set; 1 invalid input; 2 cannot connect; 3 no user with that email.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys

from _cli import owner_engine
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.core.security import get_password_hash, validate_password_policy


def _read_password() -> str:
    password = os.environ.get("NEW_PASSWORD")
    if password is None:
        password = getpass.getpass("New password (min 12 characters, hidden): ")
        if getpass.getpass("Repeat new password: ") != password:
            sys.exit("Passwords do not match; nothing changed.")
    try:
        return validate_password_policy(password)
    except ValueError as exc:
        sys.exit(f"{exc} Nothing changed.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", required=True)
    email = ap.parse_args().email.strip().lower()

    try:
        return _set(email)
    except OperationalError as exc:
        first = str(exc.orig).strip().splitlines()[0] if exc.orig else type(exc).__name__
        print(f"Cannot connect to the database: {first[:200]}. Nothing changed.", file=sys.stderr)
        return 2


def _set(email: str) -> int:
    with owner_engine().begin() as conn:
        row = conn.execute(
            text(
                "SELECT u.id, u.role, i.name FROM users u JOIN institutions i ON i.id = u.institution_id "
                "WHERE lower(u.email) = :e"
            ),
            {"e": email},
        ).first()
        if row is None:
            count = conn.execute(text("SELECT count(*) FROM users")).scalar_one()
            print(f"No user with email {email} ({count} users exist). Nothing changed.", file=sys.stderr)
            print("Create a new institution and admin with scripts/provision_institution.py.", file=sys.stderr)
            return 3
        password = _read_password()
        conn.execute(
            text(
                "UPDATE users SET hashed_password = :h, is_verified = true, "
                "token_version = token_version + 1 WHERE id = :u"
            ),
            {"h": get_password_hash(password), "u": row.id},
        )
    print(f"Password set for {email} (role {row.role}, institution {row.name!r}); existing sessions ended.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
