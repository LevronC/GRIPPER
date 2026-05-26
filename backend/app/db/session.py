import os
from typing import Generator
from fastapi import Request
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

def _engine_kwargs(url: str) -> dict:
    kwargs = {"pool_pre_ping": True}
    if "supabase.co" in url:
        kwargs["connect_args"] = {"sslmode": "require"}
    return kwargs

engine = create_engine(settings.DATABASE_URL, **_engine_kwargs(settings.DATABASE_URL))
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db(request: Request) -> Generator:
    db = SessionLocal()
    tenant_id = None
    if request:
        tenant_id = request.headers.get("X-Institution-ID")
    try:
        if tenant_id:
            # We execute SET LOCAL to configure the transaction-scoped variable.
            # This ensures that connection poolers (like PgBouncer in transaction mode) 
            # cannot leak tenant context across pooled connections.
            db.execute(
                text("SET LOCAL app.current_institution_id = :tenant_id"),
                {"tenant_id": tenant_id}
            )
        else:
            db.execute(text("SET LOCAL app.current_institution_id = ''"))
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
