"""
Request authentication and tenant binding.

The institution a request operates on is derived ONLY from the authenticated user's
membership record. Client-supplied institution identifiers (headers, query params,
body fields) are never used to select a tenant.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import List, Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWTError
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app import models
from app.core import security
from app.core.config import settings
from app.db.session import get_db, set_tenant

reusable_oauth2 = HTTPBearer(auto_error=False)

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials.",
    headers={"WWW-Authenticate": "Bearer"},
)


@dataclass(frozen=True)
class CurrentUser:
    id: uuid.UUID
    institution_id: uuid.UUID
    email: str
    role: str


def resolve_user_institution_by_id(db: Session, user_id: uuid.UUID) -> Optional[uuid.UUID]:
    """Cross-tenant lookup via SECURITY DEFINER function; returns identifiers only."""
    row = db.execute(
        text("SELECT institution_id FROM app_resolve_user_by_id(:uid)"), {"uid": user_id}
    ).first()
    return row[0] if row else None


def resolve_user_by_email(db: Session, email: str) -> Optional[tuple[uuid.UUID, uuid.UUID]]:
    row = db.execute(
        text("SELECT user_id, institution_id FROM app_resolve_user_by_email(:email)"),
        {"email": email},
    ).first()
    return (row[0], row[1]) if row else None


def get_current_user(
    db: Session = Depends(get_db),
    token_creds: Optional[HTTPAuthorizationCredentials] = Depends(reusable_oauth2),
) -> Optional[CurrentUser]:
    """
    Validates the bearer token, resolves the user's institution, binds the DB session
    to that institution (RLS context), and returns the user loaded under RLS.
    Returns None when no credentials are supplied; RoleChecker turns that into 401.
    """
    if not token_creds:
        return None
    try:
        payload = jwt.decode(
            token_creds.credentials, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        user_id = uuid.UUID(str(payload.get("sub")))
    except (PyJWTError, ValueError):
        raise _UNAUTHORIZED

    token_jti = payload.get("jti")
    if token_jti and security.is_token_blacklisted(token_jti):
        raise _UNAUTHORIZED

    institution_id = resolve_user_institution_by_id(db, user_id)
    if institution_id is None:
        raise _UNAUTHORIZED
    set_tenant(db, institution_id)

    user = db.execute(select(models.User).where(models.User.id == user_id)).scalar_one_or_none()
    if user is None or not user.is_verified:
        raise _UNAUTHORIZED
    return CurrentUser(
        id=user.id, institution_id=user.institution_id, email=user.email, role=user.role
    )


class RoleChecker:
    def __init__(self, allowed_roles: List[str]):
        self.allowed_roles = allowed_roles

    def __call__(self, current_user: Optional[CurrentUser] = Depends(get_current_user)):
        if not current_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required for this operation.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if current_user.role not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Operation not permitted for your role.",
            )
        return current_user
