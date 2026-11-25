# Phase 4B verification and migration

## Run the full verification

From the repository root:

```bash
bash backend/scripts/run_phase4b_verification.sh
```

This orchestration script calls the existing tests and benchmark harnesses. It
uses only `gripper-audit-pg` and `gripper-audit-redis`, and only host ports 55432
and 56379. Before creating databases it compares the PostgreSQL cluster ID from
inside the named container with the ID returned through port 55432. It records
the existing Gripper database names and creates five fresh, uniquely named
synthetic databases and a dedicated restricted login. It never drops an existing
database, restarts a container, or changes other projects. It reads the local
PostgreSQL password from the named container into memory without printing it;
temporary shell configuration is private and deleted on exit.

It uses the repository `.venv` and requires Python 3.12, matching `.python-version`
and CI. The earlier terminal run used a temporary Python 3.11 environment; keep
those results as historical evidence rather than a Python 3.12 verification.
One-time setup from the repository root, with Python 3.12 installed:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-dev.txt -c backend/requirements-ci.lock
.venv/bin/python -m pip check
```

No existing version pins are changed. The CI constraints cover runtime and test
dependencies; model dependencies such as torch are additional local dependencies,
not a complete cross-platform lock. The runner records installed package versions
and Python executable/version with each run. Use
`PHASE4B_PYTHON=/absolute/path/to/python3.12-environment/bin/python` to select an
existing supported environment. Missing dependencies or a non-3.12 interpreter
must be resolved before the runner can verify the phase. For model tests, the
local Hugging Face cache must contain BGE; the runner requests offline loading.
`PHASE4B_GITLEAKS` can select an installed Gitleaks 8.24.2 binary.

Results and logs go to a new `backend/eval_results/phase4b/terminal_<timestamp>/`
directory. Database or test failures stop the script; audit failures are recorded
while allowing the other audit to run. Benchmarks run sequentially with 4 workers,
20 warmups, 200 measured queries and 3 repetitions. Avoid other heavy workloads
during the run. The script retains synthetic databases for inspection and does
not commit results, push, deploy, or make live LLM requests.

The populated index overhead measurement uses non-concurrent `REINDEX` inside
these disposable databases. Its output is labeled rebuild time, not original
production index creation time.

Measured results, methodology and limitations for the committed source are in
`backend/eval_results/phase4b/SUMMARY.md`. Run directories under
`backend/eval_results/phase4b/` are generated locally and ignored by git; only
the summary is tracked. Artifacts left by the interrupted Phase 4B run are not
measurements of the current source.

## Retrieval behavior

Exploratory search still returns ranked candidates. Compliance explanations
filter semantic candidates at cosine similarity 0.55, selected on the separate
synthetic calibration corpus. RRF scores are not probabilities and are not
thresholded. Keyword-only retrieval remains available with an explicit degraded
mode and relevance disclaimer. Hash vectors bypass semantic gating for tests;
they must never be used to claim explanation quality.

No accepted excerpts means no SubQ call. An all-rejected candidate list returns
`research_status=insufficient` and a deterministic policy explanation. Neither
retrieval nor commentary changes the compliance outcome. The new BGE rerun still
accepts evidence for 3 of 6 unanswerable queries; this gate is not proof of
factual support. Held-out precision is 0.7647 and recall is 1.0 on synthetic data.

`f1b4c8d2e903` follows the interrupted agent's `e7c4b2a91d08` migration so databases
that already applied the latter receive the fixes. Search requires a processed
report and matching report/chunk institution. Pending, processing, failed and
duplicate reports are now excluded explicitly. The vector candidate query orders
by cosine distance alone, then sorts the selected candidates by distance and ID.
This permits an ANN plan without claiming exact completeness or stable membership
at a tied cutoff. Function-local HNSW settings do not leak into caller sessions.

The design follows pgvector's distance-operator ORDER BY/LIMIT requirements:
https://github.com/pgvector/pgvector#troubleshooting
`verify_search_indexes.py` measures index selection and exact-versus-approximate
recall; see the summary. Index existence alone does not establish index use.

## Local verification

Use a development environment with PostgreSQL + pgvector >= 0.8.0 and Redis.
Set `MIGRATION_DATABASE_URL` and `DATABASE_URL` to the same disposable local
database named `gripper_eval_phase4b` (owner and restricted application roles
respectively). Supply local credentials through the shell environment. Do not
source a production environment file. Evaluation scripts allow only local
hosts and `gripper_eval*` / `gripper_bench*` names.

From `backend/`, using an environment with the repository requirements installed:

```bash
alembic upgrade head
python scripts/check_db_role.py
REQUIRE_INTEGRATION=1 pytest tests -m 'integration and not model' -q
pytest tests -m 'not integration and not model' -q
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 pytest tests -m model -q -rs
ruff check .
mypy
pip-audit -r requirements-ci.txt
```

`check_db_role.py` must succeed before claiming isolation. Use the role-creation
instructions in `DATABASE_SECURITY.md` when preparing a fresh database. The
evaluation harness also rejects an unsafe runtime role.

Preserve old results by using new output names:

```bash
python scripts/calibrate_relevance.py --out eval_results/phase4b/calibration_next.json
python scripts/eval_gate_regression.py --out eval_results/phase4b/gate_next.json
python scripts/eval_retrieval.py --out eval_results/phase4b/retrieval_next
python scripts/verify_search_indexes.py --chunks 10000 --queries 200 --repeats 3 --out eval_results/phase4b/indexes_10k_next.json
python scripts/verify_search_indexes.py --chunks 50000 --queries 200 --repeats 3 --out eval_results/phase4b/indexes_50k_next.json
python scripts/eval_explanations.py --help
```

The index harness replaces only its deterministic synthetic tenants in the
selected evaluation database. `--replace` additionally drops/recreates that
database; omit it unless destruction of that disposable database is intended.
Use a separate benchmark database from the labeled retrieval corpus.

The quality evaluator compares historical expression FTS, generated-column FTS,
exact materialized vector results, the runtime vector function, hybrid and gated
hybrid. A tiny corpus may choose a sequential scan even with HNSW available; do
not call that an ANN quality measurement without plan evidence at scale.

The index harness measures 90%/9%/1% tenant partitions, exact/approximate overlap
at 1/5/10, all latency samples, failures, repeated sequential runs and concurrent
hybrid search. Hash vectors measure database behavior only. Each plan is a replay
of the **installed function body**, under the function owner's role and settings;
it is labeled separately from restricted-role service timings. A first-session
call is not a cold OS/database cache measurement. This harness does not measure
HTTP endpoint latency, live LLM latency, or index parameter sweeps, and it does
not establish a sub-300ms production p99 guarantee. `--measure-index-builds` times
a serial `REINDEX` of the populated indexes: a rebuild, not the migration's build.

## Migration and rollback

Inspect existing schema before any rollout:

```sql
SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'document_chunks';
SELECT extversion FROM pg_extension WHERE extname = 'vector';
SELECT proname, prosecdef, proconfig, proacl FROM pg_proc
WHERE proname IN ('app_search_vector', 'app_search_full_text');
```

The `e7c4` migration adds a stored generated column and non-concurrent GIN/HNSW
indexes. It can rewrite/lock the table, block writes, and consume additional
disk/memory; allow a maintenance window and measure on a disposable copy first.

Index builds in `e7c4` are serial (`SET LOCAL max_parallel_maintenance_workers = 0`).
With parallel maintenance workers allowed, a 50,000-chunk HNSW build in a container
with Docker's default 64 MiB `/dev/shm` failed: PostgreSQL asked for a ~253 MiB
dynamic shared-memory segment sized from `maintenance_work_mem = '256MB'`. The
serial build uses backend-local memory instead and succeeded (about 15 s for the
HNSW index on that synthetic table). The setting is transaction-local and does not
persist. Parallel build time on a host with enough shared memory was not measured.
Larger tables need proportionally more time, memory and disk; measure on a copy.
The migration owner needs schema/table/index creation privileges. Runtime gets
function EXECUTE; PUBLIC is revoked. SECURITY DEFINER bypasses owner RLS and
therefore relies on explicit tenant checks; the integration tests exercise these
functions directly, including malformed ownership and missing context.

`f1b4` downgrade intentionally retains the safer SQL and compatible signatures.
Downgrading `e7c4` removes the functions and generated column/indexes and restores
the historical expression GIN index. Application rollback must accompany that
schema rollback. Test a full round trip only on a disposable database:

```bash
alembic downgrade c8e2a14f6b30
alembic upgrade head
```

## Optional live SubQ check

No live request is authorized by this phase. The existing opt-in synthetic
command, to run only after separate authorization, is
`python scripts/llm_preflight.py --generate` with provider settings in the
environment. Scripted commentary tests are validator checks, not model-quality
measurements. Keep live quality UNVERIFIED until an authorized run succeeds.
