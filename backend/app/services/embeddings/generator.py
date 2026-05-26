from typing import List
from sentence_transformers import SentenceTransformer
from app.core.config import settings
from app.core.observability import observe_time

_model = None

def get_embedding_model() -> SentenceTransformer:
    """
    Lazy loads the BGE embedding model.
    Downloads locally from HuggingFace on first invocation.
    Forces CPU usage to avoid MPS overhead for small batch/small model scenarios.
    """
    global _model
    if _model is None:
        # Load sentence transformer model.
        # Forces CPU to ensure predictable performance on Apple Silicon/Standard hardware
        _model = SentenceTransformer(settings.EMBEDDING_MODEL_NAME, device="cpu")
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
