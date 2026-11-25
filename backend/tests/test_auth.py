"""Authentication validation tests."""

from __future__ import annotations

import pytest
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
