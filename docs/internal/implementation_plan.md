# Production Readiness Implementation Plan

We will implement the highest-leverage production-readiness capabilities identified in the audit. Since implementing all 8 sections fully in a single phase is not feasible, we will prioritize the core security, database, ingestion, and search features that directly harden the tenant boundaries and platform reliability.

---

## User Review Required

We propose focusing on four critical areas that directly affect the security, reliability, and accuracy of the Gripper terminal:

1. **Session Hardening & Revocation (Redis-backed Blacklist)**: Add dynamic token blacklisting on logout and intercept calls to verify token validity in real-time.
2. **PgBouncer RLS Local Transaction Isolation**: Fix the session leakage vulnerability by switching database context variable setting to transaction-scoped `SET LOCAL` statements.
3. **Ingestion Idempotency & Queue Resilience**: Prevent duplicate chunk insertions using SHA-256 file hashes and enable robust error reporting with simulated retry/DLQ states.
4. **Hybrid Search (Vector + Full-Text Search)**: Combine `pgvector` similarity search with PostgreSQL full-text search (BM25 equivalent) and merge using Reciprocal Rank Fusion (RRF) for precise keyword matching.

> [!WARNING]
> Updating database session parameters to `SET LOCAL` requires all queries modifying or fetching tenant-specific records to execute within active SQL transactions. We will wrap the FastAPI dependency accordingly.

---

## Proposed Changes

### Database & Security

#### [MODIFY] [session.py](file:///Users/levicheptoyek/Downloads/GRIPPER%20/backend/app/db/session.py)
- Update `get_db` to enforce active database transactions.
- Swap session-scoped `SET app.current_institution_id` for transaction-scoped `SET LOCAL app.current_institution_id` so that connection poolers (like PgBouncer in transaction mode) cannot leak tenant context across pooled connections.

#### [MODIFY] [security.py](file:///Users/levicheptoyek/Downloads/GRIPPER%20/backend/app/core/security.py)
- Integrate Redis connection to check for blacklisted tokens.
- Implement a helper `blacklist_token(token_jti: str, expire_seconds: int)` function.

#### [MODIFY] [deps.py](file:///Users/levicheptoyek%20/Downloads/GRIPPER/backend/app/api/deps.py) or [auth.py](file:///Users/levicheptoyek/Downloads/GRIPPER%20/backend/app/api/auth.py)
- Update `get_current_user` dependency to check Redis and reject blacklisted tokens.
- Add `/auth/logout` POST endpoint to blacklist the current JWT on the server.

### Ingestion & Search Systems

#### [MODIFY] [pipeline.py](file:///Users/levicheptoyek/Downloads/GRIPPER%20/backend/app/services/ingestion/pipeline.py)
- Calculate SHA-256 hashes of incoming files.
- Query database for existing matching document hashes before initiating parser/chunker. If a match is found, link it to the current tenant or return the existing document to avoid duplicate chunks.

#### [MODIFY] [searcher.py](file:///Users/levicheptoyek/Downloads/GRIPPER%20/backend/app/services/retrieval/searcher.py)
- Rewrite `semantic_search` to perform hybrid search:
  - Vector similarity search utilizing `pgvector` Cosine distance.
  - PostgreSQL TSVector full-text query matching standard search parameters.
  - Reciprocal Rank Fusion (RRF) merge block to calculate optimal combined scores.

---

## Verification Plan

### Automated Tests
- Execute `backend/test_rag.py` to verify that document upload, chunking, and search functionality remain fully intact and operational under the new hybrid search engine.
- Execute `backend/test_governance.py` to confirm that row-level security policy checks and compliance assertions pass successfully.
- Run a custom test script verifying that calling `/auth/logout` invalidates subsequent requests using the same JWT.

### Manual Verification
- Log in, perform a document upload, log out, and verify that the token can no longer be used to query the backend terminal.
