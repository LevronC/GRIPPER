import os
from typing import Generator

from fastapi import HTTPException, Request
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.database_url import database_url_error_hint, validate_database_url

def _engine_kwargs(url: str) -> dict:
    kwargs = {"pool_pre_ping": True}
    if "supabase.co" in url:
        kwargs["connect_args"] = {"sslmode": "require"}
    return kwargs

for _label, _url in (
    ("DATABASE_URL", settings.DATABASE_URL),
    ("SUPERUSER_DATABASE_URL", settings.SUPERUSER_DATABASE_URL),
):
    try:
        validate_database_url(_url, _label)
    except ValueError:
        # Do not crash import on local dev; production requests will surface the error.
        pass

engine = create_engine(settings.DATABASE_URL, **_engine_kwargs(settings.DATABASE_URL))
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db(request: Request) -> Generator:
    db = SessionLocal()
    tenant_id = None
    if request:
        tenant_id = request.headers.get("X-Institution-ID")
    try:
        if tenant_id:
            db.execute(
                text("SET LOCAL app.current_institution_id = :tenant_id"),
                {"tenant_id": tenant_id}
            )
        else:
            db.execute(text("SET LOCAL app.current_institution_id = ''"))
        yield db
        db.commit()
    except OperationalError as exc:
        db.rollback()
        raise HTTPException(
            status_code=503,
            detail=database_url_error_hint(settings.DATABASE_URL, exc),
        ) from exc
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
