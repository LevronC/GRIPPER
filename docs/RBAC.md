# Role matrix

| Endpoint | Allowed roles |
|----------|----------------|
| `GET /institutions` | Public (unauthenticated list for sign-up) |
| `POST /institutions` | admin |
| `GET /portfolios`, holdings, IPS rules, documents, violations | analyst, sector_lead, pm, faculty, trustee, admin |
| `POST /portfolios` | pm, admin |
| `POST /portfolios/{id}/holdings` | pm, sector_lead, admin |
| `POST /documents/upload` | analyst, sector_lead, pm, admin |
| `POST /portfolios/{id}/evaluate`, explain | analyst, sector_lead, pm, admin |
| `POST /portfolios/{id}/simulate` | pm, sector_lead, admin |

Production disables `X-Institution-ID`-only auth (JWT required). Set `ALLOW_HEADER_AUTH=true` for local integration scripts.
