# Test fixtures

## `bge-small-en-v1.5.tokenizer.json`

The WordPiece tokenizer of [BAAI/bge-small-en-v1.5](https://huggingface.co/BAAI/bge-small-en-v1.5),
vendored so the chunk-size tests (`tests/test_chunker.py`) run offline in CI with the
lightweight `tokenizers` package (no torch, no network).

| | |
|---|---|
| Source | `BAAI/bge-small-en-v1.5`, revision `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a` |
| SHA-256 | `d241a60d5e8f04cc1b2b3e9ef7a4921b27bf526d9f6050ab90f9267a1f9e5c66` |
| License | MIT (per the model card) |

It is only a tokenizer (vocabulary and rules). It contains no model weights and produces no embeddings.
