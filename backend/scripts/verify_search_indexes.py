"""Isolated Phase 4B ANN recall, runtime plans, and repeated multi-tenant latency.

Uses synthetic hash vectors, never makes semantic quality claims or LLM calls.
Use --replace only for disposable gripper_bench* / gripper_eval* databases.
The default partitions 50k rows into 90%, 9%, 1% tenants. All search measurements
use the restricted runtime role. Owner access is used for setup and inner-plan
inspection only (SECURITY DEFINER functions run with that owner's privileges).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from benchmark_search import _literal, _load, _queries, _stats
from eval_common import ensure_database, git_revision, require_local_database, upgrade
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


EXACT_SQL = """
WITH eligible AS MATERIALIZED (
    SELECT c.id, c.embedding FROM document_chunks c
    JOIN research_reports r ON r.id = c.report_id AND r.institution_id = c.institution_id
    WHERE c.institution_id = :tenant AND r.status = 'processed'
      AND c.embedding_model = :space AND c.embedding IS NOT NULL
)
SELECT id FROM eligible ORDER BY embedding <=> CAST(:embedding AS vector), id LIMIT 10
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunks", type=int, default=50000)
    parser.add_argument("--queries", type=int, default=200)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--warmup", type=int, default=20)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--measure-index-builds", action="store_true",
                        help="Time REINDEX of populated GIN/HNSW indexes in this disposable database")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    if min(args.queries, args.repeats, args.concurrency) < 1 or args.chunks < 100 or args.warmup < 0:
        parser.error("positive queries/repeats/concurrency, >=100 chunks, and nonnegative warmup required")
    out = Path(args.out)
    if out.exists():
        parser.error("output exists; choose a new path")
    admin = require_local_database(os.environ.get("MIGRATION_DATABASE_URL", ""), "owner")
    runtime = require_local_database(os.environ.get("DATABASE_URL", ""), "runtime")
    a, r = make_url(admin), make_url(runtime)
    if (a.host, a.port, a.database) != (r.host, r.port, r.database):
        parser.error("owner and runtime must point to the same local host/port/database")
    ensure_database(admin, args.replace)
    started = time.perf_counter()
    upgrade(admin)
    migration_seconds = time.perf_counter() - started

    from app.db.session import database_role_report, make_session_factory, set_tenant
    from app.services.embeddings.generator import active_space, generate_query_embedding
    from app.services.retrieval.gating import split_explanation_evidence
    from app.services.retrieval.searcher import full_text_leg, hybrid_search, vector_leg

    factory = make_session_factory(runtime)
    with factory() as db:
        role = database_role_report(db.connection())
        if role["problems"]:
            raise SystemExit("Runtime role fails isolation checks")
    sizes = [args.chunks * 90 // 100, args.chunks * 9 // 100]
    sizes.append(args.chunks - sum(sizes))
    started = time.perf_counter()
    tenants = [_load(admin, runtime, size, args.seed, i) for i, size in enumerate(sizes)]
    load_seconds = time.perf_counter() - started
    owner = create_engine(admin)
    index_builds = []
    if args.measure_index_builds:
        # REINDEX measures a populated rebuild, not initial migration time.
        # Names are fixed, and the database has already passed the local guard.
        for name in ("ix_document_chunks_search_vector", "ix_document_chunks_embedding_hnsw"):
            with owner.begin() as conn:
                conn.execute(text("SET LOCAL maintenance_work_mem = '256MB'"))
                # Serial build: parallel HNSW builds place the graph in dynamic shared
                # memory (/dev/shm), which Docker caps at 64MB by default and which a
                # 50k-chunk graph exceeds. Serial builds use backend-local memory.
                conn.execute(text("SET LOCAL max_parallel_maintenance_workers = 0"))
                started = time.perf_counter()
                conn.execute(text(f"REINDEX INDEX public.{name}"))
                elapsed = time.perf_counter() - started
                size = conn.execute(text("SELECT pg_relation_size(CAST(:name AS regclass))"),
                                    {"name": "public." + name}).scalar_one()
                index_builds.append({"index": name, "rebuild_seconds": elapsed, "bytes": size,
                                     "maintenance_work_mem": "256MB",
                                     "max_parallel_maintenance_workers": 0,
                                     "method": "serial non-concurrent REINDEX on populated synthetic data"})
    with owner.begin() as conn:
        conn.execute(text("ANALYZE document_chunks"))
        conn.execute(text("ANALYZE research_reports"))
        indexes = [dict(row) for row in conn.execute(text(
            "SELECT indexname, indexdef, pg_relation_size(indexname::regclass) AS bytes "
            "FROM pg_indexes WHERE schemaname='public' AND tablename='document_chunks'"
        )).mappings()]
        versions = list(conn.execute(text(
            "SELECT version(), (SELECT extversion FROM pg_extension WHERE extname='vector')"
        )).one())
        settings = [dict(row) for row in conn.execute(text(
            "SELECT name, setting, unit FROM pg_settings WHERE name IN "
            "('shared_buffers','work_mem','maintenance_work_mem','effective_cache_size',"
            "'random_page_cost','max_parallel_workers_per_gather')"
        )).mappings()]
    queries = _queries(args.queries, args.seed)
    space = active_space()
    embedded = [generate_query_embedding(q)[0] for q in queries]

    def call(db, mode, tenant, index):
        q, vec = queries[index], embedded[index]
        if mode == "exact":
            return [str(row[0]) for row in db.execute(text(EXACT_SQL), {
                "tenant": tenant, "space": space.space_id, "embedding": _literal(vec),
            })]
        if mode == "vector":
            rows, degraded, _, _ = vector_leg(db, q, tenant, 10, query_embedding=vec)
            if degraded:
                raise RuntimeError("Unexpected embedding degradation")
            return [row["chunk_id"] for row in rows]
        if mode == "full_text":
            return full_text_leg(db, q, tenant, 5)
        result = hybrid_search(db, q, tenant, limit=5)
        if mode == "gated_hybrid":
            # Hash bypass is explicit; this measures plumbing, not semantic gating quality.
            return split_explanation_evidence(result.results, provider=space.provider)[0]
        return result.results

    def timed(db, mode, tenant, index):
        started = time.perf_counter()
        error = None
        try:
            call(db, mode, tenant, index)
        except Exception as exc:
            error = type(exc).__name__
            db.rollback()
        return {"seconds": time.perf_counter() - started, "error": error}

    def summary(rows):
        errors = sum(row["error"] is not None for row in rows)
        return {**_stats([row["seconds"] for row in rows]), "errors": errors,
                "error_rate": errors / len(rows) if rows else None, "samples": rows}

    results = []
    recall = []
    for tenant, size in zip(tenants, sizes):
        with factory() as db:
            set_tenant(db, tenant)
            for index in range(args.queries):
                exact = call(db, "exact", tenant, index)
                approx = call(db, "vector", tenant, index)
                recall.append({"tenant": str(tenant), "query_index": index,
                               "exact": exact, "approximate": approx,
                               "recall": {str(k): len(set(exact[:k]) & set(approx[:k])) / len(exact[:k])
                                          if exact[:k] else None for k in (1, 5, 10)}})
        for repeat in range(args.repeats):
            for mode in ("exact", "vector", "full_text", "hybrid", "gated_hybrid"):
                with factory() as db:
                    set_tenant(db, tenant)
                    first = timed(db, mode, tenant, 0)
                    for index in range(args.warmup):
                        call(db, mode, tenant, index % args.queries)
                    rows = [timed(db, mode, tenant, i) for i in range(args.queries)]
                results.append({"tenant": str(tenant), "chunks": size, "repeat": repeat,
                                "mode": mode, "first_session_call": first, **summary(rows)})

    def worker(indices):
        rows = []
        with factory() as db:
            for i in indices:
                tenant = tenants[i % len(tenants)]
                set_tenant(db, tenant)
                rows.append(timed(db, "hybrid", tenant, i))
        return rows

    concurrent = []
    for repeat in range(args.repeats):
        started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            rows = [r for batch in pool.map(worker, [range(i, args.queries, args.concurrency)
                                                    for i in range(args.concurrency)]) for r in batch]
        seconds = time.perf_counter() - started
        stats = summary(rows)
        concurrent.append({"repeat": repeat, **stats, "wall_seconds": seconds,
                           "successful_qps": (len(rows) - stats["errors"]) / seconds})

    plans = []
    # Read the installed SQL body instead of maintaining a stale copy of runtime SQL.
    with owner.begin() as conn:
        for tenant in tenants:
            conn.execute(text("SELECT set_config('app.current_institution_id', :tenant, true)"),
                         {"tenant": str(tenant)})
            for signature in ("app_search_vector(vector,text,integer)", "app_search_full_text(text,integer)"):
                source, config = conn.execute(text(
                    "SELECT prosrc, proconfig FROM pg_proc WHERE oid=CAST(:sig AS regprocedure)"
                ), {"sig": signature}).one()
                for setting in config or []:
                    name, value = setting.split("=", 1)
                    conn.execute(text("SELECT set_config(:name, :value, true)"), {"name": name, "value": value})
                sql = source.strip().rstrip(";")
                if not sql.upper().startswith(("SELECT", "WITH")):
                    raise RuntimeError("Expected SQL-language function after latest migration")
                for key in ("p_embedding", "p_space", "p_limit", "p_query"):
                    replacement = "CAST(:embedding AS vector)" if key == "p_embedding" else ":" + key[2:]
                    sql = re.sub(r"\b" + key + r"\b", replacement, sql)
                plan = conn.execute(text("EXPLAIN (ANALYZE, BUFFERS, SETTINGS, FORMAT JSON) " + sql),
                                    {"embedding": _literal(embedded[0]), "space": space.space_id,
                                     "limit": 10, "query": queries[0]}).scalar_one()
                plans.append({"tenant": str(tenant), "function": signature, "source": source,
                              "context": "owner replay of installed SECURITY DEFINER SQL", "plan": plan})
    payload = {"synthetic": True, "semantic_claim": False, "embedding": space.public(),
               "args": vars(args), "git_revision": git_revision(),
               "working_diff_sha256": hashlib.sha256(subprocess.check_output(["git", "diff", "HEAD"])).hexdigest(),
               "python": platform.python_version(), "platform": platform.platform(), "cpu_count": os.cpu_count(),
               "physical_memory_bytes": os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES"),
               "versions": versions, "settings": settings, "indexes": indexes, "index_builds": index_builds,
               "runtime_role": role, "tenant_chunks": dict(zip(map(str, tenants), sizes)),
               "migration_seconds_empty_database_if_replaced": migration_seconds, "load_seconds": load_seconds,
               "timing_scope": "service calls and row mapping; exact/vector exclude query embedding; hybrid includes it",
               "cold_note": "first session call is not a cold database or OS cache measurement",
               "timeout_note": "No configured benchmark deadline; exceptions counted, no inferred timeout rate",
               "recall_note": "ANN overlap against exact vectors; not relevance. Boundary ties can lower overlap.",
               "results": results, "concurrent": concurrent, "recall": recall, "plans": plans}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, default=str) + "\n")
    print(f"Saved {out}; no semantic or API-latency claim.")
    return 1 if any(r["errors"] for r in results + concurrent) else 0


if __name__ == "__main__":
    raise SystemExit(main())
