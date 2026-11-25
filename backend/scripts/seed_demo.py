"""
Create SYNTHETIC demonstration data for local development.

    ENVIRONMENT=development MIGRATION_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/gripper \
        DEMO_PASSWORD='choose-a-local-password' python scripts/seed_demo.py

* Refuses to run when ENVIRONMENT=production, on Vercel, or against a non-local
  database host (override the host check with --allow-remote-db; production is never allowed).
* Everything lives in one synthetic institution (slug `synthetic-demo`); no real
  institution, person or fund is referenced. Re-running is idempotent.
* Demo passwords come from DEMO_PASSWORD; if unset, a random one is generated and
  printed once to this terminal. Nothing is created with a publicly known password.
"""

from __future__ import annotations

import argparse
import os
import secrets
import uuid

from _cli import owner_engine, refuse_unless_local_development
from sqlalchemy import text

from app.core.security import get_password_hash, validate_password_policy

DEMO_SLUG = "synthetic-demo"
DEMO_NAME = "Synthetic Demo Fund (not a real institution)"
DEMO_USERS = (
    ("demo-admin@synthetic-demo.example", "admin"),
    ("demo-pm@synthetic-demo.example", "pm"),
    ("demo-analyst@synthetic-demo.example", "analyst"),
)


def seed(conn, password_hash: str) -> uuid.UUID:
    inst_id = conn.execute(text("SELECT id FROM institutions WHERE slug = :s"), {"s": DEMO_SLUG}).scalar()
    if inst_id is None:
        inst_id = uuid.uuid4()
        conn.execute(
            text("INSERT INTO institutions (id, name, slug, tier, created_at) VALUES (:i, :n, :s, 'free', now())"),
            {"i": inst_id, "n": DEMO_NAME, "s": DEMO_SLUG},
        )
    for email, role in DEMO_USERS:
        conn.execute(
            text(
                "INSERT INTO users (id, institution_id, email, hashed_password, role, is_verified, token_version, created_at) "
                "VALUES (:u, :i, :e, :h, :r, true, 0, now()) "
                "ON CONFLICT (email) DO UPDATE SET hashed_password = EXCLUDED.hashed_password, "
                "token_version = users.token_version + 1"
            ),
            {"u": uuid.uuid4(), "i": inst_id, "e": email, "h": password_hash, "r": role},
        )
    return inst_id


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--allow-remote-db", action="store_true")
    args = ap.parse_args()
    refuse_unless_local_development(allow_remote=args.allow_remote_db)

    password = os.environ.get("DEMO_PASSWORD")
    generated = password is None
    if generated:
        password = secrets.token_urlsafe(12)
    validate_password_policy(password)

    with owner_engine().begin() as conn:
        inst_id = seed(conn, get_password_hash(password))

    print(f"Seeded synthetic institution {DEMO_SLUG} ({inst_id}). Accounts:")
    for email, role in DEMO_USERS:
        print(f"  {role:8s} {email}")
    if generated:
        print(f"Generated password (shown once, all demo accounts): {password}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
