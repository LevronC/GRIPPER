# Local demo (synthetic data)

Gripper no longer seeds any account automatically, and there are no shared public
credentials. The previous behaviour (a demo analyst with a password published in this
repository, created on every API start, inside tenants named after real universities)
was removed because anyone could sign in to the deployed app with it.

## Create a synthetic demo locally

```bash
cd backend
export ENVIRONMENT=development
export MIGRATION_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/gripper
export DEMO_PASSWORD='pick-a-local-passphrase'   # optional; otherwise one is generated and printed once
python scripts/seed_demo.py
```

This creates the institution **"Synthetic Demo Fund (not a real institution)"** (`synthetic-demo`)
with an admin, a PM and an analyst account. All data is fictional.

The script refuses to run when `ENVIRONMENT=production`, when `VERCEL=1`, or against a
non-local database host (override the host check with `--allow-remote-db` for a disposable
staging database; production is never allowed).

## A public demo, safely

If you want a public demo deployment, use a **separate** Vercel project and database
that contain only synthetic data. Create accounts there with `scripts/provision_institution.py`
or invitations, rotate the passwords periodically, and never point it at a database that
holds real institutional data.
