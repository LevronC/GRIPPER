"""
Violation explanations (deterministic facts, optional grounded commentary).

Separation of concerns:
  1. Compliance status comes ONLY from the deterministic evaluator (governance_events).
  2. Research retrieval finds potentially relevant documents. It never approves,
     exempts, resolves, or otherwise changes a violation. Gripper has no formal
     exception-approval workflow, and this module must not imply one.
  3. The policy sentences are a fixed template. A language model may add commentary
     about the retrieved excerpts only when external processing is authorized.
     Invalid model output is discarded and the template is returned instead.
     The response says which path was used via `explanation_source`.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import GovernanceEvent, IPSRule, Institution
from app.services.llm.grounding import maybe_explain
from app.services.retrieval.searcher import hybrid_search

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
    if event_type == "insufficient_data":
        tickers = ", ".join(details.get("tickers") or [])
        return (f"The {details.get('rule_type', 'rule')} rule could not be fully evaluated: {tickers} "
                "has no classification in Gripper's reference data, so compliance is not established for it.")
    return details.get("message") or "An investment policy rule is breached."


def research_query(event_type: str, details: Dict[str, Any]) -> str:
    """Neutral retrieval query: looks for context, not for justification."""
    if event_type == "single_position_cap":
        return f"{details.get('ticker', '')} investment thesis position sizing risk"
    if event_type == "sector_exposure_cap":
        return f"{details.get('sector', '')} sector outlook exposure risk"
    if event_type == "liquidity_constraint":
        return "micro-cap liquidity risk trading volume"
    if event_type == "insufficient_data":
        return " ".join(details.get("tickers") or []) + " company profile sector"
    return "portfolio investment policy risk"


@dataclass(frozen=True)
class ExplanationFacts:
    """
    Everything an explanation may state, computed deterministically. A renderer turns
    facts into text; it cannot change them. A future model-based renderer must take
    exactly these facts (plus the evidence passages) and nothing that can alter status.
    """
    event_type: str
    details: Dict[str, Any]
    violation_status: str      # open | resolved (from the evaluator only)
    research_status: str       # found | none | unavailable
    evidence_companies: List[str]
    evidence_count: int
    rule_scope: Optional[str] = None


def render_policy_explanation(f: ExplanationFacts) -> str:
    """Deterministic policy sentences. A model is not allowed to replace these."""
    lines = [describe_violation(f.event_type, f.details)]
    if f.rule_scope:
        lines.append(f"The rule is scoped to {f.rule_scope}.")
    if f.violation_status == "open":
        lines.append(
            "This violation is open. It stays open until the holdings or the rule change and the "
            "portfolio is re-evaluated; retrieved research does not approve, exempt, or resolve it."
        )
    else:
        reason = f.details.get("resolution")
        lines.append(
            "This violation was resolved because the rule was deactivated." if reason == "rule_inactive"
            else "This violation was resolved by a later evaluation."
        )
    return " ".join(lines)


def render_template_explanation(f: ExplanationFacts) -> str:
    """Pure function: deterministic text from facts."""
    if f.research_status == "found":
        research = (
            f"{f.evidence_count} research excerpt(s) from your institution"
            + (f" ({', '.join(f.evidence_companies)})" if f.evidence_companies else "")
            + " matched a search for related context. They are shown for review; their relevance "
              "has not been verified."
        )
    elif f.research_status == "none":
        research = "No research documents in your institution matched this violation."
    else:
        research = "Research search was unavailable, so no supporting documents were retrieved."
    return f"{render_policy_explanation(f)} {research}"


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
    retrieval_mode = None
    try:
        outcome = hybrid_search(db, query, institution_id, limit=EVIDENCE_LIMIT)
        retrieval_mode = outcome.retrieval_mode
        for chunk in outcome.results:
            evidence.append({
                "chunk_id": chunk["chunk_id"],
                "report_id": chunk["report_id"],
                "company": chunk["company"],
                "sector": chunk["sector"],
                "page": chunk["page"],
                "chunk_index": chunk.get("chunk_index"),
                "content": chunk["content"],
                "retrieval_score": chunk.get("rrf_score"),
            })
        research_status = "found" if evidence else "none"
    except Exception as exc:
        logger.warning("Research retrieval failed for event %s (%s)", event_id, type(exc).__name__)
        research_status = "unavailable"

    rule = db.get(IPSRule, event.rule_id) if event.rule_id else None
    facts = ExplanationFacts(
        event_type=event.event_type,
        details=details,
        violation_status=violation_status,
        research_status=research_status,
        evidence_companies=sorted({e["company"] for e in evidence if e.get("company")}),
        evidence_count=len(evidence),
        rule_scope=rule.scope if rule else None,
    )
    # Template first, and outside the model call, so a renderer failure still surfaces
    # and a model failure cannot replace the policy sentences.
    template = render_template_explanation(facts)
    institution = db.get(Institution, institution_id)
    llm = maybe_explain(
        institution_authorized=bool(institution and institution.external_processing_authorized),
        violation_status=violation_status,
        policy_text=render_policy_explanation(facts),
        details=details,
        retrieval_mode=retrieval_mode,
        evidence=evidence,
        institution_id=str(institution_id),
    )
    return {
        "event_id": str(event.id),
        "event_type": event.event_type,
        "severity": event.severity,
        "message": details.get("message"),
        "violation_status": violation_status,
        "research_status": research_status,
        "policy": {
            "rule_id": str(rule.id) if rule else None,
            "rule_type": rule.rule_type if rule else None,
            "scope": rule.scope if rule else None,
            "rule_active": rule.active if rule else False,
            # Threshold that applied when the event was last evaluated (not necessarily current).
            "threshold_at_evaluation": details.get("threshold"),
        },
        "explanation": llm.text or template,
        "explanation_source": "llm" if llm.text else "template",
        "fallback_reason": None if llm.text else llm.fallback_reason,
        "citations": llm.citations if llm.text else [],
        "llm": {
            "provider": "subq" if llm.attempted or llm.model else "none",
            "attempted": llm.attempted,
            "model": llm.model,
        },
        "search_query": query,
        "retrieval_mode": retrieval_mode,
        "evidence": evidence,
    }
