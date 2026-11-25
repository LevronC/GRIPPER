"""
Authentication: login, logout, invitation acceptance, password reset.

There is no public self-registration. Accounts are created only by redeeming an
invitation an institution admin issued (app/api/admin.py), which fixes the
institution and role server-side.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models
from app.api.deps import resolve_user_by_email
from app.core import rate_limit, security
from app.core.config import settings
from app.core.email import EmailUnavailable, app_link, email_delivery_available, send_email
from app.core.tokens import hash_token, new_token
from app.db.session import get_db, set_tenant

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])
reusable_oauth2 = HTTPBearer(auto_error=False)

RESET_TOKEN_TTL = timedelta(minutes=30)
RESET_TOKENS_PER_ACCOUNT_PER_HOUR = 3

_INVALID_CREDENTIALS = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Incorrect email or password.",
    headers={"WWW-Authenticate": "Bearer"},
)
_INVALID_INVITATION = HTTPException(status_code=400, detail="Invalid or expired invitation.")
_INVALID_RESET = HTTPException(status_code=400, detail="Invalid or expired reset link.")


def _utcnow() -> datetime:
    # DB columns are naive UTC timestamps.
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ── Schemas ──────────────────────────────────────────────────────────────────

class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(..., max_length=256)


class Token(BaseModel):
    access_token: str
    token_type: str
    role: str
    institution_id: str
    user_id: str
    email: str
    graduation_year: Optional[int] = None


class AcceptInvitation(BaseModel):
    token: str = Field(..., min_length=20, max_length=128)
    email: EmailStr
    password: str
    graduation_year: Optional[int] = Field(None, ge=1990, le=2100)

    @field_validator("password")
    @classmethod
    def _policy(cls, v: str) -> str:
        return security.validate_password_policy(v)


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str = Field(..., min_length=20, max_length=128)
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _policy(cls, v: str) -> str:
        return security.validate_password_policy(v)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _load_user_by_email(db: Session, email: str) -> Optional[models.User]:
    """
    Resolve the user's institution through the SECURITY DEFINER lookup, bind the
    session to it, then read the full row under RLS. No RLS-bypassing connection.
    """
    resolved = resolve_user_by_email(db, email)
    if not resolved:
        return None
    user_id, institution_id = resolved
    set_tenant(db, institution_id)
    return db.execute(select(models.User).where(models.User.id == user_id)).scalar_one_or_none()


def _token_response(user: models.User) -> dict:
    return {
        "access_token": security.create_access_token(user.id, user.token_version),
        "token_type": "bearer",
        "role": user.role,
        "institution_id": str(user.institution_id),
        "user_id": str(user.id),
        "email": user.email,
        "graduation_year": user.graduation_year,
    }


# ── Login / logout ───────────────────────────────────────────────────────────

@router.post("/login", response_model=Token)
def login_user(credentials: UserLogin, request: Request, db: Session = Depends(get_db)):
    ip = rate_limit.client_ip(request)
    rate_limit.enforce("login-ip", ip, limit=30, window_seconds=300)
    rate_limit.enforce("login-email", credentials.email, limit=10, window_seconds=300)

    db_user = _load_user_by_email(db, credentials.email)
    if not db_user or not db_user.hashed_password:
        security.verify_password(credentials.password, security.DUMMY_PASSWORD_HASH)
        raise _INVALID_CREDENTIALS
    if not security.verify_password(credentials.password, db_user.hashed_password):
        raise _INVALID_CREDENTIALS
    if not db_user.is_verified:
        raise _INVALID_CREDENTIALS
    return _token_response(db_user)


@router.post("/logout")
def logout(token_creds: Optional[HTTPAuthorizationCredentials] = Depends(reusable_oauth2)):
    """
    Revokes the presented token by JTI. Requires Redis; without it the token stays
    valid until it expires, and the response says so (`revoked: false`).
    """
    if not token_creds:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    revoked = False
    try:
        payload = jwt.decode(
            token_creds.credentials, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        token_jti, exp = payload.get("jti"), payload.get("exp")
        if token_jti and exp:
            ttl = int(exp - datetime.now(timezone.utc).timestamp())
            if ttl > 0:
                revoked = security.blacklist_token(token_jti, ttl)
    except jwt.PyJWTError:
        pass
    return {"message": "Logged out", "revoked": revoked}


# ── Invitations ──────────────────────────────────────────────────────────────

@router.post("/invitations/accept", status_code=201)
def accept_invitation(payload: AcceptInvitation, request: Request, db: Session = Depends(get_db)):
    rate_limit.enforce("invite-accept-ip", rate_limit.client_ip(request), limit=20, window_seconds=600)

    row = db.execute(
        text("SELECT invitation_id, institution_id FROM app_resolve_invitation(:h)"),
        {"h": hash_token(payload.token)},
    ).first()
    if not row:
        raise _INVALID_INVITATION
    invitation_id, institution_id = row
    set_tenant(db, institution_id)

    invitation = db.execute(
        select(models.Invitation)
        .where(models.Invitation.id == invitation_id, models.Invitation.institution_id == institution_id)
        .with_for_update()
    ).scalar_one_or_none()
    now = _utcnow()
    if (
        invitation is None
        or invitation.accepted_at is not None
        or invitation.revoked_at is not None
        or invitation.expires_at <= now
        or invitation.email.lower() != payload.email.lower()
    ):
        raise _INVALID_INVITATION
    if resolve_user_by_email(db, payload.email):
        raise _INVALID_INVITATION  # account already exists; do not confirm which

    user = models.User(
        institution_id=invitation.institution_id,  # from the invitation, never the client
        email=invitation.email.lower(),
        hashed_password=security.get_password_hash(payload.password),
        role=invitation.role,                        # from the invitation, never the client
        graduation_year=payload.graduation_year,
        is_verified=True,                            # possession of the emailed token proves the address
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise _INVALID_INVITATION
    invitation.accepted_at = now
    invitation.accepted_user_id = user.id
    logger.info("Invitation %s accepted", invitation.id)
    return {"message": "Account created. You can now sign in."}


# ── Password reset ───────────────────────────────────────────────────────────

_RESET_ACK = {"message": "If an account exists for that email, a reset link has been sent."}


@router.post("/password-reset/request", status_code=202)
def request_password_reset(payload: PasswordResetRequest, request: Request, db: Session = Depends(get_db)):
    if not email_delivery_available():
        # Same answer for every email address, so this reveals nothing about accounts.
        raise HTTPException(status_code=503, detail="Password reset is unavailable: email delivery is not configured.")
    rate_limit.enforce("reset-request-ip", rate_limit.client_ip(request), limit=10, window_seconds=3600)
    rate_limit.enforce("reset-request-email", payload.email, limit=5, window_seconds=3600)

    user = _load_user_by_email(db, payload.email)
    if not user or not user.is_verified:
        return _RESET_ACK

    now = _utcnow()
    recent = db.execute(
        select(func.count(models.PasswordResetToken.id)).where(
            models.PasswordResetToken.user_id == user.id,
            models.PasswordResetToken.created_at > now - timedelta(hours=1),
        )
    ).scalar() or 0
    if recent >= RESET_TOKENS_PER_ACCOUNT_PER_HOUR:
        return _RESET_ACK  # silently capped; response must not differ

    # Only the newest link is valid.
    db.execute(
        update(models.PasswordResetToken)
        .where(models.PasswordResetToken.user_id == user.id, models.PasswordResetToken.used_at.is_(None))
        .values(used_at=now)
    )
    raw, token_hash = new_token()
    db.add(models.PasswordResetToken(
        user_id=user.id, institution_id=user.institution_id, token_hash=token_hash,
        expires_at=now + RESET_TOKEN_TTL, created_at=now,
    ))
    db.flush()
    try:
        send_email(
            user.email,
            "Reset your Gripper password",
            "A password reset was requested for your Gripper account.\n\n"
            f"Reset link (valid for {int(RESET_TOKEN_TTL.total_seconds() // 60)} minutes):\n"
            f"{app_link('reset=' + raw)}\n\nIf you did not request this, ignore this email.",
        )
    except EmailUnavailable:
        db.rollback()
        raise HTTPException(status_code=503, detail="Password reset is temporarily unavailable.")
    return _RESET_ACK


@router.post("/password-reset/confirm")
def confirm_password_reset(payload: PasswordResetConfirm, request: Request, db: Session = Depends(get_db)):
    rate_limit.enforce("reset-confirm-ip", rate_limit.client_ip(request), limit=20, window_seconds=600)

    row = db.execute(
        text("SELECT token_id, institution_id FROM app_resolve_password_reset(:h)"),
        {"h": hash_token(payload.token)},
    ).first()
    if not row:
        raise _INVALID_RESET
    token_id, institution_id = row
    set_tenant(db, institution_id)

    token = db.execute(
        select(models.PasswordResetToken).where(models.PasswordResetToken.id == token_id).with_for_update()
    ).scalar_one_or_none()
    now = _utcnow()
    if token is None or token.used_at is not None or token.expires_at <= now:
        raise _INVALID_RESET
    user = db.execute(select(models.User).where(models.User.id == token.user_id)).scalar_one_or_none()
    if user is None:
        raise _INVALID_RESET

    user.hashed_password = security.get_password_hash(payload.new_password)
    user.token_version = (user.token_version or 0) + 1  # revokes every existing session
    db.execute(
        update(models.PasswordResetToken)
        .where(models.PasswordResetToken.user_id == user.id, models.PasswordResetToken.used_at.is_(None))
        .values(used_at=now)
    )
    logger.info("Password reset completed for user %s", uuid.UUID(str(user.id)))
    # Deliberately no access token: the user signs in with the new password.
    return {"message": "Password updated. Sign in with your new password."}
