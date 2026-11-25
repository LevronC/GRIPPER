"""Tenant-context regressions (rollback, concurrency) and explanation correctness."""

from __future__ import annotations

import concurrent.futures
import re
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from app.db.session import TenantSession, set_tenant

pytestmark = pytest.mark.integration


@pytest.fixture
def api():
    from app.main import app
    return TestClient(app)


# ── Tenant context across rollback ───────────────────────────────────────────

def test_rollback_keeps_session_tenant_but_never_leaks_to_pool(runtime_engine, two_tenants):
    """pool_size=1, so both sessions use the same physical connection."""
    a = two_tenants.a
    factory = sessionmaker(bind=runtime_engine, class_=TenantSession)
    s1 = factory()
    set_tenant(s1, a.institution_id)
    pid = s1.execute(text("SELECT pg_backend_pid()")).scalar()
    with pytest.raises(DBAPIError):
        s1.execute(text("INSERT INTO portfolios (id, institution_id, name, strategy_type, created_at) "
                        "VALUES (:p, :i, 'x', 'v', now())"), {"p": uuid.uuid4(), "i": two_tenants.b.institution_id})
    s1.rollback()
    # Same session, next transaction: tenant re-applied by the after_begin hook.
    assert str(a.portfolio_id) in {str(x) for x in s1.execute(text("SELECT id FROM portfolios")).scalars()}
    s1.close()

    s2 = factory()  # no tenant set
    assert s2.execute(text("SELECT pg_backend_pid()")).scalar() == pid
    assert s2.execute(text("SELECT current_setting('app.current_institution_id', true)")).scalar() in ("", None)
    assert s2.execute(text("SELECT count(*) FROM portfolios")).scalar() == 0
    s2.close()


def test_failed_request_does_not_poison_the_next_one(api, two_tenants):
    a, b = two_tenants.a, two_tenants.b
    rule = {"rule_type": "single_position_cap", "threshold": 0.2, "scope": "AAPL"}
    assert api.post("/ips_rules", json=rule, headers=a.auth("admin")).status_code == 201
    assert api.post("/ips_rules", json=rule, headers=a.auth("admin")).status_code == 409  # DB error + rollback
    ids = {p["id"] for p in api.get("/portfolios", headers=b.auth()).json()}
    assert ids == {str(b.portfolio_id)}
    ids = {p["id"] for p in api.get("/portfolios", headers=a.auth()).json()}
    assert str(a.portfolio_id) in ids and str(b.portfolio_id) not in ids


def test_concurrent_requests_from_two_institutions(api, two_tenants):
    a, b = two_tenants.a, two_tenants.b

    def call(tenant):
        holdings = api.get(f"/portfolios/{tenant.portfolio_id}/holdings", headers=tenant.auth()).json()
        portfolios = {p["id"] for p in api.get("/portfolios", headers=tenant.auth()).json()}
        return tenant is a, [h["ticker"] for h in holdings], portfolios

    jobs = [a, b] * 30
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(call, jobs))
    for is_a, tickers, portfolios in results:
        own, other = (a, b) if is_a else (b, a)
        assert tickers == (["ASECRET"] if is_a else ["BSECRET"])          # positive control
        assert str(own.portfolio_id) in portfolios and str(other.portfolio_id) not in portfolios


# ── Explanation correctness ──────────────────────────────────────────────────

@pytest.fixture
def scenario(api, owner_engine, two_tenants):
    a = two_tenants.a
    with owner_engine.begin() as conn:
        for table in ("governance_events", "ips_rules", "research_reports"):
            conn.execute(text(f"DELETE FROM {table} WHERE institution_id = :i"), {"i": a.institution_id})
    for body in ({"rule_type": "single_position_cap", "threshold": 0.10},
                 {"rule_type": "single_position_cap", "threshold": 0.05, "scope": "NVDA"},
                 {"rule_type": "sector_exposure_cap", "threshold": 0.30, "scope": "Technology"},
                 {"rule_type": "liquidity_constraint", "threshold": 0.05}):
        assert api.post("/ips_rules", json=body, headers=a.auth("admin")).status_code == 201
    api.post(f"/portfolios/{a.portfolio_id}/holdings", headers=a.auth("pm"), json=[
        {"ticker": t, "weight": w, "cost_basis": 1} for t, w in
        (("NVDA", 0.08), ("AAPL", 0.12), ("MSFT", 0.15), ("MCRT", 0.04), ("GCAP", 0.03))])
    events = api.post(f"/portfolios/{a.portfolio_id}/evaluate", headers=a.auth("pm")).json()["violations"]
    return a, {(e["event_type"], e["details"].get("ticker") or e["details"].get("sector") or ""): e for e in events}


def _explain(api, a, event):
    r = api.post(f"/violations/{event['id']}/explain", headers=a.auth("pm"))
    assert r.status_code == 200, r.text
    return r.json()


def test_explanations_state_the_correct_rule_values_and_thresholds(api, scenario):
    a, ev = scenario
    assert set(ev) == {("single_position_cap", "AAPL"), ("single_position_cap", "MSFT"),
                       ("single_position_cap", "NVDA"), ("sector_exposure_cap", "Technology"),
                       ("liquidity_constraint", "")}
    cases = {
        ("single_position_cap", "AAPL"): ("AAPL is 12.0% of the portfolio; the single-position limit is 10.0%.", None, 0.10),
        ("single_position_cap", "NVDA"): ("NVDA is 8.0% of the portfolio; the single-position limit is 5.0%.", "NVDA", 0.05),
        ("sector_exposure_cap", "Technology"): ("Technology exposure is 39.0%; the sector limit is 30.0%.", "Technology", 0.30),
        ("liquidity_constraint", ""): ("Micro-cap holdings (GCAP, MCRT) total 7.0%; the liquidity limit is 5.0%.", None, 0.05),
    }
    for key, (sentence, scope, threshold) in cases.items():
        body = _explain(api, a, ev[key])
        assert body["explanation"].startswith(sentence), body["explanation"]
        assert body["policy"]["scope"] == scope and body["policy"]["threshold_at_evaluation"] == threshold
        assert body["policy"]["rule_type"] == key[0] and body["policy"]["rule_active"] is True
        assert body["violation_status"] == "open" and body["explanation_source"] == "template"
        assert body["research_status"] == "none" and "No research documents" in body["explanation"]
        if scope:
            assert f"scoped to {scope}" in body["explanation"]


def test_explanation_works_without_semantic_search(api, scenario, owner_engine, monkeypatch):
    from tests.integration.test_compliance_workflow import _seed_research

    a, ev = scenario
    _seed_research(owner_engine, a.institution_id, "AAPL", "AAPL investment thesis position sizing risk note.")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "none")
    body = _explain(api, a, ev[("single_position_cap", "AAPL")])
    assert body["retrieval_mode"] == "full_text_only" and body["research_status"] == "found"
    assert body["violation_status"] == "open"


def test_explanation_matches_frontend_contract(api, scenario, owner_engine):
    """Fields read by src/components/ExplainabilityDrawer.tsx must exist with the right types."""
    from tests.integration.test_compliance_workflow import _seed_research

    a, ev = scenario
    _seed_research(owner_engine, a.institution_id, "AAPL", "AAPL investment thesis position sizing risk note.")
    body = _explain(api, a, ev[("single_position_cap", "AAPL")])
    drawer = open("../src/components/ExplainabilityDrawer.tsx").read()
    for field in ("violation_status", "research_status", "explanation", "explanation_source", "evidence"):
        assert re.search(rf"\b{field}\b", drawer), field
        assert field in body
    assert body["violation_status"] in ("open", "resolved") and body["research_status"] in ("found", "none", "unavailable")
    [e] = body["evidence"]
    for field, typ in (("chunk_id", str), ("report_id", str), ("company", str), ("sector", str), ("content", str)):
        assert re.search(rf"\b{field}\b", drawer), field
        assert isinstance(e[field], typ)
    assert isinstance(e["page"], int) and e["page"] == 3


def test_explanation_never_cites_other_tenant_research(api, scenario, owner_engine, two_tenants):
    from tests.integration.test_compliance_workflow import _seed_research

    a, ev = scenario
    b = two_tenants.b
    _seed_research(owner_engine, b.institution_id, "AAPL", "AAPL investment thesis position sizing risk BRAVO-ONLY.")
    body = _explain(api, a, ev[("single_position_cap", "AAPL")])
    assert "BRAVO-ONLY" not in str(body)
    with owner_engine.connect() as conn:
        for e in body["evidence"]:
            inst = conn.execute(text("SELECT institution_id FROM document_chunks WHERE id = :c"), {"c": e["chunk_id"]}).scalar()
            assert inst == a.institution_id
