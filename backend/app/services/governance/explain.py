import uuid
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models import GovernanceEvent
from app.services.retrieval.searcher import search_documents

def generate_violation_explanation(
    db: Session,
    event_id: uuid.UUID,
    institution_id: uuid.UUID
) -> Dict[str, Any]:
    """
    RAG-driven compliance explanation system.
    Queries the vector database for qualitative files matching the deterministic violation context
    and returns a structured explanation with retrieved precedents.
    """
    # 1. Fetch the governance event
    stmt = select(GovernanceEvent).filter(GovernanceEvent.id == event_id)
    event = db.execute(stmt).scalar_one_or_none()
    
    if not event:
        return {
            "error": "Violation event not found",
            "event_id": str(event_id)
        }
        
    details = event.details_json
    
    # 2. Formulate target semantic search query based on violation type
    search_query = ""
    if event.event_type == "single_position_cap":
        ticker = details.get("ticker", "security")
        search_query = f"{ticker} investment thesis exception allocation increase buy rationale support"
    elif event.event_type == "sector_exposure_cap":
        sector = details.get("sector", "industry")
        search_query = f"{sector} sector weight exposure increase rationale compliance decision update"
    elif event.event_type == "liquidity_constraint":
        search_query = "micro-cap illiquid holdings risk justification investment exception limit"
    else:
        search_query = f"portfolio compliance exception governance decision"
        
    # 3. Retrieve relevant analyst reports / governance notes
    try:
        retrieved_chunks = search_documents(db, search_query, institution_id, limit=3)
    except Exception as e:
        retrieved_chunks = []
        
    # 4. Formulate contextual report
    # Synthesizes retrieved evidence into structured analysis sections
    context_notes = []
    for chunk in retrieved_chunks:
        context_notes.append({
            "content": chunk["content"],
            "company": chunk["company"],
            "sector": chunk["sector"],
            "page": chunk["page"],
            "similarity": chunk["similarity"]
        })
        
    summary_analysis = ""
    if context_notes:
        best_match = context_notes[0]
        summary_analysis = (
            f"Based on internal research for {best_match['company']} (Sector: {best_match['sector']}), "
            f"analysts have documented: '{best_match['content'][:150]}...'. "
            "This suggests an active investment thesis exception may apply for this position."
        )
    else:
        summary_analysis = (
            "No historical research reports or trustee memos were retrieved explaining "
            "or justifying this portfolio allocation breach. Action required."
        )
        
    return {
        "event_id": str(event.id),
        "event_type": event.event_type,
        "severity": event.severity,
        "message": details.get("message"),
        "compliance_status": "unjustified" if not context_notes else "retrieval_justified",
        "semantic_query": search_query,
        "evidence": context_notes,
        "ai_explanation_draft": summary_analysis
    }
