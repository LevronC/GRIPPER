# Evaluation

Synthetic data only. Nothing here is a production workload, a user study, or a claim that commentary is hallucination-free. Citation checks mean the cited id was in the retrieved set for that institution.

Commands run from the repository root. `PY` should be an interpreter that has the backend dependencies. The database name must start with `gripper_eval` or `gripper_bench`, and the host must be local. The scripts create the database, enable `vector`, and run migrations. They do not add indexes for the benchmark. The HNSW index described in `backend/migrations/versions/a3f9b1c2d4e5_add_file_path_and_performance_indexes.py` is still not created by migrations.

```bash
export MIGRATION_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:55432/gripper_eval
export DATABASE_URL=postgresql://gripper_app:gripper_app_test@127.0.0.1:55432/gripper_eval
make eval-retrieval PY=/path/to/python
make eval-explanations PY=/path/to/python

export MIGRATION_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:55432/gripper_bench
export DATABASE_URL=postgresql://gripper_app:gripper_app_test@127.0.0.1:55432/gripper_bench
make bench-search PY=/path/to/python
```

## Retrieval

`backend/evals/corpus.py` holds 24 synthetic notes and 42 queries. Relevance labels were assigned from the text when the file was written. The script must not be used as a reason to edit those labels after seeing a score.

The comparison runs full-text, vector, and hybrid (RRF, k=60) at limit 5. Hybrid reads 15 candidates from each leg, which is what `hybrid_search` does in the product. Explanations in the product request 3 excerpts, not 5.

The default embedding provider is the local `BAAI/bge-small-en-v1.5` model. That run may be described as a semantic comparison on this corpus only. `--hash-embeddings` sets `semantic_claim` to false. Those numbers measure the harness, not meaning. CI runs the metric unit tests and one full-text smoke test. It does not run the model comparison or the latency benchmark.

Unanswerable queries are excluded from Hit@5, MRR@5, and Recall@5. The report counts how often a mode still returned a row. Vector search has no similarity floor, so that count is expected to be high.

## Latency

`scripts/benchmark_search.py` inserts synthetic chunks with `hash_test` vectors. Reported timings:

- cold end-to-end: the first call on a new session
- warm end-to-end: hash query embedding, SQL, and row mapping, after 20 discarded warmup calls
- warm vector SQL and warm full-text SQL: the statements in `searcher.py`, without query embedding
- concurrent end-to-end: 4 sessions by default

p99 on a few hundred samples moves when a single slow call changes. The script says so in its output. Query plans are `EXPLAIN (ANALYZE, BUFFERS)` for one vector statement and one full-text statement.

## Explanations

`scripts/eval_explanations.py` seeds 12 synthetic violations. One pass uses the deterministic template. A second pass sends scripted JSON through the real citation validator, including an other-tenant chunk id, malformed JSON, and a sentence that tries to mark the violation resolved. No live model call is made. A kept citation means the id was retrieved for that institution. It does not mean the sentence is factually supported.

Results from the runs that produced `backend/eval_results/` are the measurements. Re-run the commands to replace them. Do not copy figures into the README unless the command, commit, and limits are next to them.
