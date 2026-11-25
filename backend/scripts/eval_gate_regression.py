"""
Apply the frozen cosine cutoff to the original Phase 4 corpus.

This does not change the cutoff. It reports what the gate would do to that
historical set. Embeddings are the local BGE model, in memory, not hash vectors.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

BACKEND = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.path.insert(0, BACKEND)
os.environ.setdefault("SECRET_KEY", "cli-placeholder-" + "x" * 32)
os.environ.setdefault("ENVIRONMENT", "development")
os.environ["LLM_PROVIDER"] = "none"
os.environ["EMBEDDING_PROVIDER"] = "local"

from app.services.retrieval.gating import EXPLANATION_MIN_COSINE  # noqa: E402
from app.services.retrieval.metrics import hit_at_k, recall_at_k, reciprocal_rank_at_k  # noqa: E402
from evals.corpus import DOCUMENTS, QUERIES, validate_corpus  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="eval_results/phase4b/gate_recovery.json")
    args = parser.parse_args()
    out = Path(BACKEND) / args.out
    if out.exists():
        raise SystemExit("Output exists; choose a new --out path.")
    validate_corpus()
    from app.services.embeddings.generator import generate_embeddings, generate_query_embedding

    vectors, space = generate_embeddings([doc["text"] for doc in DOCUMENTS])
    by_id = {doc["id"]: vector for doc, vector in zip(DOCUMENTS, vectors)}

    def cosine(a, b):
        return sum(x * y for x, y in zip(a, b))

    rows = []
    for query in QUERIES:
        qv, _space = generate_query_embedding(query["text"])
        ranked = sorted(by_id, key=lambda doc_id: (-cosine(by_id[doc_id], qv), doc_id))
        accepted = [doc_id for doc_id in ranked[:5] if cosine(by_id[doc_id], qv) >= EXPLANATION_MIN_COSINE]
        rows.append({
            "query_id": query["id"],
            "category": query["category"],
            "relevant": list(query["relevant"]),
            "retrieved": ranked[:5],
            "accepted": accepted,
        })
    answerable = [row for row in rows if row["relevant"]]
    unanswerable = [row for row in rows if not row["relevant"]]
    payload = {
        "threshold": EXPLANATION_MIN_COSINE,
        "embedding": space.public(),
        "semantic_claim": True,
        "note": "In-memory exact cosine over the 24 Phase 4 notes, gating top 5 only. Not hybrid SQL and not used to choose the threshold.",
        "ungated_hit_at_5": sum(hit_at_k(row["retrieved"], row["relevant"], 5) for row in answerable) / len(answerable),
        "ungated_hit_at_1": sum(hit_at_k(row["retrieved"], row["relevant"], 1) for row in answerable) / len(answerable),
        "ungated_mrr_at_5": sum(reciprocal_rank_at_k(row["retrieved"], row["relevant"], 5) for row in answerable) / len(answerable),
        "ungated_recall_at_5": sum(recall_at_k(row["retrieved"], row["relevant"], 5) for row in answerable) / len(answerable),
        "gated_hit_at_5": sum(hit_at_k(row["accepted"], row["relevant"], 5) for row in answerable) / len(answerable),
        "gated_recall_of_labeled": sum(recall_at_k(row["accepted"], row["relevant"], len(row["accepted"]) or 1) for row in answerable) / len(answerable),
        "unanswerable_with_any_acceptance": sum(1 for row in unanswerable if row["accepted"]),
        "unanswerable_count": len(unanswerable),
        "queries": rows,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps({k: payload[k] for k in payload if k != "queries"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
