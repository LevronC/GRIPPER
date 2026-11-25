"""
Hybrid retrieval: pgvector cosine similarity + PostgreSQL full-text search, fused with
Reciprocal Rank Fusion (RRF, k=60).

Degradation is explicit. The vector leg runs only when an embedding provider is
available, and it only considers chunks embedded in the *active* embedding space
(document_chunks.embedding_model). Otherwise the search is full-text only and the
outcome says so (retrieval_mode="full_text_only", degraded_reason=...).
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.observability import observe_time
from app.models import DocumentChunk, ResearchReport
from app.services.embeddings.generator import EmbeddingUnavailable, active_space, generate_query_embedding
from app.services.retrieval.fusion import DEFAULT_K, reciprocal_rank_fusion

logger = logging.getLogger(__name__)

RRF_K = DEFAULT_K


@dataclass
class SearchOutcome:
    results: List[Dict[str, Any]]
    retrieval_mode: str  # hybrid | full_text_only
    degraded_reason: Optional[str] = None
    embedding: Optional[dict] = None
    legs: Dict[str, int] = field(default_factory=dict)


def _row_to_doc(chunk: DocumentChunk, company: str, sector: str, score: float) -> Dict[str, Any]:
    return {
        "chunk_id": str(chunk.id),
        "content": chunk.content,
        "page": chunk.metadata_json.get("page") if chunk.metadata_json else None,
        "chunk_index": chunk.metadata_json.get("chunk_index") if chunk.metadata_json else None,
        "company": company,
        "sector": sector,
        "similarity": score,
        "report_id": str(chunk.report_id),
    }


def vector_statement(institution_id: uuid.UUID, query_embedding: List[float], space_id: str, limit: int):
    """The vector-leg query. Evaluation and EXPLAIN use this same statement."""
    distance = DocumentChunk.embedding.cosine_distance(query_embedding)
    return (
        select(DocumentChunk, ResearchReport.company, ResearchReport.sector, distance.label("distance"))
        .join(ResearchReport, DocumentChunk.report_id == ResearchReport.id)
        .filter(DocumentChunk.institution_id == institution_id)
        .filter(DocumentChunk.embedding.isnot(None))
        .filter(DocumentChunk.embedding_model == space_id)
        .order_by(distance, DocumentChunk.id)  # id breaks distance ties deterministically
        .limit(limit)
    )


def full_text_statement(institution_id: uuid.UUID, query: str, limit: int):
    """The full-text leg. Evaluation and EXPLAIN use this same statement."""
    ts_query = func.plainto_tsquery("english", query)
    ts_vector = func.to_tsvector("english", DocumentChunk.content)
    return (
        select(DocumentChunk, ResearchReport.company, ResearchReport.sector, func.ts_rank(ts_vector, ts_query).label("rank"))
        .join(ResearchReport, DocumentChunk.report_id == ResearchReport.id)
        .filter(DocumentChunk.institution_id == institution_id)
        .filter(ts_vector.op("@@")(ts_query))
        .order_by(text("rank DESC"), DocumentChunk.id)  # id breaks rank ties deterministically
        .limit(limit)
    )


def vector_leg(
    db: Session,
    query: str,
    institution_id: uuid.UUID,
    limit: int,
    query_embedding: Optional[List[float]] = None,
) -> tuple[List[Dict[str, Any]], Optional[str], Optional[dict]]:
    """
    Top `limit` chunks by cosine distance inside the active embedding space.

    Returns (rows, degraded_reason, embedding_info). `degraded_reason` is set when
    no embedding can be produced; the row list is then empty.
    """
    try:
        if query_embedding is None:
            query_embedding, space = generate_query_embedding(query)
        else:
            space = active_space()
            if space is None:
                raise EmbeddingUnavailable("no embedding provider configured")
        embedding_info = space.public()
    except EmbeddingUnavailable as exc:
        logger.warning("Search degraded to full-text only (%s)", exc)
        return [], f"semantic search unavailable: {exc}", None
    rows = [
        _row_to_doc(chunk, company, sector, 1.0 - float(dist) if dist is not None else 0.0)
        for chunk, company, sector, dist in db.execute(
            vector_statement(institution_id, query_embedding, space.space_id, limit)
        ).all()
    ]
    return rows, None, embedding_info


def full_text_leg(db: Session, query: str, institution_id: uuid.UUID, limit: int) -> List[Dict[str, Any]]:
    """Top `limit` chunks by ts_rank. An empty query or no matches yields an empty list."""
    if not query.strip():
        return []
    return [
        _row_to_doc(chunk, company, sector, float(rank))
        for chunk, company, sector, rank in db.execute(full_text_statement(institution_id, query, limit)).all()
    ]


@observe_time("search_documents")
def hybrid_search(db: Session, query: str, institution_id: uuid.UUID, limit: int = 5) -> SearchOutcome:
    if not query.strip():
        return SearchOutcome(results=[], retrieval_mode="full_text_only", degraded_reason="empty query")

    # Each leg sees a wider window than the fused result. 3x is the production window.
    candidates = limit * 3
    vector_docs, degraded_reason, embedding_info = vector_leg(db, query, institution_id, candidates)
    text_docs = full_text_leg(db, query, institution_id, candidates)
    results = reciprocal_rank_fusion(vector_docs, text_docs, k=RRF_K, limit=limit)

    return SearchOutcome(
        results=results,
        retrieval_mode="full_text_only" if degraded_reason else "hybrid",
        degraded_reason=degraded_reason,
        embedding=embedding_info,
        legs={"vector": len(vector_docs), "full_text": len(text_docs)},
    )


def search_documents(db: Session, query: str, institution_id: uuid.UUID, limit: int = 5) -> List[Dict[str, Any]]:
    return hybrid_search(db, query, institution_id, limit).results
