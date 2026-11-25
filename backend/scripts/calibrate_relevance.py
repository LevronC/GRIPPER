"""
Choose the explanation cosine cutoff on the calibration split only.

Rule, fixed before looking at scores:
  Sweep 0.20, 0.25, ... 0.80.
  Recall is the fraction of labeled relevant documents whose cosine is at least T.
  False-accept rate is the fraction of non-relevant documents at or above T,
  including every document for a query that has no relevant note.
  Choose the highest T whose calibration recall is at least 0.90.
  If none qualifies, record that and choose the highest T with recall at least 0.80.
  Do not read the held-out split while choosing T. This script scores it once
  after T is chosen, and does not change T.

    cd backend
    EMBEDDING_PROVIDER=local python scripts/calibrate_relevance.py
"""

from __future__ import annotations

import argparse
import hashlib
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

import math  # noqa: E402

from evals.calibration_corpus import DOCUMENTS, QUERIES, validate_calibration_corpus  # noqa: E402


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _scores(doc_vectors: dict[str, list[float]], query_vector: list[float]) -> dict[str, float]:
    return {doc_id: _cosine(vector, query_vector) for doc_id, vector in doc_vectors.items()}


def _rates(queries: list[dict], scored: dict[str, dict[str, float]], threshold: float) -> dict:
    recalls = []
    false_accepts = []
    abstentions = 0
    for query in queries:
        scores = scored[query["id"]]
        relevant = set(query["relevant"])
        accepted = {doc_id for doc_id, score in scores.items() if score >= threshold}
        if relevant:
            recalls.append(len(relevant & accepted) / len(relevant))
        negatives = [doc_id for doc_id in scores if doc_id not in relevant]
        if negatives:
            false_accepts.append(len(set(negatives) & accepted) / len(negatives))
        if not accepted:
            abstentions += 1
    recall = sum(recalls) / len(recalls) if recalls else None
    false_rate = sum(false_accepts) / len(false_accepts) if false_accepts else None
    precision_hits = 0
    precision_total = 0
    for query in queries:
        scores = scored[query["id"]]
        relevant = set(query["relevant"])
        accepted = [doc_id for doc_id, score in scores.items() if score >= threshold]
        precision_total += len(accepted)
        precision_hits += len(relevant & set(accepted))
    precision = precision_hits / precision_total if precision_total else None
    f1 = None
    if precision is not None and recall is not None and precision + recall:
        f1 = 2 * precision * recall / (precision + recall)
    return {
        "threshold": threshold,
        "recall": recall,
        "false_accept_rate": false_rate,
        "precision": precision,
        "f1": f1,
        "abstention_rate": abstentions / len(queries) if queries else None,
    }


def choose(curve: list[dict]) -> tuple[dict, str]:
    eligible = [row for row in curve if row["recall"] is not None and row["recall"] >= 0.90]
    if eligible:
        return max(eligible, key=lambda row: row["threshold"]), "highest T with calibration recall >= 0.90"
    eligible = [row for row in curve if row["recall"] is not None and row["recall"] >= 0.80]
    if eligible:
        return max(eligible, key=lambda row: row["threshold"]), "no T kept recall >= 0.90; highest T with recall >= 0.80"
    best = max(curve, key=lambda row: (row["recall"] or 0, row["threshold"]))
    return best, "neither recall floor was met; highest-recall T is recorded and not treated as a success"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="eval_results/phase4b/calibration_rerun.json")
    args = parser.parse_args()
    validate_calibration_corpus()
    from app.services.embeddings.generator import generate_embeddings, generate_query_embedding

    doc_vectors, space = generate_embeddings([doc["text"] for doc in DOCUMENTS])
    by_id = {doc["id"]: vector for doc, vector in zip(DOCUMENTS, doc_vectors)}
    scored: dict[str, dict[str, float]] = {}
    for query in (q for q in QUERIES if q["split"] == "calibration"):
        vector, _space = generate_query_embedding(query["text"])
        scored[query["id"]] = _scores(by_id, vector)
    thresholds = [round(0.20 + 0.05 * step, 2) for step in range(13)]
    calibration = [query for query in QUERIES if query["split"] == "calibration"]
    heldout = [query for query in QUERIES if query["split"] == "heldout"]
    curve = [_rates(calibration, scored, threshold) for threshold in thresholds]
    chosen, rule = choose(curve)
    # The held-out embeddings/scores are not computed until selection is frozen.
    for query in heldout:
        vector, _space = generate_query_embedding(query["text"])
        scored[query["id"]] = _scores(by_id, vector)
    heldout_result = _rates(heldout, scored, chosen["threshold"])
    payload = {
        "semantic_claim": True,
        "embedding": space.public(),
        "selection_rule": rule,
        "chosen_threshold": chosen["threshold"],
        "calibration_curve": curve,
        "calibration_at_chosen": chosen,
        "heldout_at_chosen": heldout_result,
        "note": "Held-out was scored after T was chosen and was not used to change T.",
        "corpus_sha256": hashlib.sha256(json.dumps([DOCUMENTS, QUERIES], sort_keys=True).encode()).hexdigest(),
        "scores": scored,
    }
    out = Path(BACKEND) / args.out
    if out.exists():
        raise SystemExit("Output already exists; select a new --out path to preserve prior evidence.")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps({"chosen_threshold": chosen["threshold"], "rule": rule, "calibration": chosen, "heldout": heldout_result}, indent=2))
    if not math.isfinite(chosen["threshold"]):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
