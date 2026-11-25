"""Chunker: verbatim, page-preserving, token-bounded, deterministic (no database)."""

from __future__ import annotations

import importlib.util

import pytest

from app.services.ingestion.chunker import chunk_document_pages, estimate_tokens

SAMPLES = {
    "dense_financial": "Q3 FY2026 EBITDA margin compressed 340bps YoY to 18.7% as CapEx rose to $1.84B; management reiterated FY2027 guidance of $7.2B-$7.6B revenue, citing AI/ML data-center demand.",
    "prose": "The investment committee reviewed the portfolio's exposure to the technology sector and discussed whether the current allocation remains consistent with the policy statement adopted last year.",
    "tickers": "NVDA MSFT AAPL JPM XOM JNJ LLY AMZN BAC GOOGL META TSLA CVX BRK.B V MA UNH HD PG KO PEP",
    "numbers": "12.5% 3,450,000 (1.2x) 0.034 -7.81% $2,340.55 2026-11-25 14:32:07 1e-9 +0.0001bps",
    "legal": "Notwithstanding the foregoing, the Fund shall not invest more than ten percent (10%) of its net assets in securities of any single issuer, as defined in Section 2(a)(3) of the Act.",
    "identifiers": "See https://www.sec.gov/Archives/edgar/data/1045810/000104581025000209/nvda-20250427.htm and ISIN US67066G1040 / CUSIP 67066G104.",
    "unicode": "Société Générale’s “résumé” — naïve café façade, Zürich & São Paulo; €1.2bn ≈ £1.0bn.",
    "long_words": "Antidisestablishmentarianism pseudopseudohypoparathyroidism electroencephalographically counterrevolutionaries",
}


def _words(n, prefix="word"):
    return " ".join(f"{prefix}{i}" for i in range(n))


def test_preserves_case_and_punctuation():
    text = "NVDA's Q3 EBITDA rose 12.5%; CapEx guidance (FY2027) unchanged."
    [chunk] = chunk_document_pages([{"page_num": 4, "text": text}])
    assert chunk["content"] == text
    assert chunk["page_num"] == 4


def test_empty_and_whitespace_pages_skipped():
    assert chunk_document_pages([{"page_num": 1, "text": ""}, {"page_num": 2, "text": "  \n\t "}]) == []


def test_short_page_is_one_chunk():
    assert [c["word_count"] for c in chunk_document_pages([{"page_num": 1, "text": "Only a few words."}])] == [4]


@pytest.mark.parametrize("n_words", [1, 10, 200, 201, 450, 1000, 5000])
def test_budget_overlap_and_full_coverage(n_words):
    words = _words(n_words).split()
    chunks = chunk_document_pages([{"page_num": 7, "text": " ".join(words)}], token_budget=100, overlap=10)
    assert all(c["est_tokens"] <= 100 for c in chunks)
    assert all(c["page_num"] == 7 for c in chunks)
    assert {w for c in chunks for w in c["content"].split()} == set(words)  # nothing dropped
    for prev, nxt in zip(chunks, chunks[1:]):
        k = min(10, prev["word_count"] - 1)
        assert prev["content"].split()[-k:] == nxt["content"].split()[:k]
    assert chunks[-1]["content"].split()[-1] == words[-1]


def test_no_redundant_tail_chunk():
    page = {"page_num": 1, "text": _words(20)}
    budget = sum(estimate_tokens(w) for w in page["text"].split())
    assert len(chunk_document_pages([page], token_budget=budget, overlap=5)) == 1


def test_single_oversized_word_still_progresses():
    chunks = chunk_document_pages([{"page_num": 1, "text": "A" * 2000 + " tail"}], token_budget=50, overlap=5)
    assert chunks[0]["word_count"] == 1 and chunks[-1]["content"].endswith("tail")


def test_pages_never_merge():
    chunks = chunk_document_pages([{"page_num": 1, "text": "alpha beta"}, {"page_num": 2, "text": "gamma"}])
    assert [(c["page_num"], c["content"]) for c in chunks] == [(1, "alpha beta"), (2, "gamma")]


def test_deterministic():
    pages = [{"page_num": 1, "text": " ".join(SAMPLES.values()) * 20}]
    assert chunk_document_pages(pages) == chunk_document_pages(pages)


@pytest.mark.parametrize("budget, overlap", [(0, 0), (-5, 0), (10, -1)])
def test_invalid_parameters(budget, overlap):
    with pytest.raises(ValueError):
        chunk_document_pages([{"page_num": 1, "text": "x"}], budget, overlap)


@pytest.mark.skipif(importlib.util.find_spec("transformers") is None,
                    reason="transformers not installed (excluded from CI image); validated locally")
@pytest.mark.parametrize("kind", sorted(SAMPLES))
def test_default_chunks_fit_bge_context_window(kind):
    """Measured with the real BGE tokenizer: every default chunk fits in 512 tokens."""
    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained("BAAI/bge-small-en-v1.5")
    chunks = chunk_document_pages([{"page_num": 1, "text": (SAMPLES[kind] + " ") * 80}])
    assert len(chunks) > 1
    for chunk in chunks:
        n = len(tok.encode(chunk["content"], add_special_tokens=True))
        assert n <= 512, (kind, n)
