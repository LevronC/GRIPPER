"""
Retrieval metrics for a labeled query set.

Hit@k, MRR@k, and Recall@k are computed from document ids, not from retriever
scores. Queries with an empty relevant set are unanswerable: they are reported
separately and are not folded into the answerable averages. A vector search
with no similarity floor will usually return neighbors for those queries; that
is a measured false-return rate, not an accuracy number.
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Sequence


def _top(retrieved: Sequence[str], k: int) -> list[str]:
    if k < 0:
        raise ValueError("k must be >= 0")
    seen: list[str] = []
    for item in retrieved:
        if item not in seen:
            seen.append(item)
        if len(seen) == k:
            break
    return seen


def hit_at_k(retrieved: Sequence[str], relevant: Iterable[str], k: int) -> float:
    """1 when any relevant id is inside the first k distinct results, else 0."""
    needed = set(relevant)
    if not needed:
        raise ValueError("hit_at_k is undefined for an unanswerable query")
    return 1.0 if needed.intersection(_top(retrieved, k)) else 0.0


def reciprocal_rank_at_k(retrieved: Sequence[str], relevant: Iterable[str], k: int) -> float:
    """1/rank of the first relevant id inside k, else 0. Rank is 1-indexed."""
    needed = set(relevant)
    if not needed:
        raise ValueError("reciprocal_rank_at_k is undefined for an unanswerable query")
    for rank, item in enumerate(_top(retrieved, k), start=1):
        if item in needed:
            return 1.0 / rank
    return 0.0


def recall_at_k(retrieved: Sequence[str], relevant: Iterable[str], k: int) -> float:
    """|relevant ∩ top k| / |relevant|. Undefined when nothing is relevant."""
    needed = set(relevant)
    if not needed:
        raise ValueError("recall_at_k is undefined for an unanswerable query")
    return len(needed.intersection(_top(retrieved, k))) / len(needed)


def percentile(values: Sequence[float], p: float) -> float | None:
    """
    Linear-interpolation percentile, matching NumPy's default.

    With a small sample the upper tail is only a few points. p99 of 200 values
    is interpolated between the two slowest observations and moves if either changes.
    """
    if not values:
        return None
    if not 0 <= p <= 100:
        raise ValueError("p must be between 0 and 100")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * (p / 100.0)
    lo = math.floor(rank)
    hi = math.ceil(rank)
    if lo == hi:
        return ordered[lo]
    weight = rank - lo
    return ordered[lo] * (1.0 - weight) + ordered[hi] * weight


def summarize_queries(rows: Sequence[dict[str, Any]], k: int = 5) -> dict[str, Any]:
    """
    `rows` items need: query_id, relevant (list of doc ids), retrieved (list of doc ids).
    """
    answerable = [row for row in rows if row["relevant"]]
    unanswerable = [row for row in rows if not row["relevant"]]

    def _mean(name: str) -> float | None:
        if not answerable:
            return None
        total = 0.0
        for row in answerable:
            if name == "hit":
                total += hit_at_k(row["retrieved"], row["relevant"], k)
            elif name == "mrr":
                total += reciprocal_rank_at_k(row["retrieved"], row["relevant"], k)
            else:
                total += recall_at_k(row["retrieved"], row["relevant"], k)
        return total / len(answerable)

    returned = sum(1 for row in unanswerable if row["retrieved"][:k])
    return {
        "k": k,
        "query_count": len(rows),
        "answerable_count": len(answerable),
        "unanswerable_count": len(unanswerable),
        "hit": _mean("hit"),
        "mrr": _mean("mrr"),
        "recall": _mean("recall"),
        "unanswerable_returned_any": returned,
        "unanswerable_false_return_rate": (returned / len(unanswerable)) if unanswerable else None,
    }
