"""Metric and corpus checks. No database and no claim about retrieval quality."""

from app.services.retrieval.metrics import (
    hit_at_k,
    percentile,
    recall_at_k,
    reciprocal_rank_at_k,
    summarize_queries,
)
from evals.corpus import DOCUMENTS, QUERIES, validate_corpus


def test_corpus_labels_are_internally_consistent():
    validate_corpus()
    assert 15 <= len(DOCUMENTS) <= 30
    assert len(QUERIES) >= 40
    categories = {query["category"] for query in QUERIES}
    assert categories == {"exact", "paraphrase", "confusable", "multi", "ambiguous", "unanswerable"}
    assert all(query["text"] and isinstance(query["relevant"], list) for query in QUERIES)


def test_hit_mrr_and_recall_use_ranks_not_scores():
    retrieved = ["a", "b", "a", "c"]
    assert hit_at_k(retrieved, ["c"], 2) == 0.0
    assert hit_at_k(retrieved, ["c"], 3) == 1.0
    assert reciprocal_rank_at_k(retrieved, ["b", "c"], 5) == 0.5
    assert recall_at_k(retrieved, ["b", "c", "z"], 5) == 2 / 3


def test_unanswerable_queries_stay_out_of_the_averages():
    rows = [
        {"relevant": ["a"], "retrieved": ["a"]},
        {"relevant": ["b"], "retrieved": ["z"]},
        {"relevant": [], "retrieved": ["a"]},
        {"relevant": [], "retrieved": []},
    ]
    summary = summarize_queries(rows, k=5)
    assert summary["answerable_count"] == 2
    assert summary["unanswerable_count"] == 2
    assert summary["hit"] == 0.5
    assert summary["unanswerable_returned_any"] == 1
    assert summary["unanswerable_false_return_rate"] == 0.5


def test_percentile_is_linear_and_defined_for_a_single_point():
    assert percentile([10.0], 99) == 10.0
    assert percentile([0.0, 10.0], 50) == 5.0
