import uuid
from typing import List, Dict, Any
from sqlalchemy import select, or_
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
    Combines results using Reciprocal Rank Fusion (RRF).
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
        .limit(limit * 2) # Fetch slightly more to allow hybrid overlap
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

    # --- 2. Keyword/Exact Phrase Match (BM25 Equivalent) ---
    words = [w.strip().lower() for w in query.split() if len(w.strip()) >= 3]
    text_docs = []
    if words:
        # Build search expressions for SQL ILIKE matching
        conditions = [DocumentChunk.content.ilike(f"%{w}%") for w in words]
        
        text_stmt = (
            select(
                DocumentChunk,
                ResearchReport.company,
                ResearchReport.sector
            )
            .join(ResearchReport, DocumentChunk.report_id == ResearchReport.id)
            .filter(DocumentChunk.institution_id == institution_id)
            .filter(or_(*conditions))
            .limit(limit * 2)
        )
        text_results = db.execute(text_stmt).all()
        for row in text_results:
            chunk = row[0]
            company = row[1]
            sector = row[2]
            
            # Simple keyword matching score based on word occurrence count
            match_count = sum(1 for w in words if w in chunk.content.lower())
            
            text_docs.append({
                "chunk_id": str(chunk.id),
                "content": chunk.content,
                "page": chunk.metadata_json.get("page") if chunk.metadata_json else None,
                "company": company,
                "sector": sector,
                "similarity": 0.5 + (0.1 * match_count), # Normalise baseline similarity for keyword matches
                "report_id": str(chunk.report_id)
            })

    # --- 3. Reciprocal Rank Fusion (RRF) ---
    rrf_scores = {}
    docs_map = {}
    
    # RRF parameter
    K = 60.0
    
    for rank, doc in enumerate(vector_docs):
        cid = doc["chunk_id"]
        docs_map[cid] = doc
        rrf_scores[cid] = rrf_scores.get(cid, 0.0) + (1.0 / (K + rank + 1))
        
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
        # Include RRF score for transparency / observability
        doc["rrf_score"] = rrf_scores[cid]
        final_results.append(doc)
        
    return final_results
