# Retrieval evaluation

Synthetic corpus. Relevance labels were written before this run and were not changed to match it.

- Semantic claim: **yes**.
- Embedding: `local` / `BAAI/bge-small-en-v1.5` (384-d).
- Documents: 24. Queries: 42. Limit: 5.
- Hybrid candidate window: 15 per leg, then fused to 5. Product explanations request 3.
- Commit: `ebc60e42dc2e3bfd08c403f5b75d958a561a4089`.

| Mode | Hit@5 | MRR@5 | Recall@5 | Unanswerable queries that still returned a row |
|---|---:|---:|---:|---:|
| full_text | 0.389 | 0.389 | 0.389 | 0/6 |
| vector | 1.000 | 0.986 | 0.972 | 6/6 |
| hybrid | 1.000 | 0.986 | 1.000 | 6/6 |

Hit, MRR, and Recall use only queries that have at least one relevant document. Unanswerable queries are the last column. Vector search has no similarity floor, so a high false-return rate there is expected.

## By category (Hit@5)

| Category | Full text | Vector | Hybrid | Queries |
|---|---:|---:|---:|---:|
| ambiguous | 0.750 | 1.000 | 1.000 | 4 |
| confusable | 0.500 | 1.000 | 1.000 | 8 |
| exact | 0.875 | 1.000 | 1.000 | 8 |
| multi | 0.000 | 1.000 | 1.000 | 6 |
| paraphrase | 0.000 | 1.000 | 1.000 | 10 |
