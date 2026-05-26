import os
import uuid
import shutil
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form
from sqlalchemy.orm import Session
from sqlalchemy import text
from redis import Redis
from rq import Queue

from app.core.config import settings
from app.db.session import get_db
from app import models
from app.schemas.document import SemanticSearchRequest
from app.services.retrieval.searcher import search_documents
from app.workers.tasks import process_document_ingestion
from app.api.deps import get_current_user, RoleChecker

router = APIRouter()

# Initialize RQ connection using Redis url from configuration
redis_conn = Redis.from_url(settings.REDIS_URL)
queue = Queue("default", connection=redis_conn)

@router.post("/documents/upload", status_code=202)
def upload_document(
    sector: str = Form(...),
    company: str = Form(...),
    recommendation: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user = Depends(RoleChecker(["analyst", "sector_lead", "pm", "admin"]))
):
    """
    Accepts PDF uploads, validates file size and signature, writes to storage,
    creates a pending ResearchReport, and queues the async ingestion task.
    """
    # 1. Enforce current tenant context exists
    res = db.execute(text("SHOW app.current_institution_id")).scalar()
    if not res or res == "":
        raise HTTPException(
            status_code=400, 
            detail="X-Institution-ID header or token is required to upload documents"
        )
    institution_id = uuid.UUID(res)
    
    # 2. Input Validation
    clean_sector = sector.strip()
    clean_company = company.strip()
    clean_rec = recommendation.strip().lower()
    
    if not clean_sector or not clean_company or not clean_rec:
        raise HTTPException(status_code=400, detail="Fields sector, company, and recommendation cannot be empty.")
    if len(clean_company) > 255 or len(clean_sector) > 100:
        raise HTTPException(status_code=400, detail="Company or sector name exceeds maximum permitted length.")
    if clean_rec not in ["buy", "hold", "sell"]:
        raise HTTPException(status_code=400, detail="Recommendation must be 'buy', 'hold', or 'sell'.")
        
    # 3. File Ext & Content Type Check
    if not file.filename:
         raise HTTPException(status_code=400, detail="Filename is missing.")
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file.content_type != "application/pdf" and file_ext != ".pdf":
        raise HTTPException(
            status_code=400, 
            detail="Unsupported file format. Only PDF files are allowed."
        )
        
    # 4. File Size & Magic Bytes Security Checks
    MAX_FILE_SIZE = 10 * 1024 * 1024 # 10MB
    try:
        content = file.file.read(MAX_FILE_SIZE + 1)
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(status_code=400, detail="File size exceeds the 10MB limit.")
        if not content.startswith(b"%PDF-"):
            raise HTTPException(status_code=400, detail="Invalid PDF file signature.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read upload file: {str(e)}")

    # Generate unique report ID
    report_id = uuid.uuid4()
    filename = f"{report_id}.pdf"
    file_path = os.path.join(settings.UPLOAD_DIR, filename)
    
    # 5. Save content to local storage
    try:
        with open(file_path, "wb") as buffer:
            buffer.write(content)
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to save file to disk: {str(e)}"
        )
        
    # Create database entry (under session RLS context)
    report = models.ResearchReport(
        id=report_id,
        institution_id=institution_id,
        sector=clean_sector,
        company=clean_company,
        recommendation=clean_rec,
        status="pending",
        uploaded_by=current_user.id if current_user else None
    )
    db.add(report)
    db.commit()
    
    # Queue background task to parse, chunk, embed, and store
    try:
        queue.enqueue(
            process_document_ingestion,
            str(report_id),
            file_path,
            str(institution_id)
        )
    except Exception as e:
        # If queue fails, clean up the file and raise error
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to queue background processing job: {str(e)}"
        )
        
    return {
        "report_id": str(report_id),
        "status": "pending",
        "message": "Document enqueued for ingestion."
    }

@router.get("/documents")
def list_documents(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Returns list of research reports for the current institution context.
    """
    res = db.execute(text("SHOW app.current_institution_id")).scalar()
    if not res or res == "":
        raise HTTPException(
            status_code=400, 
            detail="X-Institution-ID header or token is required to view documents"
        )
    reports = db.query(models.ResearchReport).order_by(models.ResearchReport.created_at.desc()).all()
    return [
        {
            "id": str(r.id),
            "sector": r.sector,
            "company": r.company,
            "recommendation": r.recommendation,
            "status": r.status,
            "created_at": r.created_at.isoformat()
        }
        for r in reports
    ]

@router.post("/search/semantic")
def semantic_search(
    request: SemanticSearchRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    RAG semantic search endpoint. Takes a query string and returns relevant chunks.
    Automatically isolated by PostgreSQL Row-Level Security (RLS).
    """
    res = db.execute(text("SHOW app.current_institution_id")).scalar()
    if not res or res == "":
        raise HTTPException(
            status_code=400, 
            detail="X-Institution-ID header or token is required to perform semantic search"
        )
        
    institution_id = uuid.UUID(res)
    
    try:
        results = search_documents(db, request.query, institution_id, request.limit)
        return {
            "query": request.query,
            "results": results
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Search failed: {str(e)}"
        )


from app.services.governance.evaluator import evaluate_portfolio_compliance, simulate_portfolio_compliance
from app.services.governance.explain import generate_violation_explanation
from sqlalchemy import select, and_
from pydantic import BaseModel

@router.post("/portfolios/{portfolio_id}/evaluate")
def evaluate_portfolio(
    portfolio_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Runs deterministic compliance checks for a portfolio against active IPS rules.
    Reconciles, logs, and returns active violations.
    """
    res = db.execute(text("SHOW app.current_institution_id")).scalar()
    if not res or res == "":
        raise HTTPException(
            status_code=400, 
            detail="X-Institution-ID header or token is required to run compliance evaluations"
        )
    institution_id = uuid.UUID(res)
    
    try:
        violations = evaluate_portfolio_compliance(db, portfolio_id, institution_id)
        return {
            "portfolio_id": str(portfolio_id),
            "violations": violations
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/portfolios/{portfolio_id}/violations")
def get_portfolio_violations(
    portfolio_id: uuid.UUID,
    resolved: bool = False,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Returns the list of active or resolved compliance breach events for a portfolio.
    """
    res = db.execute(text("SHOW app.current_institution_id")).scalar()
    if not res or res == "":
        raise HTTPException(
            status_code=400, 
            detail="X-Institution-ID header or token is required to read compliance events"
        )
        
    try:
        stmt = (
            select(models.GovernanceEvent)
            .filter(
                and_(
                    models.GovernanceEvent.portfolio_id == portfolio_id,
                    models.GovernanceEvent.resolved == resolved
                )
            )
            .order_by(models.GovernanceEvent.created_at.desc())
        )
        events = db.execute(stmt).scalars().all()
        return [
            {
                "id": str(e.id),
                "event_type": e.event_type,
                "severity": e.severity,
                "details": e.details_json,
                "resolved": e.resolved,
                "resolved_at": e.resolved_at.isoformat() if e.resolved_at else None,
                "created_at": e.created_at.isoformat()
            }
            for e in events
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/violations/{event_id}/explain")
def explain_violation(
    event_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Retrieves the qualitative investment context (RAG document chunks)
    describing or justifying the asset causing a compliance breach.
    """
    res = db.execute(text("SHOW app.current_institution_id")).scalar()
    if not res or res == "":
        raise HTTPException(
            status_code=400, 
            detail="X-Institution-ID header or token is required to explain compliance events"
        )
    institution_id = uuid.UUID(res)
    
    try:
        explanation = generate_violation_explanation(db, event_id, institution_id)
        if "error" in explanation:
            raise HTTPException(status_code=404, detail=explanation["error"])
        return explanation
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class HoldingSimulation(BaseModel):
    ticker: str
    weight: float
    cost_basis: Optional[float] = 100.0
    conviction_score: Optional[int] = None

@router.post("/portfolios/{portfolio_id}/simulate")
def simulate_portfolio(
    portfolio_id: uuid.UUID,
    holdings_data: List[HoldingSimulation],
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Runs hypothetical compliance checks for a portfolio against active IPS rules
    using simulated holdings. Does not modify the database.
    """
    res = db.execute(text("SHOW app.current_institution_id")).scalar()
    if not res or res == "":
        raise HTTPException(
            status_code=400, 
            detail="X-Institution-ID header or token is required to run simulation"
        )
    institution_id = uuid.UUID(res)
    
    try:
        simulated_data = [h.model_dump() for h in holdings_data]
        violations = simulate_portfolio_compliance(db, portfolio_id, institution_id, simulated_data)
        return {
            "portfolio_id": str(portfolio_id),
            "simulated_holdings_count": len(holdings_data),
            "violations": violations
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


