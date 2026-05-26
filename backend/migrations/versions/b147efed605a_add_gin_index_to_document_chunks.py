"""add_gin_index_to_document_chunks

Revision ID: b147efed605a
Revises: bf09b29f337d
Create Date: 2026-05-26 06:22:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b147efed605a'
down_revision = 'bf09b29f337d'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create GIN index for full-text search on content column
    op.execute(
        "CREATE INDEX ix_document_chunks_content_gin ON document_chunks USING GIN (to_tsvector('english', content))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX ix_document_chunks_content_gin")
