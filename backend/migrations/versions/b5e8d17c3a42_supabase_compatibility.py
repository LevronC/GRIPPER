"""Supabase compatibility: runtime read policy on institutions; close the Data API roles.

Revision ID: b5e8d17c3a42
Revises: f1b4c8d2e903

Supabase differs from a plain PostgreSQL database in two ways that matter here.

1. Its ``rls_auto_enable`` trigger turns row-level security on for every new table,
   including ``institutions``, which this schema leaves without RLS. With RLS on and
   no policy, the restricted runtime role reads zero institutions. The policy below
   restores the intended access (the runtime role may read institutions; it has no
   write grant) while RLS stays on for every other role. Where RLS is off, the policy
   has no effect.

2. Supabase's default privileges grant ``anon`` and ``authenticated`` every privilege on
   new tables, sequences and functions in ``public``, directly, not through PUBLIC.
   ``REVOKE ... FROM PUBLIC`` on the SECURITY DEFINER lookup functions therefore leaves
   them callable through Supabase's REST API (``/rest/v1/rpc``) by anyone with the
   project's publishable key. Gripper never uses those roles; it connects only through
   PostgreSQL. When the roles exist, all of their privileges in ``public`` are revoked,
   and the migration role's default privileges stop granting them on future objects.
   Default privileges owned by other roles (e.g. ``supabase_admin``) cannot be changed
   here and apply only to objects those roles create. ``service_role`` is untouched.

Downgrade drops the policy. Revoked grants are deliberately not restored.
"""
from alembic import op

revision = "b5e8d17c3a42"
down_revision = "f1b4c8d2e903"
branch_labels = None
depends_on = None

# Also executed by tests/integration/test_supabase_compat.py.
REVOKE_DATA_API_SQL = """
DO $$
DECLARE r text;
BEGIN
    FOREACH r IN ARRAY ARRAY['anon', 'authenticated'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
            EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA public FROM %I', r);
            EXECUTE format('REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM %I', r);
            EXECUTE format('REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM %I', r);
            EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM %I', r);
            EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM %I', r);
            EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON FUNCTIONS FROM %I', r);
        END IF;
    END LOOP;
END
$$;
"""


def upgrade():
    op.execute(
        "CREATE POLICY institutions_runtime_read ON institutions "
        "FOR SELECT TO gripper_runtime USING (true)"
    )
    op.execute(REVOKE_DATA_API_SQL)


def downgrade():
    op.execute("DROP POLICY IF EXISTS institutions_runtime_read ON institutions")
