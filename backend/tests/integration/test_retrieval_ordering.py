"""
Retrieval ordering against real PostgreSQL + pgvector, with hand-calculated expectations.

The vectors below are SYNTHETIC TEST FIXTURES with chosen cosine similarities to a fixed
query vector. They are not semantic embeddings and say nothing about retrieval quality.
They are stored in the active test embedding space so the vector leg compares them.
"""

from __future__ import annotations

import math
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.session import SessionLocal, set_tenant
from app.services.embeddings.generator import EmbeddingUnavailable, active_space
from app.services.retrieval.searcher import hybrid_search

pytestmark = pytest.mark.integration

DIM = 384


def basis(*coeffs):
    v = list(coeffs) + [0.0] * (DIM - len(coeffs))
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v]


QUERY_VEC = basis(1.0)
QUERY = "liquidity covenant"
# name: (vector, content, expected cosine to QUERY_VEC)
FIXTURES = {
    "c1": (basis(1.0), "alpha beta gamma", 1.0),
    "c2": (basis(1.0, 1.0), "liquidity covenant liquidity covenant liquidity covenant", 1 / math.sqrt(2)),
    "c3": (basis(1.0, 3.0), "delta epsilon", 1 / math.sqrt(10)),
    "c4": (basis(0.0, 1.0), "liquidity covenant liquidity", 0.0),
    "c5": (basis(-1.0), "zeta eta", -1.0),
}


def _lit(v):
    return "[" + ",".join(f"{x:.9f}" for x in v) + "]"


def _insert(conn, institution_id, report_id, cid, vec, content, model):
    conn.execute(text(
        "INSERT INTO document_chunks (id, institution_id, report_id, content, embedding, embedding_model, "
        "embedding_provider, metadata_json, created_at) VALUES (:c, :i, :r, :t, CAST(:v AS vector), :m, "
        "'hash_test', CAST(:meta AS json), now())"),
        {"c": cid, "i": institution_id, "r": report_id, "t": content, "v": _lit(vec), "m": model,
         "meta": '{"page": 1, "chunk_index": 0}'})


@pytest.fixture
def corpus(owner_engine, two_tenants, monkeypatch):
    a, b = two_tenants.a, two_tenants.b
    space = active_space()
    ids = {name: uuid.uuid4() for name in FIXTURES}
    rid_a, rid_b = uuid.uuid4(), uuid.uuid4()
    with owner_engine.begin() as conn:
        conn.execute(text("DELETE FROM research_reports WHERE institution_id = :i"), {"i": a.institution_id})
        for rid, inst in ((rid_a, a.institution_id), (rid_b, b.institution_id)):
            conn.execute(text("INSERT INTO research_reports (id, institution_id, sector, company, recommendation, status, created_at) "
                              "VALUES (:r, :i, 'Financials', 'Fixture Co', 'hold', 'processed', now())"), {"r": rid, "i": inst})
        for name, (vec, content, _) in FIXTURES.items():
            _insert(conn, a.institution_id, rid_a, ids[name], vec, content, space.space_id)
        # Tenant B: a perfect vector AND keyword match. Must never appear for A.
        _insert(conn, b.institution_id, rid_b, uuid.uuid4(), QUERY_VEC, "liquidity covenant " * 5, space.space_id)
    def fixture_query_embedding(_query):
        # Behaves like the real function: unavailable when no provider is configured.
        if active_space() is None:
            raise EmbeddingUnavailable("no embedding provider configured")
        return QUERY_VEC, space

    monkeypatch.setattr("app.services.retrieval.searcher.generate_query_embedding", fixture_query_embedding)
    names = {str(v): k for k, v in ids.items()}
    return a, ids, names


def _search(a, limit=5, query=QUERY):
    with SessionLocal() as db:
        set_tenant(db, a.institution_id)
        return hybrid_search(db, query, a.institution_id, limit=limit)


def test_vector_leg_orders_by_cosine_similarity(corpus, monkeypatch):
    a, ids, names = corpus
    monkeypatch.setattr("app.services.retrieval.searcher.full_text_leg", lambda *_args, **_kwargs: [])
    out = _search(a, limit=5)
    assert [names[r["chunk_id"]] for r in out.results] == ["c1", "c2", "c3", "c4", "c5"]
    for r in out.results:
        assert r["similarity"] == pytest.approx(FIXTURES[names[r["chunk_id"]]][2], abs=1e-6)
        assert r["text_rank"] is None


def test_hybrid_order_matches_hand_calculated_rrf(corpus):
    """
    vector ranks: c1=1 c2=2 c3=3 c4=4 c5=5; full-text ranks (AND of both terms): c2=1 c4=2
    RRF(k=60): c2 = 1/62+1/61 = .03252, c4 = 1/64+1/62 = .03175, c1 = 1/61 = .01639,
               c3 = 1/63 = .01587, c5 = 1/65 = .01538
    """
    a, ids, names = corpus
    out = _search(a, limit=5)
    assert out.retrieval_mode == "hybrid" and out.legs == {"vector": 5, "full_text": 2}
    got = [(names[r["chunk_id"]], r["vector_rank"], r["text_rank"]) for r in out.results]
    assert got == [("c2", 2, 1), ("c4", 4, 2), ("c1", 1, None), ("c3", 3, None), ("c5", 5, None)]
    expected = {"c2": 1/62 + 1/61, "c4": 1/64 + 1/62, "c1": 1/61, "c3": 1/63, "c5": 1/65}
    for r in out.results:
        assert r["rrf_score"] == pytest.approx(expected[names[r["chunk_id"]]], rel=1e-12)


def test_limit_and_candidate_window(corpus):
    a, _, names = corpus
    out = _search(a, limit=2)
    assert [names[r["chunk_id"]] for r in out.results] == ["c2", "c4"]
    assert out.legs["vector"] == 5   # candidates = 3 * limit = 6 >= 5 available


def test_other_tenant_never_returned_even_as_perfect_match(corpus):
    a, ids, names = corpus
    for limit in (1, 5, 20):
        out = _search(a, limit=limit)
        assert all(r["chunk_id"] in names for r in out.results)


def test_keyword_only_fallback_orders_by_ts_rank(corpus, monkeypatch):
    a, _, names = corpus
    monkeypatch.setenv("EMBEDDING_PROVIDER", "none")
    out = _search(a, limit=5)
    assert out.retrieval_mode == "full_text_only"
    assert [(names[r["chunk_id"]], r["vector_rank"], r["text_rank"]) for r in out.results] == [("c2", None, 1), ("c4", None, 2)]
    assert out.results[0]["similarity"] > out.results[1]["similarity"]  # ts_rank: 3x terms > fewer


def test_empty_results(corpus, monkeypatch):
    a, _, _ = corpus
    monkeypatch.setenv("EMBEDDING_PROVIDER", "none")
    assert _search(a, query="zzzunmatchedterm").results == []
    assert _search(a, query="   ").results == []


def test_quarantined_vectors_do_not_participate(corpus, owner_engine):
    a, ids, names = corpus
    with owner_engine.begin() as conn:
        conn.execute(text("UPDATE document_chunks SET embedding_model = 'legacy-unknown' WHERE id = :c"), {"c": ids["c1"]})
    out = _search(a, limit=5)
    assert "c1" not in [names[r["chunk_id"]] for r in out.results]   # perfect vector match, but quarantined
    assert out.legs["vector"] == 4


def test_search_api_exposes_same_order(corpus):
    from app.main import app

    a, _, names = corpus
    body = TestClient(app).post("/search/semantic", json={"query": QUERY, "limit": 5}, headers=a.auth("analyst")).json()
    assert [names[r["chunk_id"]] for r in body["results"]] == ["c2", "c4", "c1", "c3", "c5"]
    assert body["retrieval_mode"] == "hybrid"


def test_repeated_searches_are_identical(corpus):
    a, _, _ = corpus
    first = [(r["chunk_id"], r["rrf_score"]) for r in _search(a).results]
    for _ in range(5):
        assert [(r["chunk_id"], r["rrf_score"]) for r in _search(a).results] == first
