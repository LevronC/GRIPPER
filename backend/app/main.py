import logging
import os
import uuid
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.api.auth import router as auth_router, get_superuser_session
from app.api.deps import get_current_user, RoleChecker
from app.core.rbac import (
    ADMIN_ROLES,
    ALL_ROLES as _ALL_ROLES,
    COMPLIANCE_ROLES,
    HOLDINGS_WRITE_ROLES,
    PORTFOLIO_WRITE_ROLES,
    READ_ROLES,
)
from app.core.config import settings
from app.core.database_url import database_url_error_hint
from app import models
from app.api.endpoints import router as api_router
from app.db.migrate import ensure_database_ready
from app.db.seed import DEFAULT_INSTITUTIONS
from app.db.session import get_db, engine

logger = logging.getLogger(__name__)

SWAGGER_OPENAPI_URL = os.getenv("SWAGGER_OPENAPI_URL", "/openapi.json")
public_bearer = HTTPBearer(auto_error=False)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        ensure_database_ready()
    except Exception as exc:
        logger.warning("Database bootstrap skipped or failed (%s)", exc)
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
    """Lightweight DB connectivity check — reuses the existing engine pool."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            users_exists = conn.execute(
                text(
                    "SELECT EXISTS ("
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name = 'users'"
                    ")"
                )
            ).scalar()
        return {
            "status": "ok",
            "database": "connected",
            "schema_ready": bool(users_exists),
        }
    except OperationalError as exc:
        raise HTTPException(
            status_code=503,
            detail=database_url_error_hint(settings.DATABASE_URL, exc),
        ) from exc


# ── Institutions ──────────────────────────────────────────────────────────────

@app.post("/institutions")
def create_institution(
    name: str,
    slug: str,
    db: Session = Depends(get_db),
    current_user=Depends(RoleChecker(ADMIN_ROLES)),
):
    inst = models.Institution(name=name, slug=slug)
    db.add(inst)
    db.commit()
    db.refresh(inst)
    return {
        "id": str(inst.id),
        "name": inst.name,
        "slug": inst.slug,
        "tier": inst.tier,
        "created_at": inst.created_at,
    }


@app.get("/institutions")
def list_institutions(
    token_creds: Optional[HTTPAuthorizationCredentials] = Depends(public_bearer),
):
    """
    Returns the list of institutions.
    Authenticated requests receive only their own institution.
    Unauthenticated requests receive all institutions (needed for the sign-in form).
    """
    institution_filter_id = None
    if token_creds:
        try:
            payload = jwt.decode(
                token_creds.credentials,
                settings.SECRET_KEY,
                algorithms=[settings.ALGORITHM],
            )
            user_id = payload.get("sub")
            if user_id:
                with get_superuser_session() as db:
                    user = db.query(models.User).filter(
                        models.User.id == uuid.UUID(user_id)
                    ).first()
                    if user:
                        institution_filter_id = user.institution_id
        except (JWTError, ValueError):
            pass

    try:
        with get_superuser_session() as db:
            query = db.query(models.Institution)
            if institution_filter_id:
                query = query.filter(models.Institution.id == institution_filter_id)
            else:
                query = query.order_by(models.Institution.name)
            institutions = query.all()

            if institutions:
                return [
                    {
                        "id": str(i.id),
                        "name": i.name,
                        "slug": i.slug,
                        "tier": i.tier,
                        "created_at": i.created_at,
                    }
                    for i in institutions
                ]
    except Exception:
        pass

    fallback = DEFAULT_INSTITUTIONS
    if institution_filter_id:
        fallback = [item for item in fallback if item["id"] == institution_filter_id]

    return [
        {"id": str(item["id"]), "name": item["name"], "slug": item["slug"], "tier": item["tier"]}
        for item in fallback
    ]


# ── Portfolios ────────────────────────────────────────────────────────────────

@app.post("/portfolios")
def create_portfolio(
    name: str,
    strategy_type: str,
    db: Session = Depends(get_db),
    current_user=Depends(RoleChecker(PORTFOLIO_WRITE_ROLES)),
):
    res = db.execute(text("SHOW app.current_institution_id")).scalar()
    if not res or res == "":
        raise HTTPException(
            status_code=400,
            detail="X-Institution-ID header or token is required to create a portfolio",
        )
    portfolio = models.Portfolio(
        institution_id=uuid.UUID(res),
        name=name,
        strategy_type=strategy_type,
    )
    db.add(portfolio)
    db.commit()
    db.refresh(portfolio)
    return {
        "id": str(portfolio.id),
        "name": portfolio.name,
        "strategy_type": portfolio.strategy_type,
        "institution_id": str(portfolio.institution_id),
    }


@app.get("/portfolios")
def list_portfolios(
    db: Session = Depends(get_db),
    current_user=Depends(RoleChecker(READ_ROLES)),
):
    res = db.execute(text("SHOW app.current_institution_id")).scalar()
    if not res or res == "":
        raise HTTPException(
            status_code=400,
            detail="X-Institution-ID header or token is required to retrieve portfolios",
        )
    portfolios = db.query(models.Portfolio).all()
    return [
        {
            "id": str(p.id),
            "name": p.name,
            "strategy_type": p.strategy_type,
            "institution_id": str(p.institution_id),
        }
        for p in portfolios
    ]


@app.get("/portfolios/{portfolio_id}/holdings")
def list_portfolio_holdings(
    portfolio_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user=Depends(RoleChecker(READ_ROLES)),
):
    res = db.execute(text("SHOW app.current_institution_id")).scalar()
    if not res or res == "":
        raise HTTPException(status_code=400, detail="X-Institution-ID header or token is required")
    holdings = db.query(models.Holding).filter(models.Holding.portfolio_id == portfolio_id).all()
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
    current_user=Depends(RoleChecker(HOLDINGS_WRITE_ROLES)),
):
    res = db.execute(text("SHOW app.current_institution_id")).scalar()
    if not res or res == "":
        raise HTTPException(status_code=400, detail="X-Institution-ID header or token is required")
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
    current_user=Depends(RoleChecker(READ_ROLES)),
):
    res = db.execute(text("SHOW app.current_institution_id")).scalar()
    if not res or res == "":
        raise HTTPException(status_code=400, detail="X-Institution-ID header or token is required")
    rules = db.query(models.IPSRule).all()
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
    role: str


@app.patch("/users/{user_id}/role")
def update_user_role(
    user_id: uuid.UUID,
    payload: RoleUpdate,
    current_user=Depends(RoleChecker(ADMIN_ROLES)),
):
    """
    Assigns a new role to a user within the same institution.
    Admin-only. This is the only way to grant privileged roles (pm, trustee, admin)
    since self-registration is limited to analyst/sector_lead/faculty.
    """
    if payload.role not in _ALL_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role. Must be one of: {', '.join(_ALL_ROLES)}",
        )

    with get_superuser_session() as db:
        target = db.query(models.User).filter(models.User.id == user_id).first()

        if not target:
            raise HTTPException(status_code=404, detail="User not found")

        if str(target.institution_id) != str(current_user.institution_id):
            raise HTTPException(
                status_code=403,
                detail="You may only manage users within your own institution",
            )

        if target.id == current_user.id and payload.role != "admin":
            raise HTTPException(
                status_code=400,
                detail="Admins cannot demote themselves to prevent lockouts",
            )

        target.role = payload.role
        db.commit()

    return {"user_id": str(user_id), "role": payload.role}
