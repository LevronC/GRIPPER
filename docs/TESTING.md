# Testing

```bash
cd backend
pip install -r requirements-dev.txt          # or requirements-ci.txt -c requirements-ci.lock (no torch)
ruff check . && mypy
pytest tests -m "not integration and not model"   # unit tests: no database, no network
```

## Integration tests (`tests/integration/`)

These run against **real PostgreSQL + pgvector and Redis**, with the app connected as the
**restricted runtime role**, exactly as in production. They need two URLs:

```bash
docker run -d --name gripper-pg -e POSTGRES_PASSWORD=postgres -p 5432:5432 pgvector/pgvector:pg16
docker run -d --name gripper-redis -p 6379:6379 redis:7
export MIGRATION_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/postgres   # owner
export DATABASE_URL=postgresql://gripper_app:local-test-pw@localhost:5432/postgres     # restricted
export REDIS_URL=redis://localhost:6379/0 SECRET_KEY=$(python -c "import secrets;print(secrets.token_hex(32))") ENVIRONMENT=test
psql "$MIGRATION_DATABASE_URL" -c "CREATE EXTENSION IF NOT EXISTS vector"
alembic upgrade head
APP_DB_PASSWORD=local-test-pw python scripts/create_app_role.py
pytest tests -m integration
```

Without the database the integration tests **skip**; with `REQUIRE_INTEGRATION=1` (set in CI)
they **fail** instead, so CI can never pass silently without infrastructure.

| File | What it proves |
|---|---|
| `test_rls_database.py` | RLS through the restricted role with raw SQL: per-table isolation, fail-closed without context, no leakage on reused pooled connections, no cross-tenant insert/update/delete, no DDL, composite tenant FKs, definer functions return ids only |
| `test_tenant_isolation_api.py` | Every cross-tenant API request is denied, once through RLS + app checks and once with an **owner** session (RLS bypassed) to prove the app checks alone suffice; legitimate writes that commit mid-request succeed |
| `test_role_safety_and_worker.py` | The API refuses to serve with a privileged runtime role; worker jobs cannot touch another tenant's report |
| `test_auth_flows.py` | Invitations (expiry, reuse, revocation, wrong email, manipulated institution/role), login, password reset (expiry, reuse, newest-only, rate limits, session revocation), logout revocation, tokens never logged, demo-seed guards |
| `test_compliance_workflow.py` | End-to-end rule → portfolio → holdings → evaluation → violation → research → explanation, seeded demo yields its documented violations, rule API validation/authorization, research never changes a violation, determinism |
| `test_ingestion_and_retrieval.py` | Ingestion lifecycle (success, failure keeps the file, retry, duplicates, empty PDFs, idempotent re-runs), provider-down degradation to full text, embedding-space isolation, upload API, real Redis + RQ worker |

## Embedding tests

The suite uses `EMBEDDING_PROVIDER=hash_test`: deterministic token-hash vectors that have
**no semantic meaning**, are allowed only when `ENVIRONMENT=test`, and live in their own
embedding space. They test retrieval *mechanics* (filtering, fusion, isolation, provenance),
never retrieval *quality*.

| Suite | Needs | Runs in CI |
|---|---|---|
| Chunk-size bounds vs the real BGE tokenizer (`test_chunker.py`) | `tokenizers` + vendored `tests/fixtures/bge-small-en-v1.5.tokenizer.json` (revision `5c38ec7c…`, MIT) | yes, offline |
| Hugging Face client (`test_embeddings.py::test_hf_*`) | nothing (HTTP is mocked) | yes; **mock-tested only**: no authenticated live call has been made |
| Real model semantics (`-m model`) | `sentence-transformers` + torch + model download | only via the manual `model-tests` job (`workflow_dispatch`, `run_model_tests=true`) |

Run the model suite locally:

```bash
cd backend
pip install -r requirements.txt   # includes sentence-transformers
SECRET_KEY=$(python -c "import secrets;print(secrets.token_hex(32))") ENVIRONMENT=test PYTHONPATH=. pytest tests -m model -v
```

Last local run (2026-11-25): passed with sentence-transformers 6.3.0, transformers 5.24.1,
tokenizers 0.23.3, torch 2.15.0, model `BAAI/bge-small-en-v1.5` revision
`5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`, Python 3.11, macOS (arm64).

## Not covered by automated tests

* Hugging Face API with a real key (the client is tested against mocked responses).
* Vercel Blob storage (local-disk storage is used in tests).
* SMTP delivery (the `memory` backend is used; the SMTP code path is untested).
* Browser-level UI behaviour.
