# Gripper Risk Terminal
### Multi-Tenant Investment Compliance & Institutional Intelligence Platform

Gripper is a high-performance, multi-tenant investment compliance and semantic intelligence platform. Built specifically for high-stress boardroom gauntlets and equity research programs like the **Roland George Investments Program (RGIP)**, Gripper automates the verification of Investment Policy Statements (IPS) and bridges structured portfolio allocations with unstructured analyst research.

---

## 🚀 Key Features

### 🛡️ Multi-Tenant Row-Level Security (RLS)
- True database-level multi-tenancy enforced using PostgreSQL **Row-Level Security (RLS)**.
- Session-scoped transaction isolation preventing data leakage between different institutions (e.g., Stetson vs. UF).
- Secure analyst cohort access controls preserving audit trails without mixing proprietary thesis documents.

### 🧠 Compliance-Aware RAG Ingestion Pipeline
- **Smart Parsing & Chunking**: Custom PDF parsing engine with magic byte validation and clean window-based semantic chunking.
- **pgvector Vector Database**: Native semantic similarity search powered by `pgvector` and standard embedding generation models.
- **RAG-Backed Compliance Explanations**: Every portfolio breach generates a compliance alert accompanied by contextual citations extracted from the analyst's own research memos.

### 📋 Deterministic IPS Governance Engine
- **IPSRules Evaluator**: Automated checking of complex constraints:
  - *Single Position Caps* (e.g., max 10% in any single security).
  - *Sector Exposure Limits* (e.g., max 30% Tech limit).
  - *Liquidity Constraints* (e.g., minimum cash or micro-cap caps).
- **Compliance Reconciler**: Background loop that automatically tracks, reconciles, and closes resolved violations while preserving a historic audit log.

### ⚡ Async Processing Queue
- Decoupled ingestion worker leveraging **RQ (Redis Queue)**.
- Ensures file uploads and vector calculations are processed asynchronously without blocking the client thread.

---

## 🛠️ Architecture Stack

- **Frontend**: React 18, TypeScript, Tailwind CSS, Framer Motion, Zustand (state management).
- **Backend API**: FastAPI (Python 3.9+), SQLAlchemy 2.0 ORM, Alembic migrations.
- **Database**: PostgreSQL 16+ with `pgvector` extension.
- **Background Tasks**: Redis + RQ (Redis Queue) worker processes.

---

## ⚙️ Project Structure

```
├── backend/
│   ├── app/
│   │   ├── api/             # Authentication & feature endpoints (auth, search, portfolios, documents)
│   │   ├── core/            # Configuration, cryptography (bcrypt), observability logging
│   │   ├── db/              # SQLAlchemy session initialization & RLS context management
│   │   ├── models/          # Relational tables & RLS policies
│   │   ├── schemas/         # Pydantic schemas (validations)
│   │   ├── services/        # Business logic (retrieval search, chunking, IPS evaluation, LLM explainers)
│   │   └── workers/         # Redis task definition & async entrypoints
│   ├── migrations/          # Alembic DB migration versions
│   ├── requirements.txt     # Python project dependencies
│   ├── test_governance.py   # Deterministic RLS and compliance integration tests
│   └── test_rag.py          # Vector retrieval and search isolation tests
└── src/                     # React application source (components, Zustand store, styling)
```

---

## 🏁 Quick Start & Setup

### 1. Database Setup (PostgreSQL with pgvector)
Ensure PostgreSQL is running and has the `pgvector` extension enabled.
```sql
CREATE DATABASE gripper;
-- Connect to gripper database and run:
CREATE EXTENSION IF NOT EXISTS vector;
```

Configure your environment variables (or place them in a `.env` file inside `backend/`):
```bash
export DATABASE_URL="postgresql://gripper_app:gripper_secure@localhost:5432/gripper"
export REDIS_URL="redis://localhost:6379/0"
```

### 2. Backend Installation & Migrations
```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run database migrations using Alembic
alembic upgrade head
```

### 3. Running the Backend Server
Start the main FastAPI application:
```bash
export PYTHONPATH=.
venv/bin/uvicorn app.main:app --port 8000 --reload
```

### 4. Running the Async Task Worker
In a separate terminal (with your virtual environment active):
```bash
export PYTHONPATH=.
export DATABASE_URL="postgresql://gripper_app:gripper_secure@localhost:5432/gripper"
venv/bin/python app/workers/worker.py
```

### 5. Frontend Setup
From the root directory:
```bash
npm install
npm run dev
```
Open [http://localhost:5173](http://localhost:5173) in your browser.

---

## 🧪 Integration Tests
You can run isolated integration tests to verify the RLS enforcement, embedding ingestion, and compliance evaluation loop:

To test RAG Search Isolation:
```bash
cd backend
export PYTHONPATH=.
venv/bin/python test_rag.py
```

To test Compliance Engine & IPS Rules evaluation:
```bash
cd backend
export PYTHONPATH=.
venv/bin/python test_governance.py
```

---

## 🔒 Row-Level Security (RLS) Mechanics

Multi-tenant security is enforced at the database level using session-scoped context variables:
1. When a client makes a request, they provide their tenant via the `X-Institution-ID` header.
2. The backend database session executes `SET app.current_institution_id = '...'` at the start of the transaction.
3. Every database query checks the tenant:
   ```sql
   CREATE POLICY tenant_isolation ON <table_name> 
   USING (institution_id = NULLIF(current_setting('app.current_institution_id', true), '')::uuid);
   ```
4. This ensures data segregation is guaranteed at the engine level even if application-level developer errors occur.
