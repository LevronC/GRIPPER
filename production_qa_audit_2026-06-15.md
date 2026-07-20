# GRIPPER Production QA Audit

Audit date: 2026-06-15  
Target deployment: https://gripper-arltu58lr-levroncs-projects.vercel.app/  
Scope: live deployment access check, local source review, route/API inventory, build/lint/test verification.

## Executive Summary

GRIPPER is not production-ready today. The live Vercel deployment is inaccessible to unauthenticated users because every tested route returns Vercel Authentication `401`, including `/`, `/docs`, `/terminal`, and `/api/health`. That blocks public product use and prevents deployed end-to-end validation without a Vercel bypass token or authenticated deployment access.

The local codebase builds successfully, but lint fails and backend tests cannot execute in the current environment because required Postgres and Redis services are unavailable. Source review also found security issues that should be fixed before production: a hardcoded default JWT secret, permissive CORS, JWT/local user data stored in localStorage, unauthenticated tenant-context fallback via `X-Institution-ID`, and public institution creation.

Final recommendation: Not production-ready.

## Test Evidence

Commands run:

- `curl -L -I https://gripper-arltu58lr-levroncs-projects.vercel.app/` -> `401`, Vercel Authentication page.
- `curl -L -s -o /dev/null -w ... /api/health` -> `401 text/html`.
- `curl -L -s -o /dev/null -w ... /terminal` -> `401 text/html`.
- `curl -L -s -o /dev/null -w ... /docs` -> `401 text/html`.
- `npm run build` -> passed. Bundle: JS `462.72 kB`, gzip `141.72 kB`; CSS `59.32 kB`, gzip `10.23 kB`.
- `npm run lint` -> failed with 2 React hook lint errors.
- `backend/venv/bin/python -m pytest backend/test_verification.py backend/test_logout.py backend/test_governance.py backend/test_rag.py -q` -> failed because Postgres `localhost:5432` and Redis `localhost:6379` refused connections.

Browser automation note: the in-app browser target was unavailable and Playwright is not installed in this repository, so no screenshot-backed interaction pass was possible in this session.

## Features Tested / Inventory

Frontend routes:

- `/`: landing page.
- `/docs`: documentation page.
- `/app`: GRIPPER terminal/dashboard route.
- `/app?mode=login`, `/app?mode=register`, `/app?mode=verify`: auth-mode variants.
- Unknown paths redirect to `/`.

Dashboard capabilities visible in code:

- Authentication: login, registration, email verification, logout.
- Institution selection and tenant context.
- Portfolio selection.
- Holdings matrix: add/remove/edit holdings, save holdings.
- Compliance: evaluate portfolio, fetch active/resolved violations.
- Explainability: violation explanation drawer.
- Document ingestion: PDF upload with sector, company, recommendation.
- Semantic search over documents.
- Simulated compliance sandbox.
- Frontend-only intelligence center, SEC filing Q&A simulation, news risk analysis, earnings transcript simulation.

Backend endpoints inventoried:

- `GET /`, `GET /health`.
- `POST /institutions`, `GET /institutions`.
- `POST /portfolios`, `GET /portfolios`.
- `GET /portfolios/{portfolio_id}/holdings`, `POST /portfolios/{portfolio_id}/holdings`.
- `GET /ips_rules`.
- `POST /documents/upload`, `GET /documents`.
- `POST /search/semantic`.
- `POST /portfolios/{portfolio_id}/evaluate`.
- `GET /portfolios/{portfolio_id}/violations`.
- `POST /violations/{event_id}/explain`.
- `POST /portfolios/{portfolio_id}/simulate`.
- `POST /auth/register`, `POST /auth/login`, `POST /auth/logout`, `POST /auth/forgot-password`, `POST /auth/reset-password`, `POST /auth/verify`.

## Working Correctly

- Frontend TypeScript production build completes.
- API client centralizes `VITE_API_BASE_URL` fallback to `/api`.
- Upload endpoint includes basic PDF content type/extension, magic-byte, non-empty metadata, recommendation, and 10 MB size validation.
- Role checks exist for document upload and holdings writes.
- JWT logout attempts Redis-backed token revocation.
- Login verifies selected institution matches the authenticated user's institution before persisting local auth state.

## Bugs Found

### 1. Live deployment is blocked by Vercel Authentication

Severity: Critical

Steps to reproduce:

1. Request `https://gripper-arltu58lr-levroncs-projects.vercel.app/`.
2. Request `/docs`, `/terminal`, or `/api/health`.

Expected behavior: public routes and health checks should load, or protected app routes should present GRIPPER auth.

Actual behavior: all tested routes return Vercel Authentication `401` HTML.

Suggested fix: disable deployment protection for production, configure Vercel Trusted Sources/protection bypass for automated testing, or deploy public production and protected preview environments separately.

### 2. Navigation route mismatch for terminal path

Severity: High

Evidence: `routes.terminal` is `/app`, but the prompt and deployed URL check referenced `/terminal`; `App.tsx` only mounts `/app`, so `/terminal` redirects to `/`.

Expected behavior: documented/product URL and router should agree.

Actual behavior: `/terminal` is not a real app route in the local router.

Suggested fix: either add `/terminal` as an alias route or standardize all docs, CTAs, and deployment checks on `/app`.

### 3. Lint fails

Severity: Medium

Steps to reproduce: run `npm run lint`.

Actual behavior: two `react-hooks/set-state-in-effect` errors in `src/components/GripperDashboard.tsx` and `src/landing/components/Navbar.tsx`.

Suggested fix: derive auth mode from search params without effect-driven state where possible; close the mobile menu from navigation click handlers or use a reducer/event boundary.

### 4. Backend test suite is not self-contained

Severity: Medium

Steps to reproduce: run the pytest command above on a clean machine without local services.

Actual behavior: tests fail immediately on Postgres and Redis connection refusal.

Suggested fix: provide Docker Compose or Testcontainers for Postgres/Redis, or mark integration tests with setup checks and add unit tests with dependency overrides/fakes.

### 5. Password reset flow is not reachable from the UI

Severity: Medium

Evidence: backend implements `/auth/forgot-password` and `/auth/reset-password`, but the auth screen only exposes login/register/verify links.

Expected behavior: users can initiate password reset from login.

Actual behavior: no visible password reset workflow in the terminal auth UI.

Suggested fix: add forgot/reset password screens, connect them to the existing endpoints, and replace console-only reset-code delivery before production.

## Security Findings

### Critical: Live production access control is deployment-level, not product-level

The deployed app is unavailable behind Vercel SSO. If this is meant as production, users cannot access it. If this is a preview, automated QA requires a bypass token.

### High: Hardcoded default JWT signing secret

`backend/app/core/config.py` defaults `SECRET_KEY` to `gripper_super_secret_signing_key_2026`. A production process missing `SECRET_KEY` would issue forgeable tokens with a repo-known secret.

Fix: fail startup if `SECRET_KEY` is missing in production and rotate any environment that used the default.

### High: Unauthenticated tenant-context fallback

`get_current_user` accepts `X-Institution-ID` without a token and returns `None`, setting RLS context anyway. Several read endpoints only require `get_current_user`, not `RoleChecker`, so a caller with a tenant UUID can access tenant-scoped data without authentication.

Fix: remove fallback in production or restrict it to explicit test/development mode. Require JWTs on all tenant data endpoints.

### High: Public institution creation

`POST /institutions` has no auth or role requirement. This allows arbitrary tenant creation if reachable.

Fix: protect with admin-only auth or move tenant provisioning to an internal admin path.

### Medium: Permissive CORS with credentials enabled

`allow_origins=["*"]`, `allow_credentials=True`, `allow_methods=["*"]`, and `allow_headers=["*"]` are not production-grade.

Fix: restrict origins to production frontend domains and separate local-dev settings.

### Medium: JWT and user profile stored in localStorage

`src/store/useStore.ts` persists `gripper_token` and `gripper_user` in localStorage. XSS would expose bearer tokens.

Fix: prefer HttpOnly, Secure, SameSite cookies or a short-lived access token plus refresh-token architecture with strong CSP.

### Medium: Verification and password reset codes are printed to server logs

Production logs should not contain account verification secrets.

Fix: deliver codes through email provider, hash one-time codes at rest, expire them, and avoid logging them.

## UX Improvements

1. Add visible password reset entry points.
2. Replace development-oriented copy such as "check the backend console" with production user guidance.
3. Add clear empty states for no institutions, no portfolios, no documents, and no violations.
4. Surface API errors in dashboard workflows instead of mostly logging failures to console.
5. Standardize route naming: `/app` vs `/terminal`.

## Performance Improvements

1. Add route-level code splitting for the landing page vs terminal dashboard; current main JS is `462.72 kB` before gzip.
2. Avoid polling `/documents` every 4 seconds indefinitely; use backoff, only poll pending documents, or use SSE/WebSocket updates.
3. Cache low-volatility lookup data like institutions and portfolios.
4. Avoid creating a new SQLAlchemy superuser engine on every authenticated request.
5. Add rate limits for auth, search, upload, simulation, and LLM/explanation endpoints.

## Accessibility Review

No browser-level keyboard or screen-reader pass could be completed due deployment access/tooling constraints. Code review shows some positive label usage in auth forms, but there are risks:

- Several dashboard controls are icon-heavy and need full accessible names verified.
- Color contrast needs measurement on dark cyan/blue styling.
- Motion-heavy UI should be checked with reduced-motion behavior beyond landing auth transitions.
- Focus order and mobile menu keyboard behavior need browser validation.

Estimated WCAG alignment: incomplete; likely partial, not certifiable without interactive audit.

## Responsive Review

Unable to complete visual viewport testing against the live deployment. Source review indicates responsive landing navigation exists, but dashboard layout uses fixed `h-screen`, `overflow-hidden`, and a `w-80` sidebar, which should be tested carefully on mobile/tablet for trapped content and overflow.

## Production Readiness Scores

- Functionality: 4/10
- Security: 3/10
- Reliability: 4/10
- User Experience: 5/10
- Performance: 5/10
- Accessibility: 4/10
- Overall: 4/10

## Final Recommendation

Not production-ready.

The strongest evidence is that the deployed URL is not accessible as an application, automated backend tests cannot run without external services, lint currently fails, and multiple security controls need hardening before real users or institutional data are introduced. The next release gate should require public/protected deployment clarity, passing CI with provisioned Postgres/Redis, removal of auth bypasses/default secrets, and a Playwright-based end-to-end smoke suite.
