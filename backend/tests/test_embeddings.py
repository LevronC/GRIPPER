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


def _http_error(code):
    def fake(req, timeout):
        raise urllib.error.HTTPError(req.full_url, code, "err", {}, io.BytesIO(b"{}"))
    return fake


@pytest.mark.parametrize("code, fragment", [
    (401, "authentication failed"), (403, "access denied"), (404, "not found"),
    (429, "rate limited"), (503, "unavailable"), (500, "request rejected"),
])
def test_hf_http_errors_are_classified(monkeypatch, code, fragment):
    _hf(monkeypatch)
    monkeypatch.setattr(gen.urllib.request, "urlopen", _http_error(code))
    with pytest.raises(gen.EmbeddingUnavailable, match=fragment):
        gen.generate_embeddings(["a"])


@pytest.mark.parametrize("exc", [TimeoutError("timed out"), urllib.error.URLError("dns failure")])
def test_hf_timeout_and_network_errors(monkeypatch, exc):
    _hf(monkeypatch)

    def fake(req, timeout):
        assert timeout == gen.TIMEOUT_SECONDS
        raise exc

    monkeypatch.setattr(gen.urllib.request, "urlopen", fake)
    with pytest.raises(gen.EmbeddingUnavailable, match="unreachable or timed out"):
        gen.generate_query_embedding("q")


@pytest.mark.parametrize("body, match", [
    (b"not json", "malformed JSON"),
    (b"[[0.1, \"x\"]]", "shape"),
    (b"[]", "shape"),
    (("[[" + ",".join(["NaN"] * 384) + "]]").encode(), "non-finite"),
    (("[[" + ",".join(["0"] * 384) + "]]").encode(), "zero vector"),
])
def test_hf_malformed_or_invalid_vectors_rejected(monkeypatch, body, match):
    _hf(monkeypatch)
    monkeypatch.setattr(gen.urllib.request, "urlopen", lambda req, timeout: _Resp(body))
    with pytest.raises(gen.EmbeddingUnavailable, match=match):
        gen.generate_embeddings(["a"])


def test_hf_request_format_and_batching(monkeypatch):
    import json as _json

    _hf(monkeypatch)
    calls = []
    vec = [1.0] + [0.0] * 383

    def fake(req, timeout):
        body = _json.loads(req.data)
        calls.append((req.get_header("Authorization"), req.get_header("Content-type"), len(body["inputs"])))
        return _Resp(_json.dumps([vec] * len(body["inputs"])).encode())

    monkeypatch.setattr(gen.urllib.request, "urlopen", fake)
    vectors, _ = gen.generate_embeddings([f"t{i}" for i in range(gen.HF_BATCH + 5)])
    assert len(vectors) == gen.HF_BATCH + 5
    assert calls == [("Bearer hf_test_key", "application/json", gen.HF_BATCH), ("Bearer hf_test_key", "application/json", 5)]


def test_query_embedding_uses_bge_instruction_prefix(monkeypatch):
    _hf(monkeypatch)
    seen = {}
    vec = [1.0] + [0.0] * 383

    def fake(req, timeout):
        import json as _json
        seen["inputs"] = _json.loads(req.data)["inputs"]
        return _Resp(_json.dumps([vec]).encode())

    monkeypatch.setattr(gen.urllib.request, "urlopen", fake)
    gen.generate_query_embedding("capex risk")
    assert seen["inputs"] == [gen.BGE_QUERY_PREFIX + "capex risk"]


def test_vector_count_mismatch_rejected(monkeypatch):
    """A provider answering two texts with one vector must not be silently zipped/truncated."""
    monkeypatch.setattr(gen, "_hf_embed", lambda texts: [[1.0] + [0.0] * 383])
    with pytest.raises(gen.EmbeddingUnavailable, match="wrong number"):
        gen._embed(gen.EmbeddingSpace("hf_api", "BAAI/bge-small-en-v1.5", 384), ["a", "b"])


requires_model = pytest.mark.skipif(
    importlib.util.find_spec("sentence_transformers") is None,
    reason="sentence-transformers not installed (excluded from CI image); run locally with requirements.txt",
)


@pytest.mark.model
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
