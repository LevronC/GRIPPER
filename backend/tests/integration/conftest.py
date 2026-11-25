"""
Integration fixtures: real PostgreSQL + pgvector with the production RLS policies.

Two connections are involved and they are deliberately different roles:

* ``DATABASE_URL``           — the app's runtime connection. MUST be the restricted
                               login role (member of gripper_runtime, NOSUPERUSER,
                               NOBYPASSRLS). All RLS assertions go through it.
* ``MIGRATION_DATABASE_URL`` — the owner connection, used ONLY to seed and clean up
                               fixtures and to run the "application layer only"
                               variants, where RLS is bypassed on purpose.

If the database is not configured these tests are skipped, unless
REQUIRE_INTEGRATION=1 (set in CI), in which case they fail instead of silently passing.
"""

from __future__ import annotations

import math
import os
import random
import uuid
from dataclasses import dataclass, field

import pytest
from sqlalchemy import create_engine, text

from app.core.database_url import normalize_database_url
from app.core.security import create_access_token
from app.services.embeddings.generator import _hash_embed

pytestmark = pytest.mark.integration


def pytest_collection_modifyitems(items):
    for item in items:
        if "/integration/" in str(item.fspath):
            item.add_marker(pytest.mark.integration)


def _require_env() -> tuple[str, str]:
    runtime = os.getenv("DATABASE_URL", "")
    owner = os.getenv("MIGRATION_DATABASE_URL", "")
    if not runtime or not owner:
        msg = "integration tests need DATABASE_URL (restricted role) and MIGRATION_DATABASE_URL (owner)"
        if os.getenv("REQUIRE_INTEGRATION") == "1":
            pytest.fail(msg)
        pytest.skip(msg)
    return normalize_database_url(runtime), normalize_database_url(owner)


@pytest.fixture(scope="session")
def db_urls() -> tuple[str, str]:
    runtime, owner = _require_env()
    try:
        with create_engine(owner).connect() as c:
            c.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - infra dependent
        if os.getenv("REQUIRE_INTEGRATION") == "1":
            pytest.fail(f"integration database unreachable: {exc}")
        pytest.skip(f"integration database unreachable: {exc}")
    return runtime, owner


@pytest.fixture(scope="session")
def owner_engine(db_urls):
    eng = create_engine(db_urls[1])
    yield eng
    eng.dispose()


@pytest.fixture(scope="session")
def runtime_engine(db_urls):
    eng = create_engine(db_urls[0], pool_size=1, max_overflow=0)
    yield eng
    eng.dispose()


def fake_vector(seed: str) -> list[float]:
    """Deterministic unit vector for fixtures (not a semantic embedding)."""
    rng = random.Random(seed)
    v = [rng.uniform(-1, 1) for _ in range(384)]
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v]


def _vec_literal(v: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"


@dataclass
class Tenant:
    institution_id: uuid.UUID
    portfolio_id: uuid.UUID
    report_id: uuid.UUID
    chunk_id: uuid.UUID
    event_id: uuid.UUID
    rule_id: uuid.UUID
    users: dict = field(default_factory=dict)   # role -> user_id
    tokens: dict = field(default_factory=dict)  # role -> bearer token

    def auth(self, role: str = "pm") -> dict:
        return {"Authorization": f"Bearer {self.tokens[role]}"}


@dataclass
class TwoTenants:
    a: Tenant
    b: Tenant


def _seed_tenant(conn, label: str, marker_ticker: str, roles: tuple[str, ...]) -> Tenant:
    t = Tenant(
        institution_id=uuid.uuid4(),
        portfolio_id=uuid.uuid4(),
        report_id=uuid.uuid4(),
        chunk_id=uuid.uuid4(),
        event_id=uuid.uuid4(),
        rule_id=uuid.uuid4(),
    )
    conn.execute(
        text("INSERT INTO institutions (id, name, slug, tier, created_at) VALUES (:i, :n, :s, 'free', now())"),
        {"i": t.institution_id, "n": f"Synthetic {label}", "s": f"test-{label}-{t.institution_id.hex[:8]}"},
    )
    for role in roles:
        uid = uuid.uuid4()
        conn.execute(
            text(
                "INSERT INTO users (id, institution_id, email, hashed_password, role, is_verified, created_at) "
                "VALUES (:u, :i, :e, 'unused', :r, true, now())"
            ),
            {"u": uid, "i": t.institution_id, "e": f"{role}-{uid.hex[:8]}@{label}.example.edu", "r": role},
        )
        t.users[role] = uid
        t.tokens[role] = create_access_token(uid)
    conn.execute(
        text("INSERT INTO portfolios (id, institution_id, name, strategy_type, created_at) VALUES (:p, :i, :n, 'value', now())"),
        {"p": t.portfolio_id, "i": t.institution_id, "n": f"{label} fund"},
    )
    conn.execute(
        text("INSERT INTO holdings (id, portfolio_id, ticker, weight, cost_basis, updated_at) VALUES (:h, :p, :t, 0.42, 10, now())"),
        {"h": uuid.uuid4(), "p": t.portfolio_id, "t": marker_ticker},
    )
    conn.execute(
        text(
            "INSERT INTO ips_rules (id, institution_id, rule_type, threshold, severity, active, created_at) "
            "VALUES (:r, :i, 'single_position_cap', 0.10, 'critical', true, now())"
        ),
        {"r": t.rule_id, "i": t.institution_id},
    )
    conn.execute(
        text(
            "INSERT INTO research_reports (id, institution_id, sector, company, recommendation, status, created_at) "
            "VALUES (:r, :i, 'Technology', :c, 'buy', 'processed', now())"
        ),
        {"r": t.report_id, "i": t.institution_id, "c": f"{label.upper()} Corp"},
    )
    # Overlapping vocabulary across tenants so FTS and vector search would match both without isolation.
    content = f"Semiconductor liquidity risk memo for {label} confidential thesis {marker_ticker}"
    conn.execute(
        text(
            "INSERT INTO document_chunks (id, institution_id, report_id, content, embedding, embedding_model, "
            "embedding_provider, metadata_json, created_at) "
            "VALUES (:c, :i, :r, :content, CAST(:emb AS vector), 'hash-test-v1@384', 'hash_test', CAST(:meta AS json), now())"
        ),
        {
            "c": t.chunk_id, "i": t.institution_id, "r": t.report_id,
            "content": content,
            "emb": _vec_literal(_hash_embed(content)), "meta": '{"page": 1}',
        },
    )
    conn.execute(
        text(
            "INSERT INTO governance_events (id, institution_id, portfolio_id, rule_id, event_type, severity, "
            "details_json, resolved, created_at) VALUES (:e, :i, :p, :r, 'single_position_cap', 'critical', "
            "CAST(:d AS json), false, now())"
        ),
        {
            "e": t.event_id, "i": t.institution_id, "p": t.portfolio_id, "r": t.rule_id,
            "d": f'{{"ticker": "{marker_ticker}", "current_weight": 0.42, "threshold": 0.1, "message": "x"}}',
        },
    )
    return t


@pytest.fixture
def two_tenants(owner_engine) -> TwoTenants:
    with owner_engine.begin() as conn:
        a = _seed_tenant(conn, "alpha", "ASECRET", ("admin", "pm", "analyst", "faculty", "trustee", "sector_lead"))
        b = _seed_tenant(conn, "bravo", "BSECRET", ("admin", "pm", "analyst"))
    yield TwoTenants(a=a, b=b)
    with owner_engine.begin() as conn:
        conn.execute(
            text("DELETE FROM institutions WHERE id IN (:a, :b)"),
            {"a": a.institution_id, "b": b.institution_id},
        )
