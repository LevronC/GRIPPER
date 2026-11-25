"""search indexes and tenant-scoped retrieval functions

The runtime role is subject to row-level security. The full-text ``@@`` operator
and pgvector ``<=>`` may be constrained by RLS security-barrier planning. The
inherited measurements show scans; the exact cause and optimized plan must be
verified on the target PostgreSQL version. These functions are SECURITY DEFINER and owned by the migration role,
which bypasses row-level security the same way the existing lookup functions do.
Each function still requires the session institution id and returns no rows when
that setting is missing.

HNSW uses cosine ops because retrieval orders by cosine distance. ef_search starts
at the pgvector default of 40. Exact-versus-approximate recall and actual HNSW
selection still require reproducible verification; index existence does not
establish index use. strict_order preserves distance order among visited results,
not exact nearest-neighbor completeness.

Revision ID: e7c4b2a91d08
Revises: c8e2a14f6b30
Create Date: 2026-11-25
"""
from typing import Sequence, Union

from alembic import op

revision: str = "e7c4b2a91d08"
down_revision: Union[str, Sequence[str], None] = "c8e2a14f6b30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_FUNCTIONS = (
    "app_search_full_text(text, integer)",
    "app_search_vector(vector, text, integer)",
)


def upgrade() -> None:
    op.execute("SET LOCAL maintenance_work_mem = '256MB'")
    # Serial index builds. A parallel HNSW build places its graph in dynamic shared
    # memory sized from maintenance_work_mem (~253MB here); Docker's default 64MB
    # /dev/shm rejects that on a populated table ("could not resize shared memory
    # segment"). Serial builds use backend-local memory. Transaction-scoped only.
    op.execute("SET LOCAL max_parallel_maintenance_workers = 0")
    op.execute(
        "ALTER TABLE document_chunks ADD COLUMN search_vector tsvector "
        "GENERATED ALWAYS AS (to_tsvector('english', content)) STORED"
    )
    op.execute("CREATE INDEX ix_document_chunks_search_vector ON document_chunks USING gin (search_vector)")
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_content_gin")
    op.execute(
        "CREATE INDEX ix_document_chunks_embedding_hnsw ON document_chunks "
        "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"
    )
    op.execute(
        """
        CREATE FUNCTION app_search_full_text(p_query text, p_limit integer)
        RETURNS TABLE (
            chunk_id uuid,
            report_id uuid,
            company character varying,
            sector character varying,
            content text,
            metadata_json json,
            score double precision
        )
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = public, pg_temp
        AS $$
            SELECT c.id, c.report_id, r.company, r.sector, c.content::text, c.metadata_json,
                   ts_rank(c.search_vector, plainto_tsquery('english', p_query))::float8
            FROM document_chunks c
            JOIN research_reports r ON r.id = c.report_id
            WHERE c.institution_id = NULLIF(current_setting('app.current_institution_id', true), '')::uuid
              AND c.search_vector @@ plainto_tsquery('english', p_query)
            ORDER BY ts_rank(c.search_vector, plainto_tsquery('english', p_query)) DESC, c.id
            LIMIT LEAST(GREATEST(COALESCE(p_limit, 0), 0), 100)
        $$;
        """
    )
    op.execute(
        """
        CREATE FUNCTION app_search_vector(p_embedding vector, p_space text, p_limit integer)
        RETURNS TABLE (
            chunk_id uuid,
            report_id uuid,
            company character varying,
            sector character varying,
            content text,
            metadata_json json,
            score double precision
        )
        LANGUAGE plpgsql
        STABLE
        SECURITY DEFINER
        SET search_path = public, pg_temp
        AS $$
        DECLARE
            lim integer := LEAST(GREATEST(COALESCE(p_limit, 0), 0), 100);
        BEGIN
            PERFORM set_config('hnsw.iterative_scan', 'strict_order', true);
            PERFORM set_config('hnsw.ef_search', '40', true);
            RETURN QUERY
            SELECT c.id, c.report_id, r.company, r.sector, c.content::text, c.metadata_json,
                   (c.embedding <=> p_embedding)::float8
            FROM document_chunks c
            JOIN research_reports r ON r.id = c.report_id
            WHERE c.institution_id = NULLIF(current_setting('app.current_institution_id', true), '')::uuid
              AND c.embedding IS NOT NULL
              AND c.embedding_model = p_space
            ORDER BY c.embedding <=> p_embedding, c.id
            LIMIT lim;
        END;
        $$;
        """
    )
    for name in _FUNCTIONS:
        op.execute(f"REVOKE ALL ON FUNCTION {name} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {name} TO gripper_runtime")


def downgrade() -> None:
    for name in _FUNCTIONS:
        op.execute(f"DROP FUNCTION IF EXISTS {name}")
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding_hnsw")
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_search_vector")
    op.execute("ALTER TABLE document_chunks DROP COLUMN IF EXISTS search_vector")
    op.execute(
        "CREATE INDEX ix_document_chunks_content_gin ON document_chunks "
        "USING gin (to_tsvector('english', content))"
    )
