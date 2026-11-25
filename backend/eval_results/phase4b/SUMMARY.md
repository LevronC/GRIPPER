# Phase 4B verification summary

Compact record of the Phase 4B measurements. Raw logs and per-sample JSON stay on
the machine that produced them (git-ignored, about 12 MB). Every number below was
copied or computed from those files. Data is synthetic. No production system, live
LLM provider or external search service was used.

## Evaluated source state

| Evidence | Source evaluated | Status |
|---|---|---|
| Full runner `terminal_20261125_094655_bc0e` | Commit `e657b53`, clean tree (`git status` empty; `git diff HEAD` SHA-256 `e3b0c442…`, the empty diff) | **Authoritative** |
| Calibration and gate rerun `final_20261125_095407` | Commit `e657b53`, clean tree | **Authoritative** |
| Populated-migration experiment `migration_shm_*` | `f8b56e8` plus the then-uncommitted Phase 4B tree; "original" = `e7c4b2a91d08` without the serial-build setting, "corrected" = `e7c4b2a91d08` as committed | Supporting; file hashes not recorded by the experiment |
| Runner `terminal_20261125_092326_0ddb` | `f8b56e8` plus uncommitted tree, original `e7c4` | Superseded |
| Runner `terminal_20261125_093416_ba6e` | Corrected tree | Incomplete: terminated during the 50k benchmark when its session ended. Not evidence |
| Earlier runners (`084723`, `091330`) and top-level inherited files | Older trees, partly Python 3.11 | Historical only |

Implementation commits: `420cf40` (secret scanning), `2130558` (relevance gate),
`9cdaafd` (indexed tenant-scoped retrieval and abstention), `5295428` (verification
harness and runner). This summary is added by the next commit, which changes no code.

Commit hashes recorded inside the raw results predate a message-only rewrite (commit
trailers removed before publishing). Trees are unchanged, so the tree hash identifies
the evaluated content:

| Hash recorded in results | Published commit | Tree (unchanged) |
|---|---|---|
| `e657b53` (evaluated above) | `5295428` | `1aef70735a2f` |
| `f8b56e8` | `c28f346` | `78577fbbe36a` |
| `ebc60e4` (Phase 4 `eval_results/*.json`) | `bbe6a32` | `3902cfadf820` |

`5295428` and the commit that adds this file have identical code, migrations and tests.

## Environment

- Host: macOS 27.3 arm64, 10 CPUs, 16 GiB. Docker: 10 CPUs, 7.7 GiB.
- PostgreSQL 16.16 (`pgvector/pgvector:pg16`), pgvector 0.8.7, `/dev/shm` 64 MiB (Docker default).
- Server settings: `shared_buffers` 160 MB, `work_mem` 4 MB, `maintenance_work_mem` 64 MB,
  `effective_cache_size` 5 GB, `max_parallel_workers_per_gather` 2, `max_parallel_maintenance_workers` 2.
- Python 3.12.16 (repository `.venv`). Package versions are recorded per run in `python_packages.json`.
- Every service call ran as a fresh restricted login: not superuser, no BYPASSRLS, no
  owned tables, forced RLS on every table (`check_db_role.py` reported no problems).

## Regression checks (runner on `e657b53`)

| Check | Result |
|---|---|
| Migration upgrade → downgrade to `c8e2a14f6b30` → upgrade (fresh DB) | PASS |
| Runtime role check, Redis ping | PASS |
| Ruff, mypy (48 files) | PASS |
| Unit tests | 194 passed |
| Integration tests (real PostgreSQL/Redis) | 205 passed |
| Model tests (local BGE, offline) | 2 passed |
| Retrieval and explanation evaluations | Completed (below) |
| pip-audit (`requirements-ci.txt`) | No known vulnerabilities |
| npm audit (`--audit-level=high`) | 0 vulnerabilities |
| Frontend lint and build | PASS |
| Gitleaks 8.24.2, git history (66 commits), redacted | No leaks found |

## Retrieval quality (local `BAAI/bge-small-en-v1.5`, 384-d)

Corpus: 24 synthetic documents, 42 queries (36 answerable, 6 unanswerable), limit 5.
Labels were written before the runs.

| Mode | Hit@5 | MRR@5 | Recall@5 | Unanswerable queries returning a row |
|---|---:|---:|---:|---:|
| Original expression full text | 0.389 | 0.389 | 0.389 | 0/6 |
| Generated-column full text | 0.389 | 0.389 | 0.389 | 0/6 |
| Exact vector | 1.000 | 0.986 | 0.972 | 6/6 |
| Runtime vector function | 1.000 | 0.986 | 0.972 | 6/6 |
| Hybrid (RRF) | 1.000 | 0.986 | 1.000 | 6/6 |
| Gated hybrid (cosine ≥ 0.55) | 1.000 | 0.986 | 0.958 | 3/6 |

The generated column did not change full-text results, and the runtime vector function
matched exact search on this corpus. Full text finds no paraphrase or multi-document
queries (Hit@5 0.000 in both categories).

Relevance gate (cutoff 0.55, chosen on the calibration split only). Calibration corpus:
16 documents and 28 queries, split 14/14 (4 queries have no relevant document).

| Split | Precision | Recall | False-accept rate | Abstention |
|---|---:|---:|---:|---:|
| Calibration | 0.5909 | 1.0000 | 0.0429 | 0.143 |
| Held-out (scored once, after choosing) | 0.7647 | 1.0000 | 0.0185 | 0.071 |

On the original 24-document corpus (in-memory exact cosine, top 5 gated): Hit@5 1.000
ungated and gated; labeled recall 0.9722 → 0.9583; **3 of 6 unanswerable queries still
accept evidence**. The gate is not an entailment check.

Explanation evaluation: 12 cases. Deterministic pass: 12/12 template. Scripted model
JSON: 8 kept, 4 rejected by the validator and replaced by the template. No live provider
was called, no other-tenant text appeared, and compliance outcomes were unchanged.

## Index and latency benchmark

Method: `verify_search_indexes.py` on fresh databases with three tenants holding
90% / 9% / 1% of the chunks. It uses deterministic hash vectors (database behavior only,
no semantic claim), seed 42, 200 queries, 20 warm-up queries, 3 repetitions and 4 workers
for the concurrent test. Times cover the service call and row mapping. Exact and vector
exclude query embedding; hybrid includes it. Ranges are min–max across the 3 repetitions.
These are not HTTP, cold-cache or LLM latencies. Hash vectors bypass the gate, so gated
hybrid does the same work as hybrid here.

#### 10,000 chunks (tenants 9,000 / 900 / 100)

| Tenant chunks | Mode | p50 ms | p95 ms | p99 ms | Errors |
|---:|---|---:|---:|---:|---:|
| 9,000 | exact | 8.9 | 9.3–9.6 | 9.8–11.7 | 0/600 |
| 900 | exact | 1.9–2.1 | 2.3–2.4 | 2.4–2.6 | 0/600 |
| 100 | exact | 0.4–0.8 | 0.4–1.2 | 0.5–1.2 | 0/600 |
| 9,000 | vector | 10.2–10.4 | 10.7–11.5 | 11.2–12.1 | 0/600 |
| 900 | vector | 2.1–2.4 | 2.5–2.6 | 2.6–2.9 | 0/600 |
| 100 | vector | 0.5–1.1 | 0.5–1.6 | 0.6–1.6 | 0/600 |
| 9,000 | full_text | 3.9 | 5.4–5.5 | 5.7–5.9 | 0/600 |
| 900 | full_text | 1.0–1.4 | 1.2–1.9 | 1.3–2.0 | 0/600 |
| 100 | full_text | 0.8–1.4 | 1.0–1.7 | 1.1–1.8 | 0/600 |
| 9,000 | hybrid | 15.3–15.6 | 17.5–17.8 | 18.5–19.9 | 0/600 |
| 900 | hybrid | 3.8–5.0 | 5.5–5.9 | 5.7–6.5 | 0/600 |
| 100 | hybrid | 2.6–3.3 | 3.7–4.1 | 3.9–4.3 | 0/600 |
| 9,000 | gated_hybrid | 15.3–15.6 | 17.9–18.0 | 18.7–27.7 | 0/600 |
| 900 | gated_hybrid | 3.9–5.3 | 5.6–6.0 | 6.3–6.5 | 0/600 |
| 100 | gated_hybrid | 1.9–3.7 | 4.0–4.6 | 4.5–4.8 | 0/600 |

Concurrent hybrid, 4 workers across all tenants: p50 3.1–3.2 ms, p95 19.3–19.5 ms,
p99 20.2–22.0 ms, 461–467 successful queries/s, 0/600 errors.

#### 50,000 chunks (tenants 45,000 / 4,500 / 500)

| Tenant chunks | Mode | p50 ms | p95 ms | p99 ms | Errors |
|---:|---|---:|---:|---:|---:|
| 45,000 | exact | 45.2–45.7 | 46.8–52.8 | 50.6–75.4 | 0/600 |
| 4,500 | exact | 4.6 | 4.8–5.1 | 4.9–5.7 | 0/600 |
| 500 | exact | 0.7–1.3 | 0.8–1.5 | 0.8–2.0 | 0/600 |
| 45,000 | vector | 28.0–28.5 | 28.9–49.8 | 30.0–76.7 | 0/600 |
| 4,500 | vector | 4.7–4.8 | 4.9–5.0 | 5.0–5.5 | 0/600 |
| 500 | vector | 1.0–1.9 | 1.5–2.2 | 1.6–2.3 | 0/600 |
| 45,000 | full_text | 17.7–19.4 | 25.7–28.6 | 33.0–39.3 | 0/600 |
| 4,500 | full_text | 4.0 | 4.7 | 4.7–4.8 | 0/600 |
| 500 | full_text | 2.6–2.7 | 2.8–4.1 | 2.9–5.1 | 0/600 |
| 45,000 | hybrid | 47.4–54.2 | 58.3–67.3 | 70.0–71.0 | 0/600 |
| 4,500 | hybrid | 9.8 | 10.7–11.0 | 11.3–11.6 | 0/600 |
| 500 | hybrid | 5.3–5.4 | 5.6–5.9 | 6.1–6.3 | 0/600 |
| 45,000 | gated_hybrid | 47.2–58.1 | 56.7–70.0 | 65.4–82.6 | 0/600 |
| 4,500 | gated_hybrid | 9.8–9.9 | 10.7–10.9 | 11.4–11.7 | 0/600 |
| 500 | gated_hybrid | 4.7–5.5 | 5.6–5.8 | 6.2–6.4 | 0/600 |

Concurrent hybrid, 4 workers across all tenants: p50 21.0–21.6 ms, p95 100.1–120.9 ms,
p99 110.6–129.8 ms, 83–101 successful queries/s, 0/600 errors.

HNSW helped only at the largest tenant. At 45,000 chunks the runtime vector function
(p50 ≈ 28 ms) beat exact search (≈ 45 ms). At 9,000 chunks it was slightly slower than
exact (10.2–10.4 vs 8.9 ms). Phase 4 numbers came from a different harness (one tenant,
direct ORM queries, earlier code) and are not compared here.

### Query plans (installed function bodies, owner replay)

| Tenant | `app_search_vector` | `app_search_full_text` |
|---|---|---|
| 9,000 / 45,000 | HNSW index scan | GIN bitmap scan |
| 900 / 4,500 | HNSW index scan | GIN + tenant b-tree bitmap scans |
| 100 / 500 | Tenant b-tree (exact), no HNSW | GIN + tenant b-tree bitmap scans |

`research_reports` is sequentially scanned in every plan; it holds one row per tenant here.

### HNSW recall against exact search (overlap, not relevance)

| Dataset | Tenant chunks | Recall@1 | Recall@5 | Recall@10 | Worst query @10 |
|---|---:|---:|---:|---:|---:|
| 10k | 9,000 | 1.0000 | 0.9960 | 0.9950 | 0.9 |
| 10k | 900 | 1.0000 | 0.9990 | 0.9940 | 0.9 |
| 10k | 100 | 1.0000 | 1.0000 | 0.9955 | 0.8 |
| 50k | 45,000 | 0.9900 | 0.9980 | 0.9910 | 0.8 |
| 50k | 4,500 | 1.0000 | 0.9970 | 0.9940 | 0.9 |
| 50k | 500 | 0.9950 | 0.9980 | 0.9955 | 0.8 |

Settings: `hnsw.ef_search` 40, `hnsw.iterative_scan` strict_order, m 16, ef_construction 64.
Boundary ties can lower overlap.

### Index size and populated rebuild (serial `REINDEX`, `maintenance_work_mem` 256 MB)

| Dataset | GIN size | GIN rebuild | HNSW size | HNSW rebuild |
|---|---:|---:|---:|---:|
| 10,000 chunks | 0.82 MiB | 0.04 s | 17.6 MiB | 2.24 s |
| 50,000 chunks | 3.95 MiB | 0.22 s | 87.9 MiB | 15.23 s |

## Populated migration and shared memory

The populated-migration experiment ran migration `e7c4b2a91d08` on fresh databases
preloaded with synthetic chunks.

| Variant | Chunks | Result | GIN build | HNSW build | HNSW size |
|---|---:|---|---:|---:|---:|
| Original (parallel workers allowed) | 10,000 | PASS | 0.03 s | 2.02 s | 17.6 MiB |
| Original | 50,000 | **FAIL**: `could not resize shared memory segment … to 265326112 bytes: No space left on device` | 0.18 s | — | — |
| Corrected (`SET LOCAL max_parallel_maintenance_workers = 0`) | 10,000 | PASS | 0.03 s | 2.01 s | 17.6 MiB |
| Corrected | 50,000 | PASS | 0.20 s | 15.40 s | 87.9 MiB |

- **Root cause:** a parallel HNSW build requests a dynamic shared-memory segment sized from
  `maintenance_work_mem`, which needed about 253 MiB. The container's `/dev/shm` is 64 MiB.
- **Fix:** serial builds use backend-local memory. The migration's memory setting was not
  changed, and the container was not modified.
- **After the corrected build:** both indexes were valid, ready and live. The planner used
  each index when sequential scans were disabled. HNSW recall@10 against exact search was
  0.97 over 20 queries at 50k, and GIN returned the same rows as a sequential scan.
- **Settings did not persist:** a new session after the migration showed server defaults,
  and no per-database or per-role overrides were created.
- **Round trip:** downgrade and re-upgrade passed at both sizes.
- **Not measured:** parallel build time on a host with enough shared memory, so the cost of
  serial building is unknown.
- **Prior deployment:** no persistent database had applied the original `e7c4` (it was never
  committed), so it was corrected in place.

## Limitations

- All data is synthetic. Quality corpora are small (24 and 16 documents), and latency uses
  hash vectors on one laptop running Docker on macOS.
- The gate still accepts evidence for half of the unanswerable queries. It reduces weak
  evidence; it does not establish factual support.
- No HTTP-endpoint, cold-cache, live SubQ or Hugging Face measurements, and no
  `ef_search`/`m` sweep. No sub-300 ms production p99 guarantee is claimed.
- `REINDEX` timings are rebuilds, not the migration's initial build. Larger tables need
  proportionally more time, memory and disk, and the migration locks `document_chunks`.
- The populated-migration experiment scripts were not committed; they remain with the
  local raw results.

## Reproduce

From the repository root, with Python 3.12 and Gitleaks 8.24.2 installed:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-dev.txt -c backend/requirements-ci.lock
bash backend/scripts/run_phase4b_verification.sh   # local gripper-audit-pg/-redis containers only

cd backend
EMBEDDING_PROVIDER=local HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  ../.venv/bin/python scripts/calibrate_relevance.py --out eval_results/phase4b/<new>/calibration.json
EMBEDDING_PROVIDER=local HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  ../.venv/bin/python scripts/eval_gate_regression.py --out eval_results/phase4b/<new>/gate.json
```

See `docs/PHASE4B_VERIFICATION.md` for the runner's safety checks and options.
