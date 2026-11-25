"""
Document ingestion lifecycle.

    pending ──► processing ──► processed     (chunks committed; source file deleted)
                    │      └─► duplicate     (same content already processed in this institution)
                    └────────► failed        (error_message set; source file KEPT for retry)

Guarantees
* The uploaded file is deleted only AFTER chunks are durably committed. A failed job
  never destroys its input (the previous implementation deleted the Blob in a
  `finally`, even on failure). Failed uploads are cleaned up by
  scripts/cleanup_failed_uploads.py according to the retention policy.
* Re-running a job replaces the report's chunks in the same transaction, so retries
  never create duplicates, and partial work is never visible as "processed".
* All reads and writes run under the report's institution (RLS + explicit filters).
* If no embedding provider is available, chunks are stored without vectors (still
  full-text searchable) and can be embedded later with scripts/reembed.py.
"""

from __future__ import annotations

import contextlib
import hashlib
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Generator

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import DocumentChunk, ResearchReport
from app.services.embeddings.generator import EmbeddingUnavailable, generate_embeddings
from app.services.ingestion.chunker import chunk_document_pages
from app.services.parsing.parser import parse_pdf

logger = logging.getLogger(__name__)


class IngestionError(Exception):
    """Expected failure with a user-safe message."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@contextlib.contextmanager
def _local_path(file_ref: str) -> Generator[str, None, None]:
    """Yields a local path for `file_ref`, downloading a Blob URL to a temp file. Never deletes the source."""
    if not file_ref.startswith("https://"):
        if not os.path.exists(file_ref):
            raise IngestionError("Source file is no longer available.")
        yield file_ref
        return
    from app.core.blob import fetch_blob

    content = fetch_blob(file_ref)
    tmp = f"/tmp/gripper_ingest_{uuid.uuid4().hex}.pdf"
    with open(tmp, "wb") as fh:
        fh.write(content)
    try:
        yield tmp
    finally:
        with contextlib.suppress(OSError):
            os.remove(tmp)


def _delete_source(file_ref: str) -> None:
    from app.core.blob import delete_blob

    try:
        delete_blob(file_ref)
    except Exception as exc:  # cleanup failure must not fail a committed ingestion
        logger.warning("Could not delete source after ingestion (%s)", type(exc).__name__)


def calculate_sha256(file_path: str) -> str:
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            sha256_hash.update(block)
    return sha256_hash.hexdigest()


def _load_report(db: Session, report_id: uuid.UUID, institution_id: uuid.UUID) -> ResearchReport:
    report = db.execute(
        select(ResearchReport)
        .where(ResearchReport.id == report_id, ResearchReport.institution_id == institution_id)
        .with_for_update()
    ).scalar_one_or_none()
    if report is None:
        raise IngestionError("Report not found for this institution.")
    return report


def ingest_document(db: Session, report_id: uuid.UUID, file_ref: str, institution_id: uuid.UUID) -> int:
    """Runs one ingestion attempt. Returns the number of chunks stored. Raises on failure."""
    report = _load_report(db, report_id, institution_id)
    if report.status == "processed":
        return db.execute(select(func.count(DocumentChunk.id)).where(DocumentChunk.report_id == report_id)).scalar()
    report.status = "processing"
    report.attempts = (report.attempts or 0) + 1
    report.processing_started_at = _utcnow()
    report.error_message = None
    db.commit()

    try:
        with _local_path(file_ref) as path:
            file_hash = calculate_sha256(path)
            duplicate = db.execute(
                select(ResearchReport.id).where(
                    ResearchReport.institution_id == institution_id,
                    ResearchReport.file_hash == file_hash,
                    ResearchReport.status == "processed",
                    ResearchReport.id != report_id,
                )
            ).scalar()
            report = _load_report(db, report_id, institution_id)
            report.file_hash = file_hash
            if duplicate:
                report.status = "duplicate"
                report.error_message = f"Same content as document {duplicate}."
                report.file_path = None
                report.processed_at = _utcnow()
                db.commit()
                _delete_source(file_ref)
                return 0

            try:
                pages = parse_pdf(path)
            except Exception as exc:
                raise IngestionError("The file could not be parsed as a PDF.") from exc
            chunks = chunk_document_pages(pages)
            if not chunks:
                raise IngestionError("No extractable text (the PDF may be scanned images).")

            try:
                vectors, space = generate_embeddings([c["content"] for c in chunks])
            except EmbeddingUnavailable as exc:
                logger.warning("Storing report %s without embeddings (%s)", report_id, exc)
                vectors, space = [None] * len(chunks), None

            db.execute(delete(DocumentChunk).where(DocumentChunk.report_id == report_id))  # idempotent retries
            db.add_all([
                DocumentChunk(
                    id=uuid.uuid4(),
                    institution_id=institution_id,
                    report_id=report_id,
                    content=chunk["content"],
                    embedding=vector,
                    embedding_model=space.space_id if space else None,
                    embedding_provider=space.provider if space else None,
                    metadata_json={"page": chunk["page_num"], "chunk_index": i, "word_count": chunk["word_count"]},
                )
                for i, (chunk, vector) in enumerate(zip(chunks, vectors))
            ])
            report.status = "processed"
            report.processed_at = _utcnow()
            report.file_path = None
            db.commit()  # chunks + status become visible together
    except Exception as exc:
        db.rollback()
        message = str(exc) if isinstance(exc, IngestionError) else "Processing failed; the document can be retried."
        logger.error("Ingestion failed for report %s (%s)", report_id, type(exc).__name__)
        try:
            report = _load_report(db, report_id, institution_id)
            report.status = "failed"
            report.error_message = message[:500]
            db.commit()
        except Exception as mark_exc:
            db.rollback()
            logger.error("Could not mark report %s failed (%s)", report_id, type(mark_exc).__name__)
        raise

    _delete_source(file_ref)  # only after the commit above succeeded
    logger.info("Ingestion complete: %d chunks for report %s", len(chunks), report_id)
    return len(chunks)
