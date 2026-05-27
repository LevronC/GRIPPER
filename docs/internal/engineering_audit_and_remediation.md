# GRIPPER — Principal Engineer Technical Audit & Remediation Roadmap

**Classification:** Internal Engineering Review  
**Date:** May 27, 2026  
**Auditor:** Senior Staff Software Architect  
**Scope:** Full-stack review — backend, frontend, infrastructure, security, AI pipeline, database, DevOps

---

## TABLE OF CONTENTS

1. [Executive Summary](#executive-summary)
2. [System Architecture Overview](#system-architecture-overview)
3. [Part I — Technical Due Diligence Audit](#part-i--technical-due-diligence-audit)
   - [What Has Been Implemented](#1-what-has-been-implemented)
   - [What Is Partially Implemented](#2-what-is-partially-implemented)
   - [What Is Missing](#3-what-is-missing)
   - [Security + Hardening Review](#4-security--hardening-review)
   - [Production Readiness Scores](#5-production-readiness-scores)
   - [Recruiter / Interviewer Impression](#6-recruiter--interviewer-impression)
   - [Codebase Analysis](#7-codebase-analysis)
   - [Deployment + Infrastructure Review](#8-deployment--infrastructure-review)
   - [Database Review](#9-database-review)
   - [AI System Review](#10-ai-system-review)
4. [Part II — Remediation Roadmap](#part-ii--remediation-roadmap)
   - [Phase 0 — Immediate Blockers (24–48 Hours)](#phase-0--immediate-blockers-2448-hours)
   - [Phase 1 — Security Hardening (Week 1)](#phase-1--security-hardening-week-1)
   - [Phase 2 — Infrastructure & Deployment Stabilization](#phase-2--infrastructure--deployment-stabilization)
   - [Phase 3 — Database & Performance Optimization](#phase-3--database--performance-optimization)
   - [Phase 4 — AI / RAG System Improvements](#phase-4--ai--rag-system-improvements)
   - [Phase 5 — Frontend Refactor & Product Maturity](#phase-5--frontend-refactor--product-maturity)
   - [Phase 6 — Enterprise & Long-Term Readiness](#phase-6--enterprise--long-term-readiness)
5. [Final Summary](#final-summary)
   - [Top 10 Fixes by Impact](#top-10-fixes-by-impact)
   - [Realistic Timeline for a Junior Engineer](#realistic-timeline-for-a-junior-engineer)
   - [Interview Value After Each Phase](#interview-value-after-each-phase)
   - [Do Not Recommend](#do-not-recommend)

---

## EXECUTIVE SUMMARY

GRIPPER is a genuinely ambitious project for its scope. The architecture tackles real distributed systems problems — multi-tenant Row-Level Security, hybrid RAG search with Reciprocal Rank Fusion, deterministic compliance engines, JWT revocation via Redis — things that most junior-to-mid engineers have never touched. At a portfolio level, this project signals substantially more than a tutorial build.

However, it has a cluster of critical and medium-severity issues that would make any experienced principal engineer reject it from production deployment today. Several are security-breaking. A few are performance-breaking. The frontend intelligence features are outright faked. And there are architectural decisions that will become technical debt at scale.

**Bottom line: Impressive for what it is. Not production-ready. Resume-worthy with honest framing.**

---

## SYSTEM ARCHITECTURE OVERVIEW

**Product:** Multi-tenant investment compliance terminal for university investment funds (.edu institutions)

**Stack:**
- **Frontend:** React 19, TypeScript, Vite 8, Tailwind 4, Zustand, React Router 7, Framer Motion
- **Backend:** FastAPI, SQLAlchemy 2, Alembic, PostgreSQL + pgvector, Redis + RQ workers
- **Deploy:** Vercel (frontend SPA) + `api/index.py` mounting FastAPI as a serverless function (currently broken for core features)

**Routes:** `/` landing, `/docs`, `/app` terminal, `/api/docs` OpenAPI

**Auth:** `.edu` registration, 6-digit verify (console in dev), JWT in `localStorage` (`gripper_token`), Redis token blacklist on logout, bcrypt passwords

**Tenancy:** PostgreSQL RLS via `SET LOCAL app.current_institution_id`; JWT sets institution from user record

**CI:** `.github/workflows/ci.yml` — Node 22 lint/build; Python 3.12 ruff + pytest with real pgvector Postgres + Redis services

---

# PART I — TECHNICAL DUE DILIGENCE AUDIT

---

## 1. WHAT HAS BEEN IMPLEMENTED

### Backend Systems

- FastAPI application with lifespan hooks, structured routing, and OpenAPI docs behind a custom `/docs` route
- Multi-tenant PostgreSQL architecture with **Row-Level Security (RLS)** enforced at the database level via `SET LOCAL app.current_institution_id` — architecturally sophisticated and non-trivial
- Alembic migration chain (6 migrations) that programmatically creates RLS policies, enables `FORCE ROW LEVEL SECURITY`, and handles the full schema including pgvector
- Role-Based Access Control with 7 distinct role levels (`analyst`, `sector_lead`, `pm`, `faculty`, `trustee`, `admin`) and role-scoped `RoleChecker` FastAPI dependency
- JWT authentication: bcrypt password hashing, JTI (JWT ID) generation per token, Redis-backed token blacklist for server-side revocation on logout
- `.edu` email restriction enforced at the Pydantic validator level
- 6-digit verification code flow (register → verify → login) and password reset flow
- Portfolio CRUD, Holdings upsert, IPS rules retrieval
- Document upload endpoint: magic byte validation (`%PDF-`), 10MB size cap, MIME + extension check, SHA-256 deduplication
- Redis Queue (RQ) async worker for document ingestion background processing
- Full RAG ingestion pipeline: PyMuPDF parsing → sliding-window chunking with overlap → BAAI/bge-small-en-v1.5 embeddings (384-dim) → pgvector storage
- **Hybrid semantic search**: pgvector cosine similarity + PostgreSQL `to_tsvector`/`ts_rank` FTS, fused via **Reciprocal Rank Fusion (RRF, K=60)** — senior-level RAG engineering
- Compliance evaluation engine: `single_position_cap`, `sector_exposure_cap`, `liquidity_constraint` rules with violation reconciliation (create / update existing / auto-resolve)
- Portfolio simulation endpoint (what-if, read-only, no DB mutations)
- RAG-driven compliance violation explanation: maps event type → semantic query → retrieves supporting analyst report context
- Custom `@observe_time` decorator emitting structured JSON telemetry logs
- Health check endpoints including `/health/db`

### Frontend Systems

- React 19 + TypeScript + Vite 8 + Tailwind 4 + Framer Motion SPA
- Zustand state management with proper TypeScript interfaces
- React Router 7 with three routes: landing, docs, app terminal
- Full auth flow: register, verify, login, logout, forgot-password, reset-password — all wired to real backend
- Dashboard with tabs: Compliance, Portfolio, Ingestion, Semantic Search — all wired to real backend
- `ExplainabilityDrawer` component that calls the real `/violations/{id}/explain` endpoint
- `parseApiError` utility with proper FastAPI validation error handling
- JWT + user data persisted in `localStorage`, restored on page reload
- Landing page with Navbar, Hero, Features, Products, ProSection, Community, Footer sections

### DevOps / CI

- GitHub Actions CI: Node 22 frontend lint+build, Python 3.12 backend tests
- CI uses **real pgvector/pgvector:pg16 Docker service** and Redis:7 service — integration tests run against actual database
- Alembic migration run in CI before tests
- Ruff linting on critical backend modules
- `pytest --cov` with coverage reporting
- Vercel deployment configured: `vercel.json` with SPA rewrites + Python function at `api/index.py`

### Database

- Full relational schema: `institutions`, `users`, `portfolios`, `holdings`, `research_reports`, `document_chunks` (pgvector), `meetings`, `ips_rules`, `governance_events`
- Proper foreign keys with `ondelete=CASCADE`/`SET NULL` semantics
- RLS policies on all 7 tenant-dependent tables

---

## 2. WHAT IS PARTIALLY IMPLEMENTED

### Fake / Mock Frontend Features

The "Intelligence" and "Earnings" tabs in `GripperDashboard.tsx` (1,546 lines) are **complete UI mocks** with no backend connection. They render static placeholder data. This is a deception risk during demos.

### No Real Email Delivery

Both `register` and `forgot_password` use `print(f"DEBUG: Verification code for {user.email} is: {v_code}")`. In production:
- Verification codes appear in server logs, not user inboxes
- Any user who registers through the production UI is permanently stuck at the unverified state
- No SMTP, SendGrid, or SES integration exists anywhere in the codebase

### Upload Storage on Vercel

`config.py` sets `UPLOAD_DIR = "/tmp/gripper_uploads"` when running on Vercel. The `/tmp` filesystem on Vercel serverless functions is **ephemeral and per-invocation** — files written in one invocation are invisible to another. The entire upload → ingestion pipeline silently breaks on Vercel.

### Redis Queue on Vercel

RQ workers require a persistent long-running process (`rq worker`). Vercel serverless functions are request-scoped and terminate after the response. Background ingestion jobs are queued but never consumed in the Vercel deployment.

### Missing pgvector Index

The `document_chunks.embedding` column has no HNSW or IVFFlat index. Every semantic search performs a **full sequential table scan** via `<=>` cosine distance. This is O(n) and will collapse at production document volume.

### Missing GIN Index for FTS

The code comment in `searcher.py` explicitly notes: *"Ensure a GIN index exists on to_tsvector('english', content) for production speed"* — but no such index is created in any migration.

### Meeting Model Exists, No API Exists

`Meeting` model is defined with transcript, summary, and decisions JSON fields. Zero API endpoints exist for meetings.

### Permissions JSON Column Unused

`User.permissions` is a JSON column meant for granular permission grants. It is never read or evaluated anywhere in the codebase.

### "AI Explanation" Is a String Template

The `generate_violation_explanation` function returns a hardcoded f-string template, not an LLM-generated explanation. There is no LLM call anywhere in the codebase. The "AI-powered" compliance explainability is a presentation layer illusion.

---

## 3. WHAT IS MISSING

### Security
- No rate limiting on any endpoint — trivially brute-forceable auth
- No `Content-Security-Policy`, `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy` headers
- No CSRF protection
- No input length validation on freeform text fields
- No virus scanning on PDF uploads

### Architecture
- No API versioning (`/v1/`)
- No request correlation IDs / trace IDs
- No distributed tracing (OpenTelemetry)
- No centralized structured logging
- No alerting infrastructure
- No real email service

### Database
- No composite indexes on common query patterns
- No `portfolio_snapshots` table — holdings modified in-place, no historical audit trail
- No IPS rule versioning — rule changes retroactively corrupt historical compliance records
- No soft-delete pattern on any table

### Compliance Engine
- Only 3 rule types — real IPS documents contain dozens of constraint types
- No DSL for complex conditional rules
- No exception/waiver workflow

### Testing
- Zero frontend tests (no Vitest, no Playwright, no RTL)
- Zero integration tests for the RAG pipeline end-to-end
- No load/stress tests

### DevOps
- No Docker Compose for local development
- No Dockerfile for the backend
- No environment separation (no staging environment)
- No deployment rollback strategy documented
- No database backup strategy

---

## 4. SECURITY + HARDENING REVIEW

### CRITICAL

**1. User Can Self-Register as Any Role Including Admin**

```python
# backend/app/api/auth.py:76-81
valid_roles = ["analyst", "sector_lead", "pm", "faculty", "trustee", "admin"]
if user_in.role not in valid_roles:
```

The `role` field is accepted from user input with no restriction. Any user can POST `{"role": "admin"}` and gain unrestricted system access. This nullifies all RBAC protection. **Most dangerous code in the codebase.**

---

**2. Hardcoded Default SECRET_KEY**

```python
# backend/app/core/config.py:28
SECRET_KEY: str = os.getenv("SECRET_KEY", "gripper_super_secret_signing_key_2026")
```

If `SECRET_KEY` is not set in the environment, every JWT in production is signed with a publicly known key. An attacker can forge tokens for any user, including admins.

---

**3. CORS Misconfiguration**

```python
# backend/app/main.py:72-77
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
```

`allow_credentials=True` with `allow_origins=["*"]` is explicitly rejected by browsers per the CORS spec. Should be locked to the specific frontend domain.

---

**4. JWT in localStorage**

```typescript
// src/store/useStore.ts:179
localStorage.setItem('gripper_token', data.access_token);
```

Storing JWTs in `localStorage` exposes them to any XSS attack. For a financial compliance platform, tokens should be in `httpOnly`, `Secure`, `SameSite=Strict` cookies.

---

**5. Verification Codes Printed to Console**

```python
# backend/app/api/auth.py:141
print(f"DEBUG: Verification code for {db_user.email} is: {v_code}")
```

`print()` statements in FastAPI route handlers appear in production server logs. If those logs are aggregated by any log platform, **verification codes and password reset codes are permanently stored in plaintext in your logging infrastructure.** Both `register` and `forgot_password` have this.

---

**6. New SQLAlchemy Engine Created Per Request**

```python
# backend/app/api/deps.py:59
super_engine = create_engine(settings.SUPERUSER_DATABASE_URL, pool_pre_ping=True)
```

`get_current_user()` calls `create_engine()` on **every authenticated request**. Under moderate load (50 req/s), this creates hundreds of dangling connection pools, exhausting PostgreSQL's `max_connections` and crashing the database.

### HIGH

**7. User Enumeration via forgot_password**

Returns HTTP 404 specifically for unknown emails, allowing attackers to enumerate registered accounts.

**8. HTTP 418 Easter Egg**

```python
# backend/app/api/auth.py:171
status.HTTP_418_IM_A_TEAPOT if credentials.password == "test_pot" else status.HTTP_401_UNAUTHORIZED,
```

A fingerprinting beacon that identifies the codebase to any attacker. Completely inappropriate in a financial platform.

**9. No Password Strength Enforcement at Registration**

`reset_password` validates 8-character minimum. `register_user` has **no minimum length or complexity check**.

**10. `SET LOCAL` Worker Context (RLS Bypass Risk)**

```python
# backend/app/workers/tasks.py:16
db.execute(text("SET app.current_institution_id = :id"), ...)
```

The worker uses `SET` (session-scoped) not `SET LOCAL` (transaction-scoped). In a connection-pooled environment, this session variable can persist and leak to a different tenant's request.

**11. Generic 500 Error Exposure**

Multiple endpoints catch bare `Exception as e` and return `str(e)` in the HTTP response body, leaking internal stack frames, database table names, and library internals.

### MEDIUM

- `ACCESS_TOKEN_EXPIRE_MINUTES = 1440` (24 hours) — long for a financial compliance system
- No pagination on `list_documents` — returns all documents in a single query
- `SEED_DEMO_USER = True` by default seeds known credentials (`analyst@stetson.edu` / `Gripp3rDemo!`)
- Post-ingestion PDF files are never deleted from disk

---

## 5. PRODUCTION READINESS SCORES

| Category | Score | Notes |
|---|---|---|
| Frontend Engineering | 6/10 | Clean stack, good TypeScript discipline, but GripperDashboard is a 1,546-line monolith, zero tests, mock intelligence features |
| Backend Engineering | 6.5/10 | Impressive RLS/RQ/RAG architecture, but critical security bugs in auth, engine-per-request performance bomb |
| Architecture Quality | 7/10 | Multi-tenant RLS, hybrid RAG, event reconciliation — genuinely thoughtful. Vercel/worker mismatch is a conceptual gap |
| Security | 3/10 | Self-selecting admin role at registration, default secret key, JWT in localStorage, console-logged OTP codes |
| Scalability | 4/10 | Engine-per-request kills the database. No pgvector index. No GIN index. No pagination. No cache layer |
| DevOps Maturity | 5/10 | CI is legitimately good (real DB services, coverage). No Docker Compose, no staging, no secrets management |
| Database Design | 7/10 | RLS policies, cascade rules, proper UUIDs, pgvector integration, Alembic. Missing: composite indexes, snapshots, rule versioning |
| AI Engineering | 7.5/10 | RRF hybrid search is senior-level. Deduplication in pipeline. Observability decorator. Missing: HNSW index, real LLM call |
| Code Quality | 6/10 | Generally clean. Engine-per-request, bare except, print-based debugging drag it down |
| UI/UX | 7/10 | Polished landing page, functional dashboard, Framer Motion. Intelligence tab is misleading mock |
| Hiring/Interview Impressiveness | 7.5/10 | RLS implementation, RRF, compliance reconciliation logic are genuinely differentiating |
| Startup Readiness | 3/10 | Security issues and broken Vercel deployment prevent launch |
| Enterprise Readiness | 2/10 | No SSO, no SOC-2 audit logs, no SCIM, no immutable audit trail |

---

## 6. RECRUITER / INTERVIEWER IMPRESSION

### What Would Impress a Senior Engineer

- **PostgreSQL RLS with `SET LOCAL app.current_institution_id`**: Most engineers who "do multi-tenancy" use an `institution_id = ?` WHERE clause. Pushing this into the database kernel is architecturally correct for financial data isolation.
- **Reciprocal Rank Fusion (RRF) for hybrid RAG**: Knowing that dense + sparse retrieval needs fusion, choosing RRF over naive score blending, and correctly setting K=60 from the literature — this is what senior ML engineers do.
- **JWT revocation via Redis JTI blacklist**: Correctly identifies the stateless JWT problem and solves it without session storage.
- **SHA-256 deduplication in the ingestion pipeline**: Prevents duplicate vector chunk insertion — a real production concern.
- **Governance event reconciliation**: The logic that diffs detected violations against DB state, auto-resolves cleared violations, and dispatches alerts is event-sourcing-adjacent thinking.
- **The internal `production_readiness_audit.md`**: Self-awareness about what's missing, written at staff engineer quality — this alone signals maturity.

### What Looks Junior-Level

- **HTTP 418 easter egg in auth.py**: Completely inappropriate in a production financial system.
- **print() for verification codes**: Relying on `print()` instead of a proper logging framework or email service is a hack-week shortcut.
- **1,546-line monolithic component**: `GripperDashboard.tsx` is a classic junior-developer "god component." No experienced frontend engineer would merge this.
- **User self-selects admin role at registration**: Suggests RBAC was designed as a UI concern rather than a security boundary.
- **Engine-per-request in `deps.py`**: Caught immediately in any code review at a real company.
- **`except Exception: pass` in `/institutions`**: Silent error swallowing is a disqualifying code smell at FAANG.

### What Looks Copied/Tutorial-Based

- The landing page components (Hero, Features, Products) have the standard SaaS structure that every Tailwind-based tutorial produces.
- The Zustand store pattern is clean but entirely conventional.
- The basic FastAPI CRUD endpoints in `main.py` are boilerplate.

### What to Highlight on a Resume

- "Implemented PostgreSQL Row-Level Security (RLS) with session-variable-based tenant isolation across 7 tables in a multi-institutional SaaS compliance platform"
- "Built hybrid RAG retrieval pipeline combining pgvector cosine similarity and PostgreSQL full-text search with Reciprocal Rank Fusion (K=60), achieving semantic + keyword precision for financial document queries"
- "Designed deterministic compliance engine with violation lifecycle reconciliation (detect, persist, auto-resolve) against configurable IPS rules; integrated with vector-retrieval explainability layer"
- "Implemented JWT revocation via Redis JTI blacklist with TTL-aware key expiry"

### What to Fix Before Demoing

1. Remove the HTTP 418 easter egg
2. Remove all `print()` statements with credential data
3. Force `SECRET_KEY` to be required (no default)
4. Restrict role assignment at registration (no admin via self-registration)
5. Label Intelligence/Earnings tabs as "Coming Soon" or hide them
6. Fix the CORS configuration

---

## 7. CODEBASE ANALYSIS

### Folder Structure

```
GRIPPER/
├── api/index.py              # Vercel serverless entrypoint (thin wrapper)
├── backend/
│   ├── app/
│   │   ├── api/              # Auth + endpoint routers
│   │   ├── core/             # Config, security, RBAC, Redis, observability
│   │   ├── db/               # Session, migrations, seed
│   │   ├── models/           # SQLAlchemy models
│   │   ├── schemas/          # Pydantic schemas
│   │   ├── services/         # Domain logic (embeddings, governance, ingestion, retrieval)
│   │   └── workers/          # RQ task definitions
│   └── migrations/           # Alembic
└── src/
    ├── components/           # GripperDashboard (monolith), ExplainabilityDrawer
    ├── landing/              # Landing page components
    ├── lib/                  # api.ts, routes.ts, defaultInstitutions.ts
    ├── pages/                # LandingPage, DocsPage
    └── store/                # Zustand
```

The backend structure is genuinely clean. Service layer separation is proper — `services/governance/`, `services/retrieval/`, `services/ingestion/` are appropriately bounded. `core/` is not polluted with business logic.

The frontend structure is undersized. Putting the entire terminal application into two files does not scale.

### Key Code Quality Issues

- Routes split between `app/main.py` (CRUD routes on the app instance directly) and `app/api/endpoints.py` (via `APIRouter`) — inconsistency
- `getHeaders()` closure inside the Zustand store creator can produce stale reads
- `except Exception: pass` in `list_institutions` silently swallows errors and falls back to hardcoded data

---

## 8. DEPLOYMENT + INFRASTRUCTURE REVIEW

### The Core Vercel Problem

The Vercel architecture has three fundamental incompatibilities with this backend:

| Requirement | Vercel Serverless | Status |
|---|---|---|
| Persistent RQ worker process | Not possible — functions are ephemeral | **Broken** |
| `/tmp` file storage between invocations | Ephemeral per function instance | **Broken** |
| Embedding model load (~130MB) in 60s timeout | Cold starts exceed timeout | **Broken** |

The generator already detects this: if `VERCEL == "1"`, it raises `ModuleNotFoundError` and falls back to a SHA-256 hash-based fake embedding. Every document ingested on Vercel is indexed with meaningless embeddings and all semantic search returns nonsense.

### CI Pipeline Assessment

The GitHub Actions CI is legitimately well-constructed:
- Uses `pgvector/pgvector:pg16` container service, not SQLite mocks — catches real RLS bugs
- Redis service included
- Alembic migrations run before tests
- This is notably better than most portfolios which mock the database entirely

### Missing Infrastructure

- No Docker Compose for local development
- No Dockerfile for the backend
- No staging environment
- No environment variable validation at startup
- No rollback procedure

---

## 9. DATABASE REVIEW

### Schema Quality: Good

Proper UUIDs as primary keys, UTC timestamps with `TIMEZONE('utc', NOW())`, normalized relational structure, appropriate JSON columns for semi-structured data.

### RLS Implementation: Strong

The RLS policies in the migration are correctly scoped. `FORCE ROW LEVEL SECURITY` is applied. The `NULLIF(..., '')::uuid` pattern correctly handles empty string contexts.

### Missing Indexes (Critical for Performance)

| Table | Missing Index | Impact |
|---|---|---|
| `document_chunks.embedding` | HNSW or IVFFlat (pgvector) | Every semantic search is O(n) full table scan |
| `document_chunks.content` | GIN on `to_tsvector('english', content)` | Full-text search is O(n), not O(log n) |
| `governance_events(portfolio_id, resolved)` | Composite B-tree | Violation queries scan the full events table |
| `research_reports(institution_id, status)` | Composite B-tree | Document listing queries are unoptimized |
| `holdings(portfolio_id)` | B-tree | Holdings fetch per portfolio needs this |

### Holdings Upsert Problem

The holdings update endpoint deletes all holdings and re-inserts them, destroying holding IDs. `governance_events.holding_id` foreign keys become `NULL` via `ON DELETE SET NULL`. Historical violations permanently lose their position context.

### No Audit History

Holdings are mutable in-place. No `portfolio_snapshots` table. Cannot reconstruct portfolio state as of a given date — a compliance audit failure for any real regulatory environment.

---

## 10. AI SYSTEM REVIEW

### What Is Real vs. Fake

| Feature | Reality |
|---|---|
| Hybrid RAG retrieval (pgvector + FTS + RRF) | **Real** — correctly implemented |
| BGE query embedding with instruction prefix | **Real** — `"Represent this sentence for searching relevant passages: {query}"` |
| BGE document embedding | **Real** — symmetric model, no prefix needed for documents |
| Fallback embedding on Vercel | **Fake** — SHA-256 hash-based deterministic vector with no semantic meaning |
| "AI explanation" in `generate_violation_explanation` | **Fake** — a Python f-string template, not an LLM |
| Intelligence dashboard tab | **Fake** — static mock UI with no backend |
| Earnings tab | **Fake** — static mock UI with no backend |

### RAG Pipeline Quality: 7.5/10

**Strengths:**
- Hybrid retrieval (pgvector cosine + PostgreSQL `ts_rank`) is architecturally correct
- RRF K=60 is the canonical parameter from the original RRF paper — not cargo-culted
- Tenant-scoped retrieval ensures strict data isolation through the RAG layer
- SHA-256 deduplication prevents duplicate vector chunks from re-uploads
- Batch embedding generation processes the entire document in one model call

**Weaknesses:**
1. No HNSW index — all pgvector queries are exact-scan O(n)
2. No re-ranker — retrieved chunks go directly to the explainability template without cross-encoder scoring
3. "AI explanation" is a Python f-string — the marquee AI feature is not AI
4. No RAG evaluation pipeline (Ragas, TruLens)
5. `observe_time` logs to console with emoji — not production-appropriate

---

# PART II — REMEDIATION ROADMAP

---

## PHASE 0 — IMMEDIATE BLOCKERS (24–48 HOURS)

These five issues can compromise security, leak tenant data, crash the database under load, or make the entire deployment non-functional. Fix before any demo, any public URL share, and certainly before any production deployment.

---

### BLOCKER 0.1 — User Can Self-Register as Any Role Including Admin

**1. Problem**
The registration endpoint accepts `role` as a user-supplied field and validates it against a whitelist that includes `"admin"`. Any unauthenticated person can POST `{"role": "admin"}` and gain unrestricted system access.

**2. Why It Is Dangerous**
This completely nullifies the RBAC system. All `RoleChecker` dependencies, all `ADMIN_ROLES` guards, all endpoint authorization is bypassed by anyone who reads the API schema. It is a single curl command away.

**3. Files Involved**
- `backend/app/api/auth.py` — lines 76–81

**4. Exact Implementation Strategy**

In `auth.py`, split roles into self-registrable vs. admin-provisioned:

```python
# Roles a user can choose at self-registration
SELF_REGISTRATION_ROLES = ["analyst", "sector_lead", "faculty"]
# All valid roles (for admin provisioning only)
ALL_ROLES = ["analyst", "sector_lead", "pm", "faculty", "trustee", "admin"]
```

Replace the existing role check in `register_user`:

```python
if user_in.role not in SELF_REGISTRATION_ROLES:
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Self-registration is limited to: {', '.join(SELF_REGISTRATION_ROLES)}. "
               f"Contact your institution administrator to be assigned a privileged role.",
    )
```

Add an admin-only endpoint for role upgrades:

```python
@app.patch("/users/{user_id}/role")
def update_user_role(
    user_id: uuid.UUID,
    new_role: str,
    db: Session = Depends(get_db),
    current_user=Depends(RoleChecker(ADMIN_ROLES)),
):
    if new_role not in ALL_ROLES:
        raise HTTPException(status_code=400, detail="Invalid role.")
    with get_superuser_session() as super_db:
        user = super_db.query(models.User).filter(models.User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found.")
        user.role = new_role
        super_db.commit()
    return {"id": str(user_id), "role": new_role}
```

**5. Migration Risk:** Low. Existing users in the database are not touched.

**6. Estimated Difficulty:** 2/10

**7. Validation Steps**
```bash
# Must return 400
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"attacker@stetson.edu","password":"Test1234","institution_id":"...","role":"admin"}'

# Must return 400
curl -X POST http://localhost:8000/auth/register \
  -d '...{"role":"pm"}...'

# Must succeed
curl -X POST http://localhost:8000/auth/register \
  -d '...{"role":"analyst"}...'
```

---

### BLOCKER 0.2 — Default Hardcoded SECRET_KEY

**1. Problem**
`SECRET_KEY` defaults to `"gripper_super_secret_signing_key_2026"` if the environment variable is not set.

**2. Why It Is Dangerous**
JWT forgery. An attacker with the known secret key can create a token for any user ID, sign it with the known key, and authenticate as that user. The Redis blacklist does not protect against this.

**3. Files Involved**
- `backend/app/core/config.py` — line 28

**4. Exact Implementation Strategy**

```python
# backend/app/core/config.py
import secrets

class Settings(BaseSettings):
    SECRET_KEY: str = os.getenv("SECRET_KEY", "")
    # ...

settings = Settings()

_KNOWN_INSECURE_KEYS = {
    "",
    "gripper_super_secret_signing_key_2026",
    "change-me-in-production",
    "secret",
    "dev",
}
if settings.SECRET_KEY in _KNOWN_INSECURE_KEYS:
    raise RuntimeError(
        "SECRET_KEY is not set or is using an insecure default. "
        "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
    )
```

Update `backend/.env.example`:
```
SECRET_KEY=change-me-generate-with-python-c-import-secrets-print-secrets-token-hex-32
```

**5. Migration Risk:** Zero for new deployments. Existing production deployments using the default key: all existing JWTs become invalid (users log in again — correct behavior, the old tokens were compromised).

**6. Estimated Difficulty:** 1/10

**7. Validation Steps**
```bash
# Without SECRET_KEY — must raise RuntimeError, not start
unset SECRET_KEY && python -c "from app.core.config import settings"

# With valid key — must start normally
SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))") \
  python -c "from app.core.config import settings; print('OK')"
```

---

### BLOCKER 0.3 — SQLAlchemy Engine Created On Every Authenticated Request

**1. Problem**
`get_current_user()` in `deps.py` calls `create_engine(...)` inside the function body (line 59). This runs on every authenticated request.

**2. Why It Is Dangerous**
Each `create_engine()` creates a new connection pool. Under any real load, this creates N pools for N concurrent requests, exhausting PostgreSQL's `max_connections` (default: 100) and crashing the database for all tenants.

**3. Files Involved**
- `backend/app/api/deps.py` — lines 59–61

**4. Exact Implementation Strategy**

Import and reuse the cached session factory already in `auth.py`:

```python
# backend/app/api/deps.py

# REMOVE:
# super_engine = create_engine(settings.SUPERUSER_DATABASE_URL, pool_pre_ping=True)
# SuperSession = sessionmaker(bind=super_engine)
# with SuperSession() as super_db:

# REPLACE WITH:
from app.api.auth import get_superuser_session

def get_current_user(...):
    if token_creds:
        # ... JWT decode, blacklist check ...
        with get_superuser_session() as super_db:  # reuses the cached engine
            user = super_db.query(models.User).filter(
                models.User.id == uuid.UUID(user_id)
            ).first()
        # ... rest unchanged
```

**5. Migration Risk:** None. Pure performance fix with identical behavior.

**6. Estimated Difficulty:** 1/10

**7. Validation Steps**
```bash
# Before: watch connection count spike per request
psql -c "SELECT count(*) FROM pg_stat_activity WHERE state = 'active';"
# Run 10 concurrent authenticated requests, observe count

# After: connection count stays bounded at pool_size
```

---

### BLOCKER 0.4 — Verification and Reset Codes Printed to Console Logs

**1. Problem**
`auth.py` prints 6-digit verification and password reset codes to stdout inside route handlers (lines 141, 265).

**2. Why It Is Dangerous**
Anyone with log access — a disgruntled employee, a compromised CI/CD system, a billing viewer on Vercel — can read any user's current verification or password reset code. The verification system is security theater.

**3. Files Involved**
- `backend/app/api/auth.py` — lines 141, 265

**4. Exact Implementation Strategy**

Add to `config.py`:
```python
DEBUG_PRINT_CODES: bool = os.getenv("DEBUG_PRINT_CODES", "false").lower() in ("1", "true", "yes")
```

Replace both `print()` calls:
```python
import logging
logger = logging.getLogger(__name__)

# In register_user (line 141):
if settings.DEBUG_PRINT_CODES:
    logger.warning(
        "DEBUG_PRINT_CODES is enabled — verification code for %s: %s. DISABLE IN PRODUCTION.",
        db_user.email, v_code
    )
else:
    logger.info("Verification code issued for %s (code not logged)", db_user.email)

# In forgot_password (line 265):
if settings.DEBUG_PRINT_CODES:
    logger.warning(
        "DEBUG_PRINT_CODES is enabled — reset code for %s: %s. DISABLE IN PRODUCTION.",
        payload.email, reset_code
    )
else:
    logger.info("Password reset code issued for %s (code not logged)", payload.email)
```

Set `DEBUG_PRINT_CODES=true` in `backend/.env` (local dev), `false` in production.

**5. Migration Risk:** None. Local dev behavior preserved via env var flag.

**6. Estimated Difficulty:** 1/10

**7. Validation Steps**
```bash
# With DEBUG_PRINT_CODES=false — code must not appear in logs
# With DEBUG_PRINT_CODES=true — code visible at WARNING level

# Verify no raw print() calls remain:
grep -n "print.*code.*:" backend/app/api/auth.py  # should return nothing
```

---

### BLOCKER 0.5 — HTTP 418 Easter Egg in Authentication

**1. Problem**
Line 171 of `auth.py` contains `status.HTTP_418_IM_A_TEAPOT if credentials.password == "test_pot"`.

**2. Why It Is Dangerous**
It identifies the exact codebase to any attacker probing the API and signals that no security review has been done. Completely inappropriate in a financial compliance platform.

**3. Files Involved**
- `backend/app/api/auth.py` — line 171

**4. Exact Implementation Strategy**
```python
# Remove the ternary entirely:
# BEFORE:
status.HTTP_418_IM_A_TEAPOT if credentials.password == "test_pot" else status.HTTP_401_UNAUTHORIZED,
# AFTER:
status.HTTP_401_UNAUTHORIZED,
```

**5. Migration Risk:** None.

**6. Estimated Difficulty:** 1/10

**7. Validation Steps**
```bash
curl -X POST http://localhost:8000/auth/login \
  -d '{"email":"anyone@stetson.edu","password":"test_pot"}'
# Must return 401, not 418
```

---

### Phase 0 Execution Order

1. **0.2 first** — app must not start with an insecure key before any other change
2. **0.1** — stops privilege escalation before any new test accounts are created
3. **0.4** — stop leaking codes to any log system before new registrations happen
4. **0.5** — cosmetic but takes 30 seconds
5. **0.3** — safe anytime, do last so auth changes are stable first

### Rollback Concerns

All Phase 0 changes are small, isolated, and non-destructive. None touch the database schema. `git revert` is safe for any of them. The `SECRET_KEY` hardening is the only change that invalidates existing JWTs — this is intentional.

### Expected Outcome After Phase 0

- No user can escalate to admin via self-registration
- No known-default keys can be used to forge JWTs
- PostgreSQL connection pool is bounded and stable under load
- Verification codes no longer appear in production logs
- No fingerprinting beacon in auth responses

---

## PHASE 1 — SECURITY HARDENING (WEEK 1)

---

### Task 1.1 — CORS Lockdown

**Priority:** Critical

**Rationale:** `allow_origins=["*"]` with `allow_credentials=True` is invalid per CORS spec.

**Implementation:**

```python
# backend/app/core/config.py
ALLOWED_ORIGINS: list[str] = [
    o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")
]

# backend/app/main.py
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Institution-ID"],
)
```

In production env: `ALLOWED_ORIGINS=https://gripper.vercel.app`

**Deployment Consideration:** Set `ALLOWED_ORIGINS` in the Vercel/Railway environment panel before deploying.

---

### Task 1.2 — Rate Limiting

**Priority:** High

**Rationale:** No rate limiting exists on any endpoint. Brute force and credential stuffing are trivially executable.

**Implementation:**

```bash
pip install slowapi
```

```python
# backend/app/main.py
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
```

```python
# backend/app/api/auth.py
from slowapi import Limiter
from slowapi.util import get_remote_address
from fastapi import Request

limiter = Limiter(key_func=get_remote_address)

@router.post("/login", response_model=Token)
@limiter.limit("10/minute")
def login_user(request: Request, credentials: UserLogin):
    ...

@router.post("/register", status_code=201)
@limiter.limit("5/minute")
def register_user(request: Request, user_in: UserRegister):
    ...

@router.post("/forgot-password")
@limiter.limit("3/minute")
def forgot_password(request: Request, payload: ForgotPasswordRequest):
    ...
```

---

### Task 1.3 — Password Strength Enforcement at Registration

**Priority:** Medium

**Implementation:**

```python
# backend/app/api/auth.py
def validate_password_strength(password: str) -> str:
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters.")
    if not any(c.isupper() for c in password):
        raise ValueError("Password must contain at least one uppercase letter.")
    if not any(c.isdigit() for c in password):
        raise ValueError("Password must contain at least one number.")
    return password

class UserRegister(BaseModel):
    email: EmailStr
    password: str
    institution_id: uuid.UUID
    role: str

    @validator("password")
    def validate_pwd(cls, v):
        return validate_password_strength(v)
```

Use the same `validate_password_strength` function in `ResetPasswordRequest` — no duplication.

---

### Task 1.4 — Fix User Enumeration in `forgot_password`

**Priority:** Medium

**Implementation:**

```python
@router.post("/forgot-password")
def forgot_password(payload: ForgotPasswordRequest):
    with get_superuser_session() as super_db:
        user = super_db.query(models.User).filter(
            models.User.email == payload.email
        ).first()
        
        if user and user.is_verified:
            reset_code = "".join(random.choices(string.digits, k=6))
            user.verification_code = reset_code
            super_db.commit()
            if settings.DEBUG_PRINT_CODES:
                logger.warning("Reset code for %s: %s", payload.email, reset_code)

    # Always return 200 regardless of whether user exists
    return {"message": "If an account exists for that email, a reset code has been sent."}
```

---

### Task 1.5 — Secure Error Handling

**Priority:** Medium

Create `backend/app/core/errors.py`:

```python
import logging, uuid

logger = logging.getLogger(__name__)

def internal_error(e: Exception, operation: str = "operation") -> dict:
    error_id = str(uuid.uuid4())[:8]
    logger.exception("Internal error [%s] during %s: %s", error_id, operation, e)
    return {"detail": f"An internal error occurred. Reference ID: {error_id}"}
```

Replace all bare `raise HTTPException(status_code=500, detail=str(e))` calls throughout `endpoints.py` and `main.py`:

```python
# BEFORE:
except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))

# AFTER:
except Exception as e:
    raise HTTPException(status_code=500, **internal_error(e, "evaluate_portfolio"))
```

---

### Task 1.6 — Security Response Headers

**Priority:** Low-Medium

```python
# backend/app/main.py
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = "default-src 'none'"
    return response
```

---

### Task 1.7 — Email Service Integration (Resend)

**Priority:** High — makes the product actually functional

**Rationale:** Without real email delivery, users who register on the production deployment are permanently stuck at the unverified state.

**Implementation:**

```bash
pip install resend
```

```python
# backend/app/core/config.py
RESEND_API_KEY: str = os.getenv("RESEND_API_KEY", "")
FROM_EMAIL: str = os.getenv("FROM_EMAIL", "noreply@gripperfinance.com")
```

```python
# backend/app/core/email.py (new file)
import logging, resend
from app.core.config import settings

logger = logging.getLogger(__name__)

def send_verification_email(to_email: str, code: str) -> bool:
    if not settings.RESEND_API_KEY:
        logger.warning("RESEND_API_KEY not configured — email not sent to %s", to_email)
        return False
    try:
        resend.api_key = settings.RESEND_API_KEY
        resend.Emails.send({
            "from": settings.FROM_EMAIL,
            "to": [to_email],
            "subject": "Verify your GRIPPER account",
            "html": f"<p>Your verification code is: <strong>{code}</strong></p>",
        })
        return True
    except Exception as e:
        logger.error("Failed to send verification email to %s: %s", to_email, e)
        return False
```

Resend free tier: 3,000 emails/month, no credit card required.

---

### Security Posture After Phase 1

| Risk | Status |
|---|---|
| Admin privilege escalation via registration | Eliminated |
| JWT forgery via known secret | Eliminated |
| Brute force login/register/reset | Rate-limited (10/min, 5/min, 3/min) |
| OTP codes in production logs | Eliminated |
| Error message leaking internals | Eliminated |
| User enumeration via forgot-password | Mitigated |
| Verification codes actually delivered | Functional |
| CORS wildcard | Locked to explicit domains |

**Remaining Unresolved Risks After Phase 1:**
- JWT stored in `localStorage` (XSS exposure)
- No pgvector index (search collapses at scale)
- No virus scanning on PDF uploads
- `SEED_DEMO_USER=true` by default — change to `false` in production manually

---

## PHASE 2 — INFRASTRUCTURE & DEPLOYMENT STABILIZATION

### The Core Problem

The Vercel architecture as deployed has three fundamental incompatibilities:

| Requirement | Vercel Serverless | Status |
|---|---|---|
| Persistent RQ worker process | Not possible | **Broken** |
| `/tmp` file storage between invocations | Ephemeral per function instance | **Broken** |
| Embedding model load (~130MB) in 60s timeout | Cold starts exceed timeout | **Broken** |

The ingestion pipeline does not work on Vercel as deployed. The code itself acknowledges this — the embedding generator detects `VERCEL == "1"` and falls back to a SHA-256 hash-based fake embedding.

### Infrastructure Option Analysis

| Option | Worker Support | Managed Postgres + pgvector | Ease for Junior Eng | Cost |
|---|---|---|---|---|
| **Railway** | Native (Background Worker service) | Yes (pgvector addon) | High | $5/month |
| Fly.io | Via Fly Machines | Via Supabase partnership | Medium | ~$5–10/month |
| Render | Background Worker service type | Yes | High | Free tier (cold starts) |
| EC2/VPS | Full control | Manual setup | Low | ~$5–10/month |

### Recommendation: Railway for Backend + Vercel for Frontend

**Justification:**
- Vercel stays as the frontend CDN/host — excels at static SPA delivery
- Railway hosts: FastAPI app, RQ worker, Redis (addon), Postgres with pgvector (addon)
- Workers are a native Railway service type — start with `rq worker default`
- Managed Postgres on Railway supports `pgvector` extension
- No Docker expertise required — Railway auto-detects Python

### Target Production Topology

```
┌─────────────────────────────────────────────────────────────────┐
│                        USER BROWSER                             │
└───────────────────────────┬─────────────────────────────────────┘
                            │ HTTPS
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    VERCEL (Frontend CDN)                        │
│  React SPA (dist/) — served from edge CDN globally             │
│  /api/* → proxy to Railway backend URL                         │
│  All other routes → index.html (SPA routing)                   │
└───────────────────────────┬─────────────────────────────────────┘
                            │ HTTPS (/api/*)
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                   RAILWAY (Backend Cluster)                     │
│                                                                 │
│  ┌──────────────────┐     ┌───────────────────────────────┐    │
│  │  FastAPI Service  │     │       RQ Worker Service       │    │
│  │  (Railway Web)   │     │  (Railway Background Worker)  │    │
│  │  uvicorn port 8000│    │  rq worker default            │    │
│  └────────┬─────────┘     └──────────────┬────────────────┘    │
│           │                              │                      │
│           └──────────────┬───────────────┘                      │
│                          │                                      │
│           ┌──────────────▼───────────────┐                      │
│           │       Railway Redis           │                      │
│           │  (RQ job queue + blacklist)  │                      │
│           └──────────────┬───────────────┘                      │
│                          │                                      │
│           ┌──────────────▼───────────────┐                      │
│           │     Railway Postgres          │                      │
│           │   (pgvector enabled)         │                      │
│           └──────────────┬───────────────┘                      │
│                          │                                      │
│           ┌──────────────▼───────────────┐                      │
│           │  Railway Volume (Persistent) │                      │
│           │  /app/storage/uploads        │                      │
│           │  (PDFs during worker         │                      │
│           │   processing)               │                      │
│           └──────────────────────────────┘                      │
└─────────────────────────────────────────────────────────────────┘
```

---

### Task 2.1 — Docker Compose for Local Development

```yaml
# docker-compose.yml (project root)
version: "3.9"
services:
  db:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: gripper_app
      POSTGRES_PASSWORD: gripper_secure
      POSTGRES_DB: gripper
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U gripper_app -d gripper"]
      interval: 5s
      timeout: 5s
      retries: 10

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s

  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql://gripper_app:gripper_secure@db:5432/gripper
      SUPERUSER_DATABASE_URL: postgresql://gripper_app:gripper_secure@db:5432/gripper
      REDIS_URL: redis://redis:6379/0
      SECRET_KEY: ${SECRET_KEY}
      DEBUG_PRINT_CODES: "true"
      SEED_DEMO_USER: "true"
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - ./backend:/app
      - uploads:/app/storage/uploads

  worker:
    build:
      context: ./backend
      dockerfile: Dockerfile
    command: rq worker default --url redis://redis:6379/0
    environment:
      DATABASE_URL: postgresql://gripper_app:gripper_secure@db:5432/gripper
      SUPERUSER_DATABASE_URL: postgresql://gripper_app:gripper_secure@db:5432/gripper
      REDIS_URL: redis://redis:6379/0
      SECRET_KEY: ${SECRET_KEY}
    depends_on:
      - db
      - redis
      - backend
    volumes:
      - uploads:/app/storage/uploads

volumes:
  pgdata:
  uploads:
```

```dockerfile
# backend/Dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p storage/uploads

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Developer workflow:**
```bash
cp backend/.env.example backend/.env  # edit SECRET_KEY
docker compose up
# Frontend: npm run dev (proxies /api to localhost:8000)
```

---

### Task 2.2 — Fix Vercel Proxy for Railway Backend

```json
// vercel.json
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "buildCommand": "npm run build",
  "outputDirectory": "dist",
  "rewrites": [
    {
      "source": "/api/(.*)",
      "destination": "https://your-app.up.railway.app/api/$1"
    },
    {
      "source": "/(.*)",
      "destination": "/index.html"
    }
  ]
}
```

Remove `api/index.py` — it is no longer needed. Add `VITE_API_BASE_URL` to Vercel env: `https://your-app.up.railway.app/api`

---

### Task 2.3 — Fix Upload Storage: Shared Volume

Attach a persistent Railway volume at `/app/storage/uploads` to both the FastAPI service and the RQ worker service.

```python
# backend/app/core/config.py — update UPLOAD_DIR default
UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "/app/storage/uploads")
# Remove the Vercel /tmp detection block entirely
```

Add post-ingestion file cleanup in `pipeline.py`:
```python
# At end of ingest_document(), after successful processing:
if os.path.exists(file_path):
    os.remove(file_path)
    logger.info("Cleaned up uploaded file: %s", file_path)
```

---

### Task 2.4 — Fix Observability: Remove Emoji Print

```python
# backend/app/core/observability.py
def log_json_metric(operation, duration_ms, status, error_message=None, metadata=None):
    log_data = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "operation": operation,
        "duration_ms": round(duration_ms, 2),
        "status": status,
        "error_message": error_message,
        "metadata": metadata or {},
    }
    logger.info(json.dumps(log_data))
    # REMOVE: print(f"📊 [OBSERVABILITY] {json.dumps(log_data)}")
```

---

### Deployment Migration Plan

1. Create Railway account, new project
2. Add Railway Postgres plugin → enable pgvector: `CREATE EXTENSION IF NOT EXISTS vector;`
3. Add Railway Redis plugin
4. Push backend to Railway Git integration — set all env vars in Railway dashboard
5. Run `alembic upgrade head` via Railway one-off command
6. Add Railway Volume, attach to both FastAPI and worker services at `/app/storage/uploads`
7. Deploy RQ worker as second Railway service: start command `rq worker default --url $REDIS_URL`
8. Update `vercel.json` to proxy `/api/*` to Railway URL
9. Update `ALLOWED_ORIGINS` on Railway to include the Vercel frontend URL
10. Remove `api/index.py` from project

### Rollback Strategy

Vercel rollbacks: instant (promote previous deployment from Vercel dashboard). Railway rollbacks: use "Redeploy" button on a previous deploy SHA. Database rollbacks: `alembic downgrade -1`.

### Cost

Railway Hobby plan: **$5/month** flat. Postgres: $0 for first 1GB. Redis: $0 for first 25MB. Vercel: free Hobby tier for frontend.

**Total: $5/month** for a fully functional deployment with persistent workers, real file storage, and managed database.

---

## PHASE 3 — DATABASE & PERFORMANCE OPTIMIZATION

---

### Task 3.1 — pgvector HNSW Index (Critical)

**Current Bottleneck:**
Every semantic search performs an exact nearest-neighbor scan across the entire `document_chunks` table. Cost is O(n × 384 dimensions). At 20,000 chunks: 200–800ms per search. At 100,000 chunks: multi-second.

**Expected Gain:**
HNSW reduces cost to O(log n). Queries from 400ms → 5–15ms with ~95% recall accuracy.

**Implementation — new Alembic migration:**

```bash
cd backend && alembic revision -m "add_pgvector_hnsw_and_gin_indexes"
```

```python
def upgrade():
    # HNSW index for approximate nearest neighbor search
    # ef_construction=64, m=16 are well-tuned defaults for <100K vectors
    op.execute("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS
        idx_document_chunks_embedding_hnsw
        ON document_chunks
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64);
    """)

    # GIN index for full-text search
    op.execute("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS
        idx_document_chunks_content_fts
        ON document_chunks
        USING gin (to_tsvector('english', content));
    """)

    # Composite indexes for common compliance queries
    op.create_index(
        "idx_governance_events_portfolio_resolved",
        "governance_events",
        ["portfolio_id", "resolved"],
    )
    op.create_index(
        "idx_research_reports_institution_created",
        "research_reports",
        ["institution_id", "created_at"],
    )
    op.create_index("idx_holdings_portfolio_id", "holdings", ["portfolio_id"])
    op.create_index(
        "idx_ips_rules_institution_active",
        "ips_rules",
        ["institution_id", "active"],
    )

def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_document_chunks_embedding_hnsw;")
    op.execute("DROP INDEX IF EXISTS idx_document_chunks_content_fts;")
    op.drop_index("idx_governance_events_portfolio_resolved", "governance_events")
    op.drop_index("idx_research_reports_institution_created", "research_reports")
    op.drop_index("idx_holdings_portfolio_id", "holdings")
    op.drop_index("idx_ips_rules_institution_active", "ips_rules")
```

**Migration Safety:** `CONCURRENTLY` builds indexes without table locks. No downtime required.

---

### Task 3.2 — Add Pagination to `list_documents`

**Current Bottleneck:** `GET /documents` returns every ResearchReport in a single query with no limit.

```python
# backend/app/api/endpoints.py
from sqlalchemy import func

@router.get("/documents")
def list_documents(
    db: Session = Depends(get_db),
    current_user=Depends(RoleChecker(READ_ROLES)),
    page: int = 1,
    page_size: int = 20,
):
    if page < 1:
        page = 1
    page_size = min(page_size, 100)
    offset = (page - 1) * page_size

    total = db.query(func.count(models.ResearchReport.id)).scalar()
    reports = (
        db.query(models.ResearchReport)
        .order_by(models.ResearchReport.created_at.desc())
        .offset(offset)
        .limit(page_size)
        .all()
    )
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "results": [{"id": str(r.id), "sector": r.sector, ...} for r in reports],
    }
```

Apply the same pagination to `list_portfolios` and `list_portfolio_holdings`.

---

### Task 3.3 — Fix Holdings Upsert: Preserve IDs

**Current Bottleneck:** Holdings update deletes all rows and re-inserts, destroying IDs and orphaning `governance_events.holding_id` foreign keys.

```python
# backend/app/main.py — replace update_portfolio_holdings
@app.post("/portfolios/{portfolio_id}/holdings")
def update_portfolio_holdings(
    portfolio_id: uuid.UUID,
    holdings_data: List[HoldingUpdate],
    db: Session = Depends(get_db),
    current_user=Depends(RoleChecker(HOLDINGS_WRITE_ROLES)),
):
    incoming = {h.ticker.upper(): h for h in holdings_data}
    existing = {
        h.ticker.upper(): h
        for h in db.query(models.Holding)
                   .filter(models.Holding.portfolio_id == portfolio_id)
                   .all()
    }

    # Update existing, add new
    for ticker, data in incoming.items():
        if ticker in existing:
            h = existing[ticker]
            h.weight = data.weight
            h.cost_basis = data.cost_basis
            h.conviction_score = data.conviction_score
        else:
            db.add(models.Holding(
                portfolio_id=portfolio_id,
                ticker=ticker,
                weight=data.weight,
                cost_basis=data.cost_basis,
                conviction_score=data.conviction_score,
            ))

    # Remove tickers no longer in portfolio
    for ticker, holding in existing.items():
        if ticker not in incoming:
            db.delete(holding)

    db.commit()
    return {"status": "success", "count": len(holdings_data)}
```

---

### Task 3.4 — Portfolio Snapshots

New Alembic migration:

```python
def upgrade():
    op.create_table(
        "portfolio_snapshots",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("portfolio_id", sa.UUID(),
                  sa.ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("institution_id", sa.UUID(),
                  sa.ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("holdings_json", sa.JSON(), nullable=False),
        sa.Column("compliance_status_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(),
                  server_default=sa.text("TIMEZONE('utc', NOW())"), nullable=False),
        sa.UniqueConstraint("portfolio_id", "snapshot_date", name="uq_portfolio_snapshot_date"),
    )
    op.create_index("idx_snapshots_portfolio_date", "portfolio_snapshots",
                    ["portfolio_id", "snapshot_date"])
    op.execute("ALTER TABLE portfolio_snapshots ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE portfolio_snapshots FORCE ROW LEVEL SECURITY;")
    op.execute("""
        CREATE POLICY snapshot_isolation ON portfolio_snapshots
        USING (institution_id = NULLIF(current_setting('app.current_institution_id', true), '')::uuid);
    """)
```

Write snapshots from the RQ worker after compliance evaluation — not in the sync API path.

---

## PHASE 4 — AI / RAG SYSTEM IMPROVEMENTS

### What Is Currently Fake vs. Real

| Feature | Reality |
|---|---|
| Hybrid RAG retrieval (pgvector + FTS + RRF) | **Real** — correctly implemented |
| BGE query embedding with instruction prefix | **Real** — `"Represent this sentence for searching relevant passages: {query}"` |
| Fallback embedding on Vercel | **Fake** — SHA-256 hash-based vector with no semantic meaning |
| "AI explanation" | **Fake** — Python f-string template, no LLM call |
| Intelligence dashboard tab | **Fake** — static mock UI |
| Earnings tab | **Fake** — static mock UI |

---

### Task 4.1 — Replace Fake AI Explanation with Real LLM Call

**This is the highest-impact AI task.** The violation explainability feature is the marquee AI capability. It currently returns a 150-character f-string. That is not AI.

**Recommended Provider:** Groq (free tier, Llama 3.1 70B quality, ~50ms latency, zero cost)

```bash
pip install groq
```

```python
# backend/app/core/config.py
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
LLM_MODEL: str = os.getenv("LLM_MODEL", "llama-3.1-70b-versatile")
LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "300"))
```

```python
# backend/app/services/governance/explain.py — replace the f-string summary block

def _call_llm_explanation(event_type: str, details: dict, context_notes: list) -> str:
    from app.core.config import settings
    if not settings.GROQ_API_KEY:
        return _template_explanation(event_type, details, context_notes)

    context_text = "\n\n".join([
        f"[{c['company']} — {c['sector']}]\n{c['content'][:400]}"
        for c in context_notes[:3]
    ]) or "No supporting research documents found in the knowledge base."

    violation_description = details.get("message", "Compliance violation detected.")

    system_prompt = (
        "You are a compliance analyst at a university investment fund. "
        "Explain portfolio compliance violations clearly to portfolio managers. "
        "Be factual, reference only the provided context, and suggest next steps. "
        "Do not hallucinate data not present in the context."
    )

    user_prompt = (
        f"Compliance Violation: {violation_description}\n\n"
        f"Retrieved Research Context:\n{context_text}\n\n"
        "Provide a 2-3 sentence explanation of this violation and one recommended action."
    )

    from groq import Groq
    client = Groq(api_key=settings.GROQ_API_KEY)
    completion = client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=settings.LLM_MAX_TOKENS,
        temperature=0.1,  # Low temperature for factual compliance text
    )
    return completion.choices[0].message.content.strip()
```

**Hallucination Mitigation:**
- Temperature 0.1 — near-deterministic output
- Explicit system prompt: "Do not hallucinate data not present in the context"
- Context capped at 400 chars per chunk
- `max_tokens=300` prevents verbose hallucination drift

---

### Task 4.2 — Add Re-Ranker

```bash
pip install sentence-transformers  # already installed
```

```python
# backend/app/services/retrieval/reranker.py (new file)
from typing import List, Dict, Any
import os

_reranker = None

def get_reranker():
    global _reranker
    if os.getenv("VERCEL") == "1":
        return None
    if _reranker is None:
        from sentence_transformers import CrossEncoder
        _reranker = CrossEncoder("BAAI/bge-reranker-base", device="cpu")
    return _reranker

def rerank_results(query: str, results: List[Dict[str, Any]], top_k: int = 5) -> List[Dict[str, Any]]:
    if not results:
        return results
    reranker = get_reranker()
    if not reranker:
        return results[:top_k]
    try:
        pairs = [(query, r["content"]) for r in results]
        scores = reranker.predict(pairs)
        for result, score in zip(results, scores):
            result["rerank_score"] = float(score)
        return sorted(results, key=lambda r: r["rerank_score"], reverse=True)[:top_k]
    except Exception:
        return results[:top_k]
```

Call `rerank_results` at the end of `search_documents()` before returning final results.

---

### Task 4.3 — Redis Caching for Compliance Explanations

```python
# backend/app/services/governance/explain.py
import hashlib, json
from app.core.redis_client import get_redis_client

def generate_violation_explanation(db, event_id, institution_id):
    cache_key = f"explanation:{hashlib.sha256(str(event_id).encode()).hexdigest()[:16]}"
    redis = get_redis_client()

    if redis:
        cached = redis.get(cache_key)
        if cached:
            return json.loads(cached)

    # ... existing logic + _call_llm_explanation() ...
    result = { ... }

    if redis:
        redis.setex(cache_key, 3600, json.dumps(result))  # 1-hour TTL

    return result
```

---

### Task 4.4 — RAG Evaluation Tests

```python
# backend/tests/test_rag_quality.py
import os, pytest

@pytest.mark.skipif(os.getenv("RUN_RAG_EVAL") != "1", reason="Skipped in CI")
def test_search_retrieves_relevant_context(seeded_db_with_known_document):
    db, institution_id, known_report_id = seeded_db_with_known_document
    results = search_documents(db, "AAPL investment thesis technology", institution_id, limit=5)
    report_ids = [r["report_id"] for r in results]
    assert str(known_report_id) in report_ids, f"Expected report not in top 5: {report_ids}"
    assert results[0]["similarity"] > 0.5
```

Run manually: `RUN_RAG_EVAL=1 pytest tests/test_rag_quality.py -v`

### AI Cost Summary

| Component | Option | Cost |
|---|---|---|
| LLM for explanations | Groq Llama 3.1 70B | **$0** (free tier) |
| Re-ranker | `bge-reranker-base` local | **$0** |
| Embeddings | `bge-small-en-v1.5` local | **$0** |
| Semantic cache | Railway Redis | Included in $5/month |

**Total AI infrastructure: $0/month**

---

## PHASE 5 — FRONTEND REFACTOR & PRODUCT MATURITY

### Task 5.1 — Component Decomposition

The 1,546-line `GripperDashboard.tsx` must be split. Rule: no component file exceeds 200 lines. No component mixes data fetching with rendering.

**Proposed Frontend Folder Structure:**

```
src/
├── app/
│   ├── dashboard/
│   │   ├── DashboardLayout.tsx          # Tab nav + shell (~80 lines)
│   │   ├── tabs/
│   │   │   ├── ComplianceTab.tsx        # Violations list + evaluate button
│   │   │   ├── PortfolioTab.tsx         # Holdings table + save + simulate
│   │   │   ├── ResearchTab.tsx          # Upload form + document list
│   │   │   ├── SearchTab.tsx            # Semantic search input + results
│   │   │   ├── IntelligenceTab.tsx      # Hidden behind feature flag
│   │   │   └── EarningsTab.tsx          # Hidden behind feature flag
│   │   └── components/
│   │       ├── ViolationCard.tsx        # Single violation row
│   │       ├── HoldingRow.tsx           # Editable holding entry
│   │       ├── DocumentStatusBadge.tsx  # pending/processed/failed badge
│   │       ├── SearchResultCard.tsx     # RAG result with similarity score
│   │       └── ComplianceScore.tsx      # Summary compliance status widget
├── auth/
│   ├── AuthPage.tsx
│   └── components/
│       ├── LoginForm.tsx
│       ├── RegisterForm.tsx
│       ├── VerifyForm.tsx
│       └── ResetPasswordForm.tsx
├── landing/                             # Already decomposed — keep as-is
├── lib/
│   ├── api.ts
│   ├── routes.ts
│   └── defaultInstitutions.ts
└── store/
    ├── useAuthStore.ts                  # Token, currentUser, login, logout, register
    ├── usePortfolioStore.ts             # Portfolios, holdings, violations, simulate
    ├── useResearchStore.ts              # Documents, search
    └── useInstitutionStore.ts           # Institutions list, currentInstitution
```

---

### Task 5.2 — Feature Gate Fake UI

```typescript
// src/lib/featureFlags.ts
export const FLAGS = {
  intelligenceTab: import.meta.env.VITE_FLAG_INTELLIGENCE === "true",
  earningsTab: import.meta.env.VITE_FLAG_EARNINGS === "true",
} as const;
```

```tsx
// src/app/dashboard/DashboardLayout.tsx
import { FLAGS } from '@/lib/featureFlags';

const tabs = [
  { id: 'compliance', label: 'Compliance' },
  { id: 'portfolio', label: 'Portfolio' },
  { id: 'research', label: 'Research' },
  { id: 'search', label: 'Semantic Search' },
  ...(FLAGS.intelligenceTab ? [{ id: 'intelligence', label: 'Intelligence' }] : []),
  ...(FLAGS.earningsTab ? [{ id: 'earnings', label: 'Earnings' }] : []),
];
```

Production defaults to `false` — fake tabs are invisible.

---

### Task 5.3 — State Management Cleanup

Replace the `getHeaders()` closure with a direct state read at call time:

```typescript
// In each store action, read token directly:
fetchPortfolios: async (instId) => {
  const token = get().token;  // read fresh at call time
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(instId ? { 'X-Institution-ID': instId } : {}),
  };
  // ...
}
```

---

### Task 5.4 — Testing Strategy

**Layer 1 — Unit tests (Vitest, 1 day):**
```
src/lib/api.test.ts           — parseApiError handles all FastAPI error shapes
src/lib/featureFlags.test.ts  — flags default to false in production
src/store/useAuthStore.test.ts — login sets token, logout clears all state
```

**Layer 2 — Component tests (RTL, 2 days):**
```
LoginForm — renders, shows error from store, submits correctly
ViolationCard — renders severity badge, calls explain on click
HoldingRow — weight input validation, ticker normalization
```

**Layer 3 — E2E smoke tests (Playwright, 2 days):**
```
auth.spec.ts      — register → verify → login → see dashboard
compliance.spec.ts — save holdings → evaluate → see violations
upload.spec.ts    — upload PDF → status shows processing
```

---

### What to Hide From Demos Until Complete

| Feature | Status | Demo Action |
|---|---|---|
| Intelligence tab | Frontend mock | Hide via feature flag |
| Earnings tab | Frontend mock | Hide via feature flag |
| Email verification | No email in production | Demo only with `SEED_DEMO_USER=true` account |
| LLM explanation | Fake f-string | Do not demo until Phase 4.1 complete |

---

## PHASE 6 — ENTERPRISE & LONG-TERM READINESS

*Each item is tagged:*
- **[Enterprise Required]** — needed to sell to real institutional clients
- **[Portfolio Value]** — good to discuss in interviews, not necessary to implement

---

### Task 6.1 — Immutable Audit Logs **[Enterprise Required]**

The current `governance_events` table is mutable. An admin can modify or delete any record. This fails SOC 2 Type II, FINRA Rule 17a-4, and any real institutional compliance requirement.

**Minimum implementation:**

```sql
CREATE TABLE audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    institution_id UUID NOT NULL,
    actor_user_id UUID,
    action VARCHAR(100) NOT NULL,       -- 'holdings.update', 'violation.resolve'
    target_type VARCHAR(100),
    target_id UUID,
    payload_json JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Deny UPDATE and DELETE at DB level
REVOKE UPDATE, DELETE ON audit_log FROM gripper_app;
```

2-week implementation effort.

---

### Task 6.2 — IPS Rule Versioning **[Enterprise Required]**

Editing an IPS rule currently overwrites the database row, retroactively corrupting all historical compliance evaluations.

**Implementation path:**

```sql
ALTER TABLE ips_rules
  ADD COLUMN valid_from TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  ADD COLUMN valid_to TIMESTAMPTZ;

-- "Active" rules: WHERE active = TRUE AND valid_to IS NULL
-- On rule change: SET valid_to = NOW() on old row, INSERT new row
```

---

### Task 6.3 — OpenTelemetry Distributed Tracing **[Portfolio Value]**

```bash
pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp
```

Replace `observe_time` decorator internals with `opentelemetry.trace.get_tracer(__name__).start_as_current_span(operation_name)`. Export traces to Grafana Tempo or Honeycomb (both have free tiers).

Mentioning "OpenTelemetry instrumentation with span-level tracing across embedding, retrieval, and LLM calls" in an interview is a strong senior engineering signal.

---

### Task 6.4 — SSO / OIDC Integration **[Enterprise Required]**

Institutional investment offices run Okta, Azure AD, or Google Workspace. They will not provision local username/password accounts.

**Implementation path:** Integrate Clerk or Auth0 as an OIDC provider. The `User.external_id` column already exists for this purpose.

**When to implement:** When the first enterprise customer conversation happens. Not before.

---

### Task 6.5 — PgBouncer Connection Pooling **[Enterprise Required]**

**Critical warning:** PgBouncer in **transaction mode** leaks the `SET LOCAL app.current_institution_id` session variable across connections, causing cross-tenant data leaks. Must use **session mode** — this limits pooling benefits but preserves RLS correctness.

Premature for the current scale. Implement when PostgreSQL connection saturation is observed in production metrics.

---

# FINAL SUMMARY

---

## TOP 10 FIXES BY IMPACT

| Rank | Fix | Security | Scalability | Recruiter Signal | Effort |
|---|---|---|---|---|---|
| 1 | Remove admin self-registration | Critical | None | High | 2/10 |
| 2 | Enforce non-default SECRET_KEY | Critical | None | High | 1/10 |
| 3 | Fix engine-per-request in deps.py | None | Critical | High | 1/10 |
| 4 | Add pgvector HNSW + GIN indexes | None | Critical | High | 2/10 |
| 5 | Replace AI explanation f-string with real LLM | None | None | Very High | 4/10 |
| 6 | Railway migration (fix worker + storage) | Medium | High | Medium | 5/10 |
| 7 | Remove debug print() for OTP codes | High | None | High | 1/10 |
| 8 | Real email delivery (Resend) | None | None | High | 3/10 |
| 9 | Split GripperDashboard monolith | None | None | High | 6/10 |
| 10 | Add rate limiting (slowapi) | High | Medium | Medium | 2/10 |

---

## REALISTIC TIMELINE FOR A JUNIOR ENGINEER

**2 Days:**
Phase 0 complete. All 5 blockers fixed. The project is no longer actively dangerous to demo. One hour of focused work per blocker.

**1 Week:**
Phase 0 + Phase 1 complete. CORS locked, rate limiting active, password validation consistent, error handling safe, Resend email integrated. Security posture is defensible.

**1 Month:**
Phase 0 + 1 + 2 + 3. Docker Compose and Railway migration working. Ingestion pipeline functional in production. Search queries run in <20ms with HNSW index. Pagination in place.

**3 Months:**
All phases complete. LLM explanation is real. Reranker integrated. Frontend refactored with feature flags. Tests written. Portfolio snapshots exist. The project is a genuinely impressive engineering artifact.

> **Honest estimate:** A junior engineer working part-time (10-15 hours/week) will take 3 months to complete all phases. Working full-time focused: 6–8 weeks.

---

## INTERVIEW VALUE AFTER EACH PHASE

**After Phase 0 (2 days):**
The project goes from "has an admin privilege escalation vulnerability" to "shows security awareness." Worth saying in interviews: *"I audited my own auth system and found a privilege escalation vector — here's how I fixed it."*

**After Phase 1 (1 week):**
Demonstrates security thinking: CORS, rate limiting, no credential leakage, consistent validation. A senior engineer reviewing the auth code will find no obvious holes.

**After Phase 2 (1 month):**
Being able to say *"I realized the serverless architecture was fundamentally incompatible with persistent workers and redesigned the deployment topology"* signals architectural maturity. Docker Compose shows operational thinking. This is the credibility jump.

**After Phase 3 (1 month):**
Explaining HNSW indexes (O(n) to O(log n), ef_construction trade-offs, approximate vs. exact search), pgvector indexing strategy, and connection pool lifecycle in an interview differentiates from the vast majority of portfolio projects.

**After Phase 4 (2 months) — THE TRANSITION POINT:**

Before Phase 4: "ambitious student project with impressive architecture."

After Phase 4: **"serious engineering portfolio."**

The project has a real AI feature (LLM explanation), a real retrieval pipeline (hybrid search + reranker), measurable quality (RAG eval tests), and cost-aware implementation (Groq free tier + local reranker). Explaining RRF + reranker + LLM hallucination mitigation in an interview will impress at every company.

**After Phase 5 (3 months):**
Frontend refactoring, tests, and feature flags add credibility to the full-stack claim. After Phase 5, this project can be demoed live to anyone without hidden risks or embarrassing fake features.

---

## DO NOT RECOMMEND

### Overengineering Traps

1. **Do not add Kubernetes.** Single-service Railway deployment is sufficient. Kubernetes adds 50+ hours of operational complexity with zero product value at this scale.

2. **Do not add GraphQL.** REST is sufficient. The API surface is well-bounded. GraphQL adds tooling, schema management, and N+1 query risk with no benefit.

3. **Do not rewrite the backend in Go or Rust.** FastAPI is fast enough for this workload. The bottleneck is the embedding model and the database, not the web framework.

4. **Do not add Celery to replace RQ.** RQ is simpler, requires zero configuration, and handles this workload. Celery's added complexity (broker config, result backends, task routing) is not warranted.

5. **Do not add a vector-only database (Pinecone, Weaviate, Qdrant).** pgvector with an HNSW index handles hundreds of thousands of vectors at this scale. Adding a separate vector database doubles infrastructure, doubles maintenance, and complicates the RLS tenant isolation model.

6. **Do not implement event sourcing** for the entire domain. Portfolio snapshots for compliance history (Phase 3.4) are sufficient. Full event sourcing of every state change is a 3-month rewrite of the data model.

7. **Do not add a message broker (Kafka, RabbitMQ).** Redis + RQ is the correct solution at this scale. Kafka is for 100K+ events/second scenarios.

8. **Do not introduce microservices.** The boundary between ingestion, compliance, and retrieval services is not yet stable enough to formalize as service contracts. Premature service decomposition creates distributed systems problems without distributed systems scale.

9. **Do not rebuild authentication from scratch.** The current auth is already more sophisticated than most portfolio projects. If SSO is needed later, use Clerk or Auth0 — they have FastAPI integrations. Do not build OIDC from scratch.

10. **Do not add a semantic caching layer (GPTCache) before the LLM is real.** There is nothing to cache until Phase 4.1 is complete. The correct sequence is: real LLM → measure latency → cache if needed.

### Premature Optimizations

- **PgBouncer** — only relevant at >50 concurrent users
- **CDN for uploaded PDFs** — files are deleted after ingestion; nothing to CDN
- **Read replicas** — not warranted until the primary is saturated
- **Multi-region deployment** — not warranted for a .edu-targeted demo product
- **Embedding model fine-tuning** — BGE-small with proper instruction prefixes is sufficient; fine-tuning requires 10K labeled training pairs that do not exist yet
- **Token budgeting / usage metering per tenant** — implement after the first paying customer, not before

---

*End of document. Last updated: May 27, 2026.*
