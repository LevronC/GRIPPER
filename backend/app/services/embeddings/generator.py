import hashlib
import math
import os
from typing import Any, List
from app.core.config import settings
from app.core.observability import observe_time

_model = None

def get_embedding_model() -> Any:
    """
    Lazy loads the BGE embedding model.
    Downloads locally from HuggingFace on first invocation.
    Forces CPU usage to avoid MPS overhead for small batch/small model scenarios.
    """
    global _model
    if os.getenv("VERCEL") == "1":
        raise ModuleNotFoundError("sentence-transformers intentionally disabled on Vercel")

    if _model is None:
        from sentence_transformers import SentenceTransformer

        # Load sentence transformer model.
        # Forces CPU to ensure predictable performance on Apple Silicon/Standard hardware
        _model = SentenceTransformer(settings.EMBEDDING_MODEL_NAME, device="cpu")
    return _model

def _fallback_embedding(text: str) -> List[float]:
    """
    Deterministic 384-dimensional fallback for serverless deployments where the
    full sentence-transformers stack is not installed.
    """
    vector = [0.0] * 384
    for token in text.lower().split():
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:2], "big") % len(vector)
        sign = 1.0 if digest[2] % 2 == 0 else -1.0
        vector[index] += sign

    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]

@observe_time("generate_embeddings")
def generate_embeddings(texts: List[str]) -> List[List[float]]:
    """
    Generates 384-dimensional normalized vector embeddings for a list of document chunks.
    No prefix is required for documents when using BGE models.
    """
    if not texts:
        return []
        
    try:
        model = get_embedding_model()
        # BGE models perform best with normalized embeddings. 
        # Use a batch size of 32 for optimal throughput on most hardware.
        embeddings = model.encode(
            texts, 
            normalize_embeddings=True, 
            show_progress_bar=False,
            batch_size=32,
            convert_to_numpy=True
        )
        return [e.tolist() for e in embeddings]
    except Exception:
        return [_fallback_embedding(text) for text in texts]

@observe_time("generate_query_embedding")
def generate_query_embedding(query: str) -> List[float]:
    """
    Generates normalized embedding for a search query.
    Applies the BGE retrieval instruction prefix for optimal similarity comparison.
    """
    instruction_query = f"Represent this sentence for searching relevant passages: {query}"
    try:
        model = get_embedding_model()
        # BGE queries require this exact instruction prefix to rank documents correctly
        embedding = model.encode(instruction_query, normalize_embeddings=True, show_progress_bar=False)
        return embedding.tolist()
    except Exception:
        return _fallback_embedding(instruction_query)
