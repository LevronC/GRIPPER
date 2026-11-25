"""
Retention policy for uploads whose ingestion failed.

Source files are kept after a failure so the document can be retried
(POST /documents/{id}/retry). This script deletes the source file of failed reports
older than --days (default 7) and clears their file_path. Successful ingestions delete
their source immediately; duplicates are deleted once detected.

    MIGRATION_DATABASE_URL=... python scripts/cleanup_failed_uploads.py            # dry run
    MIGRATION_DATABASE_URL=... python scripts/cleanup_failed_uploads.py --apply
"""

from __future__ import annotations

import argparse

from _cli import owner_engine
from sqlalchemy import text

from app.core.blob import delete_blob


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    eng = owner_engine()
    with eng.begin() as conn:
        rows = conn.execute(text(
            "SELECT id, file_path FROM research_reports WHERE status = 'failed' AND file_path IS NOT NULL "
            "AND created_at < TIMEZONE('utc', NOW()) - make_interval(days => :d)"
        ), {"d": args.days}).all()
        print(f"{len(rows)} failed upload(s) older than {args.days} days")
        if not args.apply:
            print("Dry run. Re-run with --apply to delete their source files.")
            return 0
        for row in rows:
            delete_blob(row.file_path)
            conn.execute(text(
                "UPDATE research_reports SET file_path = NULL, "
                "error_message = left(coalesce(error_message, '') || ' Source deleted by retention policy.', 500) "
                "WHERE id = :id"
            ), {"id": row.id})
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
