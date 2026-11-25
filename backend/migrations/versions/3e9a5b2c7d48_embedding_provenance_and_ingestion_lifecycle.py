"""embedding_provenance_and_ingestion_lifecycle

Embeddings
* document_chunks.embedding becomes NULLable: chunks are stored (and full-text
  searchable) even when no embedding provider is available.
* document_chunks.embedding_model / embedding_provider record the embedding space.
  Vector search only compares vectors from the active space.
* Existing rows get embedding_model = 'legacy-unknown'. Before this migration the app
  silently substituted SHA-256 hash vectors whenever the provider failed, and the
  configured Hugging Face endpoint (api-inference.huggingface.co) no longer resolves,
  so stored vectors cannot be trusted. They stay full-text searchable but are
  excluded from vector search until re-embedded (scripts/reembed.py).

Ingestion lifecycle (research_reports)
* status: pending -> processing -> processed | failed | duplicate
* attempts, error_message, processing_started_at, processed_at
* app_pending_ingestion_jobs also returns jobs stuck in 'processing' > 15 minutes
  (e.g. a worker crashed), so they can be retried.

Revision ID: 3e9a5b2c7d48
Revises: 2c4d8e6f1a37
Create Date: 2026-11-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "3e9a5b2c7d48"
down_revision: Union[str, Sequence[str], None] = "2c4d8e6f1a37"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("document_chunks", "embedding", nullable=True)
    op.add_column("document_chunks", sa.Column("embedding_model", sa.String(128), nullable=True))
    op.add_column("document_chunks", sa.Column("embedding_provider", sa.String(32), nullable=True))
    op.execute("UPDATE document_chunks SET embedding_model = 'legacy-unknown' WHERE embedding IS NOT NULL")
    op.create_index("idx_document_chunks_tenant_model", "document_chunks", ["institution_id", "embedding_model"])

    op.add_column("research_reports", sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("research_reports", sa.Column("error_message", sa.String(500), nullable=True))
    op.add_column("research_reports", sa.Column("processing_started_at", sa.DateTime(), nullable=True))
    op.add_column("research_reports", sa.Column("processed_at", sa.DateTime(), nullable=True))

    op.execute(
        """
        CREATE OR REPLACE FUNCTION app_pending_ingestion_jobs(p_limit integer)
        RETURNS TABLE (report_id uuid, institution_id uuid)
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = public, pg_temp
        AS $$
            SELECT r.id, r.institution_id FROM research_reports r
            WHERE r.file_path IS NOT NULL
              AND (r.status = 'pending'
                   OR (r.status = 'processing'
                       AND r.processing_started_at < TIMEZONE('utc', NOW()) - INTERVAL '15 minutes'))
            ORDER BY r.created_at
            LIMIT LEAST(GREATEST(p_limit, 0), 50)
        $$;
        """
    )


def downgrade() -> None:
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
    for col in ("processed_at", "processing_started_at", "error_message", "attempts"):
        op.drop_column("research_reports", col)
    op.drop_index("idx_document_chunks_tenant_model", table_name="document_chunks")
    op.drop_column("document_chunks", "embedding_provider")
    op.drop_column("document_chunks", "embedding_model")
    # Rows without embeddings cannot satisfy NOT NULL; they must be deleted or re-embedded first.
    op.execute("DELETE FROM document_chunks WHERE embedding IS NULL")
    op.alter_column("document_chunks", "embedding", nullable=False)
