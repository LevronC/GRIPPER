"""
Violation explanations (rule-based template + retrieved research for context).

Separation of concerns:
  1. Compliance status comes ONLY from the deterministic evaluator (governance_events).
  2. Research retrieval finds potentially relevant documents. It never approves,
     exempts, resolves, or otherwise changes a violation. Gripper has no formal
     exception-approval workflow, and this module must not imply one.
  3. The explanation text is produced by a fixed template (no language model), and the
     response says so via `explanation_source: "template"`.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import GovernanceEvent
from app.services.retrieval.searcher import search_documents

logger = logging.getLogger(__name__)

EVIDENCE_LIMIT = 3


def _pct(value: Any) -> str:
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return "unknown"


def describe_violation(event_type: str, details: Dict[str, Any]) -> str:
    """Deterministic one-sentence statement of the policy breach."""
    current, limit = _pct(details.get("current_weight")), _pct(details.get("threshold"))
    if event_type == "single_position_cap":
        return f"{details.get('ticker', 'A position')} is {current} of the portfolio; the single-position limit is {limit}."
    if event_type == "sector_exposure_cap":
        return f"{details.get('sector', 'A sector')} exposure is {current}; the sector limit is {limit}."
    if event_type == "liquidity_constraint":
        tickers = ", ".join(details.get("tickers") or []) or "micro-cap holdings"
        return f"Micro-cap holdings ({tickers}) total {current}; the liquidity limit is {limit}."
    return details.get("message") or "An investment policy rule is breached."


def research_query(event_type: str, details: Dict[str, Any]) -> str:
    """Neutral retrieval query: looks for context, not for justification."""
    if event_type == "single_position_cap":
        return f"{details.get('ticker', '')} investment thesis position sizing risk"
    if event_type == "sector_exposure_cap":
        return f"{details.get('sector', '')} sector outlook exposure risk"
    if event_type == "liquidity_constraint":
        return "micro-cap liquidity risk trading volume"
    return "portfolio investment policy risk"


def generate_violation_explanation(
    db: Session,
    event_id: uuid.UUID,
    institution_id: uuid.UUID,
) -> Dict[str, Any]:
    event = db.execute(
        select(GovernanceEvent).filter(
            GovernanceEvent.id == event_id, GovernanceEvent.institution_id == institution_id
        )
    ).scalar_one_or_none()
    if not event:
        return {"error": "Violation event not found", "event_id": str(event_id)}

    details = event.details_json or {}
    violation_status = "resolved" if event.resolved else "open"
    query = research_query(event.event_type, details)

    evidence: List[Dict[str, Any]] = []
    research_status = "none"
    try:
        for chunk in search_documents(db, query, institution_id, limit=EVIDENCE_LIMIT):
            evidence.append({
                "chunk_id": chunk["chunk_id"],
                "report_id": chunk["report_id"],
                "company": chunk["company"],
                "sector": chunk["sector"],
                "page": chunk["page"],
                "content": chunk["content"],
                "retrieval_score": chunk.get("rrf_score"),
            })
        research_status = "found" if evidence else "none"
    except Exception as exc:
        logger.warning("Research retrieval failed for event %s (%s)", event_id, type(exc).__name__)
        research_status = "unavailable"

    lines = [describe_violation(event.event_type, details)]
    if violation_status == "open":
        lines.append(
            "This violation is open. It stays open until the holdings or the rule change and the "
            "portfolio is re-evaluated; retrieved research does not approve, exempt, or resolve it."
        )
    else:
        lines.append("This violation was resolved by a later evaluation.")
    if research_status == "found":
        companies = sorted({e["company"] for e in evidence if e.get("company")})
        lines.append(
            f"{len(evidence)} research excerpt(s) from your institution"
            + (f" ({', '.join(companies)})" if companies else "")
            + " matched a search for related context. They are shown for review; their relevance "
              "has not been verified."
        )
    elif research_status == "none":
        lines.append("No research documents in your institution matched this violation.")
    else:
        lines.append("Research search was unavailable, so no supporting documents were retrieved.")

    return {
        "event_id": str(event.id),
        "event_type": event.event_type,
        "severity": event.severity,
        "message": details.get("message"),
        "violation_status": violation_status,
        "research_status": research_status,
        "explanation": " ".join(lines),
        "explanation_source": "template",
        "search_query": query,
        "evidence": evidence,
    }
