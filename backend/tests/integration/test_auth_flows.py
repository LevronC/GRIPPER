"""Invitations, login, password reset, and demo-seed guards (real DB, restricted role)."""

from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core import email as email_mod
from app.core import rate_limit
from app.core.security import get_password_hash
from app.core.tokens import hash_token
from app.main import app

pytestmark = pytest.mark.integration

PASSWORD = "correct-horse-battery-staple"
NEW_PASSWORD = "another-long-passphrase-42"
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))


@pytest.fixture(autouse=True)
def _email_and_limits(monkeypatch):
    monkeypatch.setenv("EMAIL_BACKEND", "memory")
    email_mod.OUTBOX.clear()
    rate_limit.reset_memory_limits()
    # Keep limits local and deterministic for tests.
    monkeypatch.setattr(rate_limit, "get_redis_client", lambda: None)
    yield
    email_mod.OUTBOX.clear()
    rate_limit.reset_memory_limits()


@pytest.fixture
def client():
    return TestClient(app)


def _set_password(owner_engine, user_id, password=PASSWORD) -> str:
    with owner_engine.begin() as conn:
        return conn.execute(
            text("UPDATE users SET hashed_password = :h WHERE id = :u RETURNING email"),
            {"h": get_password_hash(password), "u": user_id},
        ).scalar()


def _token_from_outbox(kind: str) -> str:
    assert email_mod.OUTBOX, "no email sent"
    m = re.search(rf"#{kind}=([A-Za-z0-9_\-]+)", email_mod.OUTBOX[-1].body)
    assert m, email_mod.OUTBOX[-1].body
    return m.group(1)


def _new_email() -> str:
    return f"invitee-{uuid.uuid4().hex[:8]}@example.edu"


# ── Registration is gone ─────────────────────────────────────────────────────

@pytest.mark.parametrize("path", ["/auth/register", "/auth/verify", "/auth/forgot-password", "/auth/reset-password"])
def test_legacy_self_service_endpoints_removed(client, path):
    assert client.post(path, json={}).status_code in (404, 405)


def test_institutions_not_publicly_enumerable(client, two_tenants):
    assert client.get("/institutions").status_code == 401
    body = client.get("/institutions", headers=two_tenants.a.auth()).json()
    assert [i["id"] for i in body] == [str(two_tenants.a.institution_id)]


def test_no_api_to_create_institutions(client, two_tenants):
    r = client.post("/institutions", params={"name": "x", "slug": "x"}, headers=two_tenants.a.auth("admin"))
    assert r.status_code == 405


# ── Login ────────────────────────────────────────────────────────────────────

def test_login_success_and_generic_failures(client, owner_engine, two_tenants):
    email = _set_password(owner_engine, two_tenants.a.users["pm"])
    ok = client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert ok.status_code == 200
    assert ok.json()["institution_id"] == str(two_tenants.a.institution_id)
    wrong = client.post("/auth/login", json={"email": email, "password": "nope-nope-nope"})
    unknown = client.post("/auth/login", json={"email": "ghost@example.edu", "password": "nope-nope-nope"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()  # no account enumeration


def test_login_rate_limited_per_email(client, owner_engine, two_tenants):
    email = _set_password(owner_engine, two_tenants.a.users["pm"])
    codes = [client.post("/auth/login", json={"email": email, "password": "bad-password-xx"}).status_code for _ in range(11)]
    assert codes[:10] == [401] * 10
    assert codes[10] == 429


# ── Invitations ──────────────────────────────────────────────────────────────

def _invite(client, tenant, email, role="pm"):
    return client.post("/admin/invitations", json={"email": email, "role": role}, headers=tenant.auth("admin"))


def test_invitation_lifecycle(client, owner_engine, two_tenants, caplog):
    caplog.set_level(logging.DEBUG)
    a = two_tenants.a
    email = _new_email()
    r = _invite(client, a, email, role="sector_lead")
    assert r.status_code == 201, r.text
    assert "token" not in r.text.lower().replace("token_", "")
    raw = _token_from_outbox("invite")

    with owner_engine.connect() as conn:
        stored = conn.execute(text("SELECT token_hash FROM invitations WHERE id = :i"), {"i": r.json()["id"]}).scalar()
    assert stored == hash_token(raw) and stored != raw

    acc = client.post("/auth/invitations/accept", json={"token": raw, "email": email, "password": PASSWORD})
    assert acc.status_code == 201, acc.text
    assert "access_token" not in acc.json()

    with owner_engine.connect() as conn:
        row = conn.execute(text("SELECT institution_id, role, is_verified FROM users WHERE email = :e"), {"e": email}).one()
    assert row == (a.institution_id, "sector_lead", True)
    assert client.post("/auth/login", json={"email": email, "password": PASSWORD}).status_code == 200

    reuse = client.post("/auth/invitations/accept", json={"token": raw, "email": email, "password": PASSWORD})
    assert reuse.status_code == 400
    assert raw not in caplog.text  # raw invitation token never logged


def test_manipulated_institution_and_role_are_ignored(client, owner_engine, two_tenants):
    a, b = two_tenants.a, two_tenants.b
    email = _new_email()
    assert _invite(client, a, email, role="analyst").status_code == 201
    raw = _token_from_outbox("invite")
    r = client.post("/auth/invitations/accept", json={
        "token": raw, "email": email, "password": PASSWORD,
        "institution_id": str(b.institution_id), "role": "admin",
    })
    assert r.status_code == 201
    with owner_engine.connect() as conn:
        row = conn.execute(text("SELECT institution_id, role FROM users WHERE email = :e"), {"e": email}).one()
    assert row == (a.institution_id, "analyst")


def test_invitation_wrong_email_rejected(client, two_tenants):
    assert _invite(client, two_tenants.a, _new_email()).status_code == 201
    raw = _token_from_outbox("invite")
    r = client.post("/auth/invitations/accept", json={"token": raw, "email": _new_email(), "password": PASSWORD})
    assert r.status_code == 400


def test_expired_invitation_rejected(client, owner_engine, two_tenants):
    email = _new_email()
    inv = _invite(client, two_tenants.a, email).json()
    raw = _token_from_outbox("invite")
    with owner_engine.begin() as conn:
        conn.execute(text("UPDATE invitations SET expires_at = :t WHERE id = :i"),
                     {"t": datetime.utcnow() - timedelta(minutes=1), "i": inv["id"]})
    r = client.post("/auth/invitations/accept", json={"token": raw, "email": email, "password": PASSWORD})
    assert r.status_code == 400


def test_revoked_invitation_rejected(client, two_tenants):
    email = _new_email()
    inv = _invite(client, two_tenants.a, email).json()
    raw = _token_from_outbox("invite")
    assert client.delete(f"/admin/invitations/{inv['id']}", headers=two_tenants.a.auth("admin")).json()["status"] == "revoked"
    r = client.post("/auth/invitations/accept", json={"token": raw, "email": email, "password": PASSWORD})
    assert r.status_code == 400


def test_reinvite_supersedes_previous_token(client, two_tenants):
    email = _new_email()
    _invite(client, two_tenants.a, email)
    first = _token_from_outbox("invite")
    _invite(client, two_tenants.a, email)
    r = client.post("/auth/invitations/accept", json={"token": first, "email": email, "password": PASSWORD})
    assert r.status_code == 400


def test_invalid_invitation_token_rejected(client, two_tenants):
    r = client.post("/auth/invitations/accept", json={"token": "x" * 43, "email": _new_email(), "password": PASSWORD})
    assert r.status_code == 400


@pytest.mark.parametrize("role", ["pm", "analyst", "faculty", "trustee", "sector_lead"])
def test_non_admin_cannot_invite(client, two_tenants, role):
    r = client.post("/admin/invitations", json={"email": _new_email(), "role": "admin"}, headers=two_tenants.a.auth(role))
    assert r.status_code == 403


def test_invite_rejects_unknown_role(client, two_tenants):
    r = _invite(client, two_tenants.a, _new_email(), role="superuser")
    assert r.status_code == 422


def test_invite_existing_account_conflicts(client, owner_engine, two_tenants):
    email = _set_password(owner_engine, two_tenants.b.users["pm"])  # exists in another tenant
    assert _invite(client, two_tenants.a, email).status_code == 409


def test_invitations_scoped_to_admins_institution(client, two_tenants):
    a, b = two_tenants.a, two_tenants.b
    inv_b = _invite(client, b, _new_email()).json()
    listed = {i["id"] for i in client.get("/admin/invitations", headers=a.auth("admin")).json()}
    assert inv_b["id"] not in listed
    assert client.delete(f"/admin/invitations/{inv_b['id']}", headers=a.auth("admin")).status_code == 404


def test_invitations_unavailable_without_email(client, owner_engine, two_tenants, monkeypatch):
    monkeypatch.setenv("EMAIL_BACKEND", "disabled")
    email = _new_email()
    r = _invite(client, two_tenants.a, email)
    assert r.status_code == 503
    assert "token" not in r.text.lower()
    with owner_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM invitations WHERE email = :e"), {"e": email}).scalar() == 0


def test_pm_cannot_assign_roles_and_admin_cannot_invent_roles(client, two_tenants):
    a = two_tenants.a
    assert client.patch(f"/users/{a.users['analyst']}/role", json={"role": "admin"}, headers=a.auth("pm")).status_code == 403
    assert client.patch(f"/users/{a.users['analyst']}/role", json={"role": "root"}, headers=a.auth("admin")).status_code == 400


# ── Password reset ───────────────────────────────────────────────────────────

def test_password_reset_flow_revokes_sessions(client, owner_engine, two_tenants, caplog):
    caplog.set_level(logging.DEBUG)
    a = two_tenants.a
    email = _set_password(owner_engine, a.users["analyst"])
    old_jwt = client.post("/auth/login", json={"email": email, "password": PASSWORD}).json()["access_token"]
    assert client.get("/portfolios", headers={"Authorization": f"Bearer {old_jwt}"}).status_code == 200

    r = client.post("/auth/password-reset/request", json={"email": email})
    assert r.status_code == 202
    raw = _token_from_outbox("reset")

    done = client.post("/auth/password-reset/confirm", json={"token": raw, "new_password": NEW_PASSWORD})
    assert done.status_code == 200, done.text
    assert "access_token" not in done.json()  # reset token is not a login token

    assert client.get("/portfolios", headers={"Authorization": f"Bearer {old_jwt}"}).status_code == 401
    assert client.post("/auth/login", json={"email": email, "password": PASSWORD}).status_code == 401
    assert client.post("/auth/login", json={"email": email, "password": NEW_PASSWORD}).status_code == 200

    again = client.post("/auth/password-reset/confirm", json={"token": raw, "new_password": "yet-another-passphrase"})
    assert again.status_code == 400
    assert raw not in caplog.text


def test_password_reset_unknown_email_is_indistinguishable(client, owner_engine, two_tenants):
    email = _set_password(owner_engine, two_tenants.a.users["analyst"])
    known = client.post("/auth/password-reset/request", json={"email": email})
    sent = len(email_mod.OUTBOX)
    unknown = client.post("/auth/password-reset/request", json={"email": "ghost@example.edu"})
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    assert len(email_mod.OUTBOX) == sent  # nothing sent for unknown address


def test_password_reset_expired_and_invalid_tokens(client, owner_engine, two_tenants):
    email = _set_password(owner_engine, two_tenants.a.users["analyst"])
    client.post("/auth/password-reset/request", json={"email": email})
    raw = _token_from_outbox("reset")
    with owner_engine.begin() as conn:
        conn.execute(text("UPDATE password_reset_tokens SET expires_at = :t WHERE token_hash = :h"),
                     {"t": datetime.utcnow() - timedelta(seconds=1), "h": hash_token(raw)})
    assert client.post("/auth/password-reset/confirm", json={"token": raw, "new_password": NEW_PASSWORD}).status_code == 400
    assert client.post("/auth/password-reset/confirm", json={"token": "y" * 43, "new_password": NEW_PASSWORD}).status_code == 400


def test_only_newest_reset_link_valid(client, owner_engine, two_tenants):
    email = _set_password(owner_engine, two_tenants.a.users["analyst"])
    client.post("/auth/password-reset/request", json={"email": email})
    first = _token_from_outbox("reset")
    client.post("/auth/password-reset/request", json={"email": email})
    assert client.post("/auth/password-reset/confirm", json={"token": first, "new_password": NEW_PASSWORD}).status_code == 400
    second = _token_from_outbox("reset")
    assert client.post("/auth/password-reset/confirm", json={"token": second, "new_password": NEW_PASSWORD}).status_code == 200


def test_reset_capped_per_account(client, owner_engine, two_tenants):
    email = _set_password(owner_engine, two_tenants.a.users["analyst"])
    for _ in range(5):
        assert client.post("/auth/password-reset/request", json={"email": email}).status_code == 202
    assert len(email_mod.OUTBOX) == 3


def test_reset_request_rate_limited(client):
    codes = [client.post("/auth/password-reset/request", json={"email": f"x{i}@example.edu"}).status_code for i in range(11)]
    assert codes[:10] == [202] * 10 and codes[10] == 429


def test_reset_confirm_rate_limited(client):
    codes = [client.post("/auth/password-reset/confirm", json={"token": "z" * 43, "new_password": NEW_PASSWORD}).status_code for _ in range(21)]
    assert codes[:20] == [400] * 20 and codes[20] == 429


def test_reset_unavailable_without_email(client, monkeypatch):
    monkeypatch.setenv("EMAIL_BACKEND", "disabled")
    r = client.post("/auth/password-reset/request", json={"email": "anyone@example.edu"})
    assert r.status_code == 503


def test_weak_password_rejected(client):
    r = client.post("/auth/password-reset/confirm", json={"token": "z" * 43, "new_password": "short"})
    assert r.status_code == 422


def test_memory_email_backend_refused_outside_test(monkeypatch):
    monkeypatch.setattr(email_mod.settings, "ENVIRONMENT", "production")
    monkeypatch.setenv("EMAIL_BACKEND", "memory")
    assert email_mod.email_delivery_available() is False


# ── Demo seed guards ─────────────────────────────────────────────────────────

def _run_seed(env_overrides, *args):
    env = {**os.environ, **env_overrides}
    return subprocess.run(
        [sys.executable, "scripts/seed_demo.py", *args],
        cwd=BACKEND_DIR, env=env, capture_output=True, text=True, timeout=60,
    )


def _demo_exists(owner_engine) -> bool:
    with owner_engine.connect() as conn:
        return conn.execute(text("SELECT count(*) FROM institutions WHERE slug = 'synthetic-demo'")).scalar() > 0


@pytest.fixture
def no_demo(owner_engine):
    with owner_engine.begin() as conn:
        conn.execute(text("DELETE FROM institutions WHERE slug = 'synthetic-demo'"))
    yield
    with owner_engine.begin() as conn:
        conn.execute(text("DELETE FROM institutions WHERE slug = 'synthetic-demo'"))


def test_demo_seed_refused_in_production(owner_engine, no_demo):
    for env in ({"ENVIRONMENT": "production"}, {"ENVIRONMENT": "development", "VERCEL": "1"}):
        r = _run_seed(env)
        assert r.returncode != 0 and "Refusing" in (r.stderr + r.stdout)
    assert not _demo_exists(owner_engine)


def test_demo_seed_refuses_remote_database(owner_engine, no_demo):
    r = _run_seed({"ENVIRONMENT": "development",
                   "MIGRATION_DATABASE_URL": "postgresql://u:p@db.example.com:5432/x"})
    assert r.returncode != 0 and "non-local" in (r.stderr + r.stdout)


def test_demo_seed_local_development_creates_synthetic_tenant(owner_engine, no_demo):
    r = _run_seed({"ENVIRONMENT": "development"})
    assert r.returncode == 0, r.stderr
    assert "Generated password" in r.stdout  # no fixed, published password
    with owner_engine.connect() as conn:
        name = conn.execute(text("SELECT name FROM institutions WHERE slug = 'synthetic-demo'")).scalar()
    assert "Synthetic" in name and "not a real institution" in name
