# Contributing to GRIPPER

Thank you for your interest in contributing to the Gripper Risk Terminal.

## Development setup

1. Fork and clone the repository
2. Copy env files: `cp backend/.env.example backend/.env` and `cp .env.example .env`
3. Start PostgreSQL with `pgvector` and Redis locally
4. Run migrations: `cd backend && alembic upgrade head`
5. Backend: `cd backend && pip install -r requirements-dev.txt && uvicorn app.main:app --reload --port 8000`
6. Frontend: `npm install && npm run dev`

## Pull requests

1. Create a feature branch from `main`
2. Run checks locally before opening a PR:
   - `npm run lint && npx tsc -b --noEmit && npm run build`
   - `cd backend && ruff check . && mypy && pytest tests` (see [docs/TESTING.md](docs/TESTING.md))
3. Keep changes focused; include tests for new behavior
4. CI must pass (see `.github/workflows/ci.yml`)

## Commit messages

Use clear, imperative messages (e.g. "Add RBAC checks to portfolio routes").

## Security

Do not commit secrets, `.env` files, or production credentials. Report security issues privately to the repository owner.

## Code style

- **Python:** Ruff (`backend/ruff.toml`)
- **TypeScript/React:** ESLint (`npm run lint`)
- Match existing patterns in the file you are editing

## Demo data

There are no shared demo credentials. See [docs/DEMO.md](docs/DEMO.md) to create a
local synthetic institution with `scripts/seed_demo.py`.
