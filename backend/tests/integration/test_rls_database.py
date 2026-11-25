"""
Database-level tenant isolation, exercised through the RESTRICTED runtime role with
raw SQL (no application code). These assertions are only meaningful because the
role is NOSUPERUSER/NOBYPASSRLS; test_runtime_role_is_restricted guards that.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db.session import PROTECTED_TABLES, database_role_report

pytestmark = pytest.mark.integration


def _tenant(conn, institution_id) -> None:
    conn.execute(
        text("SELECT set_config('app.current_institution_id', :t, true)"),
        {"t": str(institution_id) if institution_id else ""},
    )


def test_runtime_role_is_restricted(runtime_engine):
    with runtime_engine.connect() as conn:
        report = database_role_report(conn)
    assert report["rolsuper"] is False
    assert report["rolbypassrls"] is False
    assert report["owned_tables"] == []
    assert report["tables_without_forced_rls"] == []
    assert report["rls_enforced"] is True


def test_owner_role_is_reported_unsafe(owner_engine):
    """Negative control: the safety check must flag the privileged role."""
    with owner_engine.connect() as conn:
        report = database_role_report(conn)
    assert report["rls_enforced"] is False
    assert report["problems"]


@pytest.mark.parametrize(
    "table, id_attr",
    [
        ("portfolios", "portfolio_id"),
        ("research_reports", "report_id"),
        ("document_chunks", "chunk_id"),
        ("governance_events", "event_id"),
        ("ips_rules", "rule_id"),
    ],
)
def test_tenant_sees_only_own_rows(runtime_engine, two_tenants, table, id_attr):
    a, b = two_tenants.a, two_tenants.b
    with runtime_engine.begin() as conn:
        _tenant(conn, a.institution_id)
        ids = set(conn.execute(text(f"SELECT id FROM {table}")).scalars())
    assert getattr(a, id_attr) in ids          # positive control
    assert getattr(b, id_attr) not in ids      # isolation


def test_holdings_isolated_via_parent_portfolio(runtime_engine, two_tenants):
    with runtime_engine.begin() as conn:
        _tenant(conn, two_tenants.a.institution_id)
        tickers = set(conn.execute(text("SELECT ticker FROM holdings")).scalars())
    assert "ASECRET" in tickers
    assert "BSECRET" not in tickers


def test_users_isolated(runtime_engine, two_tenants):
    with runtime_engine.begin() as conn:
        _tenant(conn, two_tenants.a.institution_id)
        ids = set(conn.execute(text("SELECT id FROM users")).scalars())
    assert two_tenants.a.users["pm"] in ids
    assert two_tenants.b.users["pm"] not in ids


def test_cannot_update_or_delete_other_tenant_rows(runtime_engine, owner_engine, two_tenants):
    a, b = two_tenants.a, two_tenants.b
    with runtime_engine.begin() as conn:
        _tenant(conn, a.institution_id)
        upd = conn.execute(text("UPDATE holdings SET weight = 0.99 WHERE portfolio_id = :p"), {"p": b.portfolio_id})
        dele = conn.execute(text("DELETE FROM portfolios WHERE id = :p"), {"p": b.portfolio_id})
        assert upd.rowcount == 0
        assert dele.rowcount == 0
    with owner_engine.connect() as conn:
        assert conn.execute(text("SELECT weight FROM holdings WHERE portfolio_id = :p"), {"p": b.portfolio_id}).scalar() == 0.42
        assert conn.execute(text("SELECT count(*) FROM portfolios WHERE id = :p"), {"p": b.portfolio_id}).scalar() == 1


def test_cannot_insert_rows_for_other_tenant(runtime_engine, two_tenants):
    a, b = two_tenants.a, two_tenants.b
    with pytest.raises(DBAPIError, match="row-level security"):
        with runtime_engine.begin() as conn:
            _tenant(conn, a.institution_id)
            conn.execute(
                text("INSERT INTO portfolios (id, institution_id, name, strategy_type, created_at) "
                     "VALUES (:p, :i, 'x', 'value', now())"),
                {"p": uuid.uuid4(), "i": b.institution_id},
            )


def test_cannot_attach_holding_to_other_tenant_portfolio(runtime_engine, two_tenants):
    a, b = two_tenants.a, two_tenants.b
    with pytest.raises(DBAPIError, match="row-level security"):
        with runtime_engine.begin() as conn:
            _tenant(conn, a.institution_id)
            conn.execute(
                text("INSERT INTO holdings (id, portfolio_id, ticker, weight, cost_basis, updated_at) "
                     "VALUES (:h, :p, 'EVIL', 0.5, 1, now())"),
                {"h": uuid.uuid4(), "p": b.portfolio_id},
            )


def test_composite_fk_blocks_cross_tenant_parent_even_for_owner(owner_engine, two_tenants):
    """Constraint (not RLS): a child's institution_id must equal its parent's."""
    a, b = two_tenants.a, two_tenants.b
    with pytest.raises(DBAPIError, match="fk_governance_events_portfolio_tenant"):
        with owner_engine.begin() as conn:
            conn.execute(
                text("INSERT INTO governance_events (id, institution_id, portfolio_id, event_type, severity, "
                     "details_json, resolved, created_at) VALUES (:e, :i, :p, 'x', 'warning', '{}', false, now())"),
                {"e": uuid.uuid4(), "i": a.institution_id, "p": b.portfolio_id},
            )
    with pytest.raises(DBAPIError, match="fk_document_chunks_report_tenant"):
        with owner_engine.begin() as conn:
            conn.execute(
                text("INSERT INTO document_chunks (id, institution_id, report_id, content, embedding, created_at) "
                     "VALUES (:c, :i, :r, 'x', CAST(:v AS vector), now())"),
                {"c": uuid.uuid4(), "i": a.institution_id, "r": b.report_id, "v": "[" + ",".join(["0"] * 384) + "]"},
            )


@pytest.mark.parametrize("table", PROTECTED_TABLES)
def test_missing_tenant_context_fails_closed(runtime_engine, two_tenants, table):
    with runtime_engine.begin() as conn:
        _tenant(conn, None)
        assert conn.execute(text(f"SELECT count(*) FROM {table}")).scalar() == 0


def test_garbage_tenant_context_errors_rather_than_leaks(runtime_engine, two_tenants):
    with pytest.raises(DBAPIError):
        with runtime_engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.current_institution_id', 'not-a-uuid', true)"))
            conn.execute(text("SELECT count(*) FROM portfolios")).scalar()


def test_tenant_context_does_not_survive_transaction_on_reused_connection(runtime_engine, two_tenants):
    """pool_size=1: the second checkout is the same physical connection."""
    with runtime_engine.connect() as conn:
        pid_1 = conn.execute(text("SELECT pg_backend_pid()")).scalar()
        conn.commit()
        with conn.begin():
            _tenant(conn, two_tenants.a.institution_id)
            assert conn.execute(text("SELECT count(*) FROM portfolios")).scalar() >= 1
    with runtime_engine.connect() as conn:
        assert conn.execute(text("SELECT pg_backend_pid()")).scalar() == pid_1
        leaked = conn.execute(text("SELECT current_setting('app.current_institution_id', true)")).scalar()
        assert leaked in ("", None)
        assert conn.execute(text("SELECT count(*) FROM portfolios")).scalar() == 0


def test_runtime_role_cannot_run_ddl(runtime_engine):
    with pytest.raises(DBAPIError):
        with runtime_engine.begin() as conn:
            conn.execute(text("ALTER TABLE portfolios DISABLE ROW LEVEL SECURITY"))


def test_definer_lookup_returns_identifiers_only(runtime_engine, two_tenants):
    b = two_tenants.b
    with runtime_engine.begin() as conn:
        _tenant(conn, two_tenants.a.institution_id)
        row = conn.execute(text("SELECT * FROM app_resolve_user_by_id(:u)"), {"u": b.users["pm"]}).mappings().one()
    assert set(row.keys()) == {"user_id", "institution_id"}
    assert row["institution_id"] == b.institution_id
