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
from app.services.embeddings.generator import EmbeddingUnavailable, generate_query_embedding

logger = logging.getLogger(__name__)

RRF_K = 60.0


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


@observe_time("search_documents")
def hybrid_search(db: Session, query: str, institution_id: uuid.UUID, limit: int = 5) -> SearchOutcome:
    if not query.strip():
        return SearchOutcome(results=[], retrieval_mode="full_text_only", degraded_reason="empty query")

    tenant = DocumentChunk.institution_id == institution_id
    candidates = limit * 3

    # --- 1. Vector leg (only within the active embedding space) ---
    vector_docs: List[Dict[str, Any]] = []
    degraded_reason: Optional[str] = None
    embedding_info: Optional[dict] = None
    try:
        query_embedding, space = generate_query_embedding(query)
        embedding_info = space.public()
        distance = DocumentChunk.embedding.cosine_distance(query_embedding)
        vector_stmt = (
            select(DocumentChunk, ResearchReport.company, ResearchReport.sector, distance.label("distance"))
            .join(ResearchReport, DocumentChunk.report_id == ResearchReport.id)
            .filter(tenant)
            .filter(DocumentChunk.embedding.isnot(None))
            .filter(DocumentChunk.embedding_model == space.space_id)
            .order_by(distance)
            .limit(candidates)
        )
        for chunk, company, sector, dist in db.execute(vector_stmt).all():
            vector_docs.append(_row_to_doc(chunk, company, sector, 1.0 - float(dist) if dist is not None else 0.0))
    except EmbeddingUnavailable as exc:
        degraded_reason = f"semantic search unavailable: {exc}"
        logger.warning("Search degraded to full-text only (%s)", exc)

    # --- 2. Full-text leg ---
    ts_query = func.plainto_tsquery("english", query)
    ts_vector = func.to_tsvector("english", DocumentChunk.content)
    text_stmt = (
        select(DocumentChunk, ResearchReport.company, ResearchReport.sector, func.ts_rank(ts_vector, ts_query).label("rank"))
        .join(ResearchReport, DocumentChunk.report_id == ResearchReport.id)
        .filter(tenant)
        .filter(ts_vector.op("@@")(ts_query))
        .order_by(text("rank DESC"))
        .limit(candidates)
    )
    text_docs = [_row_to_doc(c, co, se, float(rank)) for c, co, se, rank in db.execute(text_stmt).all()]

    # --- 3. Reciprocal Rank Fusion: score(d) = sum over legs of 1 / (k + rank_leg(d)), rank from 1 ---
    rrf_scores: Dict[str, float] = {}
    docs_map: Dict[str, Dict[str, Any]] = {}
    for rank, doc in enumerate(vector_docs):
        cid = doc["chunk_id"]
        docs_map[cid] = doc
        rrf_scores[cid] = rrf_scores.get(cid, 0.0) + 1.0 / (RRF_K + rank + 1)
    for rank, doc in enumerate(text_docs):
        cid = doc["chunk_id"]
        docs_map.setdefault(cid, doc)
        rrf_scores[cid] = rrf_scores.get(cid, 0.0) + 1.0 / (RRF_K + rank + 1)

    ordered = sorted(rrf_scores, key=lambda cid: rrf_scores[cid], reverse=True)
    results = []
    for cid in ordered[:limit]:
        doc = docs_map[cid]
        doc["rrf_score"] = rrf_scores[cid]
        results.append(doc)

    return SearchOutcome(
        results=results,
        retrieval_mode="full_text_only" if degraded_reason else "hybrid",
        degraded_reason=degraded_reason,
        embedding=embedding_info,
        legs={"vector": len(vector_docs), "full_text": len(text_docs)},
    )


def search_documents(db: Session, query: str, institution_id: uuid.UUID, limit: int = 5) -> List[Dict[str, Any]]:
    return hybrid_search(db, query, institution_id, limit).results
