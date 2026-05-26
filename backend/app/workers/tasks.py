import uuid
from sqlalchemy import text
from app.db.session import SessionLocal
from app.services.ingestion.pipeline import ingest_document

def process_document_ingestion(report_id_str: str, file_path: str, institution_id_str: str) -> int:
    """
    Background task called by Redis Queue (RQ) to run document ingestion asynchronously.
    """
    report_id = uuid.UUID(report_id_str)
    institution_id = uuid.UUID(institution_id_str)
    
    db = SessionLocal()
    try:
        # Configure session-scoped tenant context for RLS policies
        db.execute(text("SET app.current_institution_id = :id"), {"id": str(institution_id)})
        
        # Run pipeline
        chunks_count = ingest_document(db, report_id, file_path, institution_id)
        return chunks_count
    except Exception as e:
        # Error is caught and handled inside ingest_document, but we raise here to let RQ record it
        raise e
    finally:
        db.close()
