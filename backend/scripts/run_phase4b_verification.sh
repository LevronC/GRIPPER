#!/usr/bin/env bash
# Terminal-only orchestration of existing Phase 4B tools; no new benchmark logic.
set -euo pipefail
umask 077
cd "$(dirname "$0")/.."
BACKEND_DIR="$PWD"
REPO_DIR="$(cd .. && pwd)"
PY="${PHASE4B_PYTHON:-$REPO_DIR/.venv/bin/python}"
test -x "$PY" || { echo 'Create the repository .venv with Python 3.12 (see docs/PHASE4B_VERIFICATION.md), or set PHASE4B_PYTHON.'; exit 1; }
"$PY" - <<'PY'
import sys
if sys.version_info[:2] != (3, 12):
    raise SystemExit('Phase 4B verification requires project-pinned Python 3.12; no databases were modified.')
PY
export LLM_PROVIDER=none LLM_EXTERNAL_PROCESSING_ENABLED=false SUBQ_API_KEY=''
export ENVIRONMENT=test EMBEDDING_PROVIDER=hash_test
export SECRET_KEY="$("$PY" -c 'import secrets; print(secrets.token_hex(32))')"
export REDIS_URL=redis://127.0.0.1:56379/15
export REQUIRE_INTEGRATION=1
export PHASE4B_CONFIG_FILE="$(mktemp -t gripper-phase4b)"
trap 'rm -f "$PHASE4B_CONFIG_FILE"' EXIT

# Read only the two named containers. Never print container environment values.
# Match the PostgreSQL cluster identifier inside the container and over :55432
# before creating anything. Create fresh names; never DROP an existing database.
"$PY" - <<'PY'
import datetime, importlib.metadata, json, os, secrets, shlex, subprocess, sys
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

def inspect(name, internal, external):
    item = json.loads(subprocess.check_output(['docker', 'inspect', name]))[0]
    if not item['State']['Running']:
        raise SystemExit(f'{name} is not running; no changes made')
    ports = item['NetworkSettings']['Ports'].get(f'{internal}/tcp') or []
    if not any(p['HostPort'] == str(external) for p in ports):
        raise SystemExit(f'{name} is not published on expected port {external}')
    return item

pg = inspect('gripper-audit-pg', 5432, 55432)
redis = inspect('gripper-audit-redis', 6379, 56379)
env = dict(value.split('=', 1) for value in pg['Config']['Env'] if '=' in value)
user = env.get('POSTGRES_USER', 'postgres')
password = env.get('POSTGRES_PASSWORD')
if not password:
    raise SystemExit('Container does not expose a local POSTGRES_PASSWORD; configure authentication manually.')
owner = URL.create('postgresql+psycopg2', username=user, password=password,
                   host='127.0.0.1', port=55432, database='postgres')
inside = subprocess.check_output(['docker', 'exec', 'gripper-audit-pg', 'psql', '-X', '-U', user,
    '-d', 'postgres', '-Atc', 'SELECT system_identifier FROM pg_control_system()'], text=True).strip()
engine = create_engine(owner, isolation_level='AUTOCOMMIT')
with engine.connect() as conn:
    outside = str(conn.execute(text('SELECT system_identifier FROM pg_control_system()')).scalar_one())
    if inside != outside:
        raise SystemExit('Host :55432 does not match gripper-audit-pg; refusing setup')
    existing = conn.execute(text("SELECT datname FROM pg_database WHERE datname LIKE 'gripper_%' ORDER BY 1")).scalars().all()
    suffix = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d_%H%M%S') + '_' + secrets.token_hex(2)
    names = {key: f'gripper_{prefix}_{suffix}' for key, prefix in
             [('TEST_DB','eval_test'), ('QUALITY_DB','eval_quality'), ('EXPLAIN_DB','eval_explain'),
              ('BENCH10_DB','bench10k'), ('BENCH50_DB','bench50k')]}
    for name in names.values():
        conn.execute(text(f'CREATE DATABASE "{name}"'))
engine.dispose()
runtime_user = 'gripper_verify_' + suffix
runtime_password = secrets.token_urlsafe(24)
runtime = URL.create('postgresql+psycopg2', username=runtime_user, password=runtime_password,
                    host='127.0.0.1', port=55432, database='postgres')
run_dir = Path('eval_results/phase4b') / ('terminal_' + suffix)
run_dir.mkdir(parents=True)
resources = subprocess.check_output(['docker','info','--format','{{.NCPU}} {{.MemTotal}}'], text=True).split()
metadata = {'existing_gripper_databases': existing, 'created_databases': names,
            'python_version':sys.version, 'python_executable':sys.executable,
            'postgres_cluster_identifier': outside, 'runtime_role': runtime_user,
            'postgres_container': pg['Name'], 'postgres_image': pg['Config']['Image'],
            'redis_container': redis['Name'], 'docker_cpus': int(resources[0]),
            'docker_memory_bytes': int(resources[1]), 'host_ports': {'postgres':55432,'redis':56379}}
(run_dir/'environment.json').write_text(json.dumps(metadata, indent=2)+'\n')
(run_dir/'python_packages.json').write_text(json.dumps(
    {dist.metadata['Name']:dist.version for dist in importlib.metadata.distributions()},
    indent=2,sort_keys=True)+'\n')
values = {**names, 'RUN_DIR':str(run_dir), 'APP_DB_USER':runtime_user, 'APP_DB_PASSWORD':runtime_password,
          'OWNER_URL':owner.render_as_string(hide_password=False),
          'RUNTIME_URL':runtime.render_as_string(hide_password=False)}
Path(os.environ['PHASE4B_CONFIG_FILE']).write_text(''.join(
    f'export {key}={shlex.quote(value)}\n' for key,value in values.items()))
print('Verified Gripper cluster on :55432. Created only fresh synthetic databases.')
print('Results directory:',run_dir)
PY
source "$PHASE4B_CONFIG_FILE"

select_database() {
  export SELECTED_DB="$1"
  # Passwords remain in a private temporary file, never in logs or shell tracing.
  "$PY" - <<'PY' >> "$PHASE4B_CONFIG_FILE"
import os, shlex
from sqlalchemy.engine import make_url
for target, source in [('MIGRATION_DATABASE_URL','OWNER_URL'), ('DATABASE_URL','RUNTIME_URL')]:
    url = make_url(os.environ[source]).set(database=os.environ['SELECTED_DB'])
    print('export '+target+'='+shlex.quote(url.render_as_string(hide_password=False)))
PY
  source "$PHASE4B_CONFIG_FILE"
}

run() {
  local label="$1"; shift
  echo "Running $label"
  "$@" 2>&1 | tee "$RUN_DIR/$label.log"
}

select_database "$TEST_DB"
"$PY" - <<'PY'
import os
from sqlalchemy import create_engine, text
with create_engine(os.environ['MIGRATION_DATABASE_URL']).begin() as conn:
    conn.execute(text('CREATE EXTENSION IF NOT EXISTS vector'))
PY
run migration_upgrade "$PY" -m alembic upgrade head
run runtime_role "$PY" scripts/create_app_role.py
run role_check "$PY" scripts/check_db_role.py
run migration_downgrade "$PY" -m alembic downgrade c8e2a14f6b30
run migration_reupgrade "$PY" -m alembic upgrade head
run redis_ping docker exec gripper-audit-redis redis-cli ping
run backend_lint "$PY" -m ruff check .
run backend_types "$PY" -m mypy
run unit_tests "$PY" -m pytest tests -m 'not integration and not model' -q
run integration_tests "$PY" -m pytest tests -m 'integration and not model' -q --tb=short
run model_tests env HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 "$PY" -m pytest tests -m model -q -rs

select_database "$QUALITY_DB"
run retrieval env HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 "$PY" scripts/eval_retrieval.py --out "$RUN_DIR/retrieval"
select_database "$EXPLAIN_DB"
run explanations "$PY" scripts/eval_explanations.py --out "$RUN_DIR/explanations"

# Sequential: do not run audits, model loads, or other benchmarks concurrently.
select_database "$BENCH10_DB"
run indexes_10k "$PY" scripts/verify_search_indexes.py --chunks 10000 --queries 200 --repeats 3 --concurrency 4 --warmup 20 --seed 42 --measure-index-builds --out "$RUN_DIR/indexes_10k.json"
select_database "$BENCH50_DB"
run indexes_50k "$PY" scripts/verify_search_indexes.py --chunks 50000 --queries 200 --repeats 3 --concurrency 4 --warmup 20 --seed 42 --measure-index-builds --out "$RUN_DIR/indexes_50k.json"

# Audit findings must be recorded without preventing other independent checks.
if run python_audit "$PY" -m pip_audit -r requirements-ci.txt; then
  echo PASS > "$RUN_DIR/python_audit.status"
else
  echo FAIL > "$RUN_DIR/python_audit.status"
fi
run frontend_lint npm --prefix "$REPO_DIR" run lint
run frontend_build npm --prefix "$REPO_DIR" run build
if run npm_audit npm --prefix "$REPO_DIR" audit --audit-level=high; then
  echo PASS > "$RUN_DIR/npm_audit.status"
else
  echo FAIL > "$RUN_DIR/npm_audit.status"
fi
GITLEAKS="${PHASE4B_GITLEAKS:-/private/tmp/gitleaks}"
test -x "$GITLEAKS" || { echo 'Set PHASE4B_GITLEAKS to Gitleaks 8.24.2'; exit 1; }
run secret_scan "$GITLEAKS" detect --source "$REPO_DIR" --config "$REPO_DIR/.gitleaks.toml" --redact --no-banner
git -C "$REPO_DIR" rev-parse HEAD > "$RUN_DIR/git_revision.txt"
git -C "$REPO_DIR" status --short > "$RUN_DIR/git_status.txt"
echo "Verification commands finished. Review failures and results in $BACKEND_DIR/$RUN_DIR."
echo 'Synthetic databases were retained. No production, other containers, pushes, or live LLM requests were used.'
