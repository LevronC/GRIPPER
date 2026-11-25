import hmac
import logging
import os
import uuid
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, File, Form, Request, UploadFile
from sqlalchemy import select, and_, func, text
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
try:
    from rq import Queue
except ImportError:
    Queue = None  # type: ignore[assignment,misc]

from app.core.config import settings
from app.core.redis_client import get_redis_client
from app.core.blob import store_upload
from app.core.errors import internal_error
from app.db.session import SessionLocal, get_db, set_tenant
from app import models
from app.schemas.document import SemanticSearchRequest
from app.services.retrieval.searcher import hybrid_search
from app.services.governance.evaluator import evaluate_portfolio_compliance, simulate_portfolio_compliance
from app.services.governance.explain import generate_violation_explanation
from app.services.governance.holdings import validate_holdings_set
from app.api.deps import CurrentUser, RoleChecker
from app.api.tenancy import require_governance_event, require_portfolio, require_report
from app.core.rbac import COMPLIANCE_ROLES, READ_ROLES, RESEARCH_ROLES, SIMULATION_ROLES

logger = logging.getLogger(__name__)

router = APIRouter()

_task_queue: Optional[Queue] = None
_task_queue_checked = False


def get_task_queue() -> Optional[Queue]:
    """
    Returns an RQ Queue if Redis is reachable, otherwise None.
    Result is cached for the lifetime of the process / warm function instance.
    On Vercel, Redis is optional — documents are processed by the cron job.
    """
    global _task_queue, _task_queue_checked
    if _task_queue_checked:
        return _task_queue
    _task_queue_checked = True
    redis_conn = get_redis_client()
    if redis_conn:
        try:
            _task_queue = Queue("default", connection=redis_conn)
        except Exception as exc:
            logger.warning("Could not create RQ queue: %s", exc)
    return _task_queue


# ── Document upload ────────────────────────────────────────────────────────────

@router.post("/documents/upload", status_code=202)
def upload_document(
    sector: str = Form(...),
    company: str = Form(...),
    recommendation: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(RoleChecker(RESEARCH_ROLES)),
):
    """
    Accepts PDF uploads, validates file size and signature, stores the file
    (Vercel Blob on Vercel, local disk in dev), creates a pending ResearchReport,
    and enqueues the async ingestion task via Redis Queue.

    On Vercel, ingestion is processed by the /cron/process-documents endpoint
    (runs every minute via Vercel Cron) rather than by a persistent RQ worker.
    """
    institution_id = current_user.institution_id

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
    except Exception:
        raise HTTPException(status_code=400, detail="Failed to read upload file.")

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
        uploaded_by=current_user.id,
    )
    db.add(report)
    db.commit()

    return _dispatch_ingestion(db, report_id, file_ref, institution_id)


def ingestion_mode() -> str:
    """
    queue: enqueue to Redis for an RQ worker. sync: process inside the request.
    INGESTION_MODE=auto (default) uses the queue only when Redis is reachable AND a worker
    can exist: never on Vercel unless INGESTION_WORKER=external declares one.
    """
    requested = os.getenv("INGESTION_MODE", "auto").strip().lower()
    if requested in ("queue", "sync"):
        return requested
    on_vercel = os.getenv("VERCEL") == "1"
    worker_declared = os.getenv("INGESTION_WORKER", "").strip().lower() == "external"
    if on_vercel and not worker_declared:
        return "sync"
    return "queue" if get_task_queue() else "sync"


def _dispatch_ingestion(db: Session, report_id: uuid.UUID, file_ref: str, institution_id: uuid.UUID) -> dict:
    if ingestion_mode() == "queue":
        task_queue = get_task_queue()
        if task_queue:
            try:
                from app.workers.tasks import process_document_ingestion
                task_queue.enqueue(process_document_ingestion, str(report_id), file_ref, str(institution_id))
                return {"report_id": str(report_id), "status": "pending", "message": "Document queued for ingestion."}
            except Exception as e:
                logger.warning("Could not enqueue ingestion job, processing synchronously (%s)", type(e).__name__)

    from app.services.ingestion.pipeline import ingest_document as _ingest
    try:
        chunks = _ingest(db, report_id, file_ref, institution_id)
    except Exception:
        report = db.get(models.ResearchReport, report_id)
        return {
            "report_id": str(report_id),
            "status": "failed",
            "message": (report.error_message if report else None) or "Ingestion failed.",
        }
    report = db.get(models.ResearchReport, report_id)
    return {
        "report_id": str(report_id),
        "status": report.status if report else "processed",
        "chunks": chunks,
        "message": "Document ingested.",
    }


@router.post("/documents/{report_id}/retry", status_code=202)
def retry_document(
    report_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(RoleChecker(RESEARCH_ROLES)),
):
    """Retries a failed ingestion. The source file is retained after failures for this purpose."""
    report = require_report(db, report_id, current_user.institution_id)
    if report.status != "failed":
        raise HTTPException(status_code=409, detail=f"Only failed documents can be retried (status: {report.status}).")
    if not report.file_path:
        raise HTTPException(status_code=410, detail="The source file is no longer retained; upload it again.")
    report.status = "pending"
    db.commit()
    return _dispatch_ingestion(db, report.id, report.file_path, current_user.institution_id)


# ── Document listing ───────────────────────────────────────────────────────────

@router.get("/documents")
def list_documents(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(RoleChecker(READ_ROLES)),
    page: int = 1,
    page_size: int = 20,
):
    page = max(1, page)
    page_size = max(1, min(page_size, 100))
    offset = (page - 1) * page_size

    # Select only the columns this endpoint actually returns — never include
    # schema-optional columns like file_path so we stay resilient during
    # rolling migrations where the column may not yet exist in all replicas.
    _cols = [
        models.ResearchReport.id,
        models.ResearchReport.sector,
        models.ResearchReport.company,
        models.ResearchReport.recommendation,
        models.ResearchReport.status,
        models.ResearchReport.error_message,
        models.ResearchReport.attempts,
        models.ResearchReport.created_at,
    ]
    try:
        own = models.ResearchReport.institution_id == current_user.institution_id
        total = db.query(func.count(models.ResearchReport.id)).filter(own).scalar()
        rows = (
            db.query(*_cols)
            .filter(own)
            .order_by(models.ResearchReport.created_at.desc())
            .offset(offset)
            .limit(page_size)
            .all()
        )
    except Exception as e:
        raise HTTPException(status_code=500, **internal_error(e, "list_documents"))

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
                "error_message": r.error_message,
                "attempts": r.attempts,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ],
    }


# ── Semantic search ────────────────────────────────────────────────────────────

@router.post("/search/semantic")
def semantic_search(
    request: SemanticSearchRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(RoleChecker(RESEARCH_ROLES)),
):
    try:
        outcome = hybrid_search(db, request.query, current_user.institution_id, request.limit)
        return {
            "query": request.query,
            "results": outcome.results,
            "retrieval_mode": outcome.retrieval_mode,
            "degraded_reason": outcome.degraded_reason,
        }
    except Exception as e:
        raise HTTPException(status_code=500, **internal_error(e, "semantic_search"))


# ── Compliance evaluation ──────────────────────────────────────────────────────

@router.post("/portfolios/{portfolio_id}/evaluate")
def evaluate_portfolio(
    portfolio_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(RoleChecker(COMPLIANCE_ROLES)),
):
    institution_id = current_user.institution_id
    require_portfolio(db, portfolio_id, institution_id)
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
    current_user: CurrentUser = Depends(RoleChecker(READ_ROLES)),
):
    require_portfolio(db, portfolio_id, current_user.institution_id)
    try:
        stmt = (
            select(models.GovernanceEvent)
            .filter(
                and_(
                    models.GovernanceEvent.portfolio_id == portfolio_id,
                    models.GovernanceEvent.institution_id == current_user.institution_id,
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
    current_user: CurrentUser = Depends(RoleChecker(COMPLIANCE_ROLES)),
):
    institution_id = current_user.institution_id
    require_governance_event(db, event_id, institution_id)
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
    ticker: str = Field(..., pattern=r"^[A-Za-z0-9.\-]{1,12}$")
    weight: float = Field(..., ge=0.0, le=1.0)
    cost_basis: Optional[float] = Field(100.0, ge=0.0)
    conviction_score: Optional[int] = Field(None, ge=1, le=10)


@router.post("/portfolios/{portfolio_id}/simulate")
def simulate_portfolio(
    portfolio_id: uuid.UUID,
    holdings_data: List[HoldingSimulation] = Body(..., max_length=500),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(RoleChecker(SIMULATION_ROLES)),
):
    validate_holdings_set([h.ticker for h in holdings_data], [h.weight for h in holdings_data])
    institution_id = current_user.institution_id
    require_portfolio(db, portfolio_id, institution_id)
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
    Processes up to 5 pending documents. NOT scheduled automatically: vercel.json
    defines no cron. It exists so an operator (or an external scheduler) can drain
    pending uploads. Authenticated with `Authorization: Bearer {CRON_SECRET}`.

    Pending jobs are listed through the SECURITY DEFINER function
    app_pending_ingestion_jobs (identifiers only); each job then runs in its own
    session bound to the report's institution, so RLS applies to all reads/writes.
    """
    if not settings.CRON_SECRET:
        raise HTTPException(status_code=503, detail="CRON_SECRET is not configured.")
    auth_header = request.headers.get("authorization", "")
    if not hmac.compare_digest(auth_header.encode(), f"Bearer {settings.CRON_SECRET}".encode()):
        raise HTTPException(status_code=401, detail="Unauthorized")

    from app.services.ingestion.pipeline import ingest_document

    with SessionLocal() as db:
        jobs = db.execute(
            text("SELECT report_id, institution_id FROM app_pending_ingestion_jobs(5)")
        ).all()

    processed, errors = [], []
    for report_id, institution_id in jobs:
        with SessionLocal() as db:
            set_tenant(db, institution_id)
            report = db.execute(
                select(models.ResearchReport).where(
                    models.ResearchReport.id == report_id,
                    models.ResearchReport.institution_id == institution_id,
                )
            ).scalar_one_or_none()
            if report is None or not report.file_path:
                continue
            try:
                chunks = ingest_document(db, report_id, report.file_path, institution_id)
                processed.append({"report_id": str(report_id), "chunks": chunks})
            except Exception as e:
                logger.error("Cron ingestion failed for report %s: %s", report_id, type(e).__name__)
                errors.append({"report_id": str(report_id)})

    return {
        "processed": len(processed),
        "errors": len(errors),
        "results": processed,
        "failures": errors,
    }
