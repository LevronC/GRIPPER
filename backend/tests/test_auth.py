"""Authentication validation tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.auth import UserRegister


def test_register_rejects_non_edu_email():
    with pytest.raises(ValidationError):
        UserRegister(
            email="student@gmail.com",
            password="password123",
            institution_id="4229435f-f427-4b6b-a432-1f6488157381",
            role="analyst",
        )


def test_register_accepts_edu_email():
    user = UserRegister(
        email="student@stetson.edu",
        password="password123",
        institution_id="4229435f-f427-4b6b-a432-1f6488157381",
        role="analyst",
    )
    assert user.email == "student@stetson.edu"


@pytest.mark.integration
def test_register_and_verify_flow(client: TestClient):
    """Full auth flow against PostgreSQL (see CI workflow)."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.core.config import settings
    from app import models

    engine = create_engine(settings.SUPERUSER_DATABASE_URL)
    Session = sessionmaker(bind=engine)

    with Session() as db:
        inst = db.query(models.Institution).filter(models.Institution.slug == "stetson").first()
        if not inst:
            inst = models.Institution(
                id=__import__("uuid").UUID("4229435f-f427-4b6b-a432-1f6488157381"),
                name="Stetson University",
                slug="stetson",
                tier="enterprise",
            )
            db.add(inst)
            db.commit()
            db.refresh(inst)
        institution_id = str(inst.id)

    email = f"pytest_{__import__('uuid').uuid4().hex[:8]}@stetson.edu"
    reg = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "password123",
            "institution_id": institution_id,
            "role": "analyst",
        },
    )
    assert reg.status_code == 201, reg.text

    with Session() as db:
        user = db.query(models.User).filter(models.User.email == email).one()
        code = user.verification_code

    assert client.post("/auth/login", json={"email": email, "password": "password123"}).status_code == 403

    assert client.post("/auth/verify", json={"email": email, "code": code}).status_code == 200

    login = client.post("/auth/login", json={"email": email, "password": "password123"})
    assert login.status_code == 200
    assert "access_token" in login.json()
