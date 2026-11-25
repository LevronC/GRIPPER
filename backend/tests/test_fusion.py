"""Reciprocal Rank Fusion: exact scores and deterministic ordering (pure, no database)."""

from __future__ import annotations

import math
import random
from fractions import Fraction

import pytest

from app.services.retrieval.fusion import reciprocal_rank_fusion as rrf


def docs(*ids):
    return [{"chunk_id": i, "content": f"text {i}"} for i in ids]


def exact(*ranks, k=60):
    return float(sum(Fraction(1, k + r) for r in ranks))


def test_hand_calculated_scores_and_order():
    # vector: a(1) b(2) c(3); text: c(1) d(2) a(3)
    out = rrf(docs("a", "b", "c"), docs("c", "d", "a"), k=60, limit=10)
    got = {d["chunk_id"]: d["rrf_score"] for d in out}
    assert got["a"] == pytest.approx(exact(1, 3), abs=1e-15)   # 1/61 + 1/63
    assert got["c"] == pytest.approx(exact(3, 1), abs=1e-15)   # 1/63 + 1/61 (same as a)
    assert got["b"] == pytest.approx(exact(2), abs=1e-15)
    assert got["d"] == pytest.approx(exact(2), abs=1e-15)
    # a and c tie on score and best rank (1): key order. b and d tie on score and best rank (2): key order.
    assert [d["chunk_id"] for d in out] == ["a", "c", "b", "d"]
    a = out[0]
    assert (a["vector_rank"], a["text_rank"]) == (1, 3)


def test_appearing_in_both_lists_beats_single_list_at_same_rank():
    out = rrf(docs("x", "y"), docs("y"), limit=10)
    assert [d["chunk_id"] for d in out] == ["y", "x"]   # 1/62 + 1/61 > 1/61


def test_vector_only_and_text_only():
    v = rrf(docs("a", "b"), [], limit=10)
    t = rrf([], docs("b", "a"), limit=10)
    assert [d["chunk_id"] for d in v] == ["a", "b"] and all(d["text_rank"] is None for d in v)
    assert [d["chunk_id"] for d in t] == ["b", "a"] and all(d["vector_rank"] is None for d in t)
    assert v[0]["rrf_score"] == t[0]["rrf_score"] == exact(1)


def test_empty_inputs_and_zero_limit():
    assert rrf([], []) == []
    assert rrf(docs("a"), docs("b"), limit=0) == []


def test_duplicates_within_a_list_count_once_at_best_rank():
    out = rrf(docs("a", "b", "a"), [], limit=10)
    assert [d["chunk_id"] for d in out] == ["a", "b"]
    assert out[0]["rrf_score"] == exact(1) and out[0]["vector_rank"] == 1


def test_limit_truncates_after_ordering():
    out = rrf(docs("a", "b", "c", "d"), docs("d"), limit=2)
    # d: 1/64 + 1/61 ≈ 0.0320 > a: 1/61 ≈ 0.0164 > b: 1/62; c is cut by the limit.
    assert [d["chunk_id"] for d in out] == ["d", "a"]


def test_payload_from_vector_list_preferred_and_inputs_not_mutated():
    v = [{"chunk_id": "a", "similarity": 0.9}]
    t = [{"chunk_id": "a", "similarity": 3.2}]
    out = rrf(v, t)
    assert out[0]["similarity"] == 0.9
    assert "rrf_score" not in v[0] and "rrf_score" not in t[0]


def test_k_changes_scores_not_validity():
    assert rrf(docs("a"), [], k=0)[0]["rrf_score"] == 1.0
    assert rrf(docs("a"), [], k=1)[0]["rrf_score"] == 0.5


@pytest.mark.parametrize("kwargs", [
    {"k": -1}, {"k": math.inf}, {"k": math.nan}, {"k": "60"}, {"k": True},
    {"limit": -1}, {"limit": 2.5}, {"limit": True},
])
def test_invalid_parameters(kwargs):
    with pytest.raises(ValueError):
        rrf(docs("a"), docs("b"), **kwargs)


def test_missing_key_raises():
    with pytest.raises(KeyError):
        rrf([{"id": "a"}], [])


def test_deterministic_regardless_of_tie_input_order():
    """Equal-score items order the same way whichever list or position they arrive in."""
    one = rrf(docs("m", "z"), docs("z", "m"), limit=10)
    two = rrf(docs("z", "m"), docs("m", "z"), limit=10)
    assert [d["chunk_id"] for d in one] == [d["chunk_id"] for d in two] == ["m", "z"]


def test_matches_reference_implementation_on_random_inputs():
    """Seeded comparison against a direct Fraction-based implementation of the formula."""
    rng = random.Random(7)
    pool = [f"c{i:02d}" for i in range(30)]
    for _ in range(200):
        v = rng.sample(pool, rng.randint(0, 15))
        t = rng.sample(pool, rng.randint(0, 15))
        k = rng.choice([0, 1, 10, 60])
        limit = rng.randint(0, 20)
        ref = {}
        best = {}
        for lst in (v, t):
            for pos, cid in enumerate(lst, start=1):
                ref[cid] = ref.get(cid, Fraction(0)) + Fraction(1, k + pos)
                best[cid] = min(best.get(cid, pos), pos)
        expected = sorted(ref, key=lambda c: (-ref[c], best[c], c))[:limit]
        out = rrf(docs(*v), docs(*t), k=k, limit=limit)
        assert [d["chunk_id"] for d in out] == expected
        for d in out:
            assert d["rrf_score"] == pytest.approx(float(ref[d["chunk_id"]]), rel=1e-12)
