# Database security and tenant isolation

Gripper is multi-tenant: every institution's portfolios, holdings, research and
compliance events share one PostgreSQL database. Isolation is enforced by **two
independent controls**, and either one alone blocks cross-tenant access (both are tested
separately, see [Verification](#verification)):

1. **Application layer.** The tenant is derived only from the authenticated user's
   membership record (`app/api/deps.py`). Every lookup by identifier also filters on that
   institution (`app/api/tenancy.py`); a resource in another institution returns 404.
   Client-supplied institution identifiers (e.g. an `X-Institution-ID` header) are ignored.
2. **Database layer (RLS).** Every tenant table has `ENABLE` + `FORCE ROW LEVEL SECURITY`
   and a policy `institution_id = NULLIF(current_setting('app.current_institution_id', true), '')::uuid`.
   Composite foreign keys additionally require a child row's `institution_id` to match its
   parent's (`governance_events → portfolios`, `document_chunks → research_reports`).

## Roles

| Role | Type | Used by | Privileges |
|---|---|---|---|
| owner (e.g. `postgres`) | login | `alembic upgrade head`, `scripts/*.py`, fixture seeding | owns tables; DDL |
| `gripper_runtime` | **NOLOGIN group**, created by migration `1b7e0c4a9d21` | — | `SELECT/INSERT/UPDATE/DELETE` on tenant tables, `SELECT` on `institutions`, `EXECUTE` on the definer functions below |
| `gripper_app` (name configurable) | login, member of `gripper_runtime` | the API (`DATABASE_URL`) and the RQ worker | inherited only; `NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE`; owns nothing |

**RLS does not apply to superusers or to roles with `BYPASSRLS`, whether or not FORCE is set.**
`FORCE ROW LEVEL SECURITY` only makes policies apply to the *table owner*; it does nothing
against privileged roles. The runtime role must therefore be neither, and must not own the
tables (an owner can `ALTER TABLE … DISABLE ROW LEVEL SECURITY`).

### Cross-tenant lookups without a privileged connection

Before this change, login and token validation read `users` through a second
"superuser" engine, and the README recommended pointing it at the same URL as
`DATABASE_URL`, so the runtime role had to bypass RLS. Now the runtime uses three
`SECURITY DEFINER` functions owned by the migration role, which return **identifiers only**:

| Function | Purpose |
|---|---|
| `app_resolve_user_by_email(text)` | login, password reset: `(user_id, institution_id)` |
| `app_resolve_user_by_id(uuid)` | token validation: `(user_id, institution_id)` |
| `app_pending_ingestion_jobs(int)` | operator-triggered ingestion: `(report_id, institution_id)`, max 50 |

The session is then bound to that institution and the full row is read **under RLS**.
The functions pin `search_path` and have `EXECUTE` revoked from `PUBLIC`. The migration
owner must be able to read all rows (superuser or `BYPASSRLS`), since `FORCE` applies to the
owner otherwise.

## Tenant context lifecycle

`app/db/session.py` binds the tenant to the SQLAlchemy session (`session.info`) and an
`after_begin` hook runs `set_config('app.current_institution_id', <id>, true)` at the start
of **every** transaction. This fixes the Phase 0 defect where `SET LOCAL` was issued once per
request, so it vanished at the first `commit()` and every later statement ran without tenant
context (`POST /portfolios` returned 500).

* `is_local = true` scopes the value to the transaction. It is gone after COMMIT/ROLLBACK,
  so it cannot leak to the next request that reuses the pooled connection. This also
  works with transaction-mode poolers (Supabase Supavisor on port 6543, PgBouncer).
* A session with no tenant explicitly sets `''`, which the policies map to `NULL`, so
  missing context fails closed: no rows are visible and inserts are rejected.
* Session-level `SET` (non-local) is never used.

## Runtime safeguard

`get_db()` performs a one-time (per process) catalog check of the runtime role. If it is a
superuser, has `BYPASSRLS`, owns a protected table, or any protected table lacks enabled+forced
RLS, requests fail with **503** (`DB_ROLE_SAFETY=enforce`, the default and the only value
permitted in production). `GET /health/db` reports `rls_enforced: true|false` (booleans only)
and returns 503 when false.

## Setup

```bash
cd backend
export MIGRATION_DATABASE_URL=postgresql://postgres:<owner-password>@<host>:5432/<db>
alembic upgrade head                                     # creates gripper_runtime + grants
APP_DB_USER=gripper_app APP_DB_PASSWORD=<strong-password> \
  python scripts/create_app_role.py                      # login role, member of gripper_runtime
export DATABASE_URL=postgresql://gripper_app:<strong-password>@<host>:5432/<db>
python scripts/check_db_role.py                          # exits 0 only if RLS is enforced
```

New tables added by future migrations must `GRANT … TO gripper_runtime` explicitly and enable+force RLS.

### Supabase notes (UNVERIFIED against a live project)

* Run the two setup commands with the project's `postgres` credentials (session pooler, port 5432, or
  the direct host). Use the transaction pooler (6543) only for the runtime `DATABASE_URL`.
* Supavisor login names are usually `<role>.<project-ref>` (e.g. `gripper_app.abcd1234`).
* Supabase exposes the `public` schema through its Data API to the `anon`/`authenticated` roles.
  Those roles receive default grants on new tables. Because Gripper's policies key off a custom
  setting that the Data API does not set, RLS hides rows from them, but you should still
  revoke their privileges (`REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon, authenticated;`)
  or disable the Data API if it is unused. Migration `1b7e0c4a9d21` already revokes `EXECUTE`
  on Gripper's definer functions from `anon` and `authenticated` when those roles exist,
  because Supabase's default privileges grant it explicitly (a `REVOKE … FROM PUBLIC` alone
  would leave them callable over the Data API).

## Verifying production (do this with the app's real credentials)

Running the query in the Supabase SQL editor tells you about the *editor's* role, not the
app's. Use the exact `DATABASE_URL` the deployment uses:

```bash
vercel env pull .env.production.local --environment=production   # writes secrets locally; do not commit
set -a; . ./.env.production.local; set +a

# Option A: the repo's checker (same normalisation as the app)
cd backend && python scripts/check_db_role.py; echo "exit=$?"

# Option B: psql with the same URL
psql "$DATABASE_URL" -c "
SELECT current_user, session_user, rolsuper, rolbypassrls
FROM pg_roles WHERE rolname = current_user;"
psql "$DATABASE_URL" -c "
SELECT c.relname, pg_get_userbyid(c.relowner) AS owner,
       c.relrowsecurity AS rls_enabled, c.relforcerowsecurity AS rls_forced
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public'
  AND c.relname IN ('users','portfolios','holdings','research_reports',
                    'document_chunks','meetings','ips_rules','governance_events');"
rm .env.production.local
```

| `rolsuper` | `rolbypassrls` | Meaning |
|---|---|---|
| true | any | RLS bypassed |
| false | true | RLS bypassed |
| false | false | RLS applies, **provided** the role doesn't own the tables (`owner` ≠ `current_user`) and every table shows `rls_enabled` and `rls_forced` true |

After deploying this branch, `GET /api/health/db` performs the same check through the
running app and returns `rls_enforced`.

If the old configuration was deployed with real data, treat it as exposed: rotate the DB
password, review access logs if available, and restrict public access until the new
role configuration is live.

## Verification

| Test file | Connection | Shows |
|---|---|---|
| `tests/integration/test_rls_database.py` | restricted role, raw SQL | RLS isolation per table, fail-closed without context, no leakage across reused pooled connections, cannot DDL / insert / update / delete across tenants, composite FKs |
| `tests/integration/test_tenant_isolation_api.py` (`rls_and_app`) | restricted role via API | end-to-end denials + legitimate writes that commit mid-request |
| same file (`app_only`) | **owner role** via API (RLS bypassed on purpose) | application checks alone block every cross-tenant request |
| `tests/integration/test_role_safety_and_worker.py` | both | the safeguard returns 503 for a privileged runtime role; worker jobs cannot touch another tenant's report |
