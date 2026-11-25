"""Migration b5e8d17c3a42 (Supabase compatibility) against a real PostgreSQL database.

Each test reproduces the relevant Supabase condition inside one owner transaction and
rolls it back, so nothing persists and the tests run the same in CI (where Supabase's
roles do not exist) as against a Supabase-shaped database.
"""
import importlib.util
import os

import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

pytestmark = pytest.mark.integration

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_API_ROLES = ("anon", "authenticated")
APP_FUNCTIONS_EXECUTABLE_BY = """
    SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'public' AND p.proname LIKE 'app\\_%' AND has_function_privilege(:role, p.oid, 'EXECUTE')
"""
TABLES_ACCESSIBLE_BY = """
    SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'v', 'm')
      AND has_table_privilege(:role, c.oid, 'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
"""


def _migration():
    path = os.path.join(BACKEND_DIR, "migrations", "versions", "b5e8d17c3a42_supabase_compatibility.py")
    spec = importlib.util.spec_from_file_location("supabase_compatibility", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _count(conn, sql, **params) -> int:
    return conn.execute(text(sql), params).scalar_one()


def test_policy_is_installed_for_runtime_reads_only(owner_engine):
    with owner_engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT cmd, roles::text FROM pg_policies "
            "WHERE schemaname = 'public' AND tablename = 'institutions' AND policyname = 'institutions_runtime_read'"
        )).all()
    assert [tuple(r) for r in rows] == [("SELECT", "{gripper_runtime}")]


def test_runtime_role_reads_institutions_when_rls_is_enabled(two_tenants, owner_engine):
    """Supabase's rls_auto_enable leaves institutions with RLS on; the policy keeps it readable."""
    with owner_engine.connect() as conn:
        trans = conn.begin()
        try:
            total = _count(conn, "SELECT count(*) FROM institutions")
            assert total >= 2
            conn.execute(text("ALTER TABLE institutions ENABLE ROW LEVEL SECURITY"))
            conn.execute(text("SET LOCAL ROLE gripper_runtime"))
            assert _count(conn, "SELECT count(*) FROM institutions") == total
            conn.execute(text("RESET ROLE"))
            # Control: without the policy the same role reads nothing.
            conn.execute(text("DROP POLICY institutions_runtime_read ON institutions"))
            conn.execute(text("SET LOCAL ROLE gripper_runtime"))
            assert _count(conn, "SELECT count(*) FROM institutions") == 0
        finally:
            trans.rollback()


def test_runtime_role_still_cannot_write_institutions(two_tenants, owner_engine):
    with owner_engine.connect() as conn:
        trans = conn.begin()
        try:
            conn.execute(text("ALTER TABLE institutions ENABLE ROW LEVEL SECURITY"))
            conn.execute(text("SET LOCAL ROLE gripper_runtime"))
            with pytest.raises(ProgrammingError) as excinfo:
                conn.execute(text("UPDATE institutions SET name = name"))
            assert getattr(excinfo.value.orig, "pgcode", None) == "42501"  # insufficient_privilege
        finally:
            trans.rollback()


def test_data_api_roles_lose_all_access(two_tenants, owner_engine):
    """Recreate Supabase's grants to anon/authenticated, then apply the migration's SQL."""
    revoke_sql = _migration().REVOKE_DATA_API_SQL
    with owner_engine.connect() as conn:
        trans = conn.begin()
        try:
            for role in DATA_API_ROLES:
                conn.execute(text(
                    f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') "
                    f"THEN CREATE ROLE {role} NOLOGIN; END IF; END $$"
                ))
                conn.execute(text(f"GRANT ALL ON ALL TABLES IN SCHEMA public TO {role}"))
                conn.execute(text(f"GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO {role}"))
                conn.execute(text(f"GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO {role}"))
                conn.execute(text(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO {role}"))
                conn.execute(text(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT EXECUTE ON FUNCTIONS TO {role}"))
                # Precondition: the exposure the migration exists to close.
                assert _count(conn, APP_FUNCTIONS_EXECUTABLE_BY, role=role) >= 7
                assert _count(conn, TABLES_ACCESSIBLE_BY, role=role) > 0

            conn.execute(text(revoke_sql))

            conn.execute(text("CREATE TABLE public.zz_supabase_probe (id integer)"))
            conn.execute(text("CREATE FUNCTION public.app_zz_probe() RETURNS integer LANGUAGE sql AS 'SELECT 1'"))
            conn.execute(text("REVOKE ALL ON FUNCTION public.app_zz_probe() FROM PUBLIC"))
            for role in DATA_API_ROLES:
                assert _count(conn, APP_FUNCTIONS_EXECUTABLE_BY, role=role) == 0
                assert _count(conn, TABLES_ACCESSIBLE_BY, role=role) == 0
            # The runtime role keeps its access.
            assert _count(conn, APP_FUNCTIONS_EXECUTABLE_BY, role="gripper_runtime") >= 7
        finally:
            trans.rollback()
