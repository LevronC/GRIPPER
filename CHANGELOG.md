# Changelog

## [Unreleased] — portfolio-hardening (Phase 1)

### Security
- Tenant isolation enforced in application code **and** by RLS through a restricted runtime
  role; tenant context re-applied per transaction; composite tenant foreign keys; startup
  safeguard refuses a runtime role that can bypass RLS (docs/DATABASE_SECURITY.md).
- Invitation-only membership; public self-registration removed; secure password reset
  (hashed single-use tokens, expiry, rate limits, session revocation).
- Automatic demo seeding with a published password removed.
- python-jose replaced by PyJWT; all Python and npm advisories resolved.

### Fixed
- Fresh installs failed to import (SQLAlchemy 2.1 default driver); dependencies pinned and locked.
- Research retrieval no longer marks violations as justified or implies exceptions.
- No silent hash-embedding fallback; failed uploads are no longer deleted; explicit ingestion lifecycle.

### Added
- IPS rule management API; guarded synthetic demo seed; ingestion retry; capability flags in /health.

### Removed
- Simulated dashboard features (SEC Q&A, news risk audit, transcription, fixed NAV/alpha KPIs).
- Internal audit documents, legacy ad-hoc test scripts, unreferenced report about a real program.

## [0.1.0] - 2026-05-26

### Added

- GitHub Actions CI (frontend build/lint, backend ruff + pytest)
- Pytest suite with RBAC, health, and auth integration tests
- Role-based access control on API routes
- React error boundary for the terminal UI
- MIT LICENSE and CONTRIBUTING.md
- `docs/DEMO.md` for demo credentials (removed from README)
- `SEED_DEMO_USER` env flag to disable demo account seeding
- Production guard: disable `X-Institution-ID`-only auth on Vercel

### Changed

- Moved internal planning docs to `docs/internal/`
- README updated with live demo link and preview image

### Fixed

- Alembic migrations on Vercel (path, URL encoding, Supabase grants)
