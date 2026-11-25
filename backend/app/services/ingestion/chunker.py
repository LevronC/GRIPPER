"""
Page-preserving chunker with a token budget.

Chunks are windows of whitespace-delimited words taken verbatim from the page text, so
stored (and cited) content keeps its original casing and punctuation (runs of
whitespace are collapsed to single spaces). The previous implementation re-decoded
token ids through an uncased tokenizer, which lowercased the stored text. It also fell
back to a different (whitespace) tokenizer when `transformers` was missing, so chunk
boundaries differed between environments.

Size limit. BAAI/bge-small-en-v1.5 embeds at most 512 tokens (510 plus [CLS]/[SEP]);
anything longer is silently truncated. The previous 700-token chunks lost their tails.
Token counts vary a lot by text type: measured with the real tokenizer, prose averages
about 1.1 tokens per word, dense financial text about 2.5, and identifiers/URLs up to 8.
So windows are sized by a deterministic, tokenizer-free estimate (`estimate_tokens`)
that overestimates the WordPiece count on every sample in tests/test_chunker.py except
pathological long words, where it is within about 10%. The 450 budget leaves margin for
that. The same input always produces the same chunks, in every environment.
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List

DEFAULT_TOKEN_BUDGET = 450
DEFAULT_OVERLAP_WORDS = 40

_RUN = re.compile(r"[^\W\d_]+|\d+|\S", re.UNICODE)


def estimate_tokens(word: str) -> int:
    """Conservative WordPiece token estimate for one whitespace-delimited word."""
    total = 0
    for run in _RUN.findall(word):
        if run[0].isdigit():
            total += len(run)                                 # digits often split individually
        elif run[0].isalpha():
            if sum(c.isupper() for c in run) >= 2 or not run.isascii():
                total += len(run)                             # acronyms/tickers, accented text
            elif len(run) > 10:
                total += math.ceil(len(run) / 3)              # long, rare words
            else:
                total += max(1, math.ceil(len(run) / 4))
        else:
            total += 1                                        # punctuation is its own token
    return max(total, 1)


def chunk_document_pages(
    pages_data: List[Dict[str, Any]],
    token_budget: int = DEFAULT_TOKEN_BUDGET,
    overlap: int = DEFAULT_OVERLAP_WORDS,
) -> List[Dict[str, Any]]:
    """
    Splits each page into overlapping word windows whose estimated token count is at
    most `token_budget`. Pages are chunked independently so every chunk carries an exact
    page number. Empty pages produce no chunks. Consecutive windows share the last
    `overlap` words of the previous window (fewer if that window is shorter).
    Returns dicts with page_num, content, word_count, est_tokens.
    """
    if token_budget <= 0:
        raise ValueError("token_budget must be positive")
    if overlap < 0:
        raise ValueError("overlap must be >= 0")

    chunks: List[Dict[str, Any]] = []
    for page in pages_data:
        words = page["text"].split()
        if not words:
            continue
        costs = [estimate_tokens(w) for w in words]
        start = 0
        while start < len(words):
            end, used = start, 0
            while end < len(words) and (used + costs[end] <= token_budget or end == start):
                used += costs[end]
                end += 1
            chunks.append({
                "page_num": page["page_num"],
                "content": " ".join(words[start:end]),
                "word_count": end - start,
                "est_tokens": used,
            })
            if end >= len(words):
                break
            # Step forward, keeping up to `overlap` words of context, always making progress.
            start = max(end - overlap, start + 1)
    return chunks
