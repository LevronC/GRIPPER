import logging
import os
import sys
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
BACKEND_DIR = os.path.join(ROOT_DIR, "backend")

# Swagger UI must load the spec from the mounted /api prefix on Vercel.
os.environ.setdefault("SWAGGER_OPENAPI_URL", "/api/openapi.json")

if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.db.migrate import ensure_database_ready  # noqa: E402
from app.main import app as backend_app  # noqa: E402

_bootstrap_error: Optional[Exception] = None

try:
    ensure_database_ready()
    logger.info("Database bootstrap succeeded on cold start")
except Exception as exc:
    _bootstrap_error = exc
    logger.exception("Database bootstrap failed on cold start: %s", exc)

app = FastAPI(title="Gripper Vercel API Gateway")


@app.middleware("http")
async def retry_bootstrap(request: Request, call_next):
    """
    If the cold-start migration failed, retry it on every request until it
    succeeds.  Once _database_ready is True (inside ensure_database_ready),
    the function returns immediately without re-running migrations.
    """
    global _bootstrap_error
    if _bootstrap_error is not None:
        try:
            ensure_database_ready()
            _bootstrap_error = None
            logger.info("Database bootstrap succeeded on retry")
        except Exception as exc:
            _bootstrap_error = exc
            logger.error("Database bootstrap retry failed: %s", exc)
            return JSONResponse(
                status_code=503,
                content={
                    "detail": (
                        "Database is not ready. Migrations may still be running. "
                        f"Error: {exc}"
                    )
                },
            )
    return await call_next(request)


app.mount("/api", backend_app)
