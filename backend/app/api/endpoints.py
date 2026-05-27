import logging
import os
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, File, Form, Request, UploadFile
from sqlalchemy import select, and_, func, text
from sqlalchemy.orm import Session
from pydantic import BaseModel
from rq import Queue

from app.core.config import settings
from app.core.redis_client import get_redis_client
from app.core.blob import store_upload, delete_blob
from app.core.errors import internal_error
from app.db.session import get_db
from app import models
from app.schemas.document import SemanticSearchRequest
from app.services.retrieval.searcher import search_documents
from app.services.governance.evaluator import evaluate_portfolio_compliance, simulate_portfolio_compliance
from app.services.governance.explain import generate_violation_explanation
from app.api.deps import RoleChecker
from app.core.rbac import COMPLIANCE_ROLES, READ_ROLES, RESEARCH_ROLES, SIMULATION_ROLES

logger = logging.getLogger(__name__)

router = APIRouter()

_redis_conn = None
_queue = None


def get_task_queue() -> Queue | None:
    global _redis_conn, _queue
    if _queue is not None:
        return _queue
    _redis_conn = get_redis_client()
    if not _redis_conn:
        return None
    _queue = Queue("default", connection=_redis_conn)
    return _queue


class _QueueProxy:
    def __getattr__(self, name):
        queue = get_task_queue()
        if queue is None:
            raise RuntimeError("Redis is not configured; background jobs are unavailable.")
        return getattr(queue, name)


queue = _QueueProxy()


# ── Document upload ────────────────────────────────────────────────────────────

@router.post("/documents/upload", status_code=202)
def upload_document(
    sector: str = Form(...),
    company: str = Form(...),
    recommendation: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user=Depends(RoleChecker(RESEARCH_ROLES)),
):
    """
    Accepts PDF uploads, validates file size and signature, stores the file
    (Vercel Blob on Vercel, local disk in dev), creates a pending ResearchReport,
    and enqueues the async ingestion task via Redis Queue.

    On Vercel, ingestion is processed by the /cron/process-documents endpoint
    (runs every minute via Vercel Cron) rather than by a persistent RQ worker.
    """
    res = db.execute(text("SHOW app.current_institution_id")).scalar()
    if not res or res == "":
        raise HTTPException(
            status_code=400,
            detail="X-Institution-ID header or token is required to upload documents",
        )
    institution_id = uuid.UUID(res)

    # Input validation
    clean_sector = sector.strip()
    clean_company = company.strip()
    clean_rec = recommendation.strip().lower()

    if not clean_sector or not clean_company or not clean_rec:
        raise HTTPException(status_code=400, detail="Fields sector, company, and recommendation cannot be empty.")
    if len(clean_company) > 255 or len(clean_sector) > 100:
        raise HTTPException(status_code=400, detail="Company or sector name exceeds maximum permitted length.")
    if clean_rec not in ["buy", "hold", "sell"]:
        raise HTTPException(status_code=400, detail="Recommendation must be 'buy', 'hold', or 'sell'.")

    # File validation
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is missing.")
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file.content_type != "application/pdf" and file_ext != ".pdf":
        raise HTTPException(status_code=400, detail="Unsupported file format. Only PDF files are allowed.")

    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
    try:
        content = file.file.read(MAX_FILE_SIZE + 1)
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(status_code=400, detail="File size exceeds the 10MB limit.")
        if not content.startswith(b"%PDF-"):
            raise HTTPException(status_code=400, detail="Invalid PDF file signature.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read upload file: {e}")

    report_id = uuid.uuid4()
    filename = f"{report_id}.pdf"

    # Store file — Vercel Blob when BLOB_READ_WRITE_TOKEN is set, local disk otherwise
    try:
        file_ref = store_upload(content, filename)
    except Exception as e:
        raise HTTPException(status_code=500, **internal_error(e, "file_storage"))

    # Create database record
    report = models.ResearchReport(
        id=report_id,
        institution_id=institution_id,
        sector=clean_sector,
        company=clean_company,
        recommendation=clean_rec,
        status="pending",
        file_path=file_ref,
        uploaded_by=current_user.id if current_user else None,
    )
    db.add(report)
    db.commit()

    # Enqueue background processing (RQ → Redis Queue)
    # On Vercel: CRON picks this up via GET /cron/process-documents (runs every minute).
    # On Railway/local: The rq worker process consumes the job immediately.
    task_queue = get_task_queue()
    if task_queue:
        try:
            from app.workers.tasks import process_document_ingestion
            task_queue.enqueue(
                process_document_ingestion,
                str(report_id),
                file_ref,
                str(institution_id),
            )
        except Exception as e:
            logger.warning("Could not enqueue ingestion job (cron will pick it up): %s", e)
    else:
        logger.info(
            "No Redis queue available — report %s will be processed by cron.", report_id
        )

    return {
        "report_id": str(report_id),
        "status": "pending",
        "message": "Document enqueued for ingestion.",
    }


# ── Document listing ───────────────────────────────────────────────────────────

@router.get("/documents")
def list_documents(
    db: Session = Depends(get_db),
    current_user=Depends(RoleChecker(READ_ROLES)),
    page: int = 1,
    page_size: int = 20,
):
    res = db.execute(text("SHOW app.current_institution_id")).scalar()
    if not res or res == "":
        raise HTTPException(status_code=400, detail="X-Institution-ID header or token is required to view documents")

    page = max(1, page)
    page_size = min(page_size, 100)
    offset = (page - 1) * page_size

    total = db.query(func.count(models.ResearchReport.id)).scalar()
    reports = (
        db.query(models.ResearchReport)
        .order_by(models.ResearchReport.created_at.desc())
        .offset(offset)
        .limit(page_size)
        .all()
    )
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "results": [
            {
                "id": str(r.id),
                "sector": r.sector,
                "company": r.company,
                "recommendation": r.recommendation,
                "status": r.status,
                "created_at": r.created_at.isoformat(),
            }
            for r in reports
        ],
    }


# ── Semantic search ────────────────────────────────────────────────────────────

@router.post("/search/semantic")
def semantic_search(
    request: SemanticSearchRequest,
    db: Session = Depends(get_db),
    current_user=Depends(RoleChecker(READ_ROLES)),
):
    res = db.execute(text("SHOW app.current_institution_id")).scalar()
    if not res or res == "":
        raise HTTPException(status_code=400, detail="X-Institution-ID header or token is required to perform semantic search")

    institution_id = uuid.UUID(res)
    try:
        results = search_documents(db, request.query, institution_id, request.limit)
        return {"query": request.query, "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, **internal_error(e, "semantic_search"))


# ── Compliance evaluation ──────────────────────────────────────────────────────

@router.post("/portfolios/{portfolio_id}/evaluate")
def evaluate_portfolio(
    portfolio_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user=Depends(RoleChecker(COMPLIANCE_ROLES)),
):
    res = db.execute(text("SHOW app.current_institution_id")).scalar()
    if not res or res == "":
        raise HTTPException(status_code=400, detail="X-Institution-ID header or token is required to run compliance evaluations")
    institution_id = uuid.UUID(res)
    try:
        violations = evaluate_portfolio_compliance(db, portfolio_id, institution_id)
        return {"portfolio_id": str(portfolio_id), "violations": violations}
    except Exception as e:
        raise HTTPException(status_code=500, **internal_error(e, "evaluate_portfolio"))


@router.get("/portfolios/{portfolio_id}/violations")
def get_portfolio_violations(
    portfolio_id: uuid.UUID,
    resolved: bool = False,
    db: Session = Depends(get_db),
    current_user=Depends(RoleChecker(READ_ROLES)),
):
    res = db.execute(text("SHOW app.current_institution_id")).scalar()
    if not res or res == "":
        raise HTTPException(status_code=400, detail="X-Institution-ID header or token is required to read compliance events")
    try:
        stmt = (
            select(models.GovernanceEvent)
            .filter(
                and_(
                    models.GovernanceEvent.portfolio_id == portfolio_id,
                    models.GovernanceEvent.resolved == resolved,
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
                "created_at": e.created_at.isoformat(),
            }
            for e in events
        ]
    except Exception as e:
        raise HTTPException(status_code=500, **internal_error(e, "get_violations"))


@router.post("/violations/{event_id}/explain")
def explain_violation(
    event_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user=Depends(RoleChecker(COMPLIANCE_ROLES)),
):
    res = db.execute(text("SHOW app.current_institution_id")).scalar()
    if not res or res == "":
        raise HTTPException(status_code=400, detail="X-Institution-ID header or token is required to explain compliance events")
    institution_id = uuid.UUID(res)
    try:
        explanation = generate_violation_explanation(db, event_id, institution_id)
        if "error" in explanation:
            raise HTTPException(status_code=404, detail=explanation["error"])
        return explanation
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, **internal_error(e, "explain_violation"))


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
    current_user=Depends(RoleChecker(SIMULATION_ROLES)),
):
    res = db.execute(text("SHOW app.current_institution_id")).scalar()
    if not res or res == "":
        raise HTTPException(status_code=400, detail="X-Institution-ID header or token is required to run simulation")
    institution_id = uuid.UUID(res)
    try:
        simulated_data = [h.model_dump() for h in holdings_data]
        violations = simulate_portfolio_compliance(db, portfolio_id, institution_id, simulated_data)
        return {
            "portfolio_id": str(portfolio_id),
            "simulated_holdings_count": len(holdings_data),
            "violations": violations,
        }
    except Exception as e:
        raise HTTPException(status_code=500, **internal_error(e, "simulate_portfolio"))


# ── Vercel Cron: process pending documents ─────────────────────────────────────

@router.get("/cron/process-documents")
def cron_process_documents(request: Request):
    """
    Internal endpoint invoked by Vercel Cron every minute.

    On Vercel, there is no persistent RQ worker process. This endpoint acts as
    the document ingestion worker: it picks up to 5 pending ResearchReports that
    have a file_path set, runs the full ingestion pipeline (parse → chunk →
    embed → store), and updates report status.

    Authentication: Vercel sends `Authorization: Bearer {CRON_SECRET}` with
    every cron invocation. Requests without this header are rejected.
    """
    # Verify cron secret
    if not settings.CRON_SECRET:
        raise HTTPException(status_code=503, detail="CRON_SECRET is not configured.")
    auth_header = request.headers.get("authorization", "")
    if auth_header != f"Bearer {settings.CRON_SECRET}":
        raise HTTPException(status_code=401, detail="Unauthorized")

    from app.api.auth import get_superuser_session
    from app.services.ingestion.pipeline import ingest_document
    from app.db.session import SessionLocal

    processed = []
    errors = []

    with get_superuser_session() as super_db:
        pending = (
            super_db.query(models.ResearchReport)
            .filter(
                models.ResearchReport.status == "pending",
                models.ResearchReport.file_path.isnot(None),
            )
            .limit(5)
            .all()
        )
        pending_snapshot = [
            (str(r.id), r.file_path, str(r.institution_id)) for r in pending
        ]

    for report_id_str, file_path, institution_id_str in pending_snapshot:
        report_id = uuid.UUID(report_id_str)
        institution_id = uuid.UUID(institution_id_str)

        db = SessionLocal()
        try:
            db.execute(
                text("SET LOCAL app.current_institution_id = :id"),
                {"id": institution_id_str},
            )
            chunks = ingest_document(db, report_id, file_path, institution_id)
            processed.append({"report_id": report_id_str, "chunks": chunks})
            logger.info("Cron ingested report %s: %d chunks", report_id_str, chunks)
        except Exception as e:
            logger.error("Cron ingestion failed for report %s: %s", report_id_str, e)
            errors.append({"report_id": report_id_str, "error": str(e)})
        finally:
            db.close()

    return {
        "processed": len(processed),
        "errors": len(errors),
        "results": processed,
        "failures": errors,
    }
