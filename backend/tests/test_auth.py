"""Unit tests for authentication primitives (no database)."""

from __future__ import annotations

import hashlib

import jwt
import pytest
from pydantic import ValidationError

from app.api.auth import AcceptInvitation, PasswordResetConfirm
from app.core import security
from app.core.config import settings
from app.core.tokens import hash_token, new_token


def test_new_token_entropy_and_hash():
    raw, digest = new_token()
    assert len(raw) >= 43  # 32 bytes urlsafe-base64
    assert digest == hashlib.sha256(raw.encode()).hexdigest() == hash_token(raw)
    assert len({new_token()[0] for _ in range(200)}) == 200


@pytest.mark.parametrize("pw", ["short", "x" * 11, "é" * 37])  # 37 * 2 bytes > 72
def test_password_policy_rejects(pw):
    with pytest.raises(ValidationError):
        PasswordResetConfirm(token="t" * 43, new_password=pw)


def test_password_policy_accepts_reasonable_passphrase():
    assert AcceptInvitation(token="t" * 43, email="a@example.edu", password="a long passphrase")


def test_access_token_claims():
    tok = security.create_access_token("1234", token_version=3)
    claims = jwt.decode(tok, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    assert claims["sub"] == "1234" and claims["ver"] == 3 and claims["typ"] == "access" and claims["jti"]


def test_token_with_other_algorithm_rejected():
    forged = jwt.encode({"sub": "1"}, settings.SECRET_KEY, algorithm="HS512")
    with pytest.raises(jwt.PyJWTError):
        jwt.decode(forged, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
