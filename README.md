# Gripper Risk Terminal

Multi-tenant investment compliance and semantic intelligence platform for student equity programs (e.g. RGIP) and institutional research teams.

## Application routes

| Route | Purpose |
|-------|---------|
| `/` | Marketing landing page |
| `/docs` | Developer and administrator documentation |
| `/app` | Authenticated compliance terminal (login required) |
| `/app?mode=register` | Open terminal in registration mode |
| `/api/docs` | FastAPI OpenAPI reference (backend must be running) |

## Quick start

### 1. Database

```bash
createdb gripper
psql gripper -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

Copy environment files:

```bash
cp backend/.env.example backend/.env
cp .env.example .env
```

### 2. Backend

```bash
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
export PYTHONPATH=.
uvicorn app.main:app --port 8000 --reload
```

### 3. Worker (separate terminal)

```bash
cd backend && source venv/bin/activate
export PYTHONPATH=.
python app/workers/worker.py
```

### 4. Frontend

```bash
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173). Vite proxies `/api` → `http://localhost:8000`.

### 5. Seed an institution (first run)

```bash
curl -X POST "http://localhost:8000/institutions?name=Stetson%20RGIP&slug=stetson-rgip"
```

### 6. Register and log in

1. Visit `/app?mode=register`
2. Use a `.edu` email, select your institution, and choose a role
3. Copy the 6-digit verification code from the **backend console**
4. Verify, then log in at `/app`

## Authentication flow

- **Register** → `POST /auth/register` (`.edu` email required)
- **Verify** → `POST /auth/verify` with 6-digit code
- **Login** → `POST /auth/login` returns JWT (`gripper_token` in localStorage)
- **Logout** → `POST /auth/logout` blacklists token + clears session

The selected institution at login must match the institution on your account.

## Project structure

```
├── src/
│   ├── landing/          # Marketing site components
│   ├── pages/            # LandingPage, DocsPage
│   ├── components/       # GripperDashboard terminal
│   ├── store/            # Zustand auth + data state
│   └── lib/              # API helpers and route constants
├── backend/              # FastAPI, SQLAlchemy, Alembic, workers
├── api/                  # Vercel serverless entry (mounts backend at /api)
└── scraped/              # Optional Scrapling output (Robinhood reference scrape)
```

## Key features

- **IPS governance** — position caps, sector limits, liquidity rules
- **RAG research search** — pgvector semantic search over uploaded PDFs
- **Multi-tenant RLS** — PostgreSQL row-level security per institution
- **Async ingestion** — Redis Queue workers for PDF parsing and embedding
- **Explainability** — violations with citations from analyst research

## Tests

```bash
cd backend && export PYTHONPATH=. && python test_governance.py
cd backend && export PYTHONPATH=. && python test_rag.py
```

## Deployment (Vercel)

The repo includes `vercel.json` that:

- Serves the Vite build as SPA
- Rewrites `/api/*` to the Python serverless handler

Set production environment variables in Vercel:

| Variable | Required | Notes |
|----------|----------|-------|
| `DATABASE_URL` | Yes | PostgreSQL with `pgvector` extension |
| `REDIS_URL` | Yes | Token blacklist + RQ (workers need separate host) |
| `SECRET_KEY` | Yes | JWT signing key |
| `SUPERUSER_DATABASE_URL` | Recommended | Auth lookups bypassing RLS (defaults from `DATABASE_URL`) |
| `VITE_API_BASE_URL` | No | Defaults to `/api` on Vercel |

## Scrapling reference scrape

```bash
source .venv/bin/activate   # from repo root if using scripts/scrape_robinhood.py
python scripts/scrape_robinhood.py
```

Output: `scraped/content.json` (layout reference only; landing copy reflects GRIPPER product).
