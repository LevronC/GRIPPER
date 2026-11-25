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


def _metadata(raw: Any) -> dict:
    if isinstance(raw, dict):
        return raw
    return {}


def _row_from_function(row: Any, *, cosine: Optional[float] = None, text_score: Optional[float] = None) -> Dict[str, Any]:
    meta = _metadata(row.metadata_json)
    score = cosine if cosine is not None else (text_score or 0.0)
    return {
        "chunk_id": str(row.chunk_id),
        "content": row.content,
        "page": meta.get("page"),
        "chunk_index": meta.get("chunk_index"),
        "company": row.company,
        "sector": row.sector,
        "similarity": score,
        "cosine_similarity": cosine,
        "text_score": text_score,
        "report_id": str(row.report_id),
    }


def _session_tenant_matches(db: Session, institution_id: uuid.UUID) -> bool:
    """The SQL functions read the session institution, not this argument. Refuse a mismatch."""
    return str(db.info.get("tenant_id") or "") == str(institution_id)


def vector_statement(institution_id: uuid.UUID, query_embedding: List[float], space_id: str, limit: int):
    """Reference ORM query; the runtime vector leg uses app_search_vector."""
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
    """Historical expression query; runtime uses app_search_full_text."""
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
) -> tuple[List[Dict[str, Any]], Optional[str], Optional[dict], Optional[List[float]]]:
    """
    Top `limit` chunks by cosine distance inside the active embedding space.

    Returns (rows, degraded_reason, embedding_info, query_embedding). `degraded_reason` is set when
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
        return [], f"semantic search unavailable: {exc}", None, None
    if not _session_tenant_matches(db, institution_id):
        return [], None, embedding_info, query_embedding
    literal = "[" + ",".join(f"{value:.8f}" for value in query_embedding) + "]"
    rows = [
        _row_from_function(row, cosine=1.0 - float(row.score) if row.score is not None else 0.0)
        for row in db.execute(
            text(
                "SELECT * FROM app_search_vector(CAST(:embedding AS vector), :space, :lim)"
            ),
            {"embedding": literal, "space": space.space_id, "lim": limit},
        ).all()
    ]
    return rows, None, embedding_info, query_embedding


def full_text_leg(db: Session, query: str, institution_id: uuid.UUID, limit: int) -> List[Dict[str, Any]]:
    """Top `limit` chunks by ts_rank. An empty query or no matches yields an empty list."""
    if not query.strip() or not _session_tenant_matches(db, institution_id):
        return []
    return [
        _row_from_function(row, text_score=float(row.score) if row.score is not None else 0.0)
        for row in db.execute(
            text("SELECT * FROM app_search_full_text(:query, :lim)"),
            {"query": query, "lim": limit},
        ).all()
    ]


def _fill_missing_cosine(
    db: Session,
    institution_id: uuid.UUID,
    results: List[Dict[str, Any]],
    query_embedding: Optional[List[float]],
    space_id: Optional[str],
) -> None:
    """Full-text-only hits do not carry a cosine. Score the few fused rows so the gate can judge them."""
    if not query_embedding or not space_id or not _session_tenant_matches(db, institution_id):
        return
    missing = [row["chunk_id"] for row in results if row.get("cosine_similarity") is None]
    if not missing:
        return
    literal = "[" + ",".join(f"{value:.8f}" for value in query_embedding) + "]"
    found: Dict[str, float] = {}
    for chunk_id in missing:
        distance = db.execute(
            text(
                "SELECT (embedding <=> CAST(:embedding AS vector))::float8 FROM document_chunks "
                "WHERE id = :chunk_id AND institution_id = :institution AND embedding IS NOT NULL "
                "AND embedding_model = :space"
            ),
            {"embedding": literal, "chunk_id": chunk_id, "institution": institution_id, "space": space_id},
        ).scalar()
        if distance is not None:
            found[chunk_id] = 1.0 - float(distance)
    for row in results:
        if row.get("cosine_similarity") is None and row["chunk_id"] in found:
            row["cosine_similarity"] = found[row["chunk_id"]]


@observe_time("search_documents")
def hybrid_search(db: Session, query: str, institution_id: uuid.UUID, limit: int = 5) -> SearchOutcome:
    if not query.strip():
        return SearchOutcome(results=[], retrieval_mode="full_text_only", degraded_reason="empty query")

    # Each leg sees a wider window than the fused result. 3x is the production window.
    candidates = limit * 3
    vector_docs, degraded_reason, embedding_info, query_embedding = vector_leg(
        db, query, institution_id, candidates
    )
    text_docs = full_text_leg(db, query, institution_id, candidates)
    results = reciprocal_rank_fusion(vector_docs, text_docs, k=RRF_K, limit=limit)
    space_id = (
        f"{embedding_info['model']}@{embedding_info['dimension']}" if embedding_info else None
    )
    _fill_missing_cosine(db, institution_id, results, query_embedding, space_id)

    return SearchOutcome(
        results=results,
        retrieval_mode="full_text_only" if degraded_reason else "hybrid",
        degraded_reason=degraded_reason,
        embedding=embedding_info,
        legs={"vector": len(vector_docs), "full_text": len(text_docs)},
    )


def search_documents(db: Session, query: str, institution_id: uuid.UUID, limit: int = 5) -> List[Dict[str, Any]]:
    return hybrid_search(db, query, institution_id, limit).results
