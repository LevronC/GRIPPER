"""
Print the privilege report for the role behind DATABASE_URL — the SAME variable the
API uses — and exit non-zero if that role could bypass row-level security.

    DATABASE_URL=... python scripts/check_db_role.py

Read-only: runs catalog queries only. Output contains role and table names; run it
from a trusted shell, not a public CI log.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
os.environ.setdefault("SECRET_KEY", "x" * 32)  # config import guard; not used here
os.environ.setdefault("DB_ROLE_SAFETY", "warn")
os.environ.setdefault("ENVIRONMENT", "development")

from sqlalchemy import create_engine  # noqa: E402

from app.core.database_url import normalize_database_url  # noqa: E402
from app.db.session import database_role_report  # noqa: E402


def main() -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is not set.", file=sys.stderr)
        return 2
    engine = create_engine(normalize_database_url(url))
    with engine.connect() as conn:
        report = database_role_report(conn)
    print(json.dumps(report, indent=2, default=str))
    return 0 if report["rls_enforced"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
