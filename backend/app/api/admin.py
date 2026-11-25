"""
Institution administration: invitations.

Only admins of an institution may invite, and only into their own institution:
the institution comes from the authenticated admin, never from the request.
Institutions themselves are provisioned out-of-band with the owner connection
(scripts/provision_institution.py); there is no API to create tenants.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app import models
from app.api.deps import CurrentUser, RoleChecker, resolve_user_by_email
from app.core.email import EmailUnavailable, app_link, email_delivery_available, send_email
from app.core.rbac import ADMIN_ROLES, INVITABLE_ROLES
from app.core.tokens import new_token
from app.db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

INVITATION_TTL = timedelta(hours=72)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class InvitationCreate(BaseModel):
    email: EmailStr
    role: Literal[tuple(INVITABLE_ROLES)]  # type: ignore[valid-type]


def _invitation_json(inv: models.Invitation) -> dict:
    now = _utcnow()
    if inv.accepted_at:
        state = "accepted"
    elif inv.revoked_at:
        state = "revoked"
    elif inv.expires_at <= now:
        state = "expired"
    else:
        state = "pending"
    return {
        "id": str(inv.id),
        "email": inv.email,
        "role": inv.role,
        "status": state,
        "expires_at": inv.expires_at.isoformat(),
        "created_at": inv.created_at.isoformat() if inv.created_at else None,
    }


@router.post("/invitations", status_code=201)
def create_invitation(
    payload: InvitationCreate,
    db: Session = Depends(get_db),
    admin: CurrentUser = Depends(RoleChecker(ADMIN_ROLES)),
):
    if not email_delivery_available():
        raise HTTPException(status_code=503, detail="Invitations are unavailable: email delivery is not configured.")
    email = payload.email.lower()
    if resolve_user_by_email(db, email):
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    now = _utcnow()
    # Supersede earlier pending invitations for the same address in this institution.
    db.execute(
        update(models.Invitation)
        .where(
            models.Invitation.institution_id == admin.institution_id,
            models.Invitation.email == email,
            models.Invitation.accepted_at.is_(None),
            models.Invitation.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    raw, token_hash = new_token()
    inv = models.Invitation(
        id=uuid.uuid4(),
        institution_id=admin.institution_id,
        email=email,
        role=payload.role,
        token_hash=token_hash,
        expires_at=now + INVITATION_TTL,
        created_by=admin.id,
        created_at=now,
    )
    db.add(inv)
    db.flush()
    institution = db.get(models.Institution, admin.institution_id)
    try:
        send_email(
            email,
            f"You're invited to {institution.name} on Gripper",
            f"{admin.email} invited you to join {institution.name} as {payload.role}.\n\n"
            f"Accept within {int(INVITATION_TTL.total_seconds() // 3600)} hours:\n"
            f"{app_link('invite=' + raw)}\n",
        )
    except EmailUnavailable:
        db.rollback()
        raise HTTPException(status_code=503, detail="Invitation email could not be sent; nothing was created.")
    logger.info("Invitation %s created by %s", inv.id, admin.id)
    return _invitation_json(inv)  # never includes the token


@router.get("/invitations")
def list_invitations(
    db: Session = Depends(get_db),
    admin: CurrentUser = Depends(RoleChecker(ADMIN_ROLES)),
):
    rows = db.execute(
        select(models.Invitation)
        .where(models.Invitation.institution_id == admin.institution_id)
        .order_by(models.Invitation.created_at.desc())
        .limit(200)
    ).scalars().all()
    return [_invitation_json(i) for i in rows]


@router.delete("/invitations/{invitation_id}")
def revoke_invitation(
    invitation_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: CurrentUser = Depends(RoleChecker(ADMIN_ROLES)),
):
    inv = db.execute(
        select(models.Invitation).where(
            models.Invitation.id == invitation_id,
            models.Invitation.institution_id == admin.institution_id,
        )
    ).scalar_one_or_none()
    if inv is None:
        raise HTTPException(status_code=404, detail="Invitation not found")
    if inv.accepted_at is None and inv.revoked_at is None:
        inv.revoked_at = _utcnow()
    return _invitation_json(inv)
