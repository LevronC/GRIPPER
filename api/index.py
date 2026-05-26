import os
import sys

from fastapi import FastAPI

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
BACKEND_DIR = os.path.join(ROOT_DIR, "backend")

# Swagger UI must load the spec from the mounted /api prefix on Vercel.
os.environ.setdefault("SWAGGER_OPENAPI_URL", "/api/openapi.json")

if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.main import app as backend_app  # noqa: E402

app = FastAPI(title="Gripper Vercel API Gateway")
app.mount("/api", backend_app)
