# Dependency management

## Python

| File | Used by | Contents |
|---|---|---|
| `backend/requirements-base.txt` | everything | Runtime dependencies, pinned exactly (`==`) |
| `backend/requirements.txt` | local dev / self-hosted | base + `sentence-transformers` (in-process embedding model) |
| `backend/requirements-ci.txt` | CI | base + pytest, ruff, pip-audit (no torch) |
| `backend/requirements-ci.lock` | CI | Full transitive lock for Python 3.12 / Linux, applied as a constraints file |
| `requirements.txt` (repo root) | Vercel | Must equal `requirements-base.txt` (CI enforces this) |

Install for CI-equivalent work:

```bash
cd backend
pip install -r requirements-ci.txt -c requirements-ci.lock
```

### Database driver

All database URLs are normalised by `app.core.database_url.normalize_database_url`,
which rewrites `postgres://` and `postgresql://` to `postgresql+psycopg2://`.
SQLAlchemy 2.1 changed the default driver for bare `postgresql://` URLs to psycopg (v3);
before this change, a fresh install resolved SQLAlchemy 2.1.x and the app failed to
import (`ModuleNotFoundError: psycopg`). SQLAlchemy is pinned to 2.0.x; with the driver
named explicitly, a future 2.1 upgrade is a deliberate, testable change rather than an
accidental driver switch.

### JWT library

`python-jose` was replaced by `PyJWT`. python-jose 3.5.0 carries PYSEC-2026-4298 (HMAC
key-confusion allowing forged HS256 tokens when algorithms are not restricted) and
pulls in `ecdsa` (PYSEC-2026-1325, Minerva timing attack, no fixed release). Gripper
only uses HS256 with an explicit `algorithms=[...]` allow-list, so exposure was limited,
but neither advisory has a fix, and PyJWT is the maintained library with the same API.

### Upgrading

1. Edit the pin in `requirements-base.txt` **and** the root `requirements.txt`.
2. Regenerate the lock in a clean Python 3.12 environment:
   ```bash
   docker run --rm -v "$PWD":/src -w /src/backend python:3.12-slim sh -c \
     'pip install -q -r requirements-ci.txt && pip freeze' > /tmp/freeze.txt
   ```
   and copy the `name==version` lines into `requirements-ci.lock` (keep the header).
3. Run `pip-audit -r requirements-ci.txt`, migrations against a fresh database, and the full test suite.

## JavaScript

`package-lock.json` is authoritative; CI and Vercel install with `npm ci`.
Security fixes are applied with `npm audit fix` (never `--force`), which stays inside the
semver ranges declared in `package.json`.

## Audit status (2026-11-25)

| Ecosystem | Before | After | Notes |
|---|---|---|---|
| Python (`pip-audit`) | 3 (python-jose, ecdsa ×2) | 0 | Library replacement, see above |
| npm (`npm audit`) | 19 (8 high, 11 moderate) | 0 | Patch/minor updates within ranges: vite 8.0.14→8.3.8, react-router(-dom) 7.15.1→7.18.7, postcss, nanoid, source-map-js; dev tooling (eslint 10.x, typescript-eslint 8.x, brace-expansion, minimatch) |
