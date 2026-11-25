# Search latency

Synthetic rows and hash embeddings. These numbers are not retrieval quality.

- Chunks: 50000. Queries: 200. Seed: 42.
- End-to-end includes session, hash query embedding, SQL, row mapping.
- Database timings include SQL and row mapping; query embedding is excluded.
- Excluded: model download, corpus insert, warmup queries.
- Cold end-to-end (one uncached call): 717.92 ms.
- Concurrent workers: 4. Throughput: 7.11 queries/s. Errors: 0 / 200.
- Postgres: `PostgreSQL 16.16 (Debian 16.16-1.pgdg12+1) on aarch64-unknown-linux-gnu, compiled by gcc (Debian 12.2.0-14+deb12u1) 12.2.0, 64-bit`
- pgvector: `0.8.7`
- Host: macOS-27.3-arm64-arm-64bit (arm64, 10 CPUs).
- Commit: `ebc60e42dc2e3bfd08c403f5b75d958a561a4089`.

p99 is interpolated from the slowest points. At this sample size one slow call moves it.

| Timing | n | mean ms | p50 | p95 | p99 |
|---|---:|---:|---:|---:|---:|
| warm end-to-end | 200 | 375.21 | 275.78 | 679.87 | 693.48 |
| warm vector SQL | 200 | 21.69 | 21.62 | 22.64 | 24.38 |
| warm full-text SQL | 200 | 255.65 | 251.36 | 282.90 | 293.40 |
| concurrent end-to-end | 200 | 531.40 | 508.24 | 722.45 | 766.58 |

## Indexes on document_chunks

- `document_chunks_pkey`: `CREATE UNIQUE INDEX document_chunks_pkey ON public.document_chunks USING btree (id)`
- `idx_document_chunks_tenant_model`: `CREATE INDEX idx_document_chunks_tenant_model ON public.document_chunks USING btree (institution_id, embedding_model)`
- `ix_document_chunks_content_gin`: `CREATE INDEX ix_document_chunks_content_gin ON public.document_chunks USING gin (to_tsvector('english'::regconfig, (content)::text))`

## Vector plan

```
Limit  (cost=13427.23..13427.24 rows=5 width=24) (actual time=20.853..20.855 rows=5 loops=1)
  Buffers: shared hit=12502
  ->  Sort  (cost=13427.23..13430.35 rows=1250 width=24) (actual time=20.852..20.854 rows=5 loops=1)
        Sort Key: ((c.embedding <=> '[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.5,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,-0.5,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,-0.5,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.5,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]'::vector)), c.id
        Sort Method: top-N heapsort  Memory: 25kB
        Buffers: shared hit=12502
        ->  Result  (cost=8.18..13406.46 rows=1250 width=24) (actual time=0.010..18.395 rows=50000 loops=1)
              One-Time Filter: ((NULLIF(current_setting('app.current_institution_id'::text, true), ''::text))::uuid = 'b5866225-05ad-5cfc-908e-c22916c6a1c6'::uuid)
              Buffers: shared hit=12502
              ->  Hash Join  (cost=8.18..13403.34 rows=1250 width=1560) (actual time=0.008..10.388 rows=50000 loops=1)
                    Hash Cond: (c.report_id = r.id)
                    Buffers: shared hit=12502
                    ->  Seq Scan on document_chunks c  (cost=0.00..13250.00 rows=50000 width=1576) (actual time=0.002..6.851 rows=50000 loops=1)
                          Filter: ((embedding IS NOT NULL) AND (institution_id = 'b5866225-05ad-5cfc-908e-c22916c6a1c6'::uuid) AND ((embedding_model)::text = 'hash-test-v1@384'::text))
                          Buffers: shared hit=12500
                    ->  Hash  (cost=8.16..8.16 rows=1 width=16) (actual time=0.004..0.004 rows=1 loops=1)
                          Buckets: 1024  Batches: 1  Memory Usage: 9kB
                          Buffers: shared hit=2
                          ->  Index Scan using idx_research_reports_institution_created on research_reports r  (cost=0.14..8.16 rows=1 width=16) (actual time=0.003..0.003 rows=1 loops=1)
                                Index Cond: (institution_id = 'b5866225-05ad-5cfc-908e-c22916c6a1c6'::uuid)
                                Buffers: shared hit=2
Planning Time: 0.075 ms
Execution Time: 20.867 ms
```

## Full-text plan

```
Limit  (cost=19066.40..19066.98 rows=5 width=20) (actual time=244.735..246.337 rows=5 loops=1)
  Buffers: shared hit=12840
  ->  Gather Merge  (cost=19066.40..19089.03 rows=194 width=20) (actual time=244.734..246.335 rows=5 loops=1)
        Workers Planned: 2
        Workers Launched: 2
        Buffers: shared hit=12840
        ->  Sort  (cost=18066.37..18066.62 rows=97 width=20) (actual time=243.455..243.456 rows=5 loops=3)
              Sort Key: (ts_rank(to_tsvector('english'::regconfig, (c.content)::text), '''uniform'' & ''delta'' & ''alpha'' & ''india'''::tsquery)) DESC, c.id
              Sort Method: top-N heapsort  Memory: 25kB
              Buffers: shared hit=12840
              Worker 0:  Sort Method: top-N heapsort  Memory: 25kB
              Worker 1:  Sort Method: top-N heapsort  Memory: 25kB
              ->  Result  (cost=8.18..18064.76 rows=97 width=20) (actual time=0.203..243.242 rows=2876 loops=3)
                    One-Time Filter: ((NULLIF(current_setting('app.current_institution_id'::text, true), ''::text))::uuid = 'b5866225-05ad-5cfc-908e-c22916c6a1c6'::uuid)
                    Buffers: shared hit=12810
                    ->  Hash Join  (cost=8.18..18040.27 rows=97 width=221) (actual time=0.186..208.107 rows=2876 loops=3)
                          Hash Cond: (c.report_id = r.id)
                          Buffers: shared hit=12810
                          ->  Parallel Seq Scan on document_chunks c  (cost=0.00..18020.83 rows=3876 width=237) (actual time=0.167..207.778 rows=2876 loops=3)
                                Filter: ((institution_id = 'b5866225-05ad-5cfc-908e-c22916c6a1c6'::uuid) AND (to_tsvector('english'::regconfig, (content)::text) @@ '''uniform'' & ''delta'' & ''alpha'' & ''india'''::tsquery))
                                Rows Removed by Filter: 13790
                                Buffers: shared hit=12744
                          ->  Hash  (cost=8.16..8.16 rows=1 width=16) (actual time=0.005..0.005 rows=1 loops=3)
                                Buckets: 1024  Batches: 1  Memory Usage: 9kB
                                Buffers: shared hit=8
                                ->  Index Scan using idx_research_reports_institution_created on research_reports r  (cost=0.14..8.16 rows=1 width=16) (actual time=0.003..0.004 rows=1 loops=3)
                                      Index Cond: (institution_id = 'b5866225-05ad-5cfc-908e-c22916c6a1c6'::uuid)
                                      Buffers: shared hit=8
Planning Time: 0.083 ms
Execution Time: 246.351 ms
```
