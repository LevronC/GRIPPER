# Deployment notes: ingestion and embeddings

What works where. "Verified" means exercised by the test suite or a manual check on
2026-11-25; "unverified" means the code path exists but has not been run against the
real service.

| Capability | Local (docker / venv) | Vercel serverless |
|---|---|---|
| Semantic embeddings | `EMBEDDING_PROVIDER=local` (sentence-transformers, BAAI/bge-small-en-v1.5). **Verified** locally (`tests/test_embeddings.py::test_local_model_produces_semantic_similarity`). | The local model does not fit Vercel's function size. `hf_api` (router.huggingface.co) needs `HF_API_KEY`: **unverified** (no key used). Without it: full-text only. |
| Full-text search | Yes | Yes |
| Async ingestion (RQ) | `INGESTION_MODE=queue` + `python app/workers/worker.py`. **Verified** (`test_queue_mode_with_real_rq_worker`). | No persistent worker can run on Vercel. `INGESTION_MODE=auto` therefore processes **synchronously in the upload request** (60 s `maxDuration`) unless you run an external worker against the same Redis and set `INGESTION_WORKER=external`. |
| Scheduled draining of pending jobs | n/a | **Not configured.** `vercel.json` has no `crons`. `GET /api/cron/process-documents` (Bearer `CRON_SECRET`) can be triggered manually or by an external scheduler. |
| Upload storage | Local disk (`UPLOAD_DIR`) | Vercel Blob (`BLOB_READ_WRITE_TOKEN`). The REST upload in `app/core/blob.py` does not set an access mode; whether blob URLs are publicly readable is **unverified**. Treat uploaded PDFs as potentially public until confirmed. |

## Embedding integrity

* There is no silent fallback. If the provider is missing or fails, ingestion stores
  chunks **without** vectors (they remain full-text searchable), search reports
  `retrieval_mode: "full_text_only"` with a `degraded_reason`, the UI shows a banner,
  and `GET /health` reports `capabilities.semantic_search: false`.
* Each chunk records `embedding_model` (the embedding space, e.g. `BAAI/bge-small-en-v1.5@384`)
  and `embedding_provider`. Vector search only compares the query with chunks in the active space.
* `hash_test` vectors exist only for tests (`ENVIRONMENT=test`) and live in their own space.

### Existing data (`legacy-unknown`)

Before this change, `generator.py` substituted SHA-256 hash vectors whenever the provider
failed, and the configured Hugging Face host `api-inference.huggingface.co` **does not
resolve** (checked 2026-11-25). A production deployment that relied on `HF_API_KEY`
has therefore most likely been storing hash vectors. Migration `3e9a5b2c7d48`
labels every pre-existing vector `legacy-unknown`, which excludes it from vector search
(full-text still works). To restore semantic search, configure a provider and run:

```bash
cd backend
MIGRATION_DATABASE_URL=... EMBEDDING_PROVIDER=local python scripts/reembed.py          # dry run: counts per space
MIGRATION_DATABASE_URL=... EMBEDDING_PROVIDER=local python scripts/reembed.py --apply  # re-embed
```

Take a backup first. Re-embedding production data is an operator decision.

## Ingestion lifecycle and retention

`pending → processing → processed | failed | duplicate`

* The source file is deleted **after** chunks are committed, never before. Failed jobs
  keep their file so `POST /documents/{id}/retry` can rerun them, and re-runs replace
  chunks instead of duplicating them.
* Jobs stuck in `processing` for more than 15 minutes (crashed worker) are returned
  by `app_pending_ingestion_jobs` and picked up by the cron endpoint.
* Retention: source files of failed uploads are deleted after 7 days by
  `scripts/cleanup_failed_uploads.py --apply` (dry run without `--apply`). Run it from a
  scheduler you control; nothing schedules it automatically.
