"""
Redis Queue (RQ) task for asynchronous document ingestion.

Requires a long-running worker (`python app/workers/worker.py`) connected to the same
Redis. Vercel cannot host one; see docs/DEPLOYMENT_NOTES.md and INGESTION_MODE.
"""

import logging
import uuid

from app.db.session import SessionLocal, set_tenant
from app.services.ingestion.pipeline import ingest_document

logger = logging.getLogger(__name__)


def process_document_ingestion(report_id_str: str, file_path: str, institution_id_str: str) -> int:
    """
    RQ background task. The tenant comes from the job arguments, which the API sets
    from the uploading user's institution; RLS then confines every read and write.
    Raises on failure so RQ marks the job failed (the report is marked failed too).
    """
    report_id = uuid.UUID(report_id_str)
    institution_id = uuid.UUID(institution_id_str)
    db = SessionLocal()
    try:
        set_tenant(db, institution_id)
        count = ingest_document(db, report_id, file_path, institution_id)
        logger.info("Worker: ingested report %s (%d chunks)", report_id_str, count)
        return count
    finally:
        db.close()
