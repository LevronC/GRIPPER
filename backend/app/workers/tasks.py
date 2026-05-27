"""
Redis Queue (RQ) worker task for asynchronous document ingestion.

On Vercel, there is no persistent worker process, so this function is only
called when Redis + a local RQ worker are both available (local dev / VM).
On Vercel, the same ingestion pipeline is triggered by the Vercel Cron job via
GET /cron/process-documents, which calls ingest_document() directly.

The file_path argument can be:
  - A local filesystem path (e.g. /app/storage/uploads/<uuid>.pdf) — dev
  - A Vercel Blob URL (e.g. https://public.blob.vercel-storage.com/...) — prod

When it is a blob URL, the file is downloaded to /tmp before ingestion and
cleaned up afterwards.
"""

import logging
import os
import uuid

from sqlalchemy import text

from app.db.session import SessionLocal
from app.services.ingestion.pipeline import ingest_document

logger = logging.getLogger(__name__)


def process_document_ingestion(
    report_id_str: str,
    file_path: str,
    institution_id_str: str,
) -> int:
    """
    RQ background task: run the full document ingestion pipeline.

    Returns the number of document chunks produced.
    Raises on failure so RQ marks the job as 'failed'.
    """
    report_id = uuid.UUID(report_id_str)
    institution_id = uuid.UUID(institution_id_str)

    # If the file reference is a Vercel Blob URL, download to /tmp first.
    # The local worker cannot access the Blob URL without the write token, but
    # it is always set in the environment when the token is configured globally.
    tmp_path = None
    if file_path.startswith("https://"):
        from app.core.blob import fetch_blob
        logger.info("Worker: downloading blob for report %s", report_id_str)
        content = fetch_blob(file_path)
        tmp_path = f"/tmp/{report_id_str}.pdf"
        with open(tmp_path, "wb") as fh:
            fh.write(content)
        effective_path = tmp_path
    else:
        effective_path = file_path

    db = SessionLocal()
    try:
        # Use SET LOCAL so the institution context is scoped to this transaction
        # and does not leak to subsequent connections on the same pool slot.
        db.execute(
            text("SET LOCAL app.current_institution_id = :id"),
            {"id": str(institution_id)},
        )
        chunks_count = ingest_document(db, report_id, effective_path, institution_id)
        logger.info("Worker: ingested report %s — %d chunks", report_id_str, chunks_count)
        return chunks_count
    except Exception:
        logger.exception("Worker: ingestion failed for report %s", report_id_str)
        raise
    finally:
        db.close()
        if tmp_path:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
