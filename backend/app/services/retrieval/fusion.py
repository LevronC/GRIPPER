"""
Reciprocal Rank Fusion (Cormack, Clarke & Büttcher, SIGIR 2009).

    RRF(d) = Σ over retrievers r containing d of  1 / (k + rank_r(d)),   rank_r ∈ {1, 2, ...}

Semantics as implemented
* Ranks are 1-indexed positions in each input list (the list order IS the ranking;
  retriever scores are ignored).
* Fusion operates on CHUNKS (keyed by chunk_id), not documents. Several chunks of the
  same report can occupy several result slots; there is no per-document diversification.
* A key appearing more than once in the same list counts only at its first (best) rank.
* The returned payload for a key is the first one seen, scanning the vector list first,
  then the full-text list.
* Ordering: RRF score descending; ties broken by the best (smallest) rank in any list,
  then by key ascending. The order is therefore fully deterministic and independent of
  dictionary or insertion order.

Complexity (V, T = input list lengths; U = distinct keys <= V + T)
* Score accumulation and deduplication: O(V + T) time with a hash map, O(U) space.
* Ordering: O(U log U) for a full sort (Python's sort), then slicing to `limit`.
  In hybrid_search both lists are capped at 3 * limit, so U <= 6 * limit.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Sequence

DEFAULT_K = 60


def reciprocal_rank_fusion(
    vector_docs: Sequence[Dict[str, Any]],
    text_docs: Sequence[Dict[str, Any]],
    k: float = DEFAULT_K,
    limit: int = 5,
    key: str = "chunk_id",
) -> List[Dict[str, Any]]:
    """
    Fuses two ranked lists. Returns at most `limit` payload dicts (copies) with:
      rrf_score, vector_rank (or None), text_rank (or None).
    """
    if isinstance(k, bool) or not isinstance(k, (int, float)) or not math.isfinite(k) or k < 0:
        raise ValueError("k must be a finite number >= 0")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
        raise ValueError("limit must be an integer >= 0")

    scores: Dict[str, float] = {}
    ranks: Dict[str, Dict[str, int]] = {}
    payloads: Dict[str, Dict[str, Any]] = {}
    for leg, docs in (("vector", vector_docs), ("text", text_docs)):
        for position, doc in enumerate(docs, start=1):
            doc_key = str(doc[key])
            leg_ranks = ranks.setdefault(doc_key, {})
            if leg in leg_ranks:
                continue  # duplicate within this list: keep the best rank only
            leg_ranks[leg] = position
            payloads.setdefault(doc_key, doc)
            scores[doc_key] = scores.get(doc_key, 0.0) + 1.0 / (k + position)

    ordered = sorted(scores, key=lambda dk: (-scores[dk], min(ranks[dk].values()), dk))
    out = []
    for dk in ordered[:limit]:
        item = dict(payloads[dk])
        item["rrf_score"] = scores[dk]
        item["vector_rank"] = ranks[dk].get("vector")
        item["text_rank"] = ranks[dk].get("text")
        out.append(item)
    return out
