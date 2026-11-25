"""
Provision a new institution and its first administrator (owner connection).

    MIGRATION_DATABASE_URL=... python scripts/provision_institution.py \
        --name "Example University SMIF" --slug example-smif --admin-email admin@example.edu

The admin password is read from ADMIN_PASSWORD or prompted for; it is never printed.
This is an operator action; the API intentionally has no endpoint to create tenants.
"""

from __future__ import annotations

import argparse
import getpass
import os
import re
import sys
import uuid

from _cli import owner_engine
from sqlalchemy import text

from app.core.security import get_password_hash, validate_password_policy


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--slug", required=True)
    ap.add_argument("--admin-email", required=True)
    args = ap.parse_args()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,62}", args.slug):
        sys.exit("slug must be lowercase letters, digits and hyphens")
    password = os.environ.get("ADMIN_PASSWORD") or getpass.getpass("Admin password: ")
    validate_password_policy(password)

    inst_id, user_id = uuid.uuid4(), uuid.uuid4()
    with owner_engine().begin() as conn:
        if conn.execute(text("SELECT 1 FROM institutions WHERE slug = :s"), {"s": args.slug}).first():
            sys.exit(f"institution with slug {args.slug!r} already exists")
        conn.execute(
            text("INSERT INTO institutions (id, name, slug, tier, created_at) VALUES (:i, :n, :s, 'free', now())"),
            {"i": inst_id, "n": args.name, "s": args.slug},
        )
        conn.execute(
            text(
                "INSERT INTO users (id, institution_id, email, hashed_password, role, is_verified, token_version, created_at) "
                "VALUES (:u, :i, :e, :h, 'admin', true, 0, now())"
            ),
            {"u": user_id, "i": inst_id, "e": args.admin_email.lower(), "h": get_password_hash(password)},
        )
    print(f"Provisioned institution {args.slug} ({inst_id}) with admin {args.admin_email.lower()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
