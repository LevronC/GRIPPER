import uuid
from typing import List, Dict, Any
from sqlalchemy import select, or_, text, func
from sqlalchemy.orm import Session
from app.models import DocumentChunk, ResearchReport
from app.services.embeddings.generator import generate_query_embedding

from app.core.config import settings
from app.core.observability import observe_time

@observe_time("search_documents")
def search_documents(
    db: Session, 
    query: str, 
    institution_id: uuid.UUID, 
    limit: int = 5
) -> List[Dict[str, Any]]:
    """
    Executes a hybrid (Vector + Keyword) multi-tenant similarity search against document_chunks.
    - Uses pgvector for semantic similarity.
    - Uses PostgreSQL Full-Text Search (TSVector) for keyword matching.
    - Combines results using Reciprocal Rank Fusion (RRF).
    """
    if not query.strip():
        return []
        
    # --- 1. Vector Cosine Similarity Search ---
    query_embedding = generate_query_embedding(query)
    distance_expr = DocumentChunk.embedding.cosine_distance(query_embedding)
    
    vector_stmt = (
        select(
            DocumentChunk, 
            ResearchReport.company, 
            ResearchReport.sector, 
            distance_expr.label("distance")
        )
        .join(ResearchReport, DocumentChunk.report_id == ResearchReport.id)
        .filter(DocumentChunk.institution_id == institution_id)
        .order_by(distance_expr)
        .limit(limit * 3) # Fetch more to allow for hybrid overlap
    )
    
    vector_results = db.execute(vector_stmt).all()
    vector_docs = []
    for row in vector_results:
        chunk = row[0]
        company = row[1]
        sector = row[2]
        distance = row[3]
        similarity = 1.0 - float(distance) if distance is not None else 0.0
        
        vector_docs.append({
            "chunk_id": str(chunk.id),
            "content": chunk.content,
            "page": chunk.metadata_json.get("page") if chunk.metadata_json else None,
            "company": company,
            "sector": sector,
            "similarity": similarity,
            "report_id": str(chunk.report_id)
        })

    # --- 2. Full-Text Search (BM25 Equivalent) ---
    # We use PostgreSQL's native tsvector and ts_rank for keyword relevance.
    # Note: Ensure a GIN index exists on to_tsvector('english', content) for production speed.
    ts_query = func.plainto_tsquery('english', query)
    ts_vector = func.to_tsvector('english', DocumentChunk.content)
    
    text_stmt = (
        select(
            DocumentChunk,
            ResearchReport.company,
            ResearchReport.sector,
            func.ts_rank(ts_vector, ts_query).label("rank")
        )
        .join(ResearchReport, DocumentChunk.report_id == ResearchReport.id)
        .filter(DocumentChunk.institution_id == institution_id)
        .filter(ts_vector.op('@@')(ts_query))
        .order_by(text("rank DESC"))
        .limit(limit * 3)
    )
    
    text_results = db.execute(text_stmt).all()
    text_docs = []
    for row in text_results:
        chunk = row[0]
        company = row[1]
        sector = row[2]
        rank = row[3]
        
        text_docs.append({
            "chunk_id": str(chunk.id),
            "content": chunk.content,
            "page": chunk.metadata_json.get("page") if chunk.metadata_json else None,
            "company": company,
            "sector": sector,
            "similarity": float(rank), 
            "report_id": str(chunk.report_id)
        })

    # --- 3. Reciprocal Rank Fusion (RRF) ---
    rrf_scores = {}
    docs_map = {}
    
    # RRF parameter (K=60 is standard in literature)
    K = 60.0
    
    # Process vector results
    for rank, doc in enumerate(vector_docs):
        cid = doc["chunk_id"]
        docs_map[cid] = doc
        rrf_scores[cid] = rrf_scores.get(cid, 0.0) + (1.0 / (K + rank + 1))
        
    # Process text results
    for rank, doc in enumerate(text_docs):
        cid = doc["chunk_id"]
        if cid not in docs_map:
            docs_map[cid] = doc
        rrf_scores[cid] = rrf_scores.get(cid, 0.0) + (1.0 / (K + rank + 1))
        
    # Sort docs based on combined RRF score
    sorted_chunk_ids = sorted(rrf_scores.keys(), key=lambda cid: rrf_scores[cid], reverse=True)
    
    # Return the top limited results
    final_results = []
    for cid in sorted_chunk_ids[:limit]:
        doc = docs_map[cid]
        doc["rrf_score"] = rrf_scores[cid]
        final_results.append(doc)
        
    return final_results
