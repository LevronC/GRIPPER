import logging
import os
import uuid
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.api.admin import router as admin_router
from app.api.auth import router as auth_router
from app.api.deps import CurrentUser, RoleChecker
from app.api.tenancy import require_portfolio
from app.core.rbac import (
    ADMIN_ROLES,
    INVITABLE_ROLES,
    HOLDINGS_WRITE_ROLES,
    PORTFOLIO_WRITE_ROLES,
    READ_ROLES,
)
from app import models
from app.core.config import settings
from app.api.endpoints import router as api_router
from app.db.migrate import ensure_database_ready
from app.db.session import database_role_report, engine, get_db

logger = logging.getLogger(__name__)

SWAGGER_OPENAPI_URL = os.getenv("SWAGGER_OPENAPI_URL", "/openapi.json")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # No-op unless AUTO_MIGRATE=true (migrations are normally a deploy step).
    try:
        ensure_database_ready()
    except Exception as exc:
        logger.error("Database bootstrap failed (%s)", type(exc).__name__)
    yield


app = FastAPI(
    title="Gripper Risk Terminal Backend API",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)


@app.get("/docs", include_in_schema=False)
async def swagger_ui_html():
    return get_swagger_ui_html(
        openapi_url=SWAGGER_OPENAPI_URL,
        title=f"{app.title} - Swagger UI",
    )


@app.get("/redoc", include_in_schema=False)
async def redoc_html():
    return get_redoc_html(
        openapi_url=SWAGGER_OPENAPI_URL,
        title=f"{app.title} - ReDoc",
    )


# ── Security response headers ─────────────────────────────────────────────────
@app.middleware("http")
async def add_security_headers(request: Request, call_next) -> Response:
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    # Tight CSP — API-only service, no HTML pages served from this origin
    response.headers["Content-Security-Policy"] = "default-src 'none'"
    return response


# ── CORS ──────────────────────────────────────────────────────────────────────
# On Vercel, the frontend is served at the same origin as the API, so
# cross-origin requests only happen in local development.
# Set ALLOWED_ORIGINS to a comma-separated list of trusted origins, e.g.:
#   http://localhost:5173,https://gripper.vercel.app
_origins = [o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(api_router)


@app.get("/")
def root():
    return {
        "message": "Gripper Risk Terminal API is running",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "gripper-backend"}


@app.get("/health/db")
def health_db_check():
    """
    Connectivity + runtime-role safety. Returns 503 when the runtime role could
    bypass row-level security. Exposes booleans only (no role or table names).
    """
    try:
        with engine.connect() as conn:
            users_exists = conn.execute(
                text(
                    "SELECT EXISTS ("
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name = 'users'"
                    ")"
                )
            ).scalar()
            report = database_role_report(conn) if users_exists else None
    except OperationalError as exc:
        logger.error("Health check: database unavailable (%s)", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Database unavailable.") from exc
    body = {
        "status": "ok",
        "database": "connected",
        "schema_ready": bool(users_exists),
        "rls_enforced": bool(report and report["rls_enforced"]),
    }
    if not body["schema_ready"] or not body["rls_enforced"]:
        raise HTTPException(status_code=503, detail=body)
    return body


# ── Institutions ──────────────────────────────────────────────────────────────

def _institution_json(i: models.Institution) -> dict:
    return {
        "id": str(i.id),
        "name": i.name,
        "slug": i.slug,
        "tier": i.tier,
        "created_at": i.created_at,
    }


@app.get("/institutions")
def list_institutions(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(RoleChecker(READ_ROLES)),
):
    """
    The authenticated user's institution. Tenants are not publicly enumerable, and
    there is no API to create one: provisioning uses scripts/provision_institution.py
    with the owner connection.
    """
    inst = db.get(models.Institution, current_user.institution_id)
    return [_institution_json(inst)] if inst else []


# ── Portfolios ────────────────────────────────────────────────────────────────

def _portfolio_json(p: models.Portfolio) -> dict:
    return {
        "id": str(p.id),
        "name": p.name,
        "strategy_type": p.strategy_type,
        "institution_id": str(p.institution_id),
    }


@app.post("/portfolios")
def create_portfolio(
    name: str,
    strategy_type: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(RoleChecker(PORTFOLIO_WRITE_ROLES)),
):
    portfolio = models.Portfolio(
        institution_id=current_user.institution_id,
        name=name,
        strategy_type=strategy_type,
    )
    db.add(portfolio)
    db.commit()
    db.refresh(portfolio)  # new transaction: tenant context re-applied by after_begin hook
    return _portfolio_json(portfolio)


@app.get("/portfolios")
def list_portfolios(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(RoleChecker(READ_ROLES)),
):
    portfolios = db.execute(
        select(models.Portfolio).where(models.Portfolio.institution_id == current_user.institution_id)
    ).scalars().all()
    return [_portfolio_json(p) for p in portfolios]


@app.get("/portfolios/{portfolio_id}/holdings")
def list_portfolio_holdings(
    portfolio_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(RoleChecker(READ_ROLES)),
):
    require_portfolio(db, portfolio_id, current_user.institution_id)
    holdings = db.execute(
        select(models.Holding).where(models.Holding.portfolio_id == portfolio_id)
    ).scalars().all()
    return [
        {
            "id": str(h.id),
            "portfolio_id": str(h.portfolio_id),
            "ticker": h.ticker,
            "weight": h.weight,
            "cost_basis": h.cost_basis,
            "conviction_score": h.conviction_score,
            "updated_at": h.updated_at.isoformat(),
        }
        for h in holdings
    ]


class HoldingUpdate(BaseModel):
    ticker: str
    weight: float
    cost_basis: float
    conviction_score: Optional[int] = None


@app.post("/portfolios/{portfolio_id}/holdings")
def update_portfolio_holdings(
    portfolio_id: uuid.UUID,
    holdings_data: List[HoldingUpdate],
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(RoleChecker(HOLDINGS_WRITE_ROLES)),
):
    require_portfolio(db, portfolio_id, current_user.institution_id)
    db.query(models.Holding).filter(models.Holding.portfolio_id == portfolio_id).delete()
    new_holdings = [
        models.Holding(
            portfolio_id=portfolio_id,
            ticker=h.ticker.upper(),
            weight=h.weight,
            cost_basis=h.cost_basis,
            conviction_score=h.conviction_score,
        )
        for h in holdings_data
    ]
    db.add_all(new_holdings)
    db.commit()
    return {"status": "success", "count": len(new_holdings)}


@app.get("/ips_rules")
def list_ips_rules(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(RoleChecker(READ_ROLES)),
):
    rules = db.execute(
        select(models.IPSRule).where(models.IPSRule.institution_id == current_user.institution_id)
    ).scalars().all()
    return [
        {
            "id": str(r.id),
            "institution_id": str(r.institution_id),
            "rule_type": r.rule_type,
            "threshold": r.threshold,
            "severity": r.severity,
        }
        for r in rules
    ]


# ── User management (admin only) ──────────────────────────────────────────────

class RoleUpdate(BaseModel):
    role: str = Field(..., max_length=50)


@app.patch("/users/{user_id}/role")
def update_user_role(
    user_id: uuid.UUID,
    payload: RoleUpdate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(RoleChecker(ADMIN_ROLES)),
):
    """
    Assigns a new role to a user within the admin's own institution. Runs under the
    admin's RLS context, so users of other institutions are invisible (404).
    """
    if payload.role not in INVITABLE_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role. Must be one of: {', '.join(INVITABLE_ROLES)}",
        )
    target = db.execute(
        select(models.User).where(
            models.User.id == user_id,
            models.User.institution_id == current_user.institution_id,
        )
    ).scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.id == current_user.id and payload.role != "admin":
        raise HTTPException(
            status_code=400,
            detail="Admins cannot demote themselves to prevent lockouts",
        )
    target.role = payload.role
    return {"user_id": str(user_id), "role": payload.role}
