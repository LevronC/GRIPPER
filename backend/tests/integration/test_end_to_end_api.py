"""
End-to-end compliance workflow through the real HTTP API, real PostgreSQL (restricted
role), real PDF parsing and the real ingestion pipeline.

Mocked / substituted components (and only these):
* Email delivery uses the in-memory test outbox (EMAIL_BACKEND=memory) to read the
  invitation links; SMTP itself is not exercised.
* Embeddings: run twice. `hash_test` vectors have no semantic meaning, so that run
  verifies keyword retrieval plus retrieval mechanics only. The `local` run uses the real
  BAAI/bge-small-en-v1.5 model (marker `model`; skipped where sentence-transformers is not
  installed, e.g. the CI image). Only the `local` run verifies semantic retrieval.
"""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
import uuid

import pymupdf
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core import email as email_mod

pytestmark = pytest.mark.integration

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
PW = "end-to-end-passphrase-1"
RESEARCH = (
    "Synthetic research note on NVDA. Our investment thesis rests on data-center demand, but "
    "position sizing must reflect concentration risk and export-control exposure. "
)


def _model_available() -> bool:
    return importlib.util.find_spec("sentence_transformers") is not None


@pytest.fixture(params=[
    "hash_test",
    pytest.param("local", marks=[pytest.mark.model, pytest.mark.skipif(not _model_available(),
                                                                       reason="sentence-transformers not installed")]),
])
def provider(request, monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", request.param)
    monkeypatch.setenv("EMAIL_BACKEND", "memory")
    monkeypatch.setenv("INGESTION_MODE", "sync")
    email_mod.OUTBOX.clear()
    return request.param


@pytest.fixture
def institution(owner_engine):
    slug = f"e2e-{uuid.uuid4().hex[:8]}"
    admin = f"admin@{slug}.example.edu"
    env = {**os.environ, "ADMIN_PASSWORD": PW}
    r = subprocess.run([sys.executable, "scripts/provision_institution.py", "--name", "Synthetic E2E Fund",
                        "--slug", slug, "--admin-email", admin], cwd=BACKEND_DIR, env=env,
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    yield slug, admin
    with owner_engine.begin() as conn:
        conn.execute(text("DELETE FROM institutions WHERE slug = :s"), {"s": slug})


def _login(api, email):
    r = api.post("/auth/login", json={"email": email, "password": PW})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _invite_and_accept(api, admin_h, email, role):
    assert api.post("/admin/invitations", json={"email": email, "role": role}, headers=admin_h).status_code == 201
    token = re.search(r"#invite=([A-Za-z0-9_\-]+)", email_mod.OUTBOX[-1].body).group(1)
    r = api.post("/auth/invitations/accept", json={"token": token, "email": email, "password": PW})
    assert r.status_code == 201, r.text
    return _login(api, email)


DISTRACTOR = ("Visitor guide for the regional botanical garden: opening hours, ticket prices, "
              "guided walks through the orchid greenhouse and seasonal flower festivals. ")


def _pdf(path, body: str = RESEARCH) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_textbox(pymupdf.Rect(36, 36, 560, 800), body * 3, fontsize=9)
    doc.save(str(path))
    doc.close()
    return open(path, "rb").read()


def test_full_workflow(provider, institution, owner_engine, tmp_path, monkeypatch):
    from app.main import app

    monkeypatch.setattr("app.core.config.settings.UPLOAD_DIR", str(tmp_path))
    api = TestClient(app)
    slug, admin_email = institution

    # 1-2. Administrator (provisioned by the operator script) authenticates.
    admin = _login(api, admin_email)
    # 3. Invitation-based onboarding of a PM and an analyst.
    pm = _invite_and_accept(api, admin, f"pm@{slug}.example.edu", "pm")
    analyst = _invite_and_accept(api, admin, f"analyst@{slug}.example.edu", "analyst")
    inst_id = api.get("/institutions", headers=pm).json()[0]["id"]

    # 4. IPS rules.
    for body in ({"rule_type": "single_position_cap", "threshold": 0.10, "severity": "critical"},
                 {"rule_type": "sector_exposure_cap", "threshold": 0.40}):
        assert api.post("/ips_rules", json=body, headers=admin).status_code == 201

    # 5-6. Portfolio and holdings.
    pid = api.post("/portfolios", params={"name": "E2E Growth", "strategy_type": "growth"}, headers=pm).json()["id"]
    assert api.post(f"/portfolios/{pid}/holdings", headers=pm, json=[
        {"ticker": "NVDA", "weight": 0.15, "cost_basis": 400}, {"ticker": "JPM", "weight": 0.10, "cost_basis": 200},
    ]).status_code == 200

    # 7-8. Deterministic evaluation detects exactly the known violation.
    [v] = api.post(f"/portfolios/{pid}/evaluate", headers=pm).json()["violations"]
    assert (v["event_type"], v["details"]["ticker"], v["details"]["current_weight"], v["severity"]) == \
        ("single_position_cap", "NVDA", 0.15, "critical")

    # 9. Research ingestion through the upload API and the real pipeline.
    up = api.post("/documents/upload", headers=analyst,
                  data={"sector": "Technology", "company": "NVDA", "recommendation": "hold"},
                  files={"file": ("nvda-note.pdf", _pdf(tmp_path / "src.pdf"), "application/pdf")})
    assert up.status_code == 202 and up.json()["status"] == "processed", up.text
    report_id = up.json()["report_id"]
    [doc] = [d for d in api.get("/documents", headers=analyst).json()["results"] if d["id"] == report_id]
    assert doc["index_mode"] == "hybrid"

    # 10. Tenant-scoped retrieval finds it (keyword query; plus a paraphrase for the real model).
    found = api.post("/search/semantic", json={"query": "concentration risk export controls", "limit": 5}, headers=analyst).json()
    assert found["retrieval_mode"] == "hybrid" and any(r["report_id"] == report_id for r in found["results"])
    # An unrelated distractor: with no similarity cutoff, vector search returns every chunk,
    # so semantic quality is only shown by RELATIVE order against something irrelevant.
    other = api.post("/documents/upload", headers=analyst,
                     data={"sector": "Other", "company": "Garden Guide", "recommendation": "hold"},
                     files={"file": ("garden.pdf", _pdf(tmp_path / "garden.pdf", DISTRACTOR), "application/pdf")})
    distractor_id = other.json()["report_id"]
    if provider == "local":
        para = api.post("/search/semantic", json={"query": "how large should the semiconductor position be", "limit": 5},
                        headers=analyst).json()
        ranks = {r["report_id"]: r["vector_rank"] for r in para["results"]}
        assert ranks[report_id] is not None and ranks[distractor_id] is not None
        assert ranks[report_id] < ranks[distractor_id]   # no keyword overlap; ordering comes from the model

    # 11-12. Rule-based explanation with verifiable citations.
    body = api.post(f"/violations/{v['id']}/explain", headers=pm).json()
    assert body["violation_status"] == "open" and body["research_status"] == "found"
    assert body["explanation"].startswith("NVDA is 15.0% of the portfolio; the single-position limit is 10.0%.")
    cited = [e for e in body["evidence"] if e["report_id"] == report_id]
    assert cited and all(e["company"] == "NVDA" and e["page"] == 1 for e in cited)
    with owner_engine.connect() as conn:
        for e in body["evidence"]:
            row = conn.execute(text("SELECT institution_id::text, content FROM document_chunks WHERE id = :c"),
                               {"c": e["chunk_id"]}).one()
            assert row[0] == inst_id and row[1] == e["content"]
    assert "Synthetic research note on NVDA" in cited[0]["content"]

    # 13-14. Fix the portfolio; re-evaluation resolves the violation.
    assert api.post(f"/portfolios/{pid}/holdings", headers=pm, json=[
        {"ticker": "NVDA", "weight": 0.09, "cost_basis": 400}, {"ticker": "JPM", "weight": 0.10, "cost_basis": 200},
    ]).status_code == 200
    assert api.post(f"/portfolios/{pid}/evaluate", headers=pm).json()["violations"] == []
    [r] = api.get(f"/portfolios/{pid}/violations", params={"resolved": True}, headers=pm).json()
    assert r["id"] == v["id"] and r["details"]["resolution"] == "no_longer_breached"
    assert api.post(f"/violations/{v['id']}/explain", headers=pm).json()["violation_status"] == "resolved"
