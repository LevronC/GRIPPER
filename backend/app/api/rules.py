"""
Investment Policy Statement (IPS) rule management.

Rules are data, not code: a rule is one of the fixed, implemented rule types with a
numeric threshold. Nothing user-supplied is ever evaluated as an expression.

Scope: a rule may be global (scope NULL) or narrowed to one ticker (single_position_cap)
or one sector (sector_exposure_cap). Several active rules of the same type may coexist
if their scopes differ; each is evaluated independently (no precedence or override).
At most one active rule exists per (institution, rule_type, scope), enforced by a
partial unique index. A rule's type and scope are immutable: deactivate it and create
a new one instead.

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
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models
from app.api.deps import CurrentUser, RoleChecker
from app.api.tenancy import require_rule
from app.core.rbac import ADMIN_ROLES, READ_ROLES
from app.db.session import get_db
from app.services.governance.rules import KNOWN_SECTORS

router = APIRouter(prefix="/ips_rules", tags=["ips_rules"])

RuleType = Literal["single_position_cap", "sector_exposure_cap", "liquidity_constraint"]
Severity = Literal["warning", "critical"]

# Thresholds are fractions of portfolio value: 0.10 means 10%.
Threshold = Field(..., gt=0.0, le=1.0, allow_inf_nan=False, description="Fraction of portfolio value, e.g. 0.10 for 10%")
_TICKER_RE = r"^[A-Za-z0-9.\-]{1,12}$"


class RuleCreate(BaseModel):
    rule_type: RuleType
    threshold: float = Threshold
    severity: Severity = "warning"
    scope: Optional[str] = Field(None, max_length=100, description="Ticker or sector; omit for a global rule")

    @model_validator(mode="after")
    def _check_scope(self) -> "RuleCreate":
        import re

        if self.scope is None:
            return self
        if self.rule_type == "liquidity_constraint":
            raise ValueError("liquidity_constraint rules cannot be scoped")
        if self.rule_type == "sector_exposure_cap" and self.scope not in KNOWN_SECTORS:
            raise ValueError(f"unknown sector; expected one of: {', '.join(KNOWN_SECTORS)}")
        if self.rule_type == "single_position_cap":
            if not re.fullmatch(_TICKER_RE, self.scope):
                raise ValueError("scope must be a ticker symbol")
            self.scope = self.scope.upper()
        return self


class RuleUpdate(BaseModel):
    threshold: Optional[float] = Field(None, gt=0.0, le=1.0, allow_inf_nan=False)
    severity: Optional[Severity] = None
    active: Optional[bool] = None


def _rule_json(r: models.IPSRule) -> dict:
    return {
        "id": str(r.id),
        "institution_id": str(r.institution_id),
        "rule_type": r.rule_type,
        "threshold": r.threshold,
        "severity": r.severity,
        "scope": r.scope,
        "active": r.active,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


_DUPLICATE = "An active rule with the same type and scope already exists; update it instead."


def _commit_or_conflict(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if "uq_ips_rules_active_type_scope" in str(exc.orig):
            raise HTTPException(status_code=409, detail=_DUPLICATE)
        raise


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
    rule = models.IPSRule(
        institution_id=admin.institution_id,
        rule_type=payload.rule_type,
        threshold=payload.threshold,
        severity=payload.severity,
        scope=payload.scope,
        active=True,
    )
    db.add(rule)
    _commit_or_conflict(db)
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
    if payload.threshold is not None:
        rule.threshold = payload.threshold
    if payload.severity is not None:
        rule.severity = payload.severity
    if payload.active is not None:
        rule.active = payload.active
    _commit_or_conflict(db)
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
