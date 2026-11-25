# Credentials

API keys stay out of git. `backend/.env` is ignored. `backend/.env.example` is tracked and must keep empty values.

| Secret | Where it lives | What must not happen |
|---|---|---|
| `SUBQ_API_KEY` | The API process environment, or `backend/.env` on a machine you control | Do not put it in `.env.example`, a report, a test, or a chat |
| `HF_API_KEY` | Same, only if embeddings are requested from Hugging Face | Local embeddings do not need a key and do not send text out |
| `SECRET_KEY` | Process environment | Not a signing default checked into the repo |

Revoke a key in the provider console if it has been pasted into a terminal, a chat, or a tracked file. Replacing the file is not the same as revoking the key.

CI runs Gitleaks `v8.24.2` (`gitleaks detect --redact`). Locally, after installing that release:

```bash
gitleaks detect --source . --redact --no-banner
```

A `.pre-commit-config.yaml` is in the repo. It runs only after `pre-commit install`. The hook is optional.
