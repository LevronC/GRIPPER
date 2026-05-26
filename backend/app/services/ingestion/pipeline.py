import uuid
import logging
from sqlalchemy.orm import Session
from app.services.parsing.parser import parse_pdf
from app.services.ingestion.chunker import chunk_document_pages
from app.services.embeddings.generator import generate_embeddings
from app.models import DocumentChunk, ResearchReport

logger = logging.getLogger(__name__)

def ingest_document(db: Session, report_id: uuid.UUID, file_path: str, institution_id: uuid.UUID) -> int:
    """
    Ingests a document:
    1. Parses PDF to get text pages.
    2. Chunks page text with overlap while preserving citations.
    3. Generates 384-dimensional normalized vector embeddings in a batch.
    4. Saves chunks + embeddings to the database.
    5. Updates ResearchReport status to 'processed'.
    """
    logger.info(f"Starting ingestion for report {report_id} from {file_path}")
    
    try:
        # 1. Parse PDF pages
        pages = parse_pdf(file_path)
        logger.info(f"Parsed {len(pages)} pages from {file_path}")
        
        # 2. Chunk pages
        chunks = chunk_document_pages(pages)
        logger.info(f"Generated {len(chunks)} chunks from document")
        
        if not chunks:
            logger.warning("No text extracted from document. Ingestion aborted.")
            return 0
            
        # 3. Generate embeddings
        chunk_texts = [c["content"] for c in chunks]
        embeddings = generate_embeddings(chunk_texts)
        logger.info("Generated embeddings for all chunks")
        
        # 4. Save to database
        db_chunks = []
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            db_chunk = DocumentChunk(
                id=uuid.uuid4(),
                institution_id=institution_id,
                report_id=report_id,
                content=chunk["content"],
                embedding=embedding,
                metadata_json={
                    "page": chunk["page_num"],
                    "chunk_index": i,
                    "token_count": chunk["token_count"]
                }
            )
            db_chunks.append(db_chunk)
            
        db.add_all(db_chunks)
        
        # 5. Update research report status
        report = db.query(ResearchReport).filter(ResearchReport.id == report_id).first()
        if report:
            report.status = "processed"
            
        db.commit()
        logger.info(f"Successfully saved {len(db_chunks)} chunks for report {report_id}")
        return len(db_chunks)
        
    except Exception as e:
        logger.error(f"Ingestion failed for report {report_id}: {str(e)}")
        # Attempt to mark report as failed
        try:
            db.rollback()
            report = db.query(ResearchReport).filter(ResearchReport.id == report_id).first()
            if report:
                report.status = "failed"
                db.commit()
        except Exception:
            pass
        raise e
