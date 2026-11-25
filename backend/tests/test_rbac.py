"""Role-based access control tests."""

from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.deps import RoleChecker, get_current_user
from app.core.rbac import HOLDINGS_WRITE_ROLES, READ_ROLES
from app.main import app


def test_role_checker_allows_matching_role(make_user):
    checker = RoleChecker(HOLDINGS_WRITE_ROLES)
    user = make_user(role="pm")
    assert checker(user) is user


def test_role_checker_blocks_wrong_role(make_user):
    checker = RoleChecker(HOLDINGS_WRITE_ROLES)
    user = make_user(role="analyst")
    with pytest.raises(HTTPException) as exc:
        checker(user)
    assert exc.value.status_code == 403


def test_role_checker_requires_authenticated_user():
    checker = RoleChecker(READ_ROLES)
    with pytest.raises(HTTPException) as exc:
        checker(None)
    assert exc.value.status_code == 401


def test_holdings_update_requires_pm_role(client: TestClient, make_user, no_db):
    user = make_user(role="analyst")
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        response = client.post(
            f"/portfolios/{uuid.uuid4()}/holdings",
            json=[{"ticker": "AAPL", "weight": 0.1, "cost_basis": 100.0}],
        )
        assert response.status_code == 403
        assert "Operation not permitted" in response.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_simulate_requires_pm_role(client: TestClient, make_user, no_db):
    user = make_user(role="faculty")
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        response = client.post(
            f"/portfolios/{uuid.uuid4()}/simulate",
            json=[{"ticker": "AAPL", "weight": 0.1}],
        )
        assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_simulate_allows_pm(client: TestClient, make_user, no_db, monkeypatch):
    user = make_user(role="pm")
    app.dependency_overrides[get_current_user] = lambda: user
    monkeypatch.setattr("app.api.endpoints.require_portfolio", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "app.api.endpoints.simulate_portfolio_compliance",
        lambda *_args, **_kwargs: [],
    )
    try:
        response = client.post(
            f"/portfolios/{uuid.uuid4()}/simulate",
            json=[{"ticker": "AAPL", "weight": 0.1}],
        )
        assert response.status_code == 200
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.parametrize("role, expected", [
    ("analyst", 200), ("sector_lead", 200), ("pm", 200), ("admin", 200),
    ("faculty", 403), ("trustee", 403),
])
def test_semantic_search_restricted_to_research_roles(client, make_user, no_db, monkeypatch, role, expected):
    user = make_user(role=role)
    app.dependency_overrides[get_current_user] = lambda: user
    from app.services.retrieval.searcher import SearchOutcome

    monkeypatch.setattr(
        "app.api.endpoints.hybrid_search",
        lambda *_a, **_k: SearchOutcome(results=[], retrieval_mode="full_text_only"),
    )
    try:
        response = client.post("/search/semantic", json={"query": "liquidity", "limit": 3})
        assert response.status_code == expected
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_unauthenticated_requests_rejected(client, no_db):
    for method, path in [
        ("get", "/portfolios"),
        ("get", f"/portfolios/{uuid.uuid4()}/holdings"),
        ("post", "/search/semantic"),
        ("get", "/documents"),
    ]:
        kwargs = {"json": {"query": "x"}} if method == "post" else {}
        response = getattr(client, method)(path, **kwargs)
        assert response.status_code == 401, (method, path)


def test_invalid_token_rejected(client, no_db):
    response = client.get("/portfolios", headers={"Authorization": "Bearer not-a-jwt"})
    assert response.status_code == 401
