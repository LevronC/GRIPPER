"""Runtime-role safeguard and background-job tenant isolation."""

from __future__ import annotations

import uuid

import fitz
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.db import session as session_mod
from app.main import app

pytestmark = pytest.mark.integration


def test_get_db_refuses_privileged_runtime_role(db_urls, two_tenants, monkeypatch):
    """If DATABASE_URL pointed at a role that bypasses RLS, requests fail closed (503)."""
    privileged = create_engine(db_urls[1])
    monkeypatch.setattr(session_mod, "engine", privileged)
    monkeypatch.setattr(session_mod.settings, "DB_ROLE_SAFETY", "enforce")
    session_mod._reset_role_check_cache()
    try:
        r = TestClient(app).get("/portfolios", headers=two_tenants.a.auth())
        assert r.status_code == 503
        assert "row-level security" in r.json()["detail"]
    finally:
        session_mod._reset_role_check_cache()
        privileged.dispose()


def test_health_db_reports_rls_enforced_for_restricted_role(db_urls):
    session_mod._reset_role_check_cache()
    r = TestClient(app).get("/health/db")
    assert r.status_code == 200, r.text
    assert r.json()["rls_enforced"] is True


def _make_pdf(path, body: str) -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), body)
    doc.save(str(path))
    doc.close()


def _pending_report(owner_engine, institution_id, path) -> uuid.UUID:
    rid = uuid.uuid4()
    with owner_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO research_reports (id, institution_id, sector, company, recommendation, status, "
                "file_path, created_at) VALUES (:r, :i, 'Energy', 'Worker Co', 'hold', 'pending', :f, now())"
            ),
            {"r": rid, "i": institution_id, "f": str(path)},
        )
    return rid


def test_worker_job_runs_in_its_own_tenant(owner_engine, two_tenants, tmp_path):
    from app.workers.tasks import process_document_ingestion

    a = two_tenants.a
    pdf = tmp_path / "a.pdf"
    _make_pdf(pdf, "Alpha energy transition research note with enough words to chunk.")
    rid = _pending_report(owner_engine, a.institution_id, pdf)

    n = process_document_ingestion(str(rid), str(pdf), str(a.institution_id))
    assert n >= 1
    with owner_engine.connect() as conn:
        status = conn.execute(text("SELECT status FROM research_reports WHERE id = :r"), {"r": rid}).scalar()
        chunk_tenants = set(conn.execute(
            text("SELECT institution_id FROM document_chunks WHERE report_id = :r"), {"r": rid}
        ).scalars())
    assert status == "processed"
    assert chunk_tenants == {a.institution_id}


def test_worker_job_with_mismatched_tenant_cannot_touch_report(owner_engine, two_tenants, tmp_path):
    """A job claiming institution B for A's report must not read or write A's data."""
    from app.workers.tasks import process_document_ingestion

    a, b = two_tenants.a, two_tenants.b
    pdf = tmp_path / "a2.pdf"
    _make_pdf(pdf, "Alpha confidential research that must stay in alpha.")
    rid = _pending_report(owner_engine, a.institution_id, pdf)

    with pytest.raises(Exception):
        process_document_ingestion(str(rid), str(pdf), str(b.institution_id))

    with owner_engine.connect() as conn:
        status = conn.execute(text("SELECT status FROM research_reports WHERE id = :r"), {"r": rid}).scalar()
        chunks = conn.execute(text("SELECT count(*) FROM document_chunks WHERE report_id = :r"), {"r": rid}).scalar()
    assert status == "pending"   # untouched: B's context cannot see or update it
    assert chunks == 0
