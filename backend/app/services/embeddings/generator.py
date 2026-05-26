from typing import List
from sentence_transformers import SentenceTransformer
from app.core.config import settings
from app.core.observability import observe_time

_model = None

def get_embedding_model() -> SentenceTransformer:
    """
    Lazy loads the BGE embedding model.
    Downloads locally from HuggingFace on first invocation.
    """
    global _model
    if _model is None:
        # Load sentence transformer model.
        # This will save model files locally inside ~/.cache/huggingface/hub/
        _model = SentenceTransformer(settings.EMBEDDING_MODEL_NAME)
    return _model

@observe_time("generate_embeddings")
def generate_embeddings(texts: List[str]) -> List[List[float]]:
    """
    Generates 384-dimensional normalized vector embeddings for a list of document chunks.
    No prefix is required for documents when using BGE models.
    """
    if not texts:
        return []
        
    model = get_embedding_model()
    # BGE models perform best with normalized embeddings
    embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return [e.tolist() for e in embeddings]

@observe_time("generate_query_embedding")
def generate_query_embedding(query: str) -> List[float]:
    """
    Generates normalized embedding for a search query.
    Applies the BGE retrieval instruction prefix for optimal similarity comparison.
    """
    model = get_embedding_model()
    # BGE queries require this exact instruction prefix to rank documents correctly
    instruction_query = f"Represent this sentence for searching relevant passages: {query}"
    embedding = model.encode(instruction_query, normalize_embeddings=True, show_progress_bar=False)
    return embedding.tolist()
