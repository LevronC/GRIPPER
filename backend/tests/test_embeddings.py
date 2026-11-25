"""Embedding provider selection: explicit, no silent fallback (no database)."""

from __future__ import annotations

import importlib.util
import io
import urllib.error

import pytest

from app.services.embeddings import generator as gen


@pytest.mark.parametrize("provider", ["none", "bogus"])
def test_disabled_or_unknown_provider_means_no_semantic_search(monkeypatch, provider):
    monkeypatch.setenv("EMBEDDING_PROVIDER", provider)
    assert gen.active_space() is None
    with pytest.raises(gen.EmbeddingUnavailable):
        gen.generate_embeddings(["text"])
    with pytest.raises(gen.EmbeddingUnavailable):
        gen.generate_query_embedding("text")


def test_hash_vectors_refused_outside_test_environment(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "hash_test")
    monkeypatch.setattr(gen.settings, "ENVIRONMENT", "production")
    assert gen.active_space() is None


def test_hash_space_never_matches_a_real_model(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "hash_test")
    space = gen.active_space()
    assert space.space_id == "hash-test-v1@384"
    assert space.space_id != gen.EmbeddingSpace("local", "BAAI/bge-small-en-v1.5", 384).space_id


def test_local_and_hf_share_a_space():
    a = gen.EmbeddingSpace("local", "BAAI/bge-small-en-v1.5", 384)
    b = gen.EmbeddingSpace("hf_api", "BAAI/bge-small-en-v1.5", 384)
    assert a.space_id == b.space_id


def test_hf_requires_key(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "hf_api")
    monkeypatch.setattr(gen.settings, "HF_API_KEY", "")
    assert gen.active_space() is None


def test_auto_on_vercel_without_key_disables_semantic_search(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "auto")
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setattr(gen.settings, "HF_API_KEY", "")
    assert gen.active_space() is None


def _hf(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "hf_api")
    monkeypatch.setattr(gen.settings, "HF_API_KEY", "hf_test_key")


def test_hf_http_error_raises_instead_of_substituting(monkeypatch):
    _hf(monkeypatch)
    seen = {}

    def fake_urlopen(req, timeout):
        seen["url"] = req.full_url
        raise urllib.error.HTTPError(req.full_url, 503, "busy", {}, io.BytesIO(b"{}"))

    monkeypatch.setattr(gen.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(gen.EmbeddingUnavailable, match="503"):
        gen.generate_embeddings(["a", "b"])
    assert seen["url"].startswith("https://router.huggingface.co/hf-inference/models/BAAI/bge-small-en-v1.5")


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_hf_bad_shape_and_dimension_rejected(monkeypatch):
    _hf(monkeypatch)
    monkeypatch.setattr(gen.urllib.request, "urlopen", lambda req, timeout: _Resp(b'{"error": "x"}'))
    with pytest.raises(gen.EmbeddingUnavailable):
        gen.generate_embeddings(["a"])
    monkeypatch.setattr(gen.urllib.request, "urlopen", lambda req, timeout: _Resp(b"[[0.1, 0.2, 0.3]]"))
    with pytest.raises(gen.EmbeddingUnavailable, match="384"):
        gen.generate_embeddings(["a"])


def test_hf_success_is_normalised(monkeypatch):
    _hf(monkeypatch)
    vec = "[" + ",".join(["2.0"] * 384) + "]"
    monkeypatch.setattr(gen.urllib.request, "urlopen", lambda req, timeout: _Resp(f"[{vec}]".encode()))
    vectors, space = gen.generate_embeddings(["a"])
    assert space.provider == "hf_api"
    assert abs(sum(v * v for v in vectors[0]) - 1.0) < 1e-9


requires_model = pytest.mark.skipif(
    importlib.util.find_spec("sentence_transformers") is None,
    reason="sentence-transformers not installed (excluded from CI image); run locally with requirements.txt",
)


@requires_model
def test_local_model_produces_semantic_similarity(monkeypatch):
    """Real BGE model: a paraphrase must score closer than an unrelated sentence."""
    monkeypatch.setenv("EMBEDDING_PROVIDER", "local")
    (doc_a, doc_b), space = gen.generate_embeddings([
        "The company's free cash flow declined because capital expenditures rose sharply.",
        "The museum extended its opening hours for the summer festival.",
    ])
    query, _ = gen.generate_query_embedding("Why did cash generation fall after higher capex?")
    sim = lambda u, v: sum(x * y for x, y in zip(u, v))  # noqa: E731 (unit vectors)
    assert space.provider == "local" and space.space_id == "BAAI/bge-small-en-v1.5@384"
    assert sim(query, doc_a) > sim(query, doc_b) + 0.1
