# Role matrix

Roles are defined in `backend/app/core/rbac.py` and enforced server-side by
`RoleChecker` (`backend/app/api/deps.py`). Every route below also applies the tenant
boundary: a user only ever acts within their own institution (see
[DATABASE_SECURITY.md](DATABASE_SECURITY.md)). Unit coverage:
`backend/tests/test_rbac.py`; integration coverage: `backend/tests/integration/`.

| Endpoint | analyst | sector_lead | pm | faculty | trustee | admin |
|---|:-:|:-:|:-:|:-:|:-:|:-:|
| `GET /institutions` (own only), `/portfolios`, holdings, `/ips_rules`, `/documents`, violations | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `POST /search/semantic` | ✓ | ✓ | ✓ | – | – | ✓ |
| `POST /documents/upload` | ✓ | ✓ | ✓ | – | – | ✓ |
| `POST /portfolios/{id}/evaluate`, `POST /violations/{id}/explain` | ✓ | ✓ | ✓ | – | – | ✓ |
| `POST /portfolios/{id}/simulate` | – | ✓ | ✓ | – | – | ✓ |
| `POST /portfolios/{id}/holdings` | – | ✓ | ✓ | – | – | ✓ |
| `POST /portfolios` | – | – | ✓ | – | – | ✓ |
| `POST/PATCH /ips_rules`, `POST /ips_rules/{id}/deactivate` | – | – | – | – | – | ✓ |
| `POST/GET/DELETE /admin/invitations`, `PATCH /users/{id}/role` | – | – | – | – | – | ✓ |

Unauthenticated: `POST /auth/login`, `/auth/invitations/accept`,
`/auth/password-reset/request`, `/auth/password-reset/confirm`, `GET /health`, `/health/db`.

## Decisions

* **Semantic search is limited to research roles** (`RESEARCH_ROLES`). Faculty and
  trustees have read-only oversight of portfolios and compliance, but not search over
  analyst research. Previously the endpoint used `READ_ROLES`, contradicting the role
  comment and this document.
* **Membership is invitation-only.** An admin may invite any role, but only into their own
  institution. There is no API for creating institutions; operators use
  `backend/scripts/provision_institution.py`.
* There is no header-based authentication. The `X-Institution-ID` header is ignored.
