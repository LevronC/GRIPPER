"""invitations_and_password_reset

* ``invitations``: admin-issued, institution-scoped, single-use, expiring, revocable.
* ``password_reset_tokens``: single-use, expiring.
Both store only SHA-256 hashes of 256-bit random tokens and are protected by RLS.
* ``users.token_version``: incremented on password reset to invalidate existing JWTs.
* Drops ``users.verification_code`` (plaintext 6-digit codes from the old flow).

Revision ID: 2c4d8e6f1a37
Revises: 1b7e0c4a9d21
Create Date: 2026-11-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "2c4d8e6f1a37"
down_revision: Union[str, Sequence[str], None] = "1b7e0c4a9d21"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

RUNTIME_ROLE = "gripper_runtime"
POLICY = "institution_id = NULLIF(current_setting('app.current_institution_id', true), '')::uuid"


def _protect(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY {table}_isolation ON {table} USING ({POLICY})")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {table} TO {RUNTIME_ROLE}")


def _definer_grants(fn: str) -> None:
    op.execute(f"REVOKE ALL ON FUNCTION {fn} FROM PUBLIC")
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


def upgrade() -> None:
    op.add_column("users", sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"))
    op.drop_column("users", "verification_code")
    op.execute("ALTER TABLE users ADD CONSTRAINT uq_users_id_institution UNIQUE (id, institution_id)")

    op.create_table(
        "invitations",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("institution_id", sa.UUID(), sa.ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("role", sa.String(50), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.UUID(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("TIMEZONE('utc', NOW())"), nullable=False),
        sa.Column("accepted_at", sa.DateTime(), nullable=True),
        sa.Column("accepted_user_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
    )
    op.create_index("idx_invitations_institution_email", "invitations", ["institution_id", "email"])
    _protect("invitations")

    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("institution_id", sa.UUID(), sa.ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("TIMEZONE('utc', NOW())"), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id", "institution_id"], ["users.id", "users.institution_id"],
            name="fk_password_reset_tokens_user_tenant", ondelete="CASCADE",
        ),
    )
    op.create_index("idx_password_reset_tokens_user_created", "password_reset_tokens", ["user_id", "created_at"])
    _protect("password_reset_tokens")

    op.execute(
        """
        CREATE OR REPLACE FUNCTION app_resolve_invitation(p_token_hash text)
        RETURNS TABLE (invitation_id uuid, institution_id uuid)
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = public, pg_temp
        AS $$ SELECT i.id, i.institution_id FROM invitations i WHERE i.token_hash = p_token_hash $$;
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION app_resolve_password_reset(p_token_hash text)
        RETURNS TABLE (token_id uuid, institution_id uuid)
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = public, pg_temp
        AS $$ SELECT t.id, t.institution_id FROM password_reset_tokens t WHERE t.token_hash = p_token_hash $$;
        """
    )
    _definer_grants("app_resolve_invitation(text)")
    _definer_grants("app_resolve_password_reset(text)")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS app_resolve_password_reset(text)")
    op.execute("DROP FUNCTION IF EXISTS app_resolve_invitation(text)")
    op.drop_table("password_reset_tokens")
    op.drop_table("invitations")
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS uq_users_id_institution")
    op.add_column("users", sa.Column("verification_code", sa.String(6), nullable=True))
    op.drop_column("users", "token_version")
