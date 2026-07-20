from __future__ import annotations

import re
from urllib.parse import quote_plus, unquote
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


def safe_encode_database_url(url: str) -> str:
    """
    Safely URL-encodes special characters in the password component of a PostgreSQL connection URL.
    This prevents breakdown in SQLAlchemy URL parsing when passwords contain symbols like @, #, ?, /, :, %, &.
    """
    if not url:
        return url

    pattern = r"^(postgresql(?:\+[a-z0-9_]+)?://)([^:]+):(.*)@([^/@]+)(/[^?]*)(?:\?(.*))?$"
    match = re.match(pattern, url)
    if not match:
        return url

    scheme, username, password, host_port, path, query = match.groups()

    clean_password = unquote(password)
    encoded_password = quote_plus(clean_password)

    res = f"{scheme}{username}:{encoded_password}@{host_port}{path}"
    if query:
        res += f"?{query}"
    return res


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

    if (
        "connection refused" in message
        or "timeout" in message
        or "cannot assign requested address" in message
    ):
        return (
            "Could not reach the database. Vercel cannot connect to Supabase's IPv6-only "
            "direct database host. Use the Supabase Transaction pooler URL "
            "(aws-<region>.pooler.supabase.com:6543) with sslmode=require."
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
