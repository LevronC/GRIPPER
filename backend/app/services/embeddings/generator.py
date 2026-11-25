"""
Embedding generation with explicit providers and NO silent fallback.

EMBEDDING_PROVIDER:
  auto (default) — hf_api if HF_API_KEY is set; else local if sentence-transformers is
                   installed and not on Vercel; else none.
  local          — sentence-transformers, in-process (BAAI/bge-small-en-v1.5, 384-d).
  hf_api         — Hugging Face Inference (router.huggingface.co, hf-inference provider).
  none           — semantic embeddings disabled; retrieval is full-text only.
  hash_test      — deterministic token-hash vectors with NO semantic meaning. Allowed only
                   when ENVIRONMENT=test, and stored under their own embedding space so
                   they can never be compared with real embeddings.

Every stored vector records the embedding *space* that produced it
(`document_chunks.embedding_model`, e.g. "BAAI/bge-small-en-v1.5@384"). Vector search
only compares a query against chunks from the active space. When the provider is
unavailable or fails, callers receive EmbeddingUnavailable and must degrade to
full-text search; no substitute vectors are ever generated.

Switching models: chunks from the old space are excluded from vector search until
re-embedded with `scripts/reembed.py` (dry-run by default).
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import logging
import math
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, List, Optional

from app.core.config import settings
from app.core.observability import observe_time

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 384  # document_chunks.embedding is vector(384)
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
HF_ROUTER_URL = "https://router.huggingface.co/hf-inference/models/{model}/pipeline/feature-extraction"
HF_BATCH = 32
TIMEOUT_SECONDS = 30


class EmbeddingUnavailable(Exception):
    """The configured provider cannot produce embeddings right now (or none is configured)."""


@dataclass(frozen=True)
class EmbeddingSpace:
    provider: str  # local | hf_api | hash_test
    model: str
    dimension: int

    @property
    def space_id(self) -> str:
        # local and hf_api serve the same model weights with the same pooling and
        # normalisation, so they share a space. hash_test never matches a real model.
        return f"{self.model}@{self.dimension}"

    def public(self) -> dict:
        return {"provider": self.provider, "model": self.model, "dimension": self.dimension}


_local_model = None


def _on_vercel() -> bool:
    return os.getenv("VERCEL") == "1"


def _requested_provider() -> str:
    return os.getenv("EMBEDDING_PROVIDER", "auto").strip().lower()


def active_space() -> Optional[EmbeddingSpace]:
    """The embedding space that would be used now, or None when semantic search is off."""
    provider = _requested_provider()
    if provider == "auto":
        if settings.HF_API_KEY:
            provider = "hf_api"
        elif not _on_vercel() and importlib.util.find_spec("sentence_transformers") is not None:
            provider = "local"
        else:
            provider = "none"
    if provider == "none":
        return None
    if provider == "hash_test":
        if settings.ENVIRONMENT != "test":
            logger.error("EMBEDDING_PROVIDER=hash_test is only allowed when ENVIRONMENT=test")
            return None
        return EmbeddingSpace("hash_test", "hash-test-v1", EMBEDDING_DIM)
    if provider == "hf_api":
        if not settings.HF_API_KEY:
            logger.error("EMBEDDING_PROVIDER=hf_api but HF_API_KEY is not set")
            return None
        return EmbeddingSpace("hf_api", settings.EMBEDDING_MODEL_NAME, EMBEDDING_DIM)
    if provider == "local":
        if _on_vercel():
            logger.error("EMBEDDING_PROVIDER=local is not supported on Vercel")
            return None
        return EmbeddingSpace("local", settings.EMBEDDING_MODEL_NAME, EMBEDDING_DIM)
    logger.error("Unknown EMBEDDING_PROVIDER=%r; semantic search disabled", provider)
    return None


# ── Providers ──────────────────────────────────────────────────────────────────

def _normalize(vec: List[float]) -> List[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0:
        raise EmbeddingUnavailable("provider returned a zero vector")
    return [v / norm for v in vec]


def _local_embed(texts: List[str]) -> List[List[float]]:
    global _local_model
    try:
        if _local_model is None:
            from sentence_transformers import SentenceTransformer

            _local_model = SentenceTransformer(settings.EMBEDDING_MODEL_NAME, device="cpu")
        vectors = _local_model.encode(
            texts, normalize_embeddings=True, show_progress_bar=False, batch_size=32, convert_to_numpy=True
        )
    except Exception as exc:
        raise EmbeddingUnavailable(f"local model failed ({type(exc).__name__})") from exc
    return [v.tolist() for v in vectors]


def _hf_embed(texts: List[str]) -> List[List[float]]:
    url = HF_ROUTER_URL.format(model=settings.EMBEDDING_MODEL_NAME)
    out: List[List[float]] = []
    for i in range(0, len(texts), HF_BATCH):
        payload = json.dumps({"inputs": texts[i:i + HF_BATCH]}).encode()
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Authorization": f"Bearer {settings.HF_API_KEY}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
                result: Any = json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            raise EmbeddingUnavailable(f"Hugging Face API returned HTTP {exc.code}") from exc
        except Exception as exc:
            raise EmbeddingUnavailable(f"Hugging Face API request failed ({type(exc).__name__})") from exc
        if not isinstance(result, list) or len(result) != len(texts[i:i + HF_BATCH]):
            raise EmbeddingUnavailable("unexpected Hugging Face API response shape")
        out.extend(_normalize([float(x) for x in vec]) for vec in result)
    return out


def _hash_embed(text: str) -> List[float]:
    """TEST ONLY. Token-hash vector; shares tokens => some similarity, no semantics."""
    vector = [0.0] * EMBEDDING_DIM
    for token in text.lower().split():
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        vector[int.from_bytes(digest[:2], "big") % EMBEDDING_DIM] += 1.0 if digest[2] % 2 == 0 else -1.0
    norm = math.sqrt(sum(v * v for v in vector))
    return [v / norm for v in vector] if norm else [1.0] + [0.0] * (EMBEDDING_DIM - 1)


def _embed(space: EmbeddingSpace, texts: List[str]) -> List[List[float]]:
    if space.provider == "local":
        vectors = _local_embed(texts)
    elif space.provider == "hf_api":
        vectors = _hf_embed(texts)
    else:
        vectors = [_hash_embed(t) for t in texts]
    for v in vectors:
        if len(v) != space.dimension:
            raise EmbeddingUnavailable(f"expected {space.dimension}-d vectors, got {len(v)}")
    return vectors


# ── Public API ─────────────────────────────────────────────────────────────────

@observe_time("generate_embeddings")
def generate_embeddings(texts: List[str]) -> tuple[List[List[float]], EmbeddingSpace]:
    """Embeds document chunks. Raises EmbeddingUnavailable; never substitutes vectors."""
    space = active_space()
    if space is None:
        raise EmbeddingUnavailable("no embedding provider configured")
    if not texts:
        return [], space
    return _embed(space, texts), space


@observe_time("generate_query_embedding")
def generate_query_embedding(query: str) -> tuple[List[float], EmbeddingSpace]:
    space = active_space()
    if space is None:
        raise EmbeddingUnavailable("no embedding provider configured")
    text = BGE_QUERY_PREFIX + query if space.provider in ("local", "hf_api") else query
    return _embed(space, [text])[0], space
