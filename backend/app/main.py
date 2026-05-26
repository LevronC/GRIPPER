import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy import text
import uuid
from pydantic import BaseModel
from typing import List, Optional
from jose import jwt, JWTError

from .db.session import get_db
from .db.seed import seed_default_data, DEFAULT_INSTITUTIONS
from . import models
from .api.endpoints import router as api_router
from app.api.auth import router as auth_router, get_superuser_session
from app.api.deps import get_current_user, RoleChecker
from app.core.config import settings

SWAGGER_OPENAPI_URL = os.getenv("SWAGGER_OPENAPI_URL", "/openapi.json")
public_bearer = HTTPBearer(auto_error=False)

@asynccontextmanager
async def lifespan(_app: FastAPI):
    seed_default_data()
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
        "health": "/health"
    }

@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "gripper-backend"}

@app.post("/institutions")
def create_institution(name: str, slug: str, db: Session = Depends(get_db)):
    # Creating an institution doesn't require tenant context.
    # We bypass RLS by not setting the X-Institution-ID header.
    inst = models.Institution(name=name, slug=slug)
    db.add(inst)
    db.commit()
    db.refresh(inst)
    return {
        "id": str(inst.id),
        "name": inst.name,
        "slug": inst.slug,
        "tier": inst.tier,
        "created_at": inst.created_at
    }

@app.post("/portfolios")
def create_portfolio(name: str, strategy_type: str, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    # Retrieve current institution from connection context (configured via dependency)
    res = db.execute(text("SHOW app.current_institution_id")).scalar()
    if not res or res == "":
        raise HTTPException(status_code=400, detail="X-Institution-ID header or token is required to create a portfolio")
    
    portfolio = models.Portfolio(
        institution_id=uuid.UUID(res),
        name=name,
        strategy_type=strategy_type
    )
    db.add(portfolio)
    db.commit()
    db.refresh(portfolio)
    return {
        "id": str(portfolio.id),
        "name": portfolio.name,
        "strategy_type": portfolio.strategy_type,
        "institution_id": str(portfolio.institution_id)
    }

@app.get("/portfolios")
def list_portfolios(db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    res = db.execute(text("SHOW app.current_institution_id")).scalar()
    if not res or res == "":
         raise HTTPException(status_code=400, detail="X-Institution-ID header or token is required to retrieve portfolios")
    
    # Due to Row-Level Security (RLS) configured in database,
    # this query will automatically be filtered by the database engine.
    portfolios = db.query(models.Portfolio).all()
    return [
        {
            "id": str(p.id),
            "name": p.name,
            "strategy_type": p.strategy_type,
            "institution_id": str(p.institution_id)
        }
        for p in portfolios
    ]

@app.get("/institutions")
def list_institutions(
    token_creds: Optional[HTTPAuthorizationCredentials] = Depends(public_bearer),
):
    """
    Returns list of institutions.
    - If unauthenticated (sign-in/sign-up): returns all available tenants.
    - If authenticated: returns ONLY the user's bound institution for security.
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
                    user = db.query(models.User).filter(models.User.id == uuid.UUID(user_id)).first()
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
        {
            "id": str(item["id"]),
            "name": item["name"],
            "slug": item["slug"],
            "tier": item["tier"],
        }
        for item in fallback
    ]

@app.get("/portfolios/{portfolio_id}/holdings")
def list_portfolio_holdings(portfolio_id: uuid.UUID, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
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
            "updated_at": h.updated_at.isoformat()
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
    current_user = Depends(RoleChecker(["pm", "sector_lead", "admin"]))
):
    res = db.execute(text("SHOW app.current_institution_id")).scalar()
    if not res or res == "":
        raise HTTPException(status_code=400, detail="X-Institution-ID header or token is required")
    
    # Clear existing holdings and save the new ones
    db.query(models.Holding).filter(models.Holding.portfolio_id == portfolio_id).delete()
    
    new_holdings = [
        models.Holding(
            portfolio_id=portfolio_id,
            ticker=h.ticker.upper(),
            weight=h.weight,
            cost_basis=h.cost_basis,
            conviction_score=h.conviction_score
        )
        for h in holdings_data
    ]
    db.add_all(new_holdings)
    db.commit()
    return {"status": "success", "count": len(new_holdings)}

@app.get("/ips_rules")
def list_ips_rules(db: Session = Depends(get_db), current_user = Depends(get_current_user)):
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
            "severity": r.severity
        }
        for r in rules
    ]

