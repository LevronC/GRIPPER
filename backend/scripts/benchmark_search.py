"""
Latency of hybrid search on a synthetic corpus. This does not measure relevance.

Embeddings are hash_test vectors, which have no semantic meaning. The HNSW index is
not created here; the plan records whatever indexes already exist.

    cd backend
    export MIGRATION_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:55432/gripper_bench
    export DATABASE_URL=postgresql://gripper_app:gripper_app_test@127.0.0.1:55432/gripper_bench
    python scripts/benchmark_search.py --chunks 10000 --queries 200 --seed 42 --replace
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import random
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BACKEND = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.path.insert(0, BACKEND)
os.environ.setdefault("SECRET_KEY", "cli-placeholder-" + "x" * 32)
os.environ["ENVIRONMENT"] = "test"
os.environ["EMBEDDING_PROVIDER"] = "hash_test"
os.environ["LLM_PROVIDER"] = "none"
os.environ["LLM_EXTERNAL_PROCESSING_ENABLED"] = "false"

from sqlalchemy import create_engine, text  # noqa: E402

from eval_common import ensure_database, git_revision, require_local_database, upgrade  # noqa: E402

NAMESPACE = uuid.UUID("6ba7b812-9dad-11d1-80b4-00c04fd430c8")
VOCAB = (
    "alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima "
    "mike november oscar papa quebec romeo sierra tango uniform victor whiskey"
).split()
SECTORS = ("Technology", "Energy", "Healthcare", "Financials", "Industrials")


def _parse() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Search latency benchmark. Synthetic rows, hash embeddings.")
    parser.add_argument("--chunks", type=int, default=10_000)
    parser.add_argument("--queries", type=int, default=200)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--warmup", type=int, default=20)
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--out", default="eval_results/benchmark")
    return parser.parse_args()


def _literal(values: list[float]) -> str:
    return "[" + ",".join(f"{value:.6f}" for value in values) + "]"


def _stats(samples: list[float]) -> dict:
    from app.services.retrieval.metrics import percentile

    if not samples:
        return {"n": 0}
    return {
        "n": len(samples),
        "mean_ms": sum(samples) / len(samples) * 1000,
        "p50_ms": percentile(samples, 50) * 1000,
        "p95_ms": percentile(samples, 95) * 1000,
        "p99_ms": percentile(samples, 99) * 1000,
        "min_ms": min(samples) * 1000,
        "max_ms": max(samples) * 1000,
    }


def _queries(count: int, seed: int) -> list[str]:
    rng = random.Random(seed)
    return [" ".join(rng.choice(VOCAB) for _ in range(4)) for _ in range(count)]


def _load(owner_url: str, runtime_url: str, chunks: int, seed: int, tenant_number: int = 0) -> uuid.UUID:
    from app.db.session import make_session_factory, set_tenant
    from app.services.embeddings.generator import _hash_embed, active_space

    space = active_space()
    if space is None or space.provider != "hash_test":
        raise SystemExit("benchmark requires EMBEDDING_PROVIDER=hash_test")
    namespace = NAMESPACE if tenant_number == 0 else uuid.uuid5(NAMESPACE, f"tenant:{tenant_number}")
    institution = uuid.uuid5(namespace, "institution")
    owner = create_engine(owner_url)
    with owner.begin() as conn:
        conn.execute(text("DELETE FROM institutions WHERE id = :i"), {"i": institution})
        conn.execute(
            text("INSERT INTO institutions (id, name, slug, tier, created_at) VALUES (:i, 'Synthetic Bench', :slug, 'free', now())"),
            {"i": institution, "slug": f"synthetic-bench-{tenant_number}"},
        )
    owner.dispose()

    rng = random.Random(seed)
    report_id = uuid.uuid5(namespace, "report")
    factory = make_session_factory(runtime_url)
    with factory() as db:
        set_tenant(db, institution)
        db.execute(
            text(
                "INSERT INTO research_reports (id, institution_id, sector, company, recommendation, status, created_at) "
                "VALUES (:r, :i, 'Mixed', 'Synthetic Bench Co', 'hold', 'processed', now())"
            ),
            {"r": report_id, "i": institution},
        )
        db.commit()
        batch: list[dict] = []
        for index in range(chunks):
            words = [rng.choice(VOCAB) for _ in range(24)]
            content = f"synthetic benchmark chunk {index} sector {SECTORS[index % len(SECTORS)]} " + " ".join(words)
            batch.append({
                "c": uuid.uuid5(namespace, f"chunk:{index}"),
                "i": institution,
                "r": report_id,
                "t": content,
                "v": _literal(_hash_embed(content)),
                "model": space.space_id,
                "meta": json.dumps({"page": 1, "chunk_index": index, "synthetic": True}),
            })
            if len(batch) == 200:
                _insert_batch(db, batch)
                batch = []
        if batch:
            _insert_batch(db, batch)
        db.commit()
    return institution


def _insert_batch(db, rows: list[dict]) -> None:
    from sqlalchemy import text as sql_text

    db.execute(
        sql_text(
            "INSERT INTO document_chunks (id, institution_id, report_id, content, embedding, embedding_model, "
            "embedding_provider, metadata_json, created_at) VALUES (:c, :i, :r, :t, CAST(:v AS vector), :model, "
            "'hash_test', CAST(:meta AS json), now())"
        ),
        rows,
    )


def _time_call(fn) -> tuple[float, object]:
    started = time.perf_counter()
    try:
        value = fn()
        return time.perf_counter() - started, value
    except Exception:
        return time.perf_counter() - started, None


def _plan(db, sql: str, params: dict) -> str:
    result = db.connection().exec_driver_sql("EXPLAIN (ANALYZE, BUFFERS) " + sql, params)
    return "\n".join(str(row[0]) for row in result)


def main() -> int:
    args = _parse()
    if args.chunks < 1 or args.queries < 1 or args.concurrency < 1:
        sys.exit("chunks, queries, and concurrency must be positive")
    admin = ensure_database(os.environ.get("MIGRATION_DATABASE_URL") or "", args.replace)
    runtime = require_local_database(os.environ.get("DATABASE_URL") or "", "DATABASE_URL")
    upgrade(admin)

    from app.db.session import make_session_factory, set_tenant
    from app.services.embeddings.generator import generate_query_embedding
    from app.services.retrieval.searcher import full_text_leg, hybrid_search, vector_leg

    load_started = time.perf_counter()
    institution = _load(admin, runtime, args.chunks, args.seed)
    load_seconds = time.perf_counter() - load_started
    queries = _queries(args.queries, args.seed)
    factory = make_session_factory(runtime)

    # Cold: first call on a new session, before any warmup.
    with factory() as db:
        set_tenant(db, institution)
        cold_e2e, _ = _time_call(lambda: hybrid_search(db, queries[0], institution, limit=5))

    with factory() as db:
        set_tenant(db, institution)
        for query in queries[: args.warmup]:
            hybrid_search(db, query, institution, limit=5)
        e2e: list[float] = []
        failures = 0
        for query in queries:
            elapsed, value = _time_call(lambda query=query: hybrid_search(db, query, institution, limit=5))
            if value is None:
                failures += 1
            else:
                e2e.append(elapsed)

        embedded = [generate_query_embedding(query)[0] for query in queries]
        db_vector: list[float] = []
        db_text: list[float] = []
        for query, vector in zip(queries, embedded):
            elapsed, value = _time_call(lambda query=query, vector=vector: vector_leg(db, query, institution, 5, query_embedding=vector))
            if value is not None and value[1] is None:
                db_vector.append(elapsed)
            else:
                failures += 1
            elapsed, value = _time_call(lambda query=query: full_text_leg(db, query, institution, 5))
            if value is not None:
                db_text.append(elapsed)
            else:
                failures += 1

        sample_vector, _space = generate_query_embedding(queries[0])
        from app.services.embeddings.generator import active_space

        space = active_space()
        # Same filters and order as vector_statement / full_text_statement. The cast is
        # what the ORM adds for the pgvector column; a bare Python list is a numeric[].
        vector_plan = _plan(
            db,
            "SELECT c.id FROM document_chunks c "
            "JOIN research_reports r ON c.report_id = r.id "
            "WHERE c.institution_id = %(i)s AND c.embedding IS NOT NULL AND c.embedding_model = %(m)s "
            "ORDER BY c.embedding <=> CAST(%(v)s AS vector), c.id LIMIT 5",
            {"i": institution, "m": space.space_id, "v": "[" + ",".join(f"{x:.6f}" for x in sample_vector) + "]"},
        )
        text_plan = _plan(
            db,
            "SELECT c.id FROM document_chunks c "
            "JOIN research_reports r ON c.report_id = r.id "
            "WHERE c.institution_id = %(i)s AND to_tsvector('english', c.content) @@ plainto_tsquery('english', %(q)s) "
            "ORDER BY ts_rank(to_tsvector('english', c.content), plainto_tsquery('english', %(q)s)) DESC, c.id LIMIT 5",
            {"i": institution, "q": queries[0]},
        )
        indexes = db.execute(text(
            "SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'document_chunks' ORDER BY indexname"
        )).all()
        versions = db.execute(text("SELECT version(), (SELECT extversion FROM pg_extension WHERE extname = 'vector')")).one()

    errors = []
    lock = threading.Lock()

    def _worker(slice_queries: list[str]) -> list[float]:
        samples: list[float] = []
        with factory() as db:
            set_tenant(db, institution)
            for query in slice_queries:
                elapsed, value = _time_call(lambda query=query: hybrid_search(db, query, institution, limit=5))
                if value is None:
                    with lock:
                        errors.append("hybrid_search failed")
                else:
                    samples.append(elapsed)
        return samples

    width = args.concurrency
    groups = [queries[i::width] for i in range(width)]
    wall_started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=width) as pool:
        concurrent_samples = [sample for group in pool.map(_worker, groups) for sample in group]
    wall = time.perf_counter() - wall_started
    attempted = args.queries
    throughput = len(concurrent_samples) / wall if wall else 0.0

    payload = {
        "synthetic": True,
        "semantic_claim": False,
        "note": "Hash embeddings. Latency only. p99 on a few hundred samples is unstable.",
        "chunks": args.chunks,
        "queries": args.queries,
        "seed": args.seed,
        "limit": 5,
        "warmup_excluded": args.warmup,
        "concurrency": args.concurrency,
        "load_seconds": round(load_seconds, 3),
        "cold_e2e_ms": None if cold_e2e is None else cold_e2e * 1000,
        "warm_end_to_end": _stats(e2e),
        "warm_db_vector": _stats(db_vector),
        "warm_db_full_text": _stats(db_text),
        "concurrent": {
            **_stats(concurrent_samples),
            "wall_seconds": wall,
            "throughput_qps": throughput,
            "errors": len(errors),
            "attempted": attempted,
            "error_rate": len(errors) / attempted if attempted else None,
        },
        "sequential_failures": failures,
        "included_in_end_to_end": "session, hash query embedding, SQL, row mapping",
        "included_in_db": "SQL and row mapping; query embedding is excluded",
        "excluded": "model download, corpus insert, warmup queries",
        "indexes": [{"name": name, "definition": definition} for name, definition in indexes],
        "postgres": versions[0],
        "pgvector": versions[1],
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu_count": os.cpu_count(),
        "git_revision": git_revision(),
        "vector_plan": vector_plan,
        "full_text_plan": text_plan,
    }
    out = Path(args.out)
    if not out.is_absolute():
        out = Path(BACKEND) / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".json").write_text(json.dumps(payload, indent=2) + "\n")
    out.with_suffix(".md").write_text(_markdown(payload))
    print(out.with_suffix(".md").read_text())
    return 0 if not failures and not errors else 1


def _markdown(payload: dict) -> str:
    def row(label: str, stats: dict) -> str:
        if not stats.get("n"):
            return f"| {label} | 0 | | | | |"
        return (
            f"| {label} | {stats['n']} | {stats['mean_ms']:.2f} | {stats['p50_ms']:.2f} | "
            f"{stats['p95_ms']:.2f} | {stats['p99_ms']:.2f} |"
        )

    concurrent = payload["concurrent"]
    lines = [
        "# Search latency",
        "",
        "Synthetic rows and hash embeddings. These numbers are not retrieval quality.",
        "",
        f"- Chunks: {payload['chunks']}. Queries: {payload['queries']}. Seed: {payload['seed']}.",
        f"- End-to-end includes {payload['included_in_end_to_end']}.",
        f"- Database timings include {payload['included_in_db']}.",
        f"- Excluded: {payload['excluded']}.",
        f"- Cold end-to-end (one uncached call): {payload['cold_e2e_ms']:.2f} ms.",
        f"- Concurrent workers: {payload['concurrency']}. Throughput: {concurrent['throughput_qps']:.2f} queries/s. "
        f"Errors: {concurrent['errors']} / {concurrent['attempted']}.",
        f"- Postgres: `{payload['postgres']}`",
        f"- pgvector: `{payload['pgvector']}`",
        f"- Host: {payload['platform']} ({payload['machine']}, {payload['cpu_count']} CPUs).",
        f"- Commit: `{payload['git_revision']}`.",
        "",
        "p99 is interpolated from the slowest points. At this sample size one slow call moves it.",
        "",
        "| Timing | n | mean ms | p50 | p95 | p99 |",
        "|---|---:|---:|---:|---:|---:|",
        row("warm end-to-end", payload["warm_end_to_end"]),
        row("warm vector SQL", payload["warm_db_vector"]),
        row("warm full-text SQL", payload["warm_db_full_text"]),
        row("concurrent end-to-end", concurrent),
        "",
        "## Indexes on document_chunks",
        "",
    ]
    if not payload["indexes"]:
        lines.append("None.")
    for index in payload["indexes"]:
        lines.append(f"- `{index['name']}`: `{index['definition']}`")
    lines += ["", "## Vector plan", "", "```", payload["vector_plan"], "```", "", "## Full-text plan", "", "```", payload["full_text_plan"], "```", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
