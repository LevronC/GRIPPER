"""
Compliance evaluation and violation lifecycle.

Lifecycle of a governance event (one row in governance_events):
  * identity  = (rule_id, event_type, ticker-or-sector). The same breach found again is
                the same event (same id), even if holdings were re-saved with new row ids.
  * open      = resolved is False. Its details (current weight, threshold, severity) are
                refreshed on every evaluation, so an open event shows the latest values.
  * resolved  = set when an evaluation no longer finds the breach. resolved_at plus
                details.resolution record why: "no_longer_breached" or "rule_inactive"
                (rule deactivated or deleted). Resolved events are never modified again.
  * recurrence = a breach that reappears after resolution creates a NEW event; the
                resolved one stays in history unchanged.

There are no per-evaluation snapshot records; governance_events is the audit trail.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.core.observability import observe_time
from app.models import GovernanceEvent, Holding, IPSRule, Portfolio
from app.services.governance.alerts import dispatch_resolution_alert, dispatch_violation_alert
from app.services.governance.rules import detect_violations

logger = logging.getLogger(__name__)

_DETAIL_KEYS = ("ticker", "sector", "tickers", "rule_type")


def _key(rule_id: Any, event_type: str, details: Dict[str, Any]) -> tuple:
    return (str(rule_id) if rule_id else "", event_type, details.get("ticker") or details.get("sector") or "")


def _details(v: Dict[str, Any]) -> Dict[str, Any]:
    d = {"message": v["message"]}
    for k in ("current_weight", "threshold"):
        if k in v:
            d[k] = v[k]
    for k in _DETAIL_KEYS:
        if k in v:
            d[k] = v[k]
    return d


def _active_rules(db: Session, institution_id: uuid.UUID) -> List[IPSRule]:
    return list(db.execute(
        select(IPSRule).where(and_(IPSRule.institution_id == institution_id, IPSRule.active.is_(True)))
    ).scalars())


def _event_json(e: GovernanceEvent) -> Dict[str, Any]:
    return {
        "id": str(e.id),
        "event_type": e.event_type,
        "severity": e.severity,
        "details": e.details_json,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


@observe_time("evaluate_portfolio_compliance")
def evaluate_portfolio_compliance(
    db: Session,
    portfolio_id: uuid.UUID,
    institution_id: uuid.UUID,
) -> List[Dict[str, Any]]:
    """Evaluates all active rules, reconciles governance_events, returns the open events."""
    rules = _active_rules(db, institution_id)
    holdings = list(db.execute(
        select(Holding)
        .join(Portfolio, Portfolio.id == Holding.portfolio_id)
        .where(Holding.portfolio_id == portfolio_id, Portfolio.institution_id == institution_id)
    ).scalars())

    # An empty portfolio is still evaluated, so stale open events get resolved.
    detected = {_key(v["rule_id"], v["type"], v): v for v in detect_violations(rules, holdings)}
    open_events = list(db.execute(
        select(GovernanceEvent).where(
            GovernanceEvent.portfolio_id == portfolio_id,
            GovernanceEvent.institution_id == institution_id,
            GovernanceEvent.resolved.is_(False),
        )
    ).scalars())
    active_rule_ids = {str(r.id) for r in rules}
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    results: List[GovernanceEvent] = []
    seen = set()
    for event in sorted(open_events, key=lambda e: e.created_at or now):
        key = _key(event.rule_id, event.event_type, event.details_json or {})
        if key in detected and key not in seen:
            seen.add(key)
            v = detected[key]
            event.details_json = _details(v)
            event.severity = v["severity"]
            if v.get("holding_id"):
                event.holding_id = v["holding_id"]
            results.append(event)
        else:
            reason = "no_longer_breached" if key[0] in active_rule_ids else "rule_inactive"
            event.resolved = True
            event.resolved_at = now
            event.details_json = {**(event.details_json or {}), "resolution": reason}
            dispatch_resolution_alert(event)
            logger.info("[Governance] Resolved %s (%s)", event.event_type, reason)

    for key, v in detected.items():
        if key in seen:
            continue
        event = GovernanceEvent(
            id=uuid.uuid4(),
            institution_id=institution_id,
            portfolio_id=portfolio_id,
            holding_id=v.get("holding_id"),
            rule_id=v["rule_id"],
            event_type=v["type"],
            severity=v["severity"],
            details_json=_details(v),
            resolved=False,
        )
        db.add(event)
        dispatch_violation_alert(event)
        results.append(event)

    db.commit()  # tenant context is re-applied by the session hook for the reads below
    return [_event_json(e) for e in sorted(results, key=lambda e: _key(e.rule_id, e.event_type, e.details_json))]


class MockHolding:
    """A hypothetical holding for what-if simulation (never persisted)."""

    def __init__(self, ticker: str, weight: float, cost_basis: float = 100.0, conviction_score: Optional[int] = None):
        self.id = uuid.uuid4()
        self.ticker = ticker.upper().strip()
        self.weight = weight
        self.cost_basis = cost_basis
        self.conviction_score = conviction_score


def simulate_portfolio_compliance(
    db: Session,
    portfolio_id: uuid.UUID,
    institution_id: uuid.UUID,
    hypothetical_holdings_data: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Same rule logic as evaluation, against hypothetical holdings, without writes."""
    holdings = [
        MockHolding(h["ticker"], h["weight"], h.get("cost_basis", 100.0), h.get("conviction_score"))
        for h in hypothetical_holdings_data
    ]
    out = []
    for v in detect_violations(_active_rules(db, institution_id), holdings):
        v = dict(v)
        v["rule_id"] = str(v["rule_id"])
        v.pop("holding_id", None)  # random ids for hypothetical rows carry no meaning
        out.append(v)
    return out
