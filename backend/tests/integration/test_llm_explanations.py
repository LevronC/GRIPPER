"""Explanation endpoint with a mocked SubQ transport. No live provider call."""

from __future__ import annotations

import json
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.config import settings
from app.services.llm.providers import subq as subq_mod

pytestmark = pytest.mark.integration


@pytest.fixture
def api():
    from app.main import app
    return TestClient(app)


@pytest.fixture
def subq_on(monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "subq")
    monkeypatch.setattr(settings, "LLM_EXTERNAL_PROCESSING_ENABLED", True)
    monkeypatch.setattr(settings, "SUBQ_API_KEY", "test-key")
    monkeypatch.setattr(settings, "SUBQ_BASE_URL", "https://api.subq.ai/v1")
    monkeypatch.setattr(settings, "SUBQ_MODEL", "subq-savant-1.4")
    monkeypatch.setattr(settings, "LLM_TIMEOUT_SECONDS", 5.0)
    monkeypatch.setattr(settings, "LLM_MAX_OUTPUT_TOKENS", 500)
    monkeypatch.setattr(settings, "LLM_MAX_RETRIES", 1)
    yield
    subq_mod.transport_override = None


def _completion(content: str) -> httpx.Response:
    return httpx.Response(200, json={
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "model": "subq-savant-1.4",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 20, "completion_tokens": 30, "total_tokens": 50,
                  "completion_tokens_details": {"reasoning_tokens": 8}},
    })


def test_default_explanation_does_not_call_subq(api, two_tenants):
    def boom(_request):
        raise AssertionError("external call")

    subq_mod.transport_override = httpx.MockTransport(boom)
    try:
        body = api.post(f"/violations/{two_tenants.a.event_id}/explain", headers=two_tenants.a.auth("pm")).json()
    finally:
        subq_mod.transport_override = None
    assert body["explanation_source"] == "template"
    assert body["fallback_reason"] is None
    assert body["violation_status"] == "open"
    assert body["explanation"].startswith("ASECRET is 42.0%")


def test_authorized_call_keeps_compliance_and_server_citations(api, two_tenants, owner_engine, subq_on):
    a, b = two_tenants.a, two_tenants.b
    chunk_id = uuid.uuid4()
    content = "ASECRET investment thesis position sizing risk synthetic excerpt ALPHA-ONLY"
    with owner_engine.begin() as conn:
        conn.execute(
            text("UPDATE institutions SET external_processing_authorized = true WHERE id = :i"),
            {"i": a.institution_id},
        )
        conn.execute(
            text(
                "INSERT INTO document_chunks (id, institution_id, report_id, content, metadata_json, created_at) "
                "VALUES (:c, :i, :r, :content, CAST(:meta AS json), now())"
            ),
            {"c": chunk_id, "i": a.institution_id, "r": a.report_id, "content": content, "meta": '{"page": 4, "chunk_index": 0}'},
        )

    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        user = json.loads(captured["body"]["messages"][1]["content"])
        captured["user"] = user
        cited = [item["chunk_id"] for item in user["excerpts"]] or []
        if cited:
            payload = {
                "policy_restatement": "ASECRET is 1.0% of the portfolio.",
                "research_commentary": "The excerpt discusses sizing. MODEL-NOTE",
                "cited_chunk_ids": [cited[0]],
                "insufficient_research": False,
            }
        else:
            payload = {
                "policy_restatement": "No excerpts were supplied.",
                "research_commentary": "The supplied research is not enough to add context.",
                "cited_chunk_ids": [],
                "insufficient_research": True,
            }
        return _completion(json.dumps(payload))

    subq_mod.transport_override = httpx.MockTransport(handler)
    body = api.post(f"/violations/{a.event_id}/explain", headers=a.auth("pm")).json()
    assert captured["url"] == "https://api.subq.ai/v1/chat/completions"
    assert "BSECRET" not in json.dumps(captured["user"])
    assert "bravo" not in json.dumps(captured["user"]).lower()
    assert body["explanation_source"] == "llm"
    assert body["violation_status"] == "open"
    assert body["explanation"].startswith("ASECRET is 42.0%")
    assert "1.0%" not in body["explanation"]
    assert "MODEL-NOTE" in body["explanation"]
    evidence_by_id = {item["chunk_id"]: item for item in body["evidence"]}
    cited = body["citations"][0]
    source = evidence_by_id[cited["chunk_id"]]
    assert cited["company"] == source["company"] == "ALPHA Corp"
    assert cited["page"] == source["page"]
    assert cited["report_id"] == source["report_id"] == str(a.report_id)
    assert str(b.chunk_id) not in json.dumps(body)
    with owner_engine.connect() as conn:
        resolved = conn.execute(
            text("SELECT resolved FROM governance_events WHERE id = :e"), {"e": a.event_id}
        ).scalar()
    assert resolved is False
    # A citation the model was not given is discarded, including text it invented.
    subq_mod.transport_override = httpx.MockTransport(
        lambda _request: _completion(json.dumps({
            "policy_restatement": "x",
            "research_commentary": "LEAKED-FROM-MODEL",
            "cited_chunk_ids": [str(b.chunk_id)],
            "insufficient_research": False,
        }))
    )
    rejected = api.post(f"/violations/{a.event_id}/explain", headers=a.auth("pm")).json()
    assert rejected["explanation_source"] == "template"
    assert rejected["fallback_reason"] == "invalid_citations"
    assert "LEAKED-FROM-MODEL" not in rejected["explanation"]
    assert rejected["violation_status"] == "open"
