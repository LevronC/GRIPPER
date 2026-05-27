import contextlib
import hashlib
import logging
import os
import uuid
from typing import Generator

from sqlalchemy.orm import Session

from app.services.parsing.parser import parse_pdf
from app.services.ingestion.chunker import chunk_document_pages
from app.services.embeddings.generator import generate_embeddings
from app.models import DocumentChunk, ResearchReport

logger = logging.getLogger(__name__)


@contextlib.contextmanager
def _local_path(file_ref: str) -> Generator[str, None, None]:
    """
    Context manager that yields a local filesystem path for `file_ref`.

    If `file_ref` is a Vercel Blob URL (https://...) it is downloaded to
    /tmp and the tmp file is removed on exit. If it is already a local path
    it is yielded as-is with no cleanup.
    """
    if file_ref.startswith("https://"):
        from app.core.blob import fetch_blob, delete_blob
        logger.info("Downloading blob for ingestion: %s", file_ref)
        content = fetch_blob(file_ref)
        # Use a unique tmp name to avoid concurrent-write collisions
        tmp = f"/tmp/gripper_ingest_{uuid.uuid4().hex}.pdf"
        with open(tmp, "wb") as fh:
            fh.write(content)
        try:
            yield tmp
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
            # Remove the blob now that ingestion is complete
            try:
                delete_blob(file_ref)
            except Exception as e:
                logger.warning("Could not delete blob after ingestion: %s", e)
    else:
        yield file_ref


def calculate_sha256(file_path: str) -> str:
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def ingest_document(db: Session, report_id: uuid.UUID, file_ref: str, institution_id: uuid.UUID) -> int:
    """
    Ingests a document:
    1. Resolves `file_ref` to a local path (downloading from Vercel Blob if needed).
    2. Calculates SHA-256 hash and checks for duplicates within the same institution.
    3. Parses PDF to get text pages.
    4. Chunks page text with overlap while preserving citations.
    5. Generates 384-dimensional normalized vector embeddings in a batch.
    6. Saves chunks + embeddings to the database.
    7. Updates ResearchReport status to 'processed' and clears file_path.

    `file_ref` can be either a local filesystem path or a Vercel Blob URL.
    """
    logger.info("Starting ingestion for report %s from %s", report_id, file_ref)

    try:
        with _local_path(file_ref) as file_path:
            # 1. Deduplicate by content hash
            file_hash = calculate_sha256(file_path)

            existing_report = (
                db.query(ResearchReport)
                .filter(
                    ResearchReport.institution_id == institution_id,
                    ResearchReport.file_hash == file_hash,
                    ResearchReport.status == "processed",
                    ResearchReport.id != report_id,
                )
                .first()
            )

            if existing_report:
                logger.info("Duplicate document found (ID: %s). Marking as processed.", existing_report.id)
                report = db.query(ResearchReport).filter(ResearchReport.id == report_id).first()
                if report:
                    report.file_hash = file_hash
                    report.status = "processed"
                    report.file_path = None
                    db.commit()
                return 0

            report = db.query(ResearchReport).filter(ResearchReport.id == report_id).first()
            if report:
                report.file_hash = file_hash
                db.flush()

            # 2. Parse PDF
            pages = parse_pdf(file_path)
            logger.info("Parsed %d pages for report %s", len(pages), report_id)

            # 3. Chunk
            chunks = chunk_document_pages(pages)
            logger.info("Generated %d chunks for report %s", len(chunks), report_id)

            if not chunks:
                logger.warning("No text extracted from document %s. Ingestion aborted.", report_id)
                if report:
                    report.status = "failed"
                    report.file_path = None
                    db.commit()
                return 0

            # 4. Embed
            chunk_texts = [c["content"] for c in chunks]
            embeddings = generate_embeddings(chunk_texts)

            # 5. Persist chunks
            db_chunks = [
                DocumentChunk(
                    id=uuid.uuid4(),
                    institution_id=institution_id,
                    report_id=report_id,
                    content=chunk["content"],
                    embedding=embedding,
                    metadata_json={
                        "page": chunk["page_num"],
                        "chunk_index": i,
                        "token_count": chunk["token_count"],
                    },
                )
                for i, (chunk, embedding) in enumerate(zip(chunks, embeddings))
            ]
            db.add_all(db_chunks)

            # 6. Mark report done and clear the stored file reference
            if report:
                report.status = "processed"
                report.file_path = None

            db.commit()
            logger.info("Ingestion complete: %d chunks saved for report %s", len(db_chunks), report_id)
            return len(db_chunks)

    except Exception as e:
        logger.error("Ingestion failed for report %s: %s", report_id, e)
        try:
            db.rollback()
            report = db.query(ResearchReport).filter(ResearchReport.id == report_id).first()
            if report:
                report.status = "failed"
                db.commit()
        except Exception:
            pass
        raise
