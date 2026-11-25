"""Blob deletion uses Vercel's real delete API; /health reflects a failing embedding provider."""
import json
import logging

import pytest

from app.core import blob
from app.services.embeddings import generator
from app.services.embeddings.generator import EmbeddingUnavailable, generate_query_embedding

BLOB_URL = "https://store.public.blob.vercel-storage.com/report-abc123.pdf"


class _Response:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return b"{}"


def test_delete_blob_posts_urls_to_delete_endpoint(monkeypatch):
    seen = []
    monkeypatch.setattr(blob.settings, "BLOB_READ_WRITE_TOKEN", "test-token")
    monkeypatch.setattr(blob.urllib.request, "urlopen", lambda req, timeout=None: seen.append(req) or _Response())

    blob.delete_blob(BLOB_URL)

    (req,) = seen
    assert req.get_method() == "POST"  # @vercel/blob del(); HTTP DELETE returned 404 in production
    assert req.full_url == "https://blob.vercel-storage.com/delete"
    assert json.loads(req.data) == {"urls": [BLOB_URL]}
    assert req.get_header("Authorization") == "Bearer test-token"
    assert req.get_header("Content-type") == "application/json"
    assert req.get_header("X-api-version") == "13"


def test_delete_blob_failure_is_logged_not_raised(monkeypatch, caplog):
    def fail(req, timeout=None):
        raise blob.urllib.error.HTTPError(req.full_url, 500, "Server Error", None, None)

    monkeypatch.setattr(blob.urllib.request, "urlopen", fail)
    with caplog.at_level(logging.WARNING, logger=blob.logger.name):
        blob.delete_blob(BLOB_URL)
    assert "Could not delete blob" in caplog.text


@pytest.fixture
def fresh_provider_status(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "hash_test")
    monkeypatch.setattr(generator, "_LAST_PROVIDER_CALL", {"state": "unverified", "reason": None, "at": None})


def test_health_reports_failing_provider_as_full_text_only(client, fresh_provider_status, monkeypatch):
    caps = client.get("/health").json()["capabilities"]
    assert caps["semantic_search"] is True and caps["embedding_provider"]["state"] == "unverified"

    def rejected(space, texts):
        raise EmbeddingUnavailable("Hugging Face API returned HTTP 402: request rejected")

    monkeypatch.setattr(generator, "_embed_unrecorded", rejected)
    with pytest.raises(EmbeddingUnavailable):
        generate_query_embedding("semiconductor liquidity")
    caps = client.get("/health").json()["capabilities"]
    assert caps["semantic_search"] is False and caps["retrieval_mode"] == "full_text_only"
    assert caps["embedding_provider"]["state"] == "failing"
    assert "HTTP 402" in caps["embedding_provider"]["reason"]
    assert caps["embedding"]["provider"] == "hash_test"  # still configured; only the outcome changed

    monkeypatch.undo()
    monkeypatch.setenv("EMBEDDING_PROVIDER", "hash_test")
    generate_query_embedding("semiconductor liquidity")
    caps = client.get("/health").json()["capabilities"]
    assert caps["semantic_search"] is True and caps["retrieval_mode"] == "hybrid"
    assert caps["embedding_provider"]["state"] == "ok" and caps["embedding_provider"]["reason"] is None


def test_health_without_provider_is_not_configured(client, monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "none")
    caps = client.get("/health").json()["capabilities"]
    assert caps["semantic_search"] is False
    assert caps["embedding_provider"] == {"state": "not_configured", "reason": None, "at": None}
