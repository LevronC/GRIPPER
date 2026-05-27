from __future__ import annotations

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


def database_url_error_hint(url: str, exc: Exception | None = None) -> str:
    host = ""
    try:
        host = make_url(url).host or ""
    except ArgumentError:
        pass

    if "@" in host:
        return (
            "Database connection URL is malformed. If your Supabase/Postgres password "
            "contains special characters (@, #, /, :, ?, &), URL-encode them in "
            "DATABASE_URL and SUPERUSER_DATABASE_URL. Example: @ becomes %40."
        )

    message = str(exc or "")
    if "could not translate host name" in message and "@" in message:
        return (
            "Database host name looks invalid, usually because the password contains an "
            "unencoded @ character. URL-encode the password in DATABASE_URL "
            "(for example, replace @ with %40), then redeploy."
        )

    if "connection refused" in message or "timeout" in message:
        return (
            "Could not reach the database. On Vercel + Supabase, use the Session pooler "
            "URL on port 6543 with sslmode=require."
        )

    if "relation" in message and "does not exist" in message:
        return (
            "Database schema is missing. Migrations have not been applied yet. "
            "Redeploy after setting SUPERUSER_DATABASE_URL (Supabase session/direct "
            "connection, not transaction pooler) and check /api/health/db."
        )

    return f"Database connection failed: {message or 'unknown error'}"


def validate_database_url(url: str, label: str = "DATABASE_URL") -> None:
    try:
        parsed = make_url(url)
    except ArgumentError as exc:
        raise ValueError(f"{label} is invalid: {exc}") from exc

    if parsed.host and "@" in parsed.host:
        raise ValueError(database_url_error_hint(url))
