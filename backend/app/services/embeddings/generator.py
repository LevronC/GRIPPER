"""
Embedding generation with two execution paths:

1. LOCAL (default, local dev / Railway):
   Uses sentence-transformers with BAAI/bge-small-en-v1.5 loaded in-process.
   Produces high-quality 384-dim embeddings. Requires ~130MB model download on
   first run.

2. VERCEL / API path (when HF_API_KEY is set):
   Calls the HuggingFace Inference API for BAAI/bge-small-en-v1.5.
   No local model download, compatible with Vercel serverless function limits.
   Free tier: 1000 req/day per model. Set HF_API_KEY in environment.

3. FALLBACK (Vercel, no HF_API_KEY):
   Deterministic SHA-256 based hash embedding. Semantically meaningless —
   semantic search will not work. Only acceptable for CI / smoke tests.
   A warning is logged whenever this path activates.
"""

import hashlib
import json
import logging
import math
import os
import urllib.request
import urllib.error
from typing import Any, List

from app.core.config import settings
from app.core.observability import observe_time

logger = logging.getLogger(__name__)

_local_model = None
_ON_VERCEL = os.getenv("VERCEL") == "1"

# HuggingFace Inference API endpoint for the BGE small model
_HF_API_URL = (
    "https://api-inference.huggingface.co/pipeline/feature-extraction/"
    "BAAI/bge-small-en-v1.5"
)


# ── Local model ────────────────────────────────────────────────────────────────

def _get_local_model() -> Any:
    """Lazy-loads the BGE model. Raises on Vercel — use API path instead."""
    global _local_model
    if _ON_VERCEL:
        raise ModuleNotFoundError(
            "sentence-transformers is intentionally not loaded on Vercel. "
            "Set HF_API_KEY to use the HuggingFace Inference API."
        )
    if _local_model is None:
        from sentence_transformers import SentenceTransformer
        _local_model = SentenceTransformer(settings.EMBEDDING_MODEL_NAME, device="cpu")
    return _local_model


# ── HuggingFace Inference API ─────────────────────────────────────────────────

def _hf_api_embed(texts: List[str]) -> List[List[float]]:
    """
    Calls the HuggingFace Inference API to embed a batch of texts.
    Returns normalized 384-dim vectors.

    The API accepts up to ~100 texts per request. For large batches the caller
    should chunk appropriately, but typical document ingestion (10-50 chunks)
    is within limits.
    """
    headers = {
        "Authorization": f"Bearer {settings.HF_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = json.dumps({"inputs": texts, "options": {"wait_for_model": True}}).encode()

    req = urllib.request.Request(_HF_API_URL, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        raise RuntimeError(f"HuggingFace API error ({e.code}): {body}") from e
    except Exception as e:
        raise RuntimeError(f"HuggingFace API request failed: {e}") from e

    # HF feature-extraction API returns a list of lists (one per input)
    if not isinstance(result, list) or not result:
        raise RuntimeError(f"Unexpected HuggingFace API response shape: {type(result)}")

    # Normalize each vector to unit length (BGE models perform best with L2-norm)
    normalized = []
    for vec in result:
        norm = math.sqrt(sum(v * v for v in vec))
        normalized.append([v / norm for v in vec] if norm > 0 else vec)
    return normalized


def _hf_api_embed_single(text: str) -> List[float]:
    return _hf_api_embed([text])[0]


# ── Fallback (no model, no API key) ───────────────────────────────────────────

def _fallback_embedding(text: str) -> List[float]:
    """
    Deterministic 384-dim fallback embedding based on SHA-256 hashing.
    Has NO semantic meaning. Semantic search will return nonsense results.
    Only acceptable for CI smoke tests where real embeddings are unavailable.
    """
    vector = [0.0] * 384
    for token in text.lower().split():
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:2], "big") % len(vector)
        sign = 1.0 if digest[2] % 2 == 0 else -1.0
        vector[index] += sign
    norm = math.sqrt(sum(v * v for v in vector))
    return [v / norm for v in vector] if norm > 0 else vector


# ── Public API ─────────────────────────────────────────────────────────────────

@observe_time("generate_embeddings")
def generate_embeddings(texts: List[str]) -> List[List[float]]:
    """
    Generates 384-dimensional normalized embeddings for a list of document chunks.
    Selects the appropriate execution path automatically.
    """
    if not texts:
        return []

    # Path 1: HuggingFace Inference API (Vercel + HF_API_KEY set)
    if settings.HF_API_KEY:
        try:
            return _hf_api_embed(texts)
        except Exception as e:
            logger.error("HuggingFace API embedding failed, falling back: %s", e)

    # Path 2: Local sentence-transformers (dev / Railway)
    if not _ON_VERCEL:
        try:
            model = _get_local_model()
            embeddings = model.encode(
                texts,
                normalize_embeddings=True,
                show_progress_bar=False,
                batch_size=32,
                convert_to_numpy=True,
            )
            return [e.tolist() for e in embeddings]
        except Exception as e:
            logger.error("Local embedding model failed, falling back: %s", e)

    # Path 3: Deterministic hash fallback — semantic search will NOT work
    logger.warning(
        "Using hash-based fallback embeddings — semantic search is DISABLED. "
        "Set HF_API_KEY to enable real embeddings on Vercel."
    )
    return [_fallback_embedding(t) for t in texts]


@observe_time("generate_query_embedding")
def generate_query_embedding(query: str) -> List[float]:
    """
    Generates a normalized query embedding.
    Applies the BGE retrieval instruction prefix for optimal similarity ranking.
    """
    instruction_query = f"Represent this sentence for searching relevant passages: {query}"

    # Path 1: HuggingFace Inference API
    if settings.HF_API_KEY:
        try:
            return _hf_api_embed_single(instruction_query)
        except Exception as e:
            logger.error("HuggingFace API query embedding failed, falling back: %s", e)

    # Path 2: Local model
    if not _ON_VERCEL:
        try:
            model = _get_local_model()
            embedding = model.encode(
                instruction_query,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            return embedding.tolist()
        except Exception as e:
            logger.error("Local query embedding failed, falling back: %s", e)

    logger.warning(
        "Using hash-based fallback for query embedding — results will be meaningless. "
        "Set HF_API_KEY to enable real embeddings."
    )
    return _fallback_embedding(instruction_query)
