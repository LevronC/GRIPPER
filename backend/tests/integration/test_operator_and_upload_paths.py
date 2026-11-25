"""Operator ingestion endpoint, upload validation, and the Redis-backed rate limiter."""

from __future__ import annotations

import os
import uuid

import fitz
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

pytestmark = pytest.mark.integration


@pytest.fixture
def api():
    from app.main import app
    return TestClient(app)


def _pdf_bytes(body: str) -> bytes:
    doc = fitz.open()
    doc.new_page().insert_textbox(fitz.Rect(36, 36, 560, 800), body, fontsize=9)
    data = doc.tobytes()
    doc.close()
    return data


# ── /cron/process-documents ──────────────────────────────────────────────────

def test_cron_requires_configured_secret(api, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.CRON_SECRET", "")
    assert api.get("/cron/process-documents").status_code == 503
    monkeypatch.setattr("app.core.config.settings.CRON_SECRET", "s3cret-value-for-tests")
    assert api.get("/cron/process-documents").status_code == 401
    assert api.get("/cron/process-documents", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert api.get("/cron/process-documents", headers={"Authorization": "s3cret-value-for-tests"}).status_code == 401


def test_cron_processes_pending_jobs_each_in_its_own_tenant(api, owner_engine, two_tenants, tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.CRON_SECRET", "s3cret-value-for-tests")
    a, b = two_tenants.a, two_tenants.b
    jobs = {}
    for tenant, label in ((a, "alpha"), (b, "bravo")):
        path = tmp_path / f"{label}.pdf"
        path.write_bytes(_pdf_bytes(f"Pending {label} research note about liquidity. " * 20))
        rid = uuid.uuid4()
        with owner_engine.begin() as conn:
            conn.execute(text("INSERT INTO research_reports (id, institution_id, sector, company, recommendation, status, "
                              "file_path, created_at) VALUES (:r, :i, 'Energy', :c, 'hold', 'pending', :f, now() - interval '1 day')"),
                         {"r": rid, "i": tenant.institution_id, "c": label, "f": str(path)})
        jobs[rid] = tenant.institution_id

    r = api.get("/cron/process-documents", headers={"Authorization": "Bearer s3cret-value-for-tests"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["errors"] == 0 and {x["report_id"] for x in body["results"]} >= {str(k) for k in jobs}
    with owner_engine.connect() as conn:
        for rid, inst in jobs.items():
            status = conn.execute(text("SELECT status FROM research_reports WHERE id = :r"), {"r": rid}).scalar()
            tenants = set(conn.execute(text("SELECT institution_id FROM document_chunks WHERE report_id = :r"), {"r": rid}).scalars())
            assert status == "processed" and tenants == {inst}
    again = api.get("/cron/process-documents", headers={"Authorization": "Bearer s3cret-value-for-tests"}).json()
    assert not {x["report_id"] for x in again["results"]} & {str(k) for k in jobs}   # nothing reprocessed


# ── Upload validation ────────────────────────────────────────────────────────

GOOD = {"sector": "Technology", "company": "Valid Co", "recommendation": "buy"}


@pytest.mark.parametrize("data, file, reason", [
    ({**GOOD, "company": "   "}, ("a.pdf", b"%PDF-1.4 x", "application/pdf"), "cannot be empty"),
    ({**GOOD, "recommendation": "strong buy"}, ("a.pdf", b"%PDF-1.4 x", "application/pdf"), "Recommendation"),
    ({**GOOD, "company": "x" * 256}, ("a.pdf", b"%PDF-1.4 x", "application/pdf"), "maximum permitted length"),
    (GOOD, ("a.txt", b"hello", "text/plain"), "Only PDF"),
    (GOOD, ("a.pdf", b"MZ\x90\x00 not a pdf", "application/pdf"), "signature"),
    (GOOD, ("big.pdf", b"%PDF-" + b"0" * (10 * 1024 * 1024), "application/pdf"), "10MB"),
])
def test_upload_rejects_invalid_input_without_creating_records(api, owner_engine, two_tenants, tmp_path, monkeypatch, data, file, reason):
    monkeypatch.setattr("app.core.config.settings.UPLOAD_DIR", str(tmp_path))
    a = two_tenants.a
    with owner_engine.connect() as conn:
        before = conn.execute(text("SELECT count(*) FROM research_reports WHERE institution_id = :i"), {"i": a.institution_id}).scalar()
    r = api.post("/documents/upload", headers=a.auth("analyst"), data=data, files={"file": file})
    assert r.status_code == 400 and reason in r.json()["detail"]
    with owner_engine.connect() as conn:
        after = conn.execute(text("SELECT count(*) FROM research_reports WHERE institution_id = :i"), {"i": a.institution_id}).scalar()
    assert after == before and os.listdir(tmp_path) == []


# ── Redis-backed rate limiter ────────────────────────────────────────────────

def test_rate_limiter_with_real_redis(monkeypatch):
    from app.core import rate_limit
    from app.core.redis_client import get_redis_client

    client = get_redis_client()
    if client is None:
        if os.getenv("REQUIRE_INTEGRATION") == "1":
            pytest.fail("Redis required")
        pytest.skip("Redis unavailable")
    monkeypatch.setattr(rate_limit, "get_redis_client", lambda: client)  # undo the test-wide in-memory default
    identity = f"test-{uuid.uuid4().hex}"
    try:
        for _ in range(3):
            rate_limit.enforce("unit", identity, limit=3, window_seconds=30)
        with pytest.raises(Exception) as exc:
            rate_limit.enforce("unit", identity, limit=3, window_seconds=30)
        assert getattr(exc.value, "status_code", None) == 429
        assert 0 < client.ttl(f"ratelimit:unit:{identity}") <= 30
    finally:
        client.delete(f"ratelimit:unit:{identity}")
