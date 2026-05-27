# Changelog

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
