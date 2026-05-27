"""add_file_path_and_performance_indexes

Adds:
  - research_reports.file_path  — stable file reference (local path or Vercel Blob URL)
  - Composite indexes for common compliance query patterns

NOTE: The HNSW vector index on document_chunks.embedding is NOT created here
because pgvector's HNSW support (>= 0.5.0) may not be present in all
environments (e.g., CI uses a locked Docker image). Run this once on a
production database with pgvector >= 0.5.0:

    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_chunks_embedding_hnsw
    ON document_chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

Revision ID: a3f9b1c2d4e5
Revises: b147efed605a
Create Date: 2026-05-27 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a3f9b1c2d4e5"
down_revision: Union[str, Sequence[str], None] = "b147efed605a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # file_path — Vercel Blob URL in production, local filesystem path in dev.
    # Cleared to NULL after the file has been ingested and deleted.
    op.add_column(
        "research_reports",
        sa.Column("file_path", sa.String(), nullable=True),
    )

    # Composite indexes for common compliance query patterns
    op.create_index(
        "idx_governance_events_portfolio_resolved",
        "governance_events",
        ["portfolio_id", "resolved"],
    )
    op.create_index(
        "idx_research_reports_institution_created",
        "research_reports",
        ["institution_id", "created_at"],
    )
    op.create_index(
        "idx_research_reports_status",
        "research_reports",
        ["status"],
    )
    op.create_index(
        "idx_holdings_portfolio_id",
        "holdings",
        ["portfolio_id"],
    )
    op.create_index(
        "idx_ips_rules_institution_active",
        "ips_rules",
        ["institution_id", "active"],
    )


def downgrade() -> None:
    op.drop_index("idx_ips_rules_institution_active", table_name="ips_rules")
    op.drop_index("idx_holdings_portfolio_id", table_name="holdings")
    op.drop_index("idx_research_reports_status", table_name="research_reports")
    op.drop_index("idx_research_reports_institution_created", table_name="research_reports")
    op.drop_index("idx_governance_events_portfolio_resolved", table_name="governance_events")
    op.drop_column("research_reports", "file_path")
