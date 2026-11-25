"""
Database sessions with transaction-scoped tenant context.

Tenant isolation model (see docs/DATABASE_SECURITY.md):

* Request handlers use ONE engine, connected as a restricted role that is a member
  of ``gripper_runtime`` (NOSUPERUSER, NOBYPASSRLS, not the table owner).
* The tenant is stored on the Session (``session.info["tenant_id"]``) and applied
  with ``set_config('app.current_institution_id', <id>, true)`` at the start of
  EVERY transaction via an ``after_begin`` hook. ``is_local=true`` scopes the value
  to the transaction, so it is discarded on COMMIT/ROLLBACK and can never leak to
  the next user of a pooled connection.
* A session with no tenant sets the value to '' explicitly. Every RLS policy maps ''
  to NULL, so missing context fails closed (no rows visible, inserts rejected).
"""

from __future__ import annotations

import logging
import threading
import uuid
from typing import Generator, Optional

from fastapi import HTTPException
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.core.database_url import normalize_database_url, validate_database_url

logger = logging.getLogger(__name__)

_SSL_HOSTS = ("supabase.co", "supabase.com", "pooler.supabase.com", "neon.tech", "neon.database", "vercel-postgres.com")

# Tables whose rows are tenant-scoped and protected by RLS.
PROTECTED_TABLES = (
    "users",
    "portfolios",
    "holdings",
    "research_reports",
    "document_chunks",
    "meetings",
    "ips_rules",
    "governance_events",
    "invitations",
    "password_reset_tokens",
)

TENANT_SETTING = "app.current_institution_id"


def _normalize_url(url: str) -> str:
    return normalize_database_url(url)


def _engine_kwargs(url: str) -> dict:
    kwargs: dict = {"pool_pre_ping": True}
    if any(host in url for host in _SSL_HOSTS):
        kwargs["connect_args"] = {"sslmode": "require"}
    return kwargs


try:
    validate_database_url(settings.DATABASE_URL, "DATABASE_URL")
except ValueError:
    # Do not crash import on local dev; requests will surface the error.
    pass


class TenantSession(Session):
    """Session subclass so the tenant hook applies to every session we create."""


@event.listens_for(TenantSession, "after_begin")
def _apply_tenant_context(session: Session, _transaction, connection) -> None:
    tenant = session.info.get("tenant_id")
    connection.execute(
        text("SELECT set_config(:name, :value, true)"),
        {"name": TENANT_SETTING, "value": str(tenant) if tenant else ""},
    )


def set_tenant(db: Session, institution_id: Optional[uuid.UUID]) -> None:
    """
    Bind the session to an institution. Applies immediately to the open transaction
    (if any) and to every later transaction on this session via the hook above.
    """
    db.info["tenant_id"] = str(institution_id) if institution_id else None
    if db.in_transaction():
        db.execute(
            text("SELECT set_config(:name, :value, true)"),
            {"name": TENANT_SETTING, "value": db.info["tenant_id"] or ""},
        )


def make_session_factory(url: str) -> sessionmaker:
    url = _normalize_url(url)
    eng = create_engine(url, **_engine_kwargs(url))
    return sessionmaker(bind=eng, class_=TenantSession, autocommit=False, autoflush=False)


SessionLocal = make_session_factory(settings.DATABASE_URL)
engine = SessionLocal.kw["bind"]


# ── Runtime role safety ───────────────────────────────────────────────────────

_ROLE_REPORT_SQL = text(
    """
    SELECT current_user                      AS current_user,
           session_user                      AS session_user,
           r.rolsuper                        AS rolsuper,
           r.rolbypassrls                    AS rolbypassrls,
           ARRAY(
             SELECT c.relname FROM pg_class c
             JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE n.nspname = 'public' AND c.relname = ANY(:tables)
               AND pg_has_role(current_user, c.relowner, 'USAGE')
           )                                 AS owned_tables,
           ARRAY(
             SELECT c.relname FROM pg_class c
             JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE n.nspname = 'public' AND c.relname = ANY(:tables)
               AND NOT (c.relrowsecurity AND c.relforcerowsecurity)
           )                                 AS tables_without_forced_rls
    FROM pg_roles r
    WHERE r.rolname = current_user
    """
)


def database_role_report(conn) -> dict:
    """Read-only privilege report for the role behind `conn`."""
    row = conn.execute(_ROLE_REPORT_SQL, {"tables": list(PROTECTED_TABLES)}).mappings().one()
    report = dict(row)
    report["owned_tables"] = list(report["owned_tables"])
    report["tables_without_forced_rls"] = list(report["tables_without_forced_rls"])
    problems = []
    if report["rolsuper"]:
        problems.append("runtime role is a superuser (bypasses RLS)")
    if report["rolbypassrls"]:
        problems.append("runtime role has BYPASSRLS")
    if report["owned_tables"]:
        problems.append("runtime role owns (or inherits ownership of) protected tables")
    if report["tables_without_forced_rls"]:
        problems.append("RLS is not enabled+forced on some protected tables")
    report["problems"] = problems
    report["rls_enforced"] = not problems
    return report


_role_check_lock = threading.Lock()
_role_check_result: Optional[dict] = None


def runtime_role_check() -> dict:
    """Cached once per process (cheap; one catalog query on first DB use)."""
    global _role_check_result
    if _role_check_result is not None:
        return _role_check_result
    with _role_check_lock:
        if _role_check_result is None:
            with engine.connect() as conn:
                report = database_role_report(conn)
            if report["problems"]:
                logger.error("Unsafe runtime database role: %s", "; ".join(report["problems"]))
            _role_check_result = report
    return _role_check_result


def _reset_role_check_cache() -> None:  # used by tests
    global _role_check_result
    _role_check_result = None


def _enforce_role_safety() -> None:
    try:
        report = runtime_role_check()
    except OperationalError as exc:
        logger.error("Database unavailable during role check: %s", exc)
        raise HTTPException(status_code=503, detail="Database unavailable.") from exc
    if report["problems"] and settings.DB_ROLE_SAFETY == "enforce":
        raise HTTPException(
            status_code=503,
            detail="Database is misconfigured: the runtime role can bypass row-level security.",
        )


def get_db() -> Generator[Session, None, None]:
    _enforce_role_safety()
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except OperationalError as exc:
        db.rollback()
        logger.error("Database operational error: %s", exc)
        raise HTTPException(status_code=503, detail="Database unavailable.") from exc
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
