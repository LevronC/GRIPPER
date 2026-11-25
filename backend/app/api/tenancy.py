"""
Application-layer tenant ownership checks.

These run in addition to PostgreSQL RLS (defense in depth): every lookup of a
tenant-scoped resource by identifier also filters on the authenticated user's
institution. A resource that exists in another institution is reported as
404 Not Found, which avoids confirming that the identifier exists at all.
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models


def _not_found(kind: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"{kind} not found")


def require_portfolio(db: Session, portfolio_id: uuid.UUID, institution_id: uuid.UUID) -> models.Portfolio:
    portfolio = db.execute(
        select(models.Portfolio).where(
            models.Portfolio.id == portfolio_id,
            models.Portfolio.institution_id == institution_id,
        )
    ).scalar_one_or_none()
    if portfolio is None:
        raise _not_found("Portfolio")
    return portfolio


def require_governance_event(
    db: Session, event_id: uuid.UUID, institution_id: uuid.UUID
) -> models.GovernanceEvent:
    event = db.execute(
        select(models.GovernanceEvent).where(
            models.GovernanceEvent.id == event_id,
            models.GovernanceEvent.institution_id == institution_id,
        )
    ).scalar_one_or_none()
    if event is None:
        raise _not_found("Violation event")
    return event


def require_report(db: Session, report_id: uuid.UUID, institution_id: uuid.UUID) -> models.ResearchReport:
    report = db.execute(
        select(models.ResearchReport).where(
            models.ResearchReport.id == report_id,
            models.ResearchReport.institution_id == institution_id,
        )
    ).scalar_one_or_none()
    if report is None:
        raise _not_found("Document")
    return report


def require_rule(db: Session, rule_id: uuid.UUID, institution_id: uuid.UUID) -> models.IPSRule:
    rule = db.execute(
        select(models.IPSRule).where(
            models.IPSRule.id == rule_id,
            models.IPSRule.institution_id == institution_id,
        )
    ).scalar_one_or_none()
    if rule is None:
        raise _not_found("IPS rule")
    return rule
