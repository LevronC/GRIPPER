"""add_file_path_and_performance_indexes

Adds:
  - research_reports.file_path  — stable file reference (local path or Vercel Blob URL)
  - HNSW index on document_chunks.embedding  — O(log n) approximate nearest neighbor
  - Composite indexes for common compliance query patterns

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
    # ── file_path on research_reports ─────────────────────────────────────────
    # Nullable TEXT — set to a Vercel Blob URL on Vercel, local filesystem path
    # in development. Cleared to NULL after the file has been ingested and deleted.
    op.add_column(
        "research_reports",
        sa.Column("file_path", sa.String(), nullable=True),
    )

    # ── pgvector HNSW index ───────────────────────────────────────────────────
    # Reduces semantic search from O(n) full-table-scan to O(log n) approximate
    # nearest neighbor. m=16, ef_construction=64 are well-tuned defaults for
    # datasets up to ~500K vectors.
    #
    # NOTE: This cannot run inside a transaction block (Alembic default).
    # If you run this migration on a live production database with existing data,
    # execute it manually with CONCURRENTLY to avoid table locks:
    #   CREATE INDEX CONCURRENTLY idx_chunks_embedding_hnsw ON document_chunks
    #   USING hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=64);
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_chunks_embedding_hnsw
        ON document_chunks
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64);
    """)

    # ── Composite indexes for compliance query patterns ────────────────────────
    # Violations lookup: WHERE portfolio_id = ? AND resolved = ?
    op.create_index(
        "idx_governance_events_portfolio_resolved",
        "governance_events",
        ["portfolio_id", "resolved"],
    )

    # Document listing: WHERE institution_id = ? ORDER BY created_at DESC
    op.create_index(
        "idx_research_reports_institution_created",
        "research_reports",
        ["institution_id", "created_at"],
    )

    # Pending ingestion jobs: WHERE status = 'pending' AND file_path IS NOT NULL
    op.create_index(
        "idx_research_reports_status",
        "research_reports",
        ["status"],
    )

    # Holdings per portfolio
    op.create_index(
        "idx_holdings_portfolio_id",
        "holdings",
        ["portfolio_id"],
    )

    # Active IPS rules per institution
    op.create_index(
        "idx_ips_rules_institution_active",
        "ips_rules",
        ["institution_id", "active"],
    )


def downgrade() -> None:
    op.drop_index("idx_ips_rules_institution_active", "ips_rules")
    op.drop_index("idx_holdings_portfolio_id", "holdings")
    op.drop_index("idx_research_reports_status", "research_reports")
    op.drop_index("idx_research_reports_institution_created", "research_reports")
    op.drop_index("idx_governance_events_portfolio_resolved", "governance_events")
    op.execute("DROP INDEX IF EXISTS idx_chunks_embedding_hnsw;")
    op.drop_column("research_reports", "file_path")
