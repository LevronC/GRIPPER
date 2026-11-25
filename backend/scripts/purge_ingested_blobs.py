"""
Delete source PDFs left in Vercel Blob after successful ingestion (owner connection).

    MIGRATION_DATABASE_URL=... BLOB_READ_WRITE_TOKEN=... python scripts/purge_ingested_blobs.py          # dry run
    MIGRATION_DATABASE_URL=... BLOB_READ_WRITE_TOKEN=... python scripts/purge_ingested_blobs.py --apply

Until the delete call was fixed, every ingested PDF stayed in the (public) Blob store,
and the pipeline had already cleared research_reports.file_path, so the database no
longer points at them. This lists the store and matches each file to its report by the
report-id prefix of its name (uploads are named "<report_id>.pdf").

Deletes:  files whose report is processed or duplicate (ingestion is finished).
Keeps:    failed / pending / processing reports (retry needs the file); files with no
          matching report unless --include-orphans; anything not named like an upload.
Output shows short report ids and sizes only, never blob URLs.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request

from _cli import owner_engine
from sqlalchemy import text

from app.core.blob import _BLOB_API, _BLOB_API_VERSION

_UPLOAD_NAME = re.compile(r"^([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})[-.]", re.I)
_FINISHED = ("processed", "duplicate")


def _request(token: str, path: str, *, method: str = "GET", body: dict | None = None) -> dict:
    req = urllib.request.Request(
        f"{_BLOB_API}{path}",
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={"Authorization": f"Bearer {token}", "x-api-version": _BLOB_API_VERSION,
                 **({"Content-Type": "application/json"} if body is not None else {})},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
    return json.loads(raw) if raw else {}


def _list_blobs(token: str) -> list[dict]:
    blobs, cursor = [], None
    while True:
        params = {"limit": "1000", **({"cursor": cursor} if cursor else {})}
        page = _request(token, "?" + urllib.parse.urlencode(params))
        blobs.extend(page.get("blobs", []))
        cursor = page.get("cursor")
        if not page.get("hasMore") or not cursor:
            return blobs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="delete; default is a dry run")
    ap.add_argument("--include-orphans", action="store_true", help="also delete upload files with no report row")
    args = ap.parse_args()
    token = os.environ.get("BLOB_READ_WRITE_TOKEN")
    if not token:
        sys.exit("BLOB_READ_WRITE_TOKEN is required.")

    blobs = _list_blobs(token)
    ids = {m.group(1).lower() for b in blobs if (m := _UPLOAD_NAME.match(b.get("pathname", "")))}
    with owner_engine().connect() as conn:
        statuses = dict(conn.execute(
            text("SELECT id::text, status FROM research_reports WHERE id::text = ANY(:ids)"), {"ids": list(ids)}
        ).all()) if ids else {}

    to_delete, rows = [], []
    for b in blobs:
        m = _UPLOAD_NAME.match(b.get("pathname", ""))
        if not m:
            rows.append(("-", "not an upload", "keep", b.get("size", 0)))
            continue
        rid = m.group(1).lower()
        status = statuses.get(rid)
        delete = status in _FINISHED or (status is None and args.include_orphans)
        reason = status or "no report row"
        rows.append((rid[:8], reason, "DELETE" if delete else "keep", b.get("size", 0)))
        if delete:
            to_delete.append(b["url"])

    for rid, reason, action, size in rows:
        print(f"  {rid:<8}  {reason:<14}  {action:<6}  {size / 1024:7.1f} KiB")
    print(f"{len(blobs)} files in the store; {len(to_delete)} to delete.")
    if not args.apply:
        print("Dry run: nothing deleted. Re-run with --apply to delete.")
        return 0

    for start in range(0, len(to_delete), 100):
        _request(token, "/delete", method="POST", body={"urls": to_delete[start:start + 100]})
    remaining = {b["url"] for b in _list_blobs(token)} & set(to_delete)
    print(f"Deleted {len(to_delete) - len(remaining)} of {len(to_delete)}; {len(remaining)} still present.")
    return 1 if remaining else 0


if __name__ == "__main__":
    raise SystemExit(main())
