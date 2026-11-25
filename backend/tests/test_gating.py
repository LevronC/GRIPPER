"""Evidence-gate rules. The cutoff number is frozen; these tests check the rule, not the corpus."""

from evals.calibration_corpus import validate_calibration_corpus
import pytest
from app.services.retrieval.gating import (
    EXPLANATION_MIN_COSINE,
    passes_evidence_gate,
    split_explanation_evidence,
)


def test_calibration_topics_do_not_overlap_the_held_out_topics():
    validate_calibration_corpus()


def test_hash_and_keyword_results_are_not_cosine_gated():
    assert passes_evidence_gate(0.01, provider="hash_test")
    assert passes_evidence_gate(None, provider=None)
    assert passes_evidence_gate(None, provider="hash_test")


def test_semantic_gate_uses_the_frozen_cosine_cutoff():
    assert passes_evidence_gate(EXPLANATION_MIN_COSINE, provider="local")
    assert not passes_evidence_gate(EXPLANATION_MIN_COSINE - 0.001, provider="hf_api")
    assert not passes_evidence_gate(None, provider="local")


def test_split_keeps_exploratory_rows_out_of_the_accepted_list():
    rows = [
        {"chunk_id": "high", "cosine_similarity": EXPLANATION_MIN_COSINE + 0.1},
        {"chunk_id": "low", "cosine_similarity": 0.0},
        {"chunk_id": "missing"},
    ]
    accepted, rejected = split_explanation_evidence(rows, provider="local")
    assert [row["chunk_id"] for row in accepted] == ["high"]
    assert [row["chunk_id"] for row in rejected] == ["low", "missing"]


@pytest.mark.parametrize("score", [float("nan"), float("inf"), -float("inf"), True, 1.1])
def test_invalid_cosine_is_not_evidence(score):
    assert not passes_evidence_gate(score, provider="local")
