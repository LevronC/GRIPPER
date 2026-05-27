# Technical Architecture Audit & Production-Readiness Review
**Project:** Gripper Risk Terminal  
**Auditor:** Senior Staff Software Architect  
**Classification:** Internal Engineering Review  

---

## Executive Summary
This document provides a technical audit of the Gripper Risk Terminal. While the current prototype establishes clean multi-tenant isolation, row-level security (RLS) policies, and semantic retrieval primitives, it is not yet suitable for institutional deployment (hedge funds, asset managers, or family offices). 

To achieve production readiness, the platform must bridge critical gaps across ingestion resilience, complex rules execution, cryptographic identity management, search hybridity, high-load database architecture, and SOC-2 auditability.

---

## 1. Ingestion Pipeline & Document Intelligence

### 1.1 Scanned & Image PDF Extraction (OCR)
* **Why it matters:** Institutional investment memos, legacy filings, and third-party broker reports are frequently delivered as scanned image-only PDFs or nested container packages.
* **Current Limitation:** The ingestion pipeline relies purely on PyMuPDF's (`fitz`) standard text layout extraction.
* **Failure Mode:** Uploading a scanned PDF yields zero extracted characters. This leads to empty document chunks, silent ingestion successes with empty vector mappings, and a complete failure of the compliance checks that rely on that document.
* **Target Architecture:** Integrate a pre-processing stage using `pdf2image` and an OCR engine (e.g., Tesseract OCR or AWS Textract). The pipeline should detect text density; if character count is below a 50-character threshold per page, route to the OCR worker.

### 1.2 Layout-Aware Chunking & Table Preservation
* **Why it matters:** Financial disclosures present crucial metrics (leverage ratios, sector caps, asset values) inside tables.
* **Current Limitation:** The chunker utilizes a sliding window based on arbitrary character lengths, ignoring page structures, margins, and tabular boundaries.
* **Failure Mode:** Table rows are sliced across chunk boundaries. The vector embeddings of these split tables lose context, causing semantic searches to return disjointed text segments and producing flawed compliance answers.
* **Target Architecture:** Implement a layout-aware chunking pipeline (e.g., via `LayoutParser` or Microsoft's Table-Transformer). Isolate tables, parse them into structured Markdown or HTML tables, and append the structural layout metadata directly to each generated vector chunk.

### 1.3 Multi-Format Ingestion Engine
* **Why it matters:** Investment teams draft memos in Word (`.docx`), maintain valuation models in Excel (`.xlsx`), and share notes in plain text (`.txt`).
* **Current Limitation:** The system hardcodes PDF parsing (`.pdf`) and rejects all other MIME types.
* **Failure Mode:** Blocked analyst workflows. Analysts are forced to manually export files to PDF, creating friction and increasing the likelihood that they bypass the ingestion system entirely.
* **Target Architecture:** Build a modular ingestion factory with adapter patterns:
  - `.docx` -> `python-docx`
  - `.xlsx` -> `openpyxl` (extracting sheets as structured markdown tables)
  - `.txt`/`.md` -> UTF-8 direct character reader

### 1.4 Queue Resilience: Idempotency, DLQs, and Retries
* **Why it matters:** Large-scale ingestion operations are prone to transient network failures, OOM crashes, and API timeouts.
* **Current Limitation:** The current RQ worker executes tasks sequentially without structured retry budgets, idempotency checks, or dead-letter queues (DLQ).
* **Failure Mode:** If a worker crashes mid-ingestion (e.g., due to a temporary database timeout), the file is left in a half-parsed state. Re-running the task inserts duplicate vector chunks, corrupting the semantic search space.
* **Target Architecture:**
  - Implement task idempotency by hashing the file content (SHA-256) and verifying if the hash exists in a global `processed_documents` registry before executing.
  - Configure RQ/Celery to support exponential backoff retries (e.g., 3 retries at $t \times 2$ intervals).
  - Route persistently failing tasks to a Dead-Letter Queue (DLQ) with automated PagerDuty alerting.

### 1.5 Input Security & Malware Prevention
* **Why it matters:** Uploading unvalidated files from third-party networks creates an entry point for malicious payloads.
* **Current Limitation:** File validation checks only basic PDF magic bytes and content length.
* **Failure Mode:** An analyst uploads a weaponized PDF containing an exploit targetting the server's PDF parsing library (e.g., PyMuPDF buffer overflows), resulting in remote code execution (RCE).
* **Target Architecture:** Run uploads through an isolated scanning microservice (e.g., ClamAV). Restrict file uploads to isolated container sandboxes with read-only filesystems before parsing.

---

## 2. Governance & Rules Engine

### 2.1 Domain-Specific Language (DSL) & Logical Rules Execution
* **Why it matters:** Investment Policy Statements (IPS) contain complex, conditional rules (e.g., *"No single tech position can exceed 10% of NAV unless it is a Magnificent 7 stock and the sector lead has uploaded a valuation exception memo"*).
* **Current Limitation:** Rules are evaluated using simple, hardcoded threshold comparisons in `evaluator.py`.
* **Failure Mode:** The compliance system cannot evaluate conditional exceptions, producing false-positive alerts that clutter the dashboard and erode analyst trust.
* **Target Architecture:** Implement a rules parser utilizing a JSON-based logic engine or a custom python DSL (e.g., `PyRules` or `Celery Rules`). Rules should be represented as logical ASTs (Abstract Syntax Trees) supporting nested operators (`AND`, `OR`, `NOT`, `IF-ELSE`).

### 2.2 Versioning & Approval Workflows for IPS Policies
* **Why it matters:** IPS rules change over time as fund mandates evolve or board members renegotiate limits.
* **Current Limitation:** The `ips_rules` database schema represents rules statically. Updating a rule overwrites the database row.
* **Failure Mode:** When a rule is modified, historical compliance evaluations are retroactively re-calculated using the new threshold, destroying the historic compliance audit trail.
* **Target Architecture:**
  - Implement rule temporal versioning (using `valid_from` and `valid_to` timestamps or a Git-like revision schema).
  - Enforce a dual-control approval workflow (Maker-Checker pattern): a compliance analyst proposes a rule change, but it must be cryptographically signed by a Portfolio Manager before it is activated.

### 2.3 Portfolio Snapshots & Backtesting Compliance
* **Why it matters:** Risk officers need to audit compliance historically or backtest new IPS rules against past portfolios.
* **Current Limitation:** Holdings are updated in-place. The database does not preserve the exact daily history of the portfolio.
* **Failure Mode:** Inability to reconstruct the portfolio state as of a specific date (e.g., during an SEC audit or a board review of a breach that occurred 6 months ago).
* **Target Architecture:** Introduce a daily snapshot table `portfolio_snapshots` which stores structured JSON representation of holdings, values, and compliance status. Run the IPS compliance engine over these snapshot tables during rule backtesting.

---

## 3. Authentication, Identity & Tenant Security

### 3.1 Token Lifecycle Hardening: JWT Revocation & Redis Blacklist
* **Why it matters:** If an analyst's laptop is compromised, security teams must immediately invalidate active sessions.
* **Current Limitation:** JWTs are stateless and expire purely based on time (`ACCESS_TOKEN_EXPIRE_MINUTES`). The backend lacks token revocation capabilities.
* **Failure Mode:** A compromised analyst token remains fully active and usable by an attacker until its expiration timestamp is reached, even if the user logs out.
* **Target Architecture:** Maintain a Redis-backed token blacklist. On logout, insert the JWT signature hash into Redis with an expiration matching the token's lifetime. The auth dependency must intercept every incoming request and verify the token signature is not blacklisted.

### 3.2 Enterprise Identity & Provisioning (SSO, SAML, SCIM)
* **Why it matters:** Institutional clients do not allow local username/password databases. They require authentication to be managed by centralized identity providers (Okta, Azure AD, Ping Identity).
* **Current Limitation:** Authentication relies on email/password registers stored in local tables.
* **Failure Mode:** Analysts who leave the firm retain access to the platform until an administrator manually deletes their user account in the Gripper database.
* **Target Architecture:**
  - Implement OpenID Connect (OIDC) and SAML 2.0 federation endpoints.
  - Implement a SCIM (System for Cross-domain Identity Management) listener to automatically provision, de-provision, and synchronize user roles from the client's corporate directory.

### 3.3 Fine-Grained Access Control (RBAC & ABAC)
* **Why it matters:** Analysts should not be able to resolve compliance violations or modify portfolios; these actions require different clearance levels.
* **Current Limitation:** Roles exist as text tags (`analyst`, `pm`) but are not enforced granularly across API endpoints.
* **Failure Mode:** A junior analyst can make direct POST requests to modify portfolio holdings or mark critical compliance violations as "Resolved".
* **Target Architecture:** Implement a decorator-based Attribute-Based Access Control (ABAC) layer (e.g., using FastAPI dependencies). Example:
  ```python
  @router.post("/violations/{id}/resolve")
  def resolve(id: uuid.UUID, user: User = Depends(get_current_user_with_roles(["pm", "admin"]))):
  ```

---

## 4. Semantic Retrieval & Knowledge Systems

### 4.1 Hybrid Search (Dense + Sparse)
* **Why it matters:** Financial documents contain specific numerical codes, ticker names, and precise acronyms (e.g., "TSLA", "8-K", "IPS"). Dense vector embeddings excel at semantic concepts but are notoriously poor at matching exact keywords.
* **Current Limitation:** The search engine uses purely cosine distance matches on vector embeddings.
* **Failure Mode:** Searching for a specific transaction ticker or numerical rule clause (like "Section 4.2.1") returns irrelevant chunks that are semantically similar but lack the exact keyword match.
* **Target Architecture:** Implement a hybrid search architecture combining `pgvector` dense vector search with a sparse search index (e.g., BM25 via PostgreSQL full-text search). Merge the results using Reciprocal Rank Fusion (RRF) with configurable weights.

### 4.2 Cohere/BGE Re-ranking Pipeline
* **Why it matters:** Initial vector similarity search often places highly relevant contexts lower in the top-K list due to semantic representation limits.
* **Current Limitation:** The top-K vector results are passed directly to the LLM context window.
* **Failure Mode:** The LLM misses critical details because the exact clause was ranked 9th and got pushed out of the context limit (the "lost in the middle" effect).
* **Target Architecture:** Implement a two-stage retrieval pipeline. Retrieve the top 50 candidates using hybrid search, pass them through a local Cross-Encoder re-ranker (e.g., `BAAI/bge-reranker-large` or Cohere Re-rank API), and feed the top 5 re-ranked results to the LLM.

### 4.3 Knowledge Provenance & Version Migration
* **Why it matters:** Vector databases require schema and model migrations when embedding models are upgraded.
* **Current Limitation:** Changing the embedding model requires dropping the vector database table and re-ingesting all documents.
* **Failure Mode:** Upgrading models causes system-wide downtime and temporary loss of semantic search capability.
* **Target Architecture:** Implement version-controlled vector columns (e.g., `embedding_v1`, `embedding_v2`) on the `document_chunks` table. A migration script should process old chunks asynchronously in the background. Route queries to the active version set in the configuration.

---

## 5. Infrastructure, Scaling & Reliability

### 5.1 Connection Pooling & Scaling PostgreSQL under RLS
* **Why it matters:** RLS relies on executing session variables (`SET app.current_institution_id = ...`) per connection.
* **Current Limitation:** FastAPI opens a new connection pool directly to PostgreSQL via SQLAlchemy.
* **Failure Mode:** High concurrent traffic exhausts PostgreSQL’s native connection limits, causing connection starvation and 500 errors. However, introducing a standard connection pooler (like PgBouncer) in transaction mode will leak the session variable (`app.current_institution_id`) across different users, causing severe cross-tenant data leaks.
* **Target Architecture:** 
  - Deploy PgBouncer in **Session Mode** (which safely isolates session variables but limits pooling benefits), or:
  - Configure PgBouncer in **Transaction Mode** and use PostgreSQL’s `local` parameters inside a transaction block (e.g. `SET LOCAL app.current_institution_id = ...` within `BEGIN ... COMMIT`) to ensure variables vanish when the transaction completes.

### 5.2 Observability & Distributed Tracing
* **Why it matters:** Debugging a slow RAG query or failed async ingestion job across distributed servers is impossible without centralized instrumentation.
* **Current Limitation:** Logging is console-only and unstructured.
* **Failure Mode:** A search endpoint becomes slow. Developers cannot isolate whether the bottleneck is the vector database query, the re-ranker, or the network latency to the LLM API.
* **Target Architecture:** Instrument the codebase with OpenTelemetry. Export traces to Jaeger, Datadog, or Honeycomb. Wrap database sessions, embedding generation, and LLM calls in spans.

---

## 6. Compliance, Auditability & Institutional Readiness

### 6.1 Immutable Audit Logs (SOC-2 Compliance)
* **Why it matters:** Regulatory bodies (SEC, FINRA) and institutional compliance officers require tamper-proof records of all modifications to compliance parameters, portfolios, and audit resolutions.
* **Current Limitation:** Audit logs are standard relational rows in the `governance_events` table, which can be modified or deleted by anyone with write access to the database.
* **Failure Mode:** A rogue actor modifies a portfolio to hide a breach, deletes the corresponding compliance alerts, and drops the history, leaving no record for external auditors.
* **Target Architecture:**
  - Route all audit events to an append-only write-once-read-many (WORM) storage system (e.g., AWS S3 with Object Lock enabled, or an immutable ledger like Amazon QLDB).
  - Cryptographically sign each log entry using SHA-256 chained hashing (where entry $N$ contains the hash of entry $N-1$) so any deletion or alteration breaks the validation chain.

### 6.2 Data Retention & Legal Hold Engine
* **Why it matters:** Firms are legally obligated to retain records for specific periods (e.g., SEC Rule 17a-4 requires keeping communications and files for 6 years).
* **Current Limitation:** There is no mechanism for automated deletion, data pruning, or blocking deletions under a legal hold.
* **Failure Mode:** Storage costs expand exponentially, or the firm deletes data that is active under a regulatory investigation, incurring massive fines.
* **Target Architecture:** Implement a background retention worker that soft-deletes expired records unless a `legal_hold` flag is active on the tenant.

---

## 7. Frontend & Product Experience Gaps

### 7.1 Compliance Alert Debugger & Diff Visualization
* **Why it matters:** When a violation is flagged, PMs need to see exactly *what* changed in the portfolio to trigger the breach and *why*.
* **Current Limitation:** The dashboard lists alerts and holdings statically.
* **Failure Mode:** PMs have to cross-reference multiple views or spreadsheets to understand how a 0.5% allocation change pushed the sector exposure past the limits.
* **Target Architecture:** Build a "Holdings Diff" visualization module that highlights the changes between the current allocation and the proposed sandbox allocation side-by-side, detailing the marginal impact on every active IPS constraint.

### 7.2 Collaborative Review Queues & Notifications
* **Why it matters:** Compliance breaches require multi-party resolution (e.g., analyst documents the cause, PM reviews and requests exception, compliance officer signs off).
* **Current Limitation:** Resolution is a single text-area input field.
* **Failure Mode:** Resolution discussions happen over email or Slack, fragmenting the context and leaving the compliance audit trail empty.
* **Target Architecture:** Build a collaborative timeline interface for each violation, supporting threaded comments, status transitions (Open -> Under Review -> Pending PM Sign-off -> Resolved), and real-time push notifications (via WebSockets or SSE).

---

## 8. AI/ML & Future Architecture Concerns

### 8.1 Model Cost Containment & Token Budgeting
* **Why it matters:** High-volume RAG queries can generate massive LLM provider bills if left unmonitored.
* **Current Limitation:** The explainer service calls LLM APIs directly without counting tokens, caching results, or limiting tenant-specific usage.
* **Failure Mode:** A single tenant runs automated script loops over the search endpoints, generating thousands of expensive LLM calls and racking up massive API bills overnight.
* **Target Architecture:**
  - Implement a token budgeting layer: track input/output tokens per tenant in Redis.
  - Rate limit tenants when they exceed their monthly dollar/token budgets.
  - Implement Semantic Caching (e.g., using GPTCache or Redis) to resolve identical compliance explanation queries without hitting the LLM.

### 8.2 Retrieval & Evaluation Pipeline (RAG Triad)
* **Why it matters:** You cannot confidently deploy RAG changes without measuring search quality, context relevance, and answer faithfulness.
* **Current Limitation:** Evaluators are tested manually.
* **Failure Mode:** Changing an embedding model or tweaking a prompt template silently degrades search quality, causing incorrect compliance citations.
* **Target Architecture:** Establish an offline evaluation pipeline using TruLens or Ragas. Measure:
  1. **Context Relevance**: Is retrieved context actually relevant to the query?
  2. **Groundedness/Faithfulness**: Is the LLM's explanation strictly backed by the retrieved context?
  3. **Answer Relevance**: Does the explanation actually answer the violation query?
  Run these evaluations as a CI/CD build step before merging changes to main.
