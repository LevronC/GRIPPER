"""
Violation lifecycle, scoped IPS rules, and independence of compliance from research,
embeddings and explanations (real DB, restricted role, real API).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

pytestmark = pytest.mark.integration


@pytest.fixture
def api():
    from app.main import app
    return TestClient(app)


@pytest.fixture
def t(owner_engine, two_tenants):
    """Tenant A with no rules/events/research; a fresh empty portfolio."""
    a = two_tenants.a
    with owner_engine.begin() as conn:
        for table in ("governance_events", "ips_rules", "research_reports"):
            conn.execute(text(f"DELETE FROM {table} WHERE institution_id = :i"), {"i": a.institution_id})
        conn.execute(text("DELETE FROM holdings WHERE portfolio_id = :p"), {"p": a.portfolio_id})
    return a


def rule(api, t, rule_type, threshold, scope=None, severity="warning"):
    body = {"rule_type": rule_type, "threshold": threshold, "severity": severity}
    if scope:
        body["scope"] = scope
    r = api.post("/ips_rules", json=body, headers=t.auth("admin"))
    assert r.status_code == 201, r.text
    return r.json()


def hold(api, t, **weights):
    r = api.post(f"/portfolios/{t.portfolio_id}/holdings", headers=t.auth("pm"),
                 json=[{"ticker": k, "weight": v, "cost_basis": 1} for k, v in weights.items()])
    assert r.status_code == 200, r.text


def evaluate(api, t):
    r = api.post(f"/portfolios/{t.portfolio_id}/evaluate", headers=t.auth("pm"))
    assert r.status_code == 200, r.text
    return r.json()["violations"]


def resolved(api, t):
    return api.get(f"/portfolios/{t.portfolio_id}/violations", params={"resolved": True}, headers=t.auth()).json()


def key(v):
    return (v["event_type"], v["details"].get("ticker") or v["details"].get("sector") or "")


# ── Lifecycle ────────────────────────────────────────────────────────────────

def test_full_lifecycle_persist_change_resolve_recur(api, t):
    rule(api, t, "single_position_cap", 0.10)
    hold(api, t, NVDA=0.14, AAPL=0.05)
    first = evaluate(api, t)
    assert [key(v) for v in first] == [("single_position_cap", "NVDA")]
    eid = first[0]["id"]

    # Unchanged, repeated, and re-saved identical holdings: same event.
    assert [v["id"] for v in evaluate(api, t)] == [eid]
    hold(api, t, NVDA=0.14, AAPL=0.05)
    assert [v["id"] for v in evaluate(api, t)] == [eid]

    # Holdings change but the breach persists: same event, refreshed values and severity.
    hold(api, t, NVDA=0.16, AAPL=0.05)
    [v] = evaluate(api, t)
    assert v["id"] == eid and v["details"]["current_weight"] == 0.16 and v["severity"] == "critical"

    # Resolution.
    hold(api, t, NVDA=0.08, AAPL=0.05)
    assert evaluate(api, t) == []
    [r] = resolved(api, t)
    assert r["id"] == eid and r["resolved_at"] and r["details"]["resolution"] == "no_longer_breached"
    assert r["details"]["current_weight"] == 0.16  # last observed value preserved

    # Recurrence: a NEW event; the resolved one is untouched.
    hold(api, t, NVDA=0.13, AAPL=0.05)
    [again] = evaluate(api, t)
    assert again["id"] != eid and again["details"]["current_weight"] == 0.13
    [r2] = resolved(api, t)
    assert r2 == r


def test_threshold_changes_refresh_open_event_but_never_rewrite_history(api, t):
    pos = rule(api, t, "single_position_cap", 0.10)
    hold(api, t, NVDA=0.14)
    [v] = evaluate(api, t)
    api.patch(f"/ips_rules/{pos['id']}", json={"threshold": 0.12}, headers=t.auth("admin"))
    [v2] = evaluate(api, t)
    assert v2["id"] == v["id"] and v2["details"]["threshold"] == 0.12        # still breached, current threshold
    api.patch(f"/ips_rules/{pos['id']}", json={"threshold": 0.20}, headers=t.auth("admin"))
    assert evaluate(api, t) == []
    [r] = resolved(api, t)
    assert r["details"]["threshold"] == 0.12 and r["details"]["resolution"] == "no_longer_breached"
    api.patch(f"/ips_rules/{pos['id']}", json={"threshold": 0.05}, headers=t.auth("admin"))
    [v3] = evaluate(api, t)
    assert v3["id"] != v["id"]
    assert resolved(api, t) == [r]  # the resolved record kept its original threshold


def test_rule_deactivation_resolves_with_reason(api, t):
    pos = rule(api, t, "single_position_cap", 0.10)
    hold(api, t, NVDA=0.14)
    [v] = evaluate(api, t)
    api.post(f"/ips_rules/{pos['id']}/deactivate", headers=t.auth("admin"))
    assert evaluate(api, t) == []
    [r] = resolved(api, t)
    assert r["id"] == v["id"] and r["details"]["resolution"] == "rule_inactive"
    body = api.post(f"/violations/{v['id']}/explain", headers=t.auth("pm")).json()
    assert body["violation_status"] == "resolved" and "deactivated" in body["explanation"]


def test_emptying_portfolio_resolves_open_violations(api, t):
    """Regression: an empty portfolio used to return early and leave events open forever."""
    rule(api, t, "single_position_cap", 0.10)
    hold(api, t, NVDA=0.14)
    [v] = evaluate(api, t)
    r = api.post(f"/portfolios/{t.portfolio_id}/holdings", json=[], headers=t.auth("pm"))
    assert r.status_code == 200
    assert evaluate(api, t) == []
    assert [x["id"] for x in resolved(api, t)] == [v["id"]]


# ── Scoped rules ─────────────────────────────────────────────────────────────

def test_realistic_policy_with_multiple_scoped_rules(api, t):
    rule(api, t, "sector_exposure_cap", 0.30, scope="Technology")
    rule(api, t, "sector_exposure_cap", 0.20, scope="Healthcare")
    rule(api, t, "sector_exposure_cap", 0.15, scope="Energy")
    rule(api, t, "single_position_cap", 0.05)
    rule(api, t, "single_position_cap", 0.03, scope="NVDA")
    hold(api, t, NVDA=0.04, AAPL=0.10, MSFT=0.10, JNJ=0.05, LLY=0.05, XOM=0.10, CVX=0.06, JPM=0.05)
    got = sorted((key(v), v["details"]["threshold"]) for v in evaluate(api, t))
    # Technology 24% <= 30%, Healthcare 10% <= 20%: pass. Energy 16% > 15%: breach.
    # Positions at exactly 5% (JNJ, LLY, JPM) pass the global cap; NVDA 4% passes the
    # global 5% cap but breaches its own 3% cap. Each rule is evaluated independently.
    assert got == [
        (("sector_exposure_cap", "Energy"), 0.15),
        (("single_position_cap", "AAPL"), 0.05),
        (("single_position_cap", "CVX"), 0.05),
        (("single_position_cap", "MSFT"), 0.05),
        (("single_position_cap", "NVDA"), 0.03),
        (("single_position_cap", "XOM"), 0.05),
    ]


def test_same_scope_duplicate_rejected_but_different_scope_allowed(api, t):
    rule(api, t, "sector_exposure_cap", 0.30, scope="Technology")
    dup = api.post("/ips_rules", json={"rule_type": "sector_exposure_cap", "threshold": 0.2, "scope": "Technology"},
                   headers=t.auth("admin"))
    assert dup.status_code == 409
    rule(api, t, "sector_exposure_cap", 0.20, scope="Energy")
    glob = rule(api, t, "sector_exposure_cap", 0.40)  # unscoped coexists with scoped
    api.post(f"/ips_rules/{glob['id']}/deactivate", headers=t.auth("admin"))
    rule(api, t, "sector_exposure_cap", 0.35)        # replacement after deactivation
    again = api.patch(f"/ips_rules/{glob['id']}", json={"active": True}, headers=t.auth("admin"))
    assert again.status_code == 409                  # reactivating would duplicate


@pytest.mark.parametrize("body", [
    {"rule_type": "liquidity_constraint", "threshold": 0.05, "scope": "MCRT"},
    {"rule_type": "sector_exposure_cap", "threshold": 0.3, "scope": "Crypto"},
    {"rule_type": "single_position_cap", "threshold": 0.05, "scope": "NV DA; --"},
])
def test_invalid_scopes_rejected(api, t, body):
    assert api.post("/ips_rules", json=body, headers=t.auth("admin")).status_code == 422


def test_scope_is_normalised_and_reported(api, t):
    r = rule(api, t, "single_position_cap", 0.05, scope="nvda")
    assert r["scope"] == "NVDA"
    listed = api.get("/ips_rules", headers=t.auth("analyst")).json()
    assert [x["scope"] for x in listed] == ["NVDA"]


# ── Missing information ──────────────────────────────────────────────────────

def test_unclassified_holding_produces_insufficient_data_event(api, t):
    rule(api, t, "liquidity_constraint", 0.05)
    hold(api, t, ZZZZ=0.50)
    [v] = evaluate(api, t)
    assert v["event_type"] == "insufficient_data" and v["details"]["tickers"] == ["ZZZZ"]
    body = api.post(f"/violations/{v['id']}/explain", headers=t.auth("pm")).json()
    assert "could not be fully evaluated" in body["explanation"] and body["violation_status"] == "open"
    hold(api, t, MCRT=0.02)
    assert evaluate(api, t) == []


# ── Non-finite numbers over HTTP ─────────────────────────────────────────────

@pytest.mark.parametrize("raw", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_numbers_rejected_by_api(api, t, raw):
    h = {**t.auth("admin"), "Content-Type": "application/json"}
    r = api.post(f"/portfolios/{t.portfolio_id}/holdings", headers=h,
                 content=f'[{{"ticker": "AAPL", "weight": {raw}, "cost_basis": 1}}]')
    assert r.status_code == 422
    r = api.post(f"/portfolios/{t.portfolio_id}/simulate", headers=h, content=f'[{{"ticker": "AAPL", "weight": {raw}}}]')
    assert r.status_code == 422
    r = api.post("/ips_rules", headers=h, content=f'{{"rule_type": "single_position_cap", "threshold": {raw}}}')
    assert r.status_code == 422


def test_portfolio_model_is_long_only_unleveraged(api, t):
    h = t.auth("pm")
    ok = api.post(f"/portfolios/{t.portfolio_id}/holdings", headers=h,
                  json=[{"ticker": "AAPL", "weight": 0.1, "cost_basis": 1}, {"ticker": "MSFT", "weight": 0.2, "cost_basis": 1},
                        {"ticker": "XOM", "weight": 0.7, "cost_basis": 1}])
    assert ok.status_code == 200          # exactly 100% (0.1 + 0.2 + 0.7, decimal-exact)
    over = api.post(f"/portfolios/{t.portfolio_id}/holdings", headers=h,
                    json=[{"ticker": "AAPL", "weight": 0.6, "cost_basis": 1}, {"ticker": "MSFT", "weight": 0.4000001, "cost_basis": 1}])
    assert over.status_code == 422 and "long-only" in over.json()["detail"]
    short = api.post(f"/portfolios/{t.portfolio_id}/holdings", headers=h, json=[{"ticker": "AAPL", "weight": -0.1, "cost_basis": 1}])
    assert short.status_code == 422


# ── Compliance is independent of research, embeddings and explanations ──────

def test_compliance_unaffected_by_research_embeddings_or_explanation_failure(api, t, owner_engine, monkeypatch):
    rule(api, t, "single_position_cap", 0.10)
    rule(api, t, "liquidity_constraint", 0.05)
    hold(api, t, NVDA=0.14, MCRT=0.06)
    baseline = [(v["id"], key(v), v["severity"]) for v in evaluate(api, t)]
    assert len(baseline) == 2

    monkeypatch.setenv("EMBEDDING_PROVIDER", "none")
    assert [(v["id"], key(v), v["severity"]) for v in evaluate(api, t)] == baseline
    monkeypatch.delenv("EMBEDDING_PROVIDER")

    from tests.integration.test_compliance_workflow import _seed_research
    _seed_research(owner_engine, t.institution_id, "NVDA", "NVDA thesis supports a larger position; exception approved.")
    assert [(v["id"], key(v), v["severity"]) for v in evaluate(api, t)] == baseline

    def broken(*_a, **_k):
        raise RuntimeError("renderer failure")

    monkeypatch.setattr("app.services.governance.explain.render_template_explanation", broken)
    r = api.post(f"/violations/{baseline[0][0]}/explain", headers=t.auth("pm"))
    assert r.status_code == 500 and "renderer failure" not in r.text
    assert [(v["id"], key(v), v["severity"]) for v in evaluate(api, t)] == baseline
    with owner_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM governance_events WHERE institution_id = :i AND NOT resolved"),
                            {"i": t.institution_id}).scalar() == 2
