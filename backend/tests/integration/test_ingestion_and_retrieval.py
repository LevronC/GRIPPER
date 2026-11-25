"""Ingestion lifecycle and degraded retrieval (real DB, restricted role)."""

from __future__ import annotations

import os
import uuid

import pymupdf
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.session import SessionLocal, set_tenant
from app.services.embeddings import generator as gen
from app.services.embeddings.generator import EmbeddingUnavailable
from app.services.ingestion.pipeline import ingest_document
from app.services.retrieval.searcher import hybrid_search

pytestmark = pytest.mark.integration

BODY = ("Synthetic research note. The semiconductor supplier reported elevated inventory and "
        "weaker gross margin guidance; liquidity remains adequate. ") * 40


@pytest.fixture
def api():
    from app.main import app
    return TestClient(app)


def _pdf(path, body: str = BODY, pages: int = 2) -> str:
    doc = pymupdf.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_textbox(pymupdf.Rect(36, 36, 560, 800), f"Page {i + 1}. {body}" if body else "", fontsize=8)
    doc.save(str(path))
    doc.close()
    return str(path)


def _report(owner_engine, institution_id, file_path, status="pending") -> uuid.UUID:
    rid = uuid.uuid4()
    with owner_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO research_reports (id, institution_id, sector, company, recommendation, status, "
                 "file_path, created_at) VALUES (:r, :i, 'Technology', 'Synthetic Semi', 'hold', :s, :f, now())"),
            {"r": rid, "i": institution_id, "s": status, "f": file_path},
        )
    return rid


def _state(owner_engine, rid):
    with owner_engine.connect() as conn:
        r = conn.execute(text("SELECT status, attempts, error_message, file_path, processed_at FROM research_reports WHERE id = :r"),
                         {"r": rid}).mappings().one()
        n = conn.execute(text("SELECT count(*) FROM document_chunks WHERE report_id = :r"), {"r": rid}).scalar()
        models = set(conn.execute(text("SELECT embedding_model FROM document_chunks WHERE report_id = :r"), {"r": rid}).scalars())
    return dict(r), n, models


def _ingest(rid, file_ref, institution_id):
    with SessionLocal() as db:
        set_tenant(db, institution_id)
        return ingest_document(db, rid, file_ref, institution_id)


def test_successful_ingestion_records_provenance_and_deletes_source(owner_engine, two_tenants, tmp_path):
    a = two_tenants.a
    path = _pdf(tmp_path / "ok.pdf")
    rid = _report(owner_engine, a.institution_id, path)
    n = _ingest(rid, path, a.institution_id)
    state, chunks, models = _state(owner_engine, rid)
    assert n == chunks >= 2
    assert state["status"] == "processed" and state["attempts"] == 1 and state["processed_at"] is not None
    assert models == {"hash-test-v1@384"}
    assert state["file_path"] is None and not os.path.exists(path)  # deleted only after commit
    with owner_engine.connect() as conn:
        pages = set(conn.execute(text("SELECT metadata_json->>'page' FROM document_chunks WHERE report_id = :r"), {"r": rid}).scalars())
    assert pages == {"1", "2"}


def test_failed_ingestion_keeps_source_and_is_visible(owner_engine, two_tenants, tmp_path):
    a = two_tenants.a
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"%PDF-1.4 this is not really a pdf")
    rid = _report(owner_engine, a.institution_id, str(bad))
    with pytest.raises(Exception):
        _ingest(rid, str(bad), a.institution_id)
    state, chunks, _ = _state(owner_engine, rid)
    assert state["status"] == "failed" and chunks == 0
    assert state["error_message"] == "The file could not be parsed as a PDF."
    assert state["file_path"] == str(bad) and bad.exists()  # input preserved for retry


def test_retry_after_fix_succeeds_without_duplicate_chunks(api, owner_engine, two_tenants, tmp_path, monkeypatch):
    monkeypatch.setenv("INGESTION_MODE", "sync")
    a = two_tenants.a
    path = tmp_path / "retry.pdf"
    path.write_bytes(b"%PDF-1.4 broken")
    rid = _report(owner_engine, a.institution_id, str(path))
    with pytest.raises(Exception):
        _ingest(rid, str(path), a.institution_id)
    _pdf(path)  # operator replaces the file; source was retained
    r = api.post(f"/documents/{rid}/retry", headers=a.auth("analyst"))
    assert r.status_code == 202, r.text
    assert r.json()["status"] == "processed"
    state, chunks, _ = _state(owner_engine, rid)
    assert state["attempts"] == 2 and chunks >= 2
    # Re-running a completed job is a no-op, not a duplicate.
    assert _ingest(rid, str(path), a.institution_id) == chunks
    assert _state(owner_engine, rid)[1] == chunks


def test_reprocessing_replaces_chunks(owner_engine, two_tenants, tmp_path):
    a = two_tenants.a
    path = _pdf(tmp_path / "again.pdf")
    keep = tmp_path / "again-copy.pdf"
    keep.write_bytes(open(path, "rb").read())
    rid = _report(owner_engine, a.institution_id, path)
    n1 = _ingest(rid, path, a.institution_id)
    with owner_engine.begin() as conn:  # simulate a crashed run that must be redone
        conn.execute(text("UPDATE research_reports SET status = 'failed', file_path = :f WHERE id = :r"), {"f": str(keep), "r": rid})
    n2 = _ingest(rid, str(keep), a.institution_id)
    assert n1 == n2 == _state(owner_engine, rid)[1]


def test_retry_rules(api, owner_engine, two_tenants, tmp_path):
    a, b = two_tenants.a, two_tenants.b
    assert api.post(f"/documents/{a.report_id}/retry", headers=a.auth("analyst")).status_code == 409  # processed
    gone = _report(owner_engine, a.institution_id, None, status="failed")
    assert api.post(f"/documents/{gone}/retry", headers=a.auth("analyst")).status_code == 410
    other = _report(owner_engine, b.institution_id, str(tmp_path / "x.pdf"), status="failed")
    assert api.post(f"/documents/{other}/retry", headers=a.auth("analyst")).status_code == 404
    assert api.post(f"/documents/{gone}/retry", headers=a.auth("faculty")).status_code == 403


def test_empty_pdf_fails_with_clear_reason(owner_engine, two_tenants, tmp_path):
    a = two_tenants.a
    path = str(tmp_path / "empty.pdf")
    doc = pymupdf.open()
    doc.new_page()
    doc.save(path)
    doc.close()
    rid = _report(owner_engine, a.institution_id, path)
    with pytest.raises(Exception):
        _ingest(rid, path, a.institution_id)
    state, _, _ = _state(owner_engine, rid)
    assert state["status"] == "failed" and "No extractable text" in state["error_message"]


def test_duplicate_content_marked_duplicate(owner_engine, two_tenants, tmp_path):
    a = two_tenants.a
    first = _pdf(tmp_path / "d1.pdf")
    second = tmp_path / "d2.pdf"
    second.write_bytes(open(first, "rb").read())
    r1 = _report(owner_engine, a.institution_id, first)
    _ingest(r1, first, a.institution_id)
    r2 = _report(owner_engine, a.institution_id, str(second))
    assert _ingest(r2, str(second), a.institution_id) == 0
    state, chunks, _ = _state(owner_engine, r2)
    assert state["status"] == "duplicate" and chunks == 0 and str(r1) in state["error_message"]


def test_provider_failure_stores_chunks_without_vectors_and_search_degrades(owner_engine, two_tenants, tmp_path, monkeypatch):
    a = two_tenants.a

    def down(*_a, **_k):
        raise EmbeddingUnavailable("provider down")

    monkeypatch.setattr(gen, "_embed", down)
    path = _pdf(tmp_path / "novec.pdf")
    rid = _report(owner_engine, a.institution_id, path)
    n = _ingest(rid, path, a.institution_id)
    state, chunks, models = _state(owner_engine, rid)
    assert state["status"] == "processed" and n == chunks and models == {None}
    with owner_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM document_chunks WHERE report_id = :r AND embedding IS NOT NULL"),
                            {"r": rid}).scalar() == 0  # no substitute vectors

    with SessionLocal() as db:
        set_tenant(db, a.institution_id)
        out = hybrid_search(db, "semiconductor inventory gross margin", a.institution_id, limit=5)
    assert out.retrieval_mode == "full_text_only" and "provider down" in out.degraded_reason
    assert any(r["report_id"] == str(rid) for r in out.results)  # FTS still finds it


def test_vector_leg_ignores_other_embedding_spaces(owner_engine, two_tenants):
    a = two_tenants.a
    with owner_engine.begin() as conn:
        conn.execute(text("UPDATE document_chunks SET embedding_model = 'legacy-unknown' WHERE id = :c"), {"c": a.chunk_id})
    query = "zzunrelatedqueryterm"  # no FTS match, so only the vector leg could return anything
    with SessionLocal() as db:
        set_tenant(db, a.institution_id)
        assert hybrid_search(db, query, a.institution_id).legs["vector"] == 0
    with owner_engine.begin() as conn:
        conn.execute(text("UPDATE document_chunks SET embedding_model = 'hash-test-v1@384' WHERE id = :c"), {"c": a.chunk_id})
    with SessionLocal() as db:
        set_tenant(db, a.institution_id)
        assert hybrid_search(db, query, a.institution_id).legs["vector"] == 1


def test_search_api_reports_mode(api, two_tenants, monkeypatch):
    a = two_tenants.a
    body = api.post("/search/semantic", json={"query": "semiconductor liquidity", "limit": 3}, headers=a.auth("analyst")).json()
    assert body["retrieval_mode"] == "hybrid" and body["degraded_reason"] is None
    monkeypatch.setenv("EMBEDDING_PROVIDER", "none")
    body = api.post("/search/semantic", json={"query": "semiconductor liquidity", "limit": 3}, headers=a.auth("analyst")).json()
    assert body["retrieval_mode"] == "full_text_only" and body["degraded_reason"]
    assert any(r["chunk_id"] == str(a.chunk_id) for r in body["results"])


def test_health_reports_capabilities(api, monkeypatch):
    caps = api.get("/health").json()["capabilities"]
    assert caps["semantic_search"] is True and caps["retrieval_mode"] == "hybrid"
    assert caps["embedding"] == {"provider": "hash_test", "model": "hash-test-v1", "dimension": 384}
    monkeypatch.setenv("EMBEDDING_PROVIDER", "none")
    caps = api.get("/health").json()["capabilities"]
    assert caps["semantic_search"] is False and caps["retrieval_mode"] == "full_text_only" and caps["embedding"] is None
    assert set(caps) == {
        "semantic_search", "retrieval_mode", "embedding", "embedding_provider", "ingestion_mode",
        "email_delivery", "llm",
    }
    assert caps["embedding_provider"]["state"] == "not_configured"
    assert caps["llm"] == {
        "provider": "none",
        "external_processing_enabled": False,
        "model": None,
        "credentials_configured": False,
        "live_generation": "unverified",
    }


def test_upload_endpoint_end_to_end(api, owner_engine, two_tenants, tmp_path, monkeypatch):
    a = two_tenants.a
    monkeypatch.setenv("INGESTION_MODE", "sync")
    monkeypatch.setattr("app.core.config.settings.UPLOAD_DIR", str(tmp_path))
    pdf = _pdf(tmp_path / "upload-src.pdf")
    with open(pdf, "rb") as fh:
        r = api.post("/documents/upload", headers=a.auth("analyst"),
                     data={"sector": "Technology", "company": "Synthetic Semi", "recommendation": "hold"},
                     files={"file": ("note.pdf", fh, "application/pdf")})
    assert r.status_code == 202, r.text
    assert r.json()["status"] == "processed" and r.json()["chunks"] >= 2
    listed = api.get("/documents", headers=a.auth("analyst")).json()["results"]
    assert any(d["id"] == r.json()["report_id"] and d["status"] == "processed" for d in listed)

    with open(pdf, "rb") as fh:
        denied = api.post("/documents/upload", headers=a.auth("faculty"),
                          data={"sector": "Technology", "company": "X", "recommendation": "hold"},
                          files={"file": ("note.pdf", fh, "application/pdf")})
    assert denied.status_code == 403


def test_upload_failure_is_reported_not_hidden(api, owner_engine, two_tenants, tmp_path, monkeypatch):
    a = two_tenants.a
    monkeypatch.setenv("INGESTION_MODE", "sync")
    monkeypatch.setattr("app.core.config.settings.UPLOAD_DIR", str(tmp_path))
    r = api.post("/documents/upload", headers=a.auth("analyst"),
                 data={"sector": "Technology", "company": "Broken", "recommendation": "sell"},
                 files={"file": ("bad.pdf", b"%PDF-1.4 garbage", "application/pdf")})
    assert r.status_code == 202
    assert r.json()["status"] == "failed" and "parsed" in r.json()["message"]
    listed = {d["id"]: d for d in api.get("/documents", headers=a.auth("analyst")).json()["results"]}
    doc = listed[r.json()["report_id"]]
    assert doc["status"] == "failed" and doc["error_message"] and "Traceback" not in doc["error_message"]


def test_stale_processing_job_is_picked_up(owner_engine, runtime_engine, two_tenants, tmp_path):
    a = two_tenants.a
    rid = _report(owner_engine, a.institution_id, str(tmp_path / "stale.pdf"), status="processing")
    with owner_engine.begin() as conn:
        conn.execute(text("UPDATE research_reports SET processing_started_at = TIMEZONE('utc', NOW()) - INTERVAL '1 hour' WHERE id = :r"), {"r": rid})
    with runtime_engine.connect() as conn:
        ids = set(conn.execute(text("SELECT report_id FROM app_pending_ingestion_jobs(50)")).scalars())
    assert rid in ids


def test_auto_mode_never_queues_on_vercel_without_declared_worker(monkeypatch):
    from app.api import endpoints

    monkeypatch.setattr(endpoints, "get_task_queue", lambda: object())   # Redis reachable
    monkeypatch.setenv("INGESTION_MODE", "auto")
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.delenv("INGESTION_WORKER", raising=False)
    assert endpoints.ingestion_mode() == "sync"        # no worker can exist on Vercel
    monkeypatch.setenv("INGESTION_WORKER", "external")
    assert endpoints.ingestion_mode() == "queue"       # operator declared an external worker
    monkeypatch.setattr(endpoints, "get_task_queue", lambda: None)
    assert endpoints.ingestion_mode() == "sync"        # Redis unreachable
    monkeypatch.delenv("VERCEL")
    monkeypatch.setattr(endpoints, "get_task_queue", lambda: object())
    assert endpoints.ingestion_mode() == "queue"       # local dev with Redis


def test_queue_mode_with_real_rq_worker(api, owner_engine, two_tenants, tmp_path, monkeypatch):
    """Upload enqueues to real Redis; an RQ worker (burst mode) processes it under the tenant."""
    from rq import SimpleWorker

    from app.api import endpoints
    from app.core.redis_client import get_redis_client

    redis = get_redis_client()
    if redis is None:
        if os.getenv("REQUIRE_INTEGRATION") == "1":
            pytest.fail("Redis required for the queue-mode test")
        pytest.skip("Redis unavailable")
    a = two_tenants.a
    monkeypatch.setenv("INGESTION_MODE", "queue")
    monkeypatch.setattr("app.core.config.settings.UPLOAD_DIR", str(tmp_path))
    queue = endpoints.get_task_queue()
    queue.empty()
    with open(_pdf(tmp_path / "queued-src.pdf"), "rb") as fh:
        r = api.post("/documents/upload", headers=a.auth("analyst"),
                     data={"sector": "Energy", "company": "Queued Co", "recommendation": "buy"},
                     files={"file": ("q.pdf", fh, "application/pdf")})
    assert r.status_code == 202 and r.json()["status"] == "pending"
    rid = uuid.UUID(r.json()["report_id"])
    assert _state(owner_engine, rid)[0]["status"] == "pending"

    SimpleWorker([queue], connection=redis).work(burst=True)

    state, chunks, models = _state(owner_engine, rid)
    assert state["status"] == "processed" and chunks >= 2 and models == {"hash-test-v1@384"}
    with owner_engine.connect() as conn:
        tenants = set(conn.execute(text("SELECT institution_id FROM document_chunks WHERE report_id = :r"), {"r": rid}).scalars())
    assert tenants == {a.institution_id}


# ── Phase 2: source integrity, stable ids, partial failures ─────────────────

def _pages_pdf(path, texts):
    doc = pymupdf.open()
    for body in texts:
        page = doc.new_page()
        if body:
            page.insert_textbox(pymupdf.Rect(36, 36, 560, 800), body, fontsize=8)
    doc.save(str(path))
    doc.close()
    return str(path)


def _chunks(owner_engine, rid):
    with owner_engine.connect() as conn:
        return conn.execute(text(
            "SELECT id, content, metadata_json FROM document_chunks WHERE report_id = :r "
            "ORDER BY (metadata_json->>'chunk_index')::int"), {"r": rid}).all()


def test_chunk_ids_stable_and_metadata_locates_passage(owner_engine, two_tenants, tmp_path):
    from app.services.parsing.parser import parse_pdf

    a = two_tenants.a
    # Must fit the PDF text box (insert_textbox silently drops overflowing text) yet
    # exceed one chunk's token budget (~35 estimated tokens per item x 30 items).
    long_body = " ".join(f"Société Générale word{i} — naïve résumé €1.2bn;" for i in range(30))
    path = _pages_pdf(tmp_path / "multi.pdf", ["Page one intro.  Multiple   spaces\tand\ttabs.", "", long_body])
    copy = tmp_path / "multi-copy.pdf"
    copy.write_bytes(open(path, "rb").read())
    pages = {p["page_num"]: p["text"].split() for p in parse_pdf(str(copy))}
    assert pages[2] == [] and len(pages[3]) > 200  # fixture sanity

    rid = _report(owner_engine, a.institution_id, path)
    _ingest(rid, path, a.institution_id)
    first = _chunks(owner_engine, rid)
    assert {m["page"] for _, _, m in first} == {1, 3}           # blank page 2 yields no chunks, numbering kept
    assert len([m for _, _, m in first if m["page"] == 3]) > 1   # long page split with overlap
    for _, content, m in first:
        assert content == " ".join(pages[m["page"]][m["word_start"]:m["word_end"]])  # exact source location
    assert "Société Générale" in first[-1][1] and "\t" not in first[0][1]          # unicode kept, whitespace normalised

    with owner_engine.begin() as conn:                           # force a reprocess of the same content
        conn.execute(text("UPDATE research_reports SET status = 'failed', file_path = :f WHERE id = :r"),
                     {"f": str(copy), "r": rid})
    _ingest(rid, str(copy), a.institution_id)
    second = _chunks(owner_engine, rid)
    assert [c[0] for c in second] == [c[0] for c in first]      # same chunk ids => citations stay valid


def test_partial_database_write_failure_leaves_nothing_indexed(owner_engine, two_tenants, tmp_path, monkeypatch):
    """A chunk Postgres refuses (NUL byte) fails the whole transaction: no partial index."""
    a = two_tenants.a
    path = _pdf(tmp_path / "nul.pdf")
    monkeypatch.setattr("app.services.ingestion.pipeline.parse_pdf",
                        lambda _p: [{"page_num": 1, "text": "good text " * 50}, {"page_num": 2, "text": "bad \x00 byte"}])
    rid = _report(owner_engine, a.institution_id, path)
    with pytest.raises(Exception):
        _ingest(rid, path, a.institution_id)
    state, chunks, _ = _state(owner_engine, rid)
    assert state["status"] == "failed" and chunks == 0 and os.path.exists(path)
    assert "Traceback" not in (state["error_message"] or "") and "\x00" not in (state["error_message"] or "")


def test_worker_interruption_then_recovery(owner_engine, runtime_engine, two_tenants, tmp_path, monkeypatch):
    """A process killed mid-job leaves 'processing'; the stale sweep re-queues it and a rerun completes once."""
    a = two_tenants.a
    path = _pdf(tmp_path / "crash.pdf")
    rid = _report(owner_engine, a.institution_id, path)

    def killed(*_a, **_k):
        raise KeyboardInterrupt  # BaseException: not handled like an ordinary failure

    monkeypatch.setattr("app.services.ingestion.pipeline.generate_embeddings", killed)
    with pytest.raises(KeyboardInterrupt):
        _ingest(rid, path, a.institution_id)
    state, chunks, _ = _state(owner_engine, rid)
    assert state["status"] == "processing" and chunks == 0 and os.path.exists(path)

    with owner_engine.begin() as conn:
        conn.execute(text("UPDATE research_reports SET processing_started_at = TIMEZONE('utc', NOW()) - INTERVAL '20 minutes' WHERE id = :r"), {"r": rid})
    with runtime_engine.connect() as conn:
        assert rid in set(conn.execute(text("SELECT report_id FROM app_pending_ingestion_jobs(50)")).scalars())

    monkeypatch.undo()
    n = _ingest(rid, path, a.institution_id)
    state, chunks, _ = _state(owner_engine, rid)
    assert state["status"] == "processed" and chunks == n and state["attempts"] == 2


def test_documents_list_reports_index_mode(api, owner_engine, two_tenants, tmp_path, monkeypatch):
    a = two_tenants.a
    hybrid = _pdf(tmp_path / "h.pdf")
    rh = _report(owner_engine, a.institution_id, hybrid)
    _ingest(rh, hybrid, a.institution_id)

    def down(*_a, **_k):
        raise EmbeddingUnavailable("down")

    monkeypatch.setattr(gen, "_embed", down)
    kw = _pdf(tmp_path / "k.pdf", body=BODY + " different content")
    rk = _report(owner_engine, a.institution_id, kw)
    _ingest(rk, kw, a.institution_id)
    monkeypatch.undo()

    docs = {d["id"]: d for d in api.get("/documents", headers=a.auth()).json()["results"]}
    assert docs[str(rh)]["index_mode"] == "hybrid" and docs[str(rh)]["chunks"] >= 1
    assert docs[str(rk)]["index_mode"] == "keyword_only"
    pending = _report(owner_engine, a.institution_id, str(tmp_path / "p.pdf"))
    docs = {d["id"]: d for d in api.get("/documents", headers=a.auth()).json()["results"]}
    assert docs[str(pending)]["index_mode"] is None


def test_reembed_moves_quarantined_vectors_into_active_space(owner_engine, two_tenants):
    """legacy-unknown vectors are excluded from vector search until scripts/reembed.py --apply."""
    import subprocess
    import sys

    a = two_tenants.a
    with owner_engine.begin() as conn:
        conn.execute(text("UPDATE document_chunks SET embedding_model = 'legacy-unknown', embedding = CAST(:v AS vector) "
                          "WHERE id = :c"), {"v": "[" + ",".join(["0.05"] * 384) + "]", "c": a.chunk_id})
    query = "zzunrelatedqueryterm"
    with SessionLocal() as db:
        set_tenant(db, a.institution_id)
        assert hybrid_search(db, query, a.institution_id).legs["vector"] == 0

    backend = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
    env = {**os.environ, "ENVIRONMENT": "test", "EMBEDDING_PROVIDER": "hash_test"}
    dry = subprocess.run([sys.executable, "scripts/reembed.py"], cwd=backend, env=env, capture_output=True, text=True, timeout=120)
    assert dry.returncode == 0 and "legacy-unknown" in dry.stdout and "needs re-embedding" in dry.stdout
    with owner_engine.connect() as conn:
        assert conn.execute(text("SELECT embedding_model FROM document_chunks WHERE id = :c"), {"c": a.chunk_id}).scalar() == "legacy-unknown"

    applied = subprocess.run([sys.executable, "scripts/reembed.py", "--apply"], cwd=backend, env=env, capture_output=True, text=True, timeout=120)
    assert applied.returncode == 0, applied.stderr
    with owner_engine.connect() as conn:
        assert conn.execute(text("SELECT embedding_model FROM document_chunks WHERE id = :c"), {"c": a.chunk_id}).scalar() == "hash-test-v1@384"
    with SessionLocal() as db:
        set_tenant(db, a.institution_id)
        assert hybrid_search(db, query, a.institution_id).legs["vector"] == 1


def test_reembed_refuses_without_provider(owner_engine):
    import subprocess
    import sys

    backend = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
    r = subprocess.run([sys.executable, "scripts/reembed.py", "--apply"], cwd=backend,
                       env={**os.environ, "EMBEDDING_PROVIDER": "none"}, capture_output=True, text=True, timeout=60)
    assert r.returncode != 0 and "No embedding provider" in (r.stderr + r.stdout)


def test_unlabelled_vector_rejected_by_database(owner_engine, two_tenants):
    """CHECK constraint: a vector cannot enter document_chunks without its embedding-space id."""
    from sqlalchemy.exc import IntegrityError

    a = two_tenants.a
    with pytest.raises(IntegrityError, match="ck_document_chunks_vector_provenance"):
        with owner_engine.begin() as conn:
            conn.execute(text("UPDATE document_chunks SET embedding_model = NULL WHERE id = :c"), {"c": a.chunk_id})
