"""Pytest fixtures and shared test configuration.

Unit tests (this directory) never touch a database: endpoints that need one get a
stub session via the `no_db` fixture. Database tests live in tests/integration/.
"""

from __future__ import annotations

import os
import uuid
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

# Must be set before importing the app
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-0123456789abcdef0123")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
# Deterministic, clearly non-semantic vectors in their own embedding space (see
# app/services/embeddings/generator.py). Tests that exercise real models opt in.
os.environ.setdefault("EMBEDDING_PROVIDER", "hash_test")

from app.main import app  # noqa: E402
from app import models  # noqa: E402
from app.db.session import get_db  # noqa: E402


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def no_db():
    """Replace get_db with a stub so unit tests never open a connection."""
    stub = MagicMock(name="db")

    def _fake_get_db():
        yield stub

    app.dependency_overrides[get_db] = _fake_get_db
    yield stub
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def make_user():
    def _factory(role: str = "analyst") -> models.User:
        return models.User(
            id=uuid.uuid4(),
            email=f"{role}@example.edu",
            hashed_password="hashed",
            institution_id=uuid.uuid4(),
            role=role,
            is_verified=True,
        )

    return _factory


@pytest.fixture(autouse=True)
def isolated_rate_limits(monkeypatch):
    """
    Every test client shares one 'IP' (testclient). With Redis-backed counters, logins from
    earlier tests (or earlier runs within the window) would make later tests flaky with 429.
    Tests therefore use the in-memory limiter, reset per test. Rate-limit behaviour itself
    is asserted in tests/integration/test_auth_flows.py against this same limiter.
    """
    from app.core import rate_limit

    monkeypatch.setattr(rate_limit, "get_redis_client", lambda: None)
    rate_limit.reset_memory_limits()
    yield
    rate_limit.reset_memory_limits()
