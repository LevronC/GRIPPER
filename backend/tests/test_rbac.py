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


def test_holdings_update_requires_pm_role(client: TestClient, make_user):
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
        app.dependency_overrides.clear()


def test_simulate_requires_pm_role(client: TestClient, make_user):
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


def test_simulate_allows_pm(client: TestClient, make_user, monkeypatch):
    user = make_user(role="pm")

    class FakeResult:
        def scalar(self):
            return str(user.institution_id)

    class FakeDb:
        def execute(self, *_args, **_kwargs):
            return FakeResult()

    def fake_get_db():
        yield FakeDb()

    from app.db.session import get_db

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = fake_get_db
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
        app.dependency_overrides.clear()
