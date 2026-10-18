"""Application skeleton. Retrieval and inference are NOT implemented here (T09, T05).

Readiness stays false until corpus/index assets are loaded: a marker file
`$BERNMATCH_DATA_DIR/READY` written by the index-build step.
"""
import os
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .contracts import MAX_CONTEXT_CHARS, MAX_NEEDS, MAX_QUERY_CHARS, SearchRequest, error

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


def data_dir() -> str:
    return os.environ.get("BERNMATCH_DATA_DIR", "data")


def index_ready() -> bool:
    return os.path.exists(os.path.join(data_dir(), "READY"))


app = FastAPI(title="Bern Match", version="0.0.1")


@app.exception_handler(RequestValidationError)
async def _validation(_: Request, exc: RequestValidationError):
    # Fixed text only: validation details can contain submitted company text.
    return JSONResponse(error("VALIDATION_ERROR", "Request does not match the schema."), status_code=422)


@app.get("/healthz")
def healthz():
    """Liveness only."""
    return {"status": "ok"}


@app.get("/readyz")
def readyz():
    if not index_ready():
        return JSONResponse(error("INDEX_NOT_READY", "Search indexes are not ready.", True), status_code=503)
    return {"status": "ready"}


@app.post("/api/v1/search")
def search(req: SearchRequest):
    if (len(req.query) > MAX_QUERY_CHARS or len(req.company_context or "") > MAX_CONTEXT_CHARS
            or len(req.needs) > MAX_NEEDS):
        return JSONResponse(error("INPUT_TOO_LARGE", "Input exceeds the configured limit."), status_code=413)
    if not index_ready():
        return JSONResponse(error("INDEX_NOT_READY", "Search indexes are not ready.", True), status_code=503)
    # Placeholder until T09 supplies retrieval; never invent results.
    return JSONResponse(error("NOT_IMPLEMENTED", "Retrieval is not implemented yet."), status_code=501,
                        headers={"X-Request-Id": "req_" + uuid.uuid4().hex})


if os.path.isdir(STATIC_DIR):
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="ui")
