import uuid
from datetime import datetime
import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, text

from app.models import Portfolio, Holding, IPSRule, GovernanceEvent
from app.services.governance.rules import (
    validate_single_position,
    validate_sector_exposures,
    validate_liquidity_constraints,
)
from app.services.governance.alerts import dispatch_violation_alert, dispatch_resolution_alert
from app.core.observability import observe_time

logger = logging.getLogger(__name__)

@observe_time("evaluate_portfolio_compliance")
def evaluate_portfolio_compliance(
    db: Session,
    portfolio_id: uuid.UUID,
    institution_id: uuid.UUID
) -> List[Dict[str, Any]]:
    """
    Evaluates all active IPS rules for an institution against a portfolio.
    Reconciles violations with database audit trails.
    Returns list of active violations.
    """
    # 1. Fetch active rules for the institution
    rules_stmt = select(IPSRule).filter(
        and_(IPSRule.institution_id == institution_id, IPSRule.active == True)
    )
    rules = db.execute(rules_stmt).scalars().all()
    
    # 2. Fetch portfolio holdings
    holdings_stmt = select(Holding).filter(Holding.portfolio_id == portfolio_id)
    holdings = db.execute(holdings_stmt).scalars().all()
    
    if not holdings:
        logger.info(f"No holdings found for portfolio {portfolio_id}. Compliance pass skipped.")
        return []
        
    detected_violations: List[Dict[str, Any]] = []
    
    # Run evaluation logic
    for rule in rules:
        if rule.rule_type == "single_position_cap":
            for h in holdings:
                violation = validate_single_position(h, rule.threshold)
                if violation:
                    violation["rule_id"] = rule.id
                    violation["holding_id"] = h.id
                    detected_violations.append(violation)
                    
        elif rule.rule_type == "sector_exposure_cap":
            violations = validate_sector_exposures(holdings, rule.threshold)
            for v in violations:
                v["rule_id"] = rule.id
                detected_violations.append(v)
                
        elif rule.rule_type == "liquidity_constraint":
            violation = validate_liquidity_constraints(holdings, rule.threshold)
            if violation:
                violation["rule_id"] = rule.id
                detected_violations.append(violation)
                
    # 3. Retrieve currently active violations from the database
    active_events_stmt = select(GovernanceEvent).filter(
        and_(
            GovernanceEvent.portfolio_id == portfolio_id,
            GovernanceEvent.resolved == False
        )
    )
    db_active_events = db.execute(active_events_stmt).scalars().all()
    
    # Create comparison keys for active events in DB
    # Key helper: (rule_id, holding_id, event_type, sector_or_ticker)
    def get_event_key(event: Any) -> tuple:
        details = event.details_json
        ticker_or_sector = details.get("ticker") or details.get("sector") or ""
        return (event.rule_id, event.holding_id, event.event_type, ticker_or_sector)
        
    def get_violation_key(v: dict) -> tuple:
        ticker_or_sector = v.get("ticker") or v.get("sector") or ""
        return (v.get("rule_id"), v.get("holding_id"), v["type"], ticker_or_sector)
        
    db_active_map = {get_event_key(e): e for e in db_active_events}
    detected_map = {get_violation_key(v): v for v in detected_violations}
    
    # 4. Reconcile
    now = datetime.utcnow()
    
    # - Handle Resolved Violations (Active in DB, but not detected anymore)
    for key, db_event in db_active_map.items():
        if key not in detected_map:
            db_event.resolved = True
            db_event.resolved_at = now
            dispatch_resolution_alert(db_event)
            logger.info(f"[Governance] Resolved breach: {db_event.event_type} on {key[3]}")
            
    # - Handle Active or New Violations
    active_results = []
    for key, v in detected_map.items():
        if key in db_active_map:
            # Breach is already known, update details (weights, etc.) if they changed
            db_event = db_active_map[key]
            db_event.details_json = {
                "current_weight": v["current_weight"],
                "threshold": v["threshold"],
                "message": v["message"],
                **({"ticker": v["ticker"]} if "ticker" in v else {}),
                **({"sector": v["sector"]} if "sector" in v else {}),
                **({"tickers": v["tickers"]} if "tickers" in v else {})
            }
            db_event.severity = v["severity"]
            active_results.append(db_event)
        else:
            # Create a new governance breach record
            new_event = GovernanceEvent(
                id=uuid.uuid4(),
                institution_id=institution_id,
                portfolio_id=portfolio_id,
                holding_id=v.get("holding_id"),
                rule_id=v.get("rule_id"),
                event_type=v["type"],
                severity=v["severity"],
                details_json={
                    "current_weight": v["current_weight"],
                    "threshold": v["threshold"],
                    "message": v["message"],
                    **({"ticker": v["ticker"]} if "ticker" in v else {}),
                    **({"sector": v["sector"]} if "sector" in v else {}),
                    **({"tickers": v["tickers"]} if "tickers" in v else {})
                },
                resolved=False
            )
            db.add(new_event)
            dispatch_violation_alert(new_event)
            active_results.append(new_event)
            logger.warning(f"[Governance] New breach detected: {v['message']}")
            
    db.commit()
    
    # Re-set transaction-scoped RLS context after commit because SET LOCAL is cleared.
    # This is required so that we can read back the objects (e.g. created_at) for the return list.
    db.execute(text("SET LOCAL app.current_institution_id = :inst_id"), {"inst_id": str(institution_id)})

    # Format return list
    return [
        {
            "id": str(e.id),
            "event_type": e.event_type,
            "severity": e.severity,
            "details": e.details_json,
            "created_at": e.created_at.isoformat()
        }
        for e in active_results
    ]


class MockHolding:
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
    hypothetical_holdings_data: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Simulates compliance checks against hypothetical holdings without database mutations.
    """
    # 1. Fetch active rules
    rules_stmt = select(IPSRule).filter(
        and_(IPSRule.institution_id == institution_id, IPSRule.active == True)
    )
    rules = db.execute(rules_stmt).scalars().all()
    
    # 2. Map payload into mock holdings
    holdings = [
        MockHolding(
            ticker=h["ticker"],
            weight=h["weight"],
            cost_basis=h.get("cost_basis", 100.0),
            conviction_score=h.get("conviction_score")
        )
        for h in hypothetical_holdings_data
    ]
    
    if not holdings:
        return []
        
    detected_violations: List[Dict[str, Any]] = []
    
    for rule in rules:
        if rule.rule_type == "single_position_cap":
            for h in holdings:
                violation = validate_single_position(h, rule.threshold)
                if violation:
                    violation["rule_id"] = str(rule.id)
                    violation["holding_id"] = str(h.id)
                    detected_violations.append(violation)
                    
        elif rule.rule_type == "sector_exposure_cap":
            violations = validate_sector_exposures(holdings, rule.threshold)
            for v in violations:
                v["rule_id"] = str(rule.id)
                detected_violations.append(v)
                
        elif rule.rule_type == "liquidity_constraint":
            violation = validate_liquidity_constraints(holdings, rule.threshold)
            if violation:
                violation["rule_id"] = str(rule.id)
                detected_violations.append(violation)
                
    return detected_violations

