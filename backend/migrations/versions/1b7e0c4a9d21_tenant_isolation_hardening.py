"""tenant_isolation_hardening

Separates runtime privileges from migration (owner) privileges and removes the need
for any RLS-bypassing connection at request time.

* Creates the NOLOGIN group role ``gripper_runtime`` (NOSUPERUSER, NOBYPASSRLS) and
  grants it DML on tenant tables. The application's login role is made a member of
  this group outside migrations (see backend/scripts/create_app_role.py).
* Adds narrowly scoped SECURITY DEFINER functions for the only cross-tenant lookups
  the runtime needs (resolve a user's institution during authentication; list
  pending ingestion jobs). They return identifiers only; the caller then binds the
  session to that institution and reads rows under RLS.
* Adds composite foreign keys so a child row's institution_id must match its
  parent's (governance_events -> portfolios, document_chunks -> research_reports).

Revision ID: 1b7e0c4a9d21
Revises: f4de4f049821
Create Date: 2026-11-25
"""
from typing import Sequence, Union

from alembic import op

revision: str = "1b7e0c4a9d21"
down_revision: Union[str, Sequence[str], None] = "f4de4f049821"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

RUNTIME_ROLE = "gripper_runtime"

TENANT_TABLES = (
    "users",
    "portfolios",
    "holdings",
    "research_reports",
    "document_chunks",
    "meetings",
    "ips_rules",
    "governance_events",
)


def upgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{RUNTIME_ROLE}') THEN
                CREATE ROLE {RUNTIME_ROLE} NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
            END IF;
        END $$;
        """
    )
    op.execute(f"GRANT USAGE ON SCHEMA public TO {RUNTIME_ROLE}")
    for table in TENANT_TABLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {table} TO {RUNTIME_ROLE}")
    # Institutions are tenant metadata (no RLS); runtime may read but not create/alter.
    op.execute(f"GRANT SELECT ON TABLE institutions TO {RUNTIME_ROLE}")

    # ── Composite tenant-consistency constraints ─────────────────────────────
    op.execute("ALTER TABLE portfolios ADD CONSTRAINT uq_portfolios_id_institution UNIQUE (id, institution_id)")
    op.execute(
        "ALTER TABLE governance_events ADD CONSTRAINT fk_governance_events_portfolio_tenant "
        "FOREIGN KEY (portfolio_id, institution_id) REFERENCES portfolios (id, institution_id) ON DELETE CASCADE"
    )
    op.execute("ALTER TABLE research_reports ADD CONSTRAINT uq_research_reports_id_institution UNIQUE (id, institution_id)")
    op.execute(
        "ALTER TABLE document_chunks ADD CONSTRAINT fk_document_chunks_report_tenant "
        "FOREIGN KEY (report_id, institution_id) REFERENCES research_reports (id, institution_id) ON DELETE CASCADE"
    )

    # ── SECURITY DEFINER lookups (owner privileges, identifiers only) ────────
    op.execute(
        """
        CREATE OR REPLACE FUNCTION app_resolve_user_by_email(p_email text)
        RETURNS TABLE (user_id uuid, institution_id uuid)
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = public, pg_temp
        AS $$
            SELECT u.id, u.institution_id FROM users u WHERE lower(u.email) = lower(p_email)
        $$;
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION app_resolve_user_by_id(p_user_id uuid)
        RETURNS TABLE (user_id uuid, institution_id uuid)
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = public, pg_temp
        AS $$
            SELECT u.id, u.institution_id FROM users u WHERE u.id = p_user_id
        $$;
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION app_pending_ingestion_jobs(p_limit integer)
        RETURNS TABLE (report_id uuid, institution_id uuid)
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = public, pg_temp
        AS $$
            SELECT r.id, r.institution_id FROM research_reports r
            WHERE r.status = 'pending' AND r.file_path IS NOT NULL
            ORDER BY r.created_at
            LIMIT LEAST(GREATEST(p_limit, 0), 50)
        $$;
        """
    )
    for fn in (
        "app_resolve_user_by_email(text)",
        "app_resolve_user_by_id(uuid)",
        "app_pending_ingestion_jobs(integer)",
    ):
        op.execute(f"REVOKE ALL ON FUNCTION {fn} FROM PUBLIC")
        # Supabase grants EXECUTE on new public functions to its Data API roles via
        # default privileges; REVOKE FROM PUBLIC does not remove explicit grants.
        op.execute(
            f"""
            DO $$
            DECLARE r text;
            BEGIN
                FOREACH r IN ARRAY ARRAY['anon', 'authenticated'] LOOP
                    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
                        EXECUTE format('REVOKE ALL ON FUNCTION {fn} FROM %I', r);
                    END IF;
                END LOOP;
            END $$;
            """
        )
        op.execute(f"GRANT EXECUTE ON FUNCTION {fn} TO {RUNTIME_ROLE}")

    # Legacy grant from c6a17410438c (local Docker role) is superseded by group membership.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'gripper_app') THEN
                REVOKE ALL PRIVILEGES ON TABLE governance_events FROM gripper_app;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS app_pending_ingestion_jobs(integer)")
    op.execute("DROP FUNCTION IF EXISTS app_resolve_user_by_id(uuid)")
    op.execute("DROP FUNCTION IF EXISTS app_resolve_user_by_email(text)")
    op.execute("ALTER TABLE document_chunks DROP CONSTRAINT IF EXISTS fk_document_chunks_report_tenant")
    op.execute("ALTER TABLE research_reports DROP CONSTRAINT IF EXISTS uq_research_reports_id_institution")
    op.execute("ALTER TABLE governance_events DROP CONSTRAINT IF EXISTS fk_governance_events_portfolio_tenant")
    op.execute("ALTER TABLE portfolios DROP CONSTRAINT IF EXISTS uq_portfolios_id_institution")
    op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {RUNTIME_ROLE}")
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {RUNTIME_ROLE}")
    # The role itself is left in place (it may have members); drop manually if desired.
