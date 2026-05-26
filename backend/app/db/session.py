import os
from typing import Generator
from fastapi import Request
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db(request: Request = None) -> Generator:
    db = SessionLocal()
    tenant_id = None
    if request:
        tenant_id = request.headers.get("X-Institution-ID")
    try:
        if tenant_id:
            # We execute SET to configure the session variable.
            # In PostgreSQL, RLS policies will reference 'app.current_institution_id'.
            # Session-scoped variables survive commits, which is required for SQLAlchemy
            # to reload newly committed objects under RLS rules.
            db.execute(
                text("SET app.current_institution_id = :tenant_id"),
                {"tenant_id": tenant_id}
            )
        else:
            db.execute(text("SET app.current_institution_id = ''"))
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
