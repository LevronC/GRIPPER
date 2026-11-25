"""
Investment Policy Statement (IPS) rule management.

Rules are data, not code: a rule is one of the fixed, implemented rule types with a
numeric threshold. Nothing user-supplied is ever evaluated as an expression.

Limitation (no policy versioning): a rule row is mutable. Updating a threshold affects
future evaluations only. Resolved governance events keep the threshold that applied when
they were detected (details_json.threshold); events that are still open are refreshed with
the current threshold on the next evaluation. Rules are deactivated, never deleted, so
historical events keep a valid rule_id.
"""

from __future__ import annotations

import uuid
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.api.deps import CurrentUser, RoleChecker
from app.api.tenancy import require_rule
from app.core.rbac import ADMIN_ROLES, READ_ROLES
from app.db.session import get_db

router = APIRouter(prefix="/ips_rules", tags=["ips_rules"])

RuleType = Literal["single_position_cap", "sector_exposure_cap", "liquidity_constraint"]
Severity = Literal["warning", "critical"]

# Thresholds are fractions of portfolio value: 0.10 means 10%.
Threshold = Field(..., gt=0.0, le=1.0, description="Fraction of portfolio value, e.g. 0.10 for 10%")


class RuleCreate(BaseModel):
    rule_type: RuleType
    threshold: float = Threshold
    severity: Severity = "warning"


class RuleUpdate(BaseModel):
    threshold: Optional[float] = Field(None, gt=0.0, le=1.0)
    severity: Optional[Severity] = None
    active: Optional[bool] = None


def _rule_json(r: models.IPSRule) -> dict:
    return {
        "id": str(r.id),
        "institution_id": str(r.institution_id),
        "rule_type": r.rule_type,
        "threshold": r.threshold,
        "severity": r.severity,
        "active": r.active,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _active_rule_of_type(db: Session, institution_id: uuid.UUID, rule_type: str, exclude: Optional[uuid.UUID] = None):
    stmt = select(models.IPSRule).where(
        models.IPSRule.institution_id == institution_id,
        models.IPSRule.rule_type == rule_type,
        models.IPSRule.active.is_(True),
    )
    if exclude:
        stmt = stmt.where(models.IPSRule.id != exclude)
    return db.execute(stmt).scalars().first()


@router.get("")
def list_rules(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(RoleChecker(READ_ROLES)),
):
    stmt = select(models.IPSRule).where(models.IPSRule.institution_id == user.institution_id)
    if not include_inactive:
        stmt = stmt.where(models.IPSRule.active.is_(True))
    return [_rule_json(r) for r in db.execute(stmt.order_by(models.IPSRule.created_at)).scalars()]


@router.post("", status_code=201)
def create_rule(
    payload: RuleCreate,
    db: Session = Depends(get_db),
    admin: CurrentUser = Depends(RoleChecker(ADMIN_ROLES)),
):
    # One active rule per type keeps evaluation unambiguous (no duplicate breaches).
    if _active_rule_of_type(db, admin.institution_id, payload.rule_type):
        raise HTTPException(status_code=409, detail=f"An active {payload.rule_type} rule already exists; update it instead.")
    rule = models.IPSRule(
        institution_id=admin.institution_id,
        rule_type=payload.rule_type,
        threshold=payload.threshold,
        severity=payload.severity,
        active=True,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return _rule_json(rule)


@router.patch("/{rule_id}")
def update_rule(
    rule_id: uuid.UUID,
    payload: RuleUpdate,
    db: Session = Depends(get_db),
    admin: CurrentUser = Depends(RoleChecker(ADMIN_ROLES)),
):
    rule = require_rule(db, rule_id, admin.institution_id)
    if payload.active and not rule.active and _active_rule_of_type(db, admin.institution_id, rule.rule_type, exclude=rule.id):
        raise HTTPException(status_code=409, detail=f"Another active {rule.rule_type} rule exists.")
    if payload.threshold is not None:
        rule.threshold = payload.threshold
    if payload.severity is not None:
        rule.severity = payload.severity
    if payload.active is not None:
        rule.active = payload.active
    db.commit()
    db.refresh(rule)
    return _rule_json(rule)


@router.post("/{rule_id}/deactivate")
def deactivate_rule(
    rule_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: CurrentUser = Depends(RoleChecker(ADMIN_ROLES)),
):
    rule = require_rule(db, rule_id, admin.institution_id)
    rule.active = False
    db.commit()
    db.refresh(rule)
    return _rule_json(rule)
