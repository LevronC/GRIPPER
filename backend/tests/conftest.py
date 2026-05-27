"""Pytest fixtures and shared test configuration."""

from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient

# Must be set before importing the app
os.environ.setdefault("SKIP_DB_BOOTSTRAP", "1")
os.environ.setdefault("SEED_DEMO_USER", "false")
os.environ.setdefault("ALLOW_HEADER_AUTH", "true")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from app.main import app  # noqa: E402
from app import models  # noqa: E402


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def make_user():
    def _factory(role: str = "analyst") -> models.User:
        return models.User(
            id=uuid.uuid4(),
            email=f"{role}@stetson.edu",
            hashed_password="hashed",
            institution_id=uuid.uuid4(),
            role=role,
            is_verified=True,
        )

    return _factory
