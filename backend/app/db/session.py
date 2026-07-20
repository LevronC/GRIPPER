from typing import Generator

from fastapi import HTTPException, Request
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError, ProgrammingError, DatabaseError
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.database_url import database_url_error_hint, safe_encode_database_url, validate_database_url

_SSL_HOSTS = ("supabase.co", "supabase.com", "pooler.supabase.com", "neon.tech", "neon.database", "vercel-postgres.com")


def _normalize_url(url: str) -> str:
    """SQLAlchemy 2.0 requires 'postgresql://' — Vercel Postgres provides 'postgres://'."""
    url = safe_encode_database_url(url)
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://"):]
    return url


def _engine_kwargs(url: str) -> dict:
    kwargs = {"pool_pre_ping": True}
    if any(host in url for host in _SSL_HOSTS):
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

_db_url = _normalize_url(settings.DATABASE_URL)
engine = create_engine(_db_url, **_engine_kwargs(_db_url))
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
    except (OperationalError, ProgrammingError, DatabaseError) as exc:
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
