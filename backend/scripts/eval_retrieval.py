"""
Compare full-text, vector, and hybrid retrieval on the labeled synthetic corpus.

Labels live in evals/corpus.py and are not adjusted to the scores this script prints.
The default run embeds with the local BGE model. --hash-embeddings is a mechanics
check only: the output is marked semantic_claim=false and must not be quoted as quality.

    cd backend
    export MIGRATION_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:55432/gripper_eval
    export DATABASE_URL=postgresql://gripper_app:gripper_app_test@127.0.0.1:55432/gripper_eval
    python scripts/eval_retrieval.py --replace
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import time
import uuid
from pathlib import Path

BACKEND = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.path.insert(0, BACKEND)
os.environ.setdefault("SECRET_KEY", "cli-placeholder-" + "x" * 32)
os.environ["LLM_PROVIDER"] = "none"
os.environ["LLM_EXTERNAL_PROCESSING_ENABLED"] = "false"

from sqlalchemy import create_engine, text  # noqa: E402

from eval_common import ensure_database, git_revision, require_local_database, upgrade  # noqa: E402


NAMESPACE = uuid.UUID("6ba7b811-9dad-11d1-80b4-00c04fd430c8")
LIMIT = 5
INSTITUTION = uuid.uuid5(NAMESPACE, "institution")


def _parse() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Labeled retrieval comparison. Synthetic documents only.")
    parser.add_argument("--replace", action="store_true", help="Drop and recreate the eval database if it exists.")
    parser.add_argument(
        "--hash-embeddings",
        action="store_true",
        help="Use test hash vectors. The result is not a semantic measurement.",
    )
    parser.add_argument("--out", default="eval_results/retrieval")
    return parser.parse_args()


def _prepare_env(use_hash: bool) -> None:
    if use_hash:
        os.environ["ENVIRONMENT"] = "test"
        os.environ["EMBEDDING_PROVIDER"] = "hash_test"
    else:
        os.environ.setdefault("ENVIRONMENT", "development")
        os.environ["EMBEDDING_PROVIDER"] = "local"


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in values) + "]"


def _load(owner_url: str, runtime_url: str, documents: list[dict], vectors: list[list[float]], space) -> None:
    from app.db.session import make_session_factory, set_tenant

    owner = create_engine(owner_url)
    with owner.begin() as conn:
        conn.execute(text("DELETE FROM institutions WHERE id = :i"), {"i": INSTITUTION})
        conn.execute(
            text("INSERT INTO institutions (id, name, slug, tier, created_at) VALUES (:i, :n, :s, 'free', now())"),
            {"i": INSTITUTION, "n": "Synthetic Eval", "s": "synthetic-eval"},
        )
    owner.dispose()

    factory = make_session_factory(runtime_url)
    with factory() as db:
        set_tenant(db, INSTITUTION)
        for document, vector in zip(documents, vectors):
            report_id = uuid.uuid5(NAMESPACE, "report:" + document["id"])
            chunk_id = uuid.uuid5(NAMESPACE, "chunk:" + document["id"])
            db.execute(
                text(
                    "INSERT INTO research_reports (id, institution_id, sector, company, recommendation, status, created_at) "
                    "VALUES (:r, :i, :sector, :company, 'hold', 'processed', now())"
                ),
                {"r": report_id, "i": INSTITUTION, "sector": document["sector"], "company": document["company"]},
            )
            db.execute(
                text(
                    "INSERT INTO document_chunks (id, institution_id, report_id, content, embedding, embedding_model, "
                    "embedding_provider, metadata_json, created_at) "
                    "VALUES (:c, :i, :r, :t, CAST(:v AS vector), :model, :provider, CAST(:meta AS json), now())"
                ),
                {
                    "c": chunk_id,
                    "i": INSTITUTION,
                    "r": report_id,
                    "t": document["text"],
                    "v": _vector_literal(vector),
                    "model": space.space_id,
                    "provider": space.provider,
                    "meta": json.dumps({"page": 1, "chunk_index": 0, "doc_id": document["id"], "synthetic": True}),
                },
            )
        db.commit()


def _retrieve(runtime_url: str, queries: list[dict]) -> dict[str, list[dict]]:
    from app.db.session import database_role_report, make_session_factory, set_tenant
    from app.services.retrieval.gating import split_explanation_evidence
    from app.services.retrieval.searcher import full_text_leg, full_text_statement, hybrid_search, vector_leg

    factory = make_session_factory(runtime_url)
    modes: dict[str, list[dict]] = {name: [] for name in (
        "original_full_text", "full_text", "exact_vector", "vector", "hybrid", "gated_hybrid"
    )}
    with factory() as db:
        if database_role_report(db.connection())["problems"]:
            raise SystemExit("Evaluation requires a restricted runtime role")
        set_tenant(db, INSTITUTION)
        for query in queries:
            text_rows = full_text_leg(db, query["text"], INSTITUTION, LIMIT)
            vector_rows, degraded, _info, _embedding = vector_leg(db, query["text"], INSTITUTION, LIMIT)
            if degraded:
                raise SystemExit(f"Vector leg degraded: {degraded}")
            hybrid = hybrid_search(db, query["text"], INSTITUTION, limit=LIMIT)
            original = [{"chunk_id": str(row[0].id)} for row in db.execute(
                full_text_statement(INSTITUTION, query["text"], LIMIT)
            )]
            exact = [{"chunk_id": str(row[0])} for row in db.execute(text("""
                WITH eligible AS MATERIALIZED (
                    SELECT c.id,c.embedding FROM document_chunks c
                    JOIN research_reports r ON r.id=c.report_id AND r.institution_id=c.institution_id
                    WHERE c.institution_id=:tenant AND c.embedding_model=:space
                      AND c.embedding IS NOT NULL AND r.status='processed'
                ) SELECT id FROM eligible
                ORDER BY embedding <=> CAST(:v AS vector), id LIMIT :lim
            """), {"tenant": INSTITUTION, "space": f"{_info['model']}@{_info['dimension']}",
                   "v": "[" + ",".join(map(str, _embedding)) + "]", "lim": LIMIT})]
            accepted, rejected = split_explanation_evidence(hybrid.results, provider=_info["provider"])
            packed = {"original_full_text": original, "full_text": text_rows,
                      "exact_vector": exact, "vector": vector_rows,
                      "hybrid": hybrid.results, "gated_hybrid": accepted}
            for mode, rows in packed.items():
                modes[mode].append({
                    "query_id": query["id"],
                    "category": query["category"],
                    "relevant": list(query["relevant"]),
                    "retrieved_chunks": [row["chunk_id"] for row in rows],
                    "rejected_chunks": [row["chunk_id"] for row in rejected] if mode == "gated_hybrid" else [],
                })
    return modes


def _with_doc_ids(modes: dict[str, list[dict]], documents: list[dict]) -> dict[str, list[dict]]:
    mapping = {str(uuid.uuid5(NAMESPACE, "chunk:" + doc["id"])): doc["id"] for doc in documents}
    for rows in modes.values():
        for row in rows:
            row["retrieved"] = [mapping.get(chunk_id, chunk_id) for chunk_id in row["retrieved_chunks"]]
    return modes


def _markdown(payload: dict) -> str:
    semantic = payload["semantic_claim"]
    lines = [
        "# Retrieval evaluation",
        "",
        "Synthetic corpus. Relevance labels were written before this run and were not changed to match it.",
        "",
        f"- Semantic claim: **{'yes' if semantic else 'no'}**.",
    ]
    if not semantic:
        lines.append("- These figures use hash embeddings. They measure the harness, not meaning.")
    lines += [
        f"- Embedding: `{payload['embedding']['provider']}` / `{payload['embedding']['model']}` ({payload['embedding']['dimension']}-d).",
        f"- Documents: {payload['document_count']}. Queries: {payload['query_count']}. Limit: {payload['limit']}.",
        f"- Hybrid candidate window: {payload['hybrid_candidate_window']} per leg, then fused to {payload['limit']}. Product explanations request 3.",
        f"- Commit: `{payload['git_revision']}`.",
        "",
        "| Mode | Hit@5 | MRR@5 | Recall@5 | Unanswerable queries that still returned a row |",
        "|---|---:|---:|---:|---:|",
    ]
    for mode, summary in payload["summary"].items():
        lines.append(
            "| {mode} | {hit:.3f} | {mrr:.3f} | {recall:.3f} | {false}/{unans} |".format(
                mode=mode,
                hit=summary["hit"],
                mrr=summary["mrr"],
                recall=summary["recall"],
                false=summary["unanswerable_returned_any"],
                unans=summary["unanswerable_count"],
            )
        )
    lines += [
        "",
        "Hit, MRR, and Recall use only queries that have at least one relevant document. "
        "Unanswerable queries are the last column. Vector search has no similarity floor, so a high false-return rate there is expected.",
        "",
        "## By category (Hit@5)",
        "",
        "| Category | " + " | ".join(payload["summary"]) + " | Queries |",
        "|---|" + "---:|" * (len(payload["summary"]) + 1),
    ]
    for category, counts in payload["by_category"].items():
        if not counts["n"]:
            continue
        lines.append(
            f"| {category} | " + " | ".join(f"{counts[mode]:.3f}" for mode in payload["summary"]) + f" | {counts['n']} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    args = _parse()
    out = Path(BACKEND) / args.out
    if out.with_suffix(".json").exists() or out.with_suffix(".md").exists():
        raise SystemExit("Output exists; choose a new --out to preserve previous results.")
    _prepare_env(args.hash_embeddings)
    # Settings read the environment at import.
    from app.services.embeddings.generator import generate_embeddings
    from app.services.retrieval.metrics import hit_at_k, summarize_queries
    from evals.corpus import DOCUMENTS, QUERIES, validate_corpus

    validate_corpus()
    admin = os.environ.get("MIGRATION_DATABASE_URL") or ""
    runtime = os.environ.get("DATABASE_URL") or ""
    if not admin or not runtime:
        sys.exit("MIGRATION_DATABASE_URL and DATABASE_URL are required.")
    admin = ensure_database(admin, args.replace)
    require_local_database(runtime, "DATABASE_URL")
    upgrade(admin)

    started = time.perf_counter()
    vectors, space = generate_embeddings([doc["text"] for doc in DOCUMENTS])
    embed_seconds = time.perf_counter() - started
    _load(admin, runtime, DOCUMENTS, vectors, space)
    modes = _with_doc_ids(_retrieve(runtime, QUERIES), DOCUMENTS)

    by_category: dict[str, dict] = {}
    for category in sorted({query["category"] for query in QUERIES}):
        subset = {
            mode: [row for row in rows if row["category"] == category and row["relevant"]]
            for mode, rows in modes.items()
        }
        n = len(next(iter(subset.values())))
        by_category[category] = {
            "n": n,
            **{mode: (sum(hit_at_k(row["retrieved"], row["relevant"], LIMIT) for row in rows) / n if n else None) for mode, rows in subset.items()},
        }

    payload = {
        "synthetic": True,
        "semantic_claim": space.provider in ("local", "hf_api"),
        "label_source": "evals/corpus.py, assigned before this run",
        "embedding": space.public(),
        "embed_seconds": round(embed_seconds, 3),
        "document_count": len(DOCUMENTS),
        "query_count": len(QUERIES),
        "limit": LIMIT,
        "hybrid_candidate_window": LIMIT * 3,
        "rrf_k": 60,
        "git_revision": git_revision(),
        "platform": platform.platform(),
        "summary": {mode: {**summarize_queries(rows, LIMIT),
                           "hit_at_1": summarize_queries(rows, 1)["hit"]} for mode, rows in modes.items()},
        "by_category": by_category,
        "queries": modes,
    }
    out = Path(args.out)
    if not out.is_absolute():
        out = Path(BACKEND) / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".json").write_text(json.dumps(payload, indent=2) + "\n")
    out.with_suffix(".md").write_text(_markdown(payload))
    print(out.with_suffix(".md").read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
