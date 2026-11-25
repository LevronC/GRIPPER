"""Search SQL boundary tests against the restricted runtime database role."""
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db.session import SessionLocal, database_role_report, set_tenant
from app.services.embeddings.generator import _hash_embed
from app.services.retrieval.searcher import full_text_leg, hybrid_search, vector_leg

pytestmark = pytest.mark.integration
QUERY = "Semiconductor liquidity risk"


def _literal():
    return "[" + ",".join(map(str, _hash_embed(QUERY))) + "]"


@pytest.mark.parametrize("tenant_index", ["a", "b"])
def test_sql_functions_isolate_each_tenant(two_tenants, tenant_index):
    tenant = getattr(two_tenants, tenant_index)
    with SessionLocal() as db:
        set_tenant(db, tenant.institution_id)
        for sql, params in (
            ("SELECT * FROM app_search_full_text(:q, 10)", {"q": QUERY}),
            ("SELECT * FROM app_search_vector(CAST(:v AS vector), :space, 10)",
             {"v": _literal(), "space": "hash-test-v1@384"}),
        ):
            rows = db.execute(text(sql), params).all()
            assert {row.chunk_id for row in rows} == {tenant.chunk_id}
            assert {row.report_id for row in rows} == {tenant.report_id}


def test_sql_functions_fail_closed_without_tenant(two_tenants):
    with SessionLocal() as db:
        assert db.execute(text("SELECT * FROM app_search_full_text(:q, 10)"), {"q": QUERY}).all() == []
        assert db.execute(text("SELECT * FROM app_search_vector(CAST(:v AS vector), :s, 10)"),
                          {"v": _literal(), "s": "hash-test-v1@384"}).all() == []


@pytest.mark.parametrize("status", ["pending", "processing", "failed", "duplicate"])
def test_unpublished_reports_are_not_searchable(two_tenants, owner_engine, status):
    a = two_tenants.a
    with owner_engine.begin() as conn:
        conn.execute(text("UPDATE research_reports SET status=:status WHERE id=:id"),
                     {"status": status, "id": a.report_id})
    with SessionLocal() as db:
        set_tenant(db, a.institution_id)
        assert full_text_leg(db, QUERY, a.institution_id, 10) == []
        assert vector_leg(db, QUERY, a.institution_id, 10)[0] == []


def test_chunk_report_tenant_constraint_rejects_cross_tenant_reference(two_tenants, owner_engine):
    a, b = two_tenants.a, two_tenants.b
    chunk_id = uuid.uuid4()
    insert = text(
        "INSERT INTO document_chunks (id,institution_id,report_id,content,embedding,embedding_model) "
        "VALUES (:id,:tenant,:report,:q,CAST(:v AS vector),'hash-test-v1@384')"
    )
    params = {"id": chunk_id, "tenant": a.institution_id, "report": b.report_id,
              "q": QUERY, "v": _literal()}
    with owner_engine.begin() as conn:
        # Use the owner so this proves the constraint, independently of RLS.
        # The nested context rolls back before the exception is inspected.
        with pytest.raises(IntegrityError) as rejected:
            with conn.begin_nested():
                conn.execute(insert, params)
        assert rejected.value.orig.pgcode == "23503"
        assert rejected.value.orig.diag.constraint_name == "fk_document_chunks_report_tenant"
        assert conn.execute(text("SELECT count(*) FROM document_chunks WHERE id=:id"),
                            {"id": chunk_id}).scalar_one() == 0
        # Positive control in the same recovered transaction: changing only the
        # report to one in the chunk's institution makes the relationship valid.
        conn.execute(insert, {**params, "report": a.report_id})
        row = conn.execute(text("SELECT institution_id,report_id FROM document_chunks WHERE id=:id"),
                           {"id": chunk_id}).one()
        assert tuple(row) == (a.institution_id, a.report_id)


@pytest.mark.parametrize("tenant_index", ["a", "b"])
def test_valid_research_isolated_across_all_retrieval_modes(two_tenants, owner_engine, tenant_index):
    import json

    tenants = {"a": two_tenants.a, "b": two_tenants.b}
    tenant = tenants[tenant_index]
    with owner_engine.begin() as conn:
        for index, (key, item) in enumerate(tenants.items(), start=1):
            conn.execute(text("UPDATE document_chunks SET metadata_json=CAST(:meta AS json) WHERE id=:id"),
                         {"id": item.chunk_id, "meta": json.dumps({"page": index * 10, "chunk_index": index})})
            conn.execute(text("UPDATE research_reports SET company=:company,sector=:sector WHERE id=:id"),
                         {"id": item.report_id, "company": f"Private company {key}", "sector": f"Sector {key}"})
    expected_index = 1 if tenant_index == "a" else 2
    with SessionLocal() as db:
        assert database_role_report(db.connection())["problems"] == []
        set_tenant(db, tenant.institution_id)
        expected_content = db.execute(text("SELECT content FROM document_chunks WHERE id=:id"),
                                      {"id": tenant.chunk_id}).scalar_one()
        modes = {
            "full_text": full_text_leg(db, QUERY, tenant.institution_id, 10),
            "vector": vector_leg(db, QUERY, tenant.institution_id, 10)[0],
            "hybrid": hybrid_search(db, QUERY, tenant.institution_id, 10).results,
        }
        for mode, rows in modes.items():
            assert len(rows) == 1, mode
            row = rows[0]
            assert row["chunk_id"] == str(tenant.chunk_id), mode
            assert row["report_id"] == str(tenant.report_id), mode
            assert row["content"] == expected_content, mode
            assert row["company"] == f"Private company {tenant_index}", mode
            assert row["sector"] == f"Sector {tenant_index}", mode
            assert row["page"] == expected_index * 10, mode
            assert row["chunk_index"] == expected_index, mode


def test_index_definitions_and_generated_column(owner_engine):
    with owner_engine.connect() as conn:
        indexes = dict(conn.execute(text(
            "SELECT indexname,indexdef FROM pg_indexes WHERE tablename='document_chunks'"
        )).all())
        assert "vector_cosine_ops" in indexes["ix_document_chunks_embedding_hnsw"]
        assert "USING gin (search_vector)" in indexes["ix_document_chunks_search_vector"]
        generated = conn.execute(text(
            "SELECT is_generated FROM information_schema.columns WHERE table_schema='public' "
            "AND table_name='document_chunks' AND column_name='search_vector'"
        )).scalar_one()
        assert generated == "ALWAYS"
        public_grants = conn.execute(text(
            "SELECT count(*) FROM pg_proc p, LATERAL aclexplode(p.proacl) acl "
            "WHERE p.proname IN ('app_search_vector','app_search_full_text') "
            "AND acl.grantee=0 AND acl.privilege_type='EXECUTE'"
        )).scalar_one()
        assert public_grants == 0
