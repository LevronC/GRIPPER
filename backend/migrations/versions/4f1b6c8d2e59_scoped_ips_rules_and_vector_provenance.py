"""scoped_ips_rules_and_vector_provenance

* ips_rules.scope: NULL (global) or a ticker / sector name. An IPS can now hold several
  rules of the same type with different scopes (e.g. Technology <= 30% and
  Energy <= 15%, or all positions <= 5% plus NVDA <= 3%).
* Uniqueness moves from the application ("one active rule per type", Phase 1) to a
  partial unique index on (institution_id, rule_type, scope) among ACTIVE rules.
  Fails if existing data already has duplicate active rules for the same type+scope:
      SELECT institution_id, rule_type, count(*) FROM ips_rules
      WHERE active GROUP BY 1, 2 HAVING count(*) > 1;
* document_chunks: a vector must carry its embedding-space id
  (CHECK embedding IS NULL OR embedding_model IS NOT NULL), so no unlabelled vector can
  enter the table.

Revision ID: 4f1b6c8d2e59
Revises: 3e9a5b2c7d48
Create Date: 2026-11-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "4f1b6c8d2e59"
down_revision: Union[str, Sequence[str], None] = "3e9a5b2c7d48"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("ips_rules", sa.Column("scope", sa.String(100), nullable=True))
    op.execute(
        "CREATE UNIQUE INDEX uq_ips_rules_active_type_scope ON ips_rules "
        "(institution_id, rule_type, COALESCE(scope, '')) WHERE active"
    )
    op.execute(
        "ALTER TABLE ips_rules ADD CONSTRAINT ck_ips_rules_liquidity_unscoped "
        "CHECK (rule_type <> 'liquidity_constraint' OR scope IS NULL)"
    )
    op.execute(
        "ALTER TABLE document_chunks ADD CONSTRAINT ck_document_chunks_vector_provenance "
        "CHECK (embedding IS NULL OR embedding_model IS NOT NULL)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE document_chunks DROP CONSTRAINT IF EXISTS ck_document_chunks_vector_provenance")
    op.execute("ALTER TABLE ips_rules DROP CONSTRAINT IF EXISTS ck_ips_rules_liquidity_unscoped")
    op.execute("DROP INDEX IF EXISTS uq_ips_rules_active_type_scope")
    op.drop_column("ips_rules", "scope")
