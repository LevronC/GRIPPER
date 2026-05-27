# Gripper Risk Terminal

Multi-tenant investment compliance and semantic intelligence platform for student equity programs (e.g. RGIP) and institutional research teams.

[![CI](https://github.com/LevronC/GRIPPER/actions/workflows/ci.yml/badge.svg)](https://github.com/LevronC/GRIPPER/actions/workflows/ci.yml)

**Live demo:** [gripper-ten.vercel.app/app](https://gripper-ten.vercel.app/app) · Demo credentials in [docs/DEMO.md](docs/DEMO.md)

![Gripper Risk Terminal preview](docs/screenshots/dashboard-preview.svg)

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
pip install -r requirements-dev.txt
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

### 5. Register and log in

Default institutions (Stetson, UF, RGIP Demo) are seeded on API startup. To try immediately, see [docs/DEMO.md](docs/DEMO.md).

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
├── src/                  # React landing + terminal UI
├── backend/              # FastAPI, SQLAlchemy, Alembic, workers
├── api/                  # Vercel serverless entry (mounts backend at /api)
├── docs/                 # DEMO, RBAC, internal planning notes
└── .github/workflows/    # CI (lint, build, pytest)
```

## Key features

- **IPS governance** — position caps, sector limits, liquidity rules
- **RAG research search** — pgvector semantic search over uploaded PDFs
- **Multi-tenant RLS** — PostgreSQL row-level security per institution
- **Role-based access control** — see [docs/RBAC.md](docs/RBAC.md)
- **Async ingestion** — Redis Queue workers for PDF parsing and embedding
- **Explainability** — violations with citations from analyst research

## Tests

```bash
# Automated suite (CI)
cd backend && pip install -r requirements-dev.txt
pytest tests/ -v

# Legacy integration scripts (require local Postgres + Redis)
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
| `DATABASE_URL` | Yes | PostgreSQL with `pgvector`. On Vercel + Supabase, use the **Session pooler** on port **6543**. URL-encode password specials (`@` → `%40`). |
| `REDIS_URL` | Yes | Token blacklist + RQ (must start with `redis://` or `rediss://`) |
| `SECRET_KEY` | Yes | JWT signing key |
| `SUPERUSER_DATABASE_URL` | Recommended | Same encoded Supabase pooler URL as `DATABASE_URL` |
| `SEED_DEMO_USER` | No | Set `false` in production to skip shared demo password seed |
| `VITE_API_BASE_URL` | No | Defaults to `/api` on Vercel |

Migrations run automatically on API cold start. Check `/api/health/db` for `"schema_ready": true`.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Licensed under [MIT](LICENSE).
