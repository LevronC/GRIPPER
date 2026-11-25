"""
Tenant isolation through the HTTP API.

Every cross-tenant test runs in two modes:

* ``rls_and_app`` — the real stack: get_db uses the restricted runtime role, so both
  PostgreSQL RLS and the application-layer ownership checks apply.
* ``app_only``    — get_db is replaced by a session on the OWNER role (RLS bypassed).
  Passing in this mode proves the application layer alone blocks the access, i.e.
  isolation does not rest on a single control.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.session import get_db, make_session_factory
from app.main import app

pytestmark = pytest.mark.integration


@pytest.fixture(params=["rls_and_app", "app_only"])
def api(request, db_urls):
    if request.param == "app_only":
        factory = make_session_factory(db_urls[1])

        def _privileged_get_db():
            db = factory()
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()

        app.dependency_overrides[get_db] = _privileged_get_db
    client = TestClient(app)
    client.mode = request.param
    yield client
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def rls_api(db_urls):
    """Real stack only (restricted role)."""
    return TestClient(app)


# ── Positive controls ────────────────────────────────────────────────────────

def test_tenant_reads_own_holdings(api, two_tenants):
    a = two_tenants.a
    r = api.get(f"/portfolios/{a.portfolio_id}/holdings", headers=a.auth())
    assert r.status_code == 200
    assert [h["ticker"] for h in r.json()] == ["ASECRET"]


def test_list_portfolios_returns_only_own(api, two_tenants):
    a, b = two_tenants.a, two_tenants.b
    ids = {p["id"] for p in api.get("/portfolios", headers=a.auth()).json()}
    assert str(a.portfolio_id) in ids
    assert str(b.portfolio_id) not in ids


def test_create_portfolio_and_update_holdings_succeed_under_rls(rls_api, two_tenants):
    """Regression for Phase 0 C2: commit() used to drop tenant context -> 500."""
    a = two_tenants.a
    r = rls_api.post("/portfolios", params={"name": "New fund", "strategy_type": "growth"}, headers=a.auth())
    assert r.status_code == 200, r.text
    assert r.json()["institution_id"] == str(a.institution_id)
    pid = r.json()["id"]
    r = rls_api.post(
        f"/portfolios/{pid}/holdings",
        json=[{"ticker": "nvda", "weight": 0.2, "cost_basis": 100}],
        headers=a.auth(),
    )
    assert r.status_code == 200, r.text
    r = rls_api.get(f"/portfolios/{pid}/holdings", headers=a.auth())
    assert [h["ticker"] for h in r.json()] == ["NVDA"]


def test_evaluate_commits_then_reads_back_under_rls(rls_api, two_tenants):
    """Evaluator commits mid-request then reads created_at: needs per-transaction context."""
    a = two_tenants.a
    r = rls_api.post(f"/portfolios/{a.portfolio_id}/evaluate", headers=a.auth("pm"))
    assert r.status_code == 200, r.text
    assert any(v["details"].get("ticker") == "ASECRET" for v in r.json()["violations"])


# ── Cross-tenant denials (both modes) ────────────────────────────────────────

def test_cannot_read_other_tenant_holdings(api, two_tenants):
    a, b = two_tenants.a, two_tenants.b
    r = api.get(f"/portfolios/{b.portfolio_id}/holdings", headers=a.auth())
    assert r.status_code == 404
    assert "BSECRET" not in r.text


def test_cannot_overwrite_other_tenant_holdings(api, owner_engine, two_tenants):
    a, b = two_tenants.a, two_tenants.b
    r = api.post(
        f"/portfolios/{b.portfolio_id}/holdings",
        json=[{"ticker": "PWNED", "weight": 0.99, "cost_basis": 1}],
        headers=a.auth("pm"),
    )
    assert r.status_code == 404
    with owner_engine.connect() as conn:
        tickers = conn.execute(
            text("SELECT ticker FROM holdings WHERE portfolio_id = :p"), {"p": b.portfolio_id}
        ).scalars().all()
    assert tickers == ["BSECRET"]


@pytest.mark.parametrize("method, path_tpl, role, body", [
    ("post", "/portfolios/{pid}/evaluate", "pm", None),
    ("post", "/portfolios/{pid}/simulate", "pm", [{"ticker": "AAPL", "weight": 0.5}]),
    ("get", "/portfolios/{pid}/violations", "pm", None),
])
def test_cannot_act_on_other_tenant_portfolio(api, owner_engine, two_tenants, method, path_tpl, role, body):
    a, b = two_tenants.a, two_tenants.b
    path = path_tpl.format(pid=b.portfolio_id)
    kwargs = {"headers": a.auth(role)}
    if body is not None:
        kwargs["json"] = body
    r = getattr(api, method)(path, **kwargs)
    assert r.status_code == 404, r.text
    with owner_engine.connect() as conn:
        n = conn.execute(
            text("SELECT count(*) FROM governance_events WHERE portfolio_id = :p"), {"p": b.portfolio_id}
        ).scalar()
    assert n == 1  # only B's own seeded event; nothing created by A


def test_cannot_explain_other_tenant_violation(api, two_tenants):
    a, b = two_tenants.a, two_tenants.b
    r = api.post(f"/violations/{b.event_id}/explain", headers=a.auth("pm"))
    assert r.status_code == 404
    assert "BSECRET" not in r.text


def test_documents_list_only_own(api, two_tenants):
    a, b = two_tenants.a, two_tenants.b
    body = api.get("/documents", headers=a.auth()).json()
    ids = {d["id"] for d in body["results"]}
    assert str(a.report_id) in ids
    assert str(b.report_id) not in ids


def test_search_returns_only_own_chunks(api, two_tenants):
    a, b = two_tenants.a, two_tenants.b
    r = api.post("/search/semantic", json={"query": "semiconductor liquidity risk memo", "limit": 10}, headers=a.auth("analyst"))
    assert r.status_code == 200, r.text
    chunk_ids = {res["chunk_id"] for res in r.json()["results"]}
    assert str(a.chunk_id) in chunk_ids
    assert str(b.chunk_id) not in chunk_ids
    assert "BSECRET" not in r.text


def test_spoofed_institution_header_is_ignored(api, two_tenants):
    a, b = two_tenants.a, two_tenants.b
    headers = {**a.auth(), "X-Institution-ID": str(b.institution_id)}
    r = api.get(f"/portfolios/{b.portfolio_id}/holdings", headers=headers)
    assert r.status_code == 404
    ids = {p["id"] for p in api.get("/portfolios", headers=headers).json()}
    assert ids and str(b.portfolio_id) not in ids


def test_admin_cannot_change_role_of_other_tenant_user(api, owner_engine, two_tenants):
    a, b = two_tenants.a, two_tenants.b
    r = api.patch(f"/users/{b.users['pm']}/role", json={"role": "analyst"}, headers=a.auth("admin"))
    assert r.status_code == 404
    with owner_engine.connect() as conn:
        role = conn.execute(text("SELECT role FROM users WHERE id = :u"), {"u": b.users["pm"]}).scalar()
    assert role == "pm"


def test_token_for_unknown_user_rejected(api, two_tenants):
    from app.core.security import create_access_token

    r = api.get("/portfolios", headers={"Authorization": f"Bearer {create_access_token(uuid.uuid4())}"})
    assert r.status_code == 401


def test_consecutive_requests_for_different_tenants_do_not_leak(rls_api, two_tenants):
    """Same process, same pool: alternate tenants and confirm each sees only its own data."""
    a, b = two_tenants.a, two_tenants.b
    for _ in range(3):
        ra = {p["id"] for p in rls_api.get("/portfolios", headers=a.auth()).json()}
        rb = {p["id"] for p in rls_api.get("/portfolios", headers=b.auth()).json()}
        assert str(a.portfolio_id) in ra and str(b.portfolio_id) not in ra
        assert str(b.portfolio_id) in rb and str(a.portfolio_id) not in rb
