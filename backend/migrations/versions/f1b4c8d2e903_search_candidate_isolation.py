"""Isolate eligible ANN candidates before deterministic result ordering.

Revision ID: f1b4c8d2e903
Revises: e7c4b2a91d08

Separate revision because the interrupted agent may already have applied e7c4.
The SQL constants are also used by the isolated plan-verification harness.
"""
from alembic import op

revision = "f1b4c8d2e903"
down_revision = "e7c4b2a91d08"
branch_labels = None
depends_on = None

VECTOR_SQL = """
WITH candidates AS MATERIALIZED (
    SELECT c.id, c.report_id, c.content, c.metadata_json,
           c.embedding <=> p_embedding AS distance
    FROM public.document_chunks c
    WHERE c.institution_id = NULLIF(current_setting('app.current_institution_id', true), '')::uuid
      AND c.embedding IS NOT NULL
      AND c.embedding_model = p_space
      AND EXISTS (
          SELECT 1 FROM public.research_reports r
          WHERE r.id = c.report_id AND r.institution_id = c.institution_id
            AND r.status = 'processed'
      )
    ORDER BY c.embedding <=> p_embedding
    LIMIT LEAST(GREATEST(COALESCE(p_limit, 0), 0), 100)
)
SELECT c.id, c.report_id, r.company, r.sector, c.content::text, c.metadata_json,
       c.distance::float8
FROM candidates c JOIN public.research_reports r ON r.id = c.report_id
WHERE r.institution_id = NULLIF(current_setting('app.current_institution_id', true), '')::uuid
ORDER BY c.distance, c.id
"""

TEXT_SQL = """
SELECT c.id, c.report_id, r.company, r.sector, c.content::text, c.metadata_json,
       ts_rank(c.search_vector, plainto_tsquery('english', p_query))::float8
FROM public.document_chunks c
JOIN public.research_reports r ON r.id = c.report_id AND r.institution_id = c.institution_id
WHERE c.institution_id = NULLIF(current_setting('app.current_institution_id', true), '')::uuid
  AND r.status = 'processed'
  AND c.search_vector @@ plainto_tsquery('english', p_query)
ORDER BY ts_rank(c.search_vector, plainto_tsquery('english', p_query)) DESC, c.id
LIMIT LEAST(GREATEST(COALESCE(p_limit, 0), 0), 100)
"""

RETURNS = """RETURNS TABLE (
    chunk_id uuid, report_id uuid, company character varying, sector character varying,
    content text, metadata_json json, score double precision
)"""


def upgrade():
    op.execute(f"""
        CREATE OR REPLACE FUNCTION app_search_vector(p_embedding vector, p_space text, p_limit integer)
        {RETURNS} LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, public, pg_temp
        SET hnsw.iterative_scan = 'strict_order'
        SET hnsw.ef_search = '40'
        AS $query$ {VECTOR_SQL} $query$;
    """)
    op.execute(f"""
        CREATE OR REPLACE FUNCTION app_search_full_text(p_query text, p_limit integer)
        {RETURNS} LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, public, pg_temp
        AS $query$ {TEXT_SQL} $query$;
    """)
    for signature in ("app_search_vector(vector, text, integer)", "app_search_full_text(text, integer)"):
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO gripper_runtime")


def downgrade():
    # Retain the security/visibility checks on rollback to e7c4. The signatures
    # remain compatible. Rolling back e7c4 itself removes these functions.
    pass
