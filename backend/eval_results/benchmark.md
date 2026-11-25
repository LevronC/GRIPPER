# Search latency

Synthetic rows and hash embeddings. These numbers are not retrieval quality.

- Chunks: 10000. Queries: 200. Seed: 42.
- End-to-end includes session, hash query embedding, SQL, row mapping.
- Database timings include SQL and row mapping; query embedding is excluded.
- Excluded: model download, corpus insert, warmup queries.
- Cold end-to-end (one uncached call): 76.08 ms.
- Concurrent workers: 4. Throughput: 37.80 queries/s. Errors: 0 / 200.
- Postgres: `PostgreSQL 16.16 (Debian 16.16-1.pgdg12+1) on aarch64-unknown-linux-gnu, compiled by gcc (Debian 12.2.0-14+deb12u1) 12.2.0, 64-bit`
- pgvector: `0.8.7`
- Host: macOS-27.3-arm64-arm-64bit (arm64, 10 CPUs).
- Commit: `ebc60e42dc2e3bfd08c403f5b75d958a561a4089`.

p99 is interpolated from the slowest points. At this sample size one slow call moves it.

| Timing | n | mean ms | p50 | p95 | p99 |
|---|---:|---:|---:|---:|---:|
| warm end-to-end | 200 | 58.37 | 57.20 | 63.71 | 90.19 |
| warm vector SQL | 200 | 5.79 | 5.80 | 6.79 | 7.21 |
| warm full-text SQL | 200 | 51.81 | 51.01 | 57.13 | 62.78 |
| concurrent end-to-end | 200 | 104.12 | 98.79 | 143.03 | 156.27 |

## Indexes on document_chunks

- `document_chunks_pkey`: `CREATE UNIQUE INDEX document_chunks_pkey ON public.document_chunks USING btree (id)`
- `idx_document_chunks_tenant_model`: `CREATE INDEX idx_document_chunks_tenant_model ON public.document_chunks USING btree (institution_id, embedding_model)`
- `ix_document_chunks_content_gin`: `CREATE INDEX ix_document_chunks_content_gin ON public.document_chunks USING gin (to_tsvector('english'::regconfig, (content)::text))`

## Vector plan

```
Limit  (cost=5191.99..5192.00 rows=5 width=24) (actual time=4.321..4.322 rows=5 loops=1)
  Buffers: shared hit=5002
  ->  Sort  (cost=5191.99..5192.62 rows=250 width=24) (actual time=4.320..4.321 rows=5 loops=1)
        Sort Key: ((c.embedding <=> '[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.5,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,-0.5,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,-0.5,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.5,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]'::vector)), c.id
        Sort Method: top-N heapsort  Memory: 25kB
        Buffers: shared hit=5002
        ->  Result  (cost=8.18..5187.84 rows=250 width=24) (actual time=0.550..3.842 rows=10000 loops=1)
              One-Time Filter: ((NULLIF(current_setting('app.current_institution_id'::text, true), ''::text))::uuid = 'b5866225-05ad-5cfc-908e-c22916c6a1c6'::uuid)
              Buffers: shared hit=5002
              ->  Hash Join  (cost=8.18..5187.21 rows=250 width=1560) (actual time=0.548..2.287 rows=10000 loops=1)
                    Hash Cond: (c.report_id = r.id)
                    Buffers: shared hit=5002
                    ->  Seq Scan on document_chunks c  (cost=0.00..5150.00 rows=10000 width=1576) (actual time=0.544..1.584 rows=10000 loops=1)
                          Filter: ((embedding IS NOT NULL) AND (institution_id = 'b5866225-05ad-5cfc-908e-c22916c6a1c6'::uuid) AND ((embedding_model)::text = 'hash-test-v1@384'::text))
                          Buffers: shared hit=5000
                    ->  Hash  (cost=8.16..8.16 rows=1 width=16) (actual time=0.003..0.003 rows=1 loops=1)
                          Buckets: 1024  Batches: 1  Memory Usage: 9kB
                          Buffers: shared hit=2
                          ->  Index Scan using idx_research_reports_institution_created on research_reports r  (cost=0.14..8.16 rows=1 width=16) (actual time=0.002..0.002 rows=1 loops=1)
                                Index Cond: (institution_id = 'b5866225-05ad-5cfc-908e-c22916c6a1c6'::uuid)
                                Buffers: shared hit=2
Planning Time: 0.063 ms
Execution Time: 4.339 ms
```

## Full-text plan

```
Limit  (cost=7120.04..7120.62 rows=5 width=20) (actual time=49.538..50.635 rows=5 loops=1)
  Buffers: shared hit=5340
  ->  Gather Merge  (cost=7120.04..7124.71 rows=40 width=20) (actual time=49.537..50.634 rows=5 loops=1)
        Workers Planned: 2
        Workers Launched: 2
        Buffers: shared hit=5340
        ->  Sort  (cost=6120.02..6120.07 rows=20 width=20) (actual time=48.172..48.173 rows=4 loops=3)
              Sort Key: (ts_rank(to_tsvector('english'::regconfig, (c.content)::text), '''uniform'' & ''delta'' & ''alpha'' & ''india'''::tsquery)) DESC, c.id
              Sort Method: top-N heapsort  Memory: 25kB
              Buffers: shared hit=5340
              Worker 0:  Sort Method: top-N heapsort  Memory: 25kB
              Worker 1:  Sort Method: top-N heapsort  Memory: 25kB
              ->  Result  (cost=8.18..6119.68 rows=20 width=20) (actual time=0.280..48.116 rows=563 loops=3)
                    One-Time Filter: ((NULLIF(current_setting('app.current_institution_id'::text, true), ''::text))::uuid = 'b5866225-05ad-5cfc-908e-c22916c6a1c6'::uuid)
                    Buffers: shared hit=5310
                    ->  Hash Join  (cost=8.18..6114.63 rows=20 width=220) (actual time=0.259..41.372 rows=563 loops=3)
                          Hash Cond: (c.report_id = r.id)
                          Buffers: shared hit=5310
                          ->  Parallel Seq Scan on document_chunks c  (cost=0.00..6104.17 rows=786 width=236) (actual time=0.240..41.289 rows=563 loops=3)
                                Filter: ((institution_id = 'b5866225-05ad-5cfc-908e-c22916c6a1c6'::uuid) AND (to_tsvector('english'::regconfig, (content)::text) @@ '''uniform'' & ''delta'' & ''alpha'' & ''india'''::tsquery))
                                Rows Removed by Filter: 2770
                                Buffers: shared hit=5244
                          ->  Hash  (cost=8.16..8.16 rows=1 width=16) (actual time=0.006..0.006 rows=1 loops=3)
                                Buckets: 1024  Batches: 1  Memory Usage: 9kB
                                Buffers: shared hit=8
                                ->  Index Scan using idx_research_reports_institution_created on research_reports r  (cost=0.14..8.16 rows=1 width=16) (actual time=0.005..0.005 rows=1 loops=3)
                                      Index Cond: (institution_id = 'b5866225-05ad-5cfc-908e-c22916c6a1c6'::uuid)
                                      Buffers: shared hit=8
Planning Time: 0.077 ms
Execution Time: 50.647 ms
```
