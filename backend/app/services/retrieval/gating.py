"""
Evidence gate for compliance explanations.

This is not a relevance probability and it is not applied to exploratory search.
Cosine similarity is the pgvector cosine similarity already used for ranking
(1 - cosine distance). The cutoff was chosen on a separate calibration corpus
and then frozen. It is not applied to hash-test vectors: those have no semantic
meaning, and a cutoff measured on BGE would not mean anything for them.

When semantic search is off, keyword results stay available and the explanation
still says their relevance has not been verified.
"""

from __future__ import annotations

import math
from typing import Any

# Frozen 2026-11-25 from scripts/calibrate_relevance.py; see eval_results/phase4b/SUMMARY.md.
# Highest cutoff on the calibration split with recall at least 0.90.
# The held-out split was not used to choose this number.
EXPLANATION_MIN_COSINE = 0.55

SEMANTIC_PROVIDERS = ("local", "hf_api")


def semantic_gate_applies(provider: str | None) -> bool:
    return provider in SEMANTIC_PROVIDERS


def passes_evidence_gate(cosine_similarity: float | None, *, provider: str | None) -> bool:
    """True when this chunk may be shown as explanation evidence."""
    if not semantic_gate_applies(provider):
        return True
    if cosine_similarity is None or isinstance(cosine_similarity, bool):
        return False
    return math.isfinite(cosine_similarity) and EXPLANATION_MIN_COSINE <= cosine_similarity <= 1.000001


def split_explanation_evidence(
    results: list[dict[str, Any]],
    *,
    provider: str | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (accepted, rejected). Rejected rows are not sent to the model."""
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for row in results:
        cosine = row.get("cosine_similarity")
        if passes_evidence_gate(cosine if isinstance(cosine, (int, float)) else None, provider=provider):
            accepted.append(row)
        else:
            rejected.append(row)
    return accepted, rejected
