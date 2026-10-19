"""Application skeleton. Retrieval and inference are NOT implemented here (T09, T05).

Readiness stays false until corpus/index assets are loaded: a marker file
`$BERNMATCH_DATA_DIR/READY` written by the index-build step.
"""
import mimetypes
import os

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .api.admin import router as admin_router
from .api import enrich, ratelimit
from .api.enrichment import router as enrichment_router, set_interpreter
from .api.evidence import router as evidence_router
from .api.feedback import router as feedback_router
from .api.search import router as search_router
from .contracts import error

# The container's mime table lacks .webp: without this hero.webp is served as text/plain.
mimetypes.add_type("image/webp", ".webp")

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


def data_dir() -> str:
    return os.environ.get("BERNMATCH_DATA_DIR", "data")


def index_ready() -> bool:
    return os.path.exists(os.path.join(data_dir(), "READY"))


def deployed_revision() -> str | None:
    """The git revision the deploy script wrote next to the app (T33), if any."""
    try:
        with open(os.path.join(os.path.dirname(__file__), "REVISION"), encoding="utf-8") as f:
            return f.read().strip() or None
    except OSError:
        return None


# No /docs or /redoc pages: they load scripts from a CDN, and the UI makes no external requests.
app = FastAPI(title="Bern Match", version="0.0.1", docs_url=None, redoc_url=None)
app.middleware("http")(ratelimit.middleware)


@app.middleware("http")
async def _revalidate_ui(request: Request, call_next):
    # UI files must never be served from a stale browser cache: without this header Chrome reused
    # an old style.css next to a new index.html (blue page, giant search icon). ETag still gives 304s.
    response = await call_next(request)
    if not request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-cache")
    return response


@app.exception_handler(RequestValidationError)
async def _validation(_: Request, exc: RequestValidationError):
    # Fixed text only: validation details can contain submitted company text.
    return JSONResponse(error("VALIDATION_ERROR", "Request does not match the schema."), status_code=422)


@app.get("/healthz")
def healthz():
    """Liveness only. `revision` is set when the app was deployed with scripts/deploy_space.sh."""
    return {"status": "ok", "revision": deployed_revision()}


@app.get("/readyz")
def readyz():
    if not index_ready():
        return JSONResponse(error("INDEX_NOT_READY", "Search indexes are not ready.", True), status_code=503)
    return {"status": "ready"}


app.include_router(search_router)
app.include_router(feedback_router)
from .api.brief import router as brief_router  # T23/T24/T28 (Stretch)
app.include_router(brief_router)
app.include_router(enrichment_router)
app.include_router(evidence_router)

if enrich.fixture_mode():
    set_interpreter(enrich.fixture_interpreter)  # SYNTHETIC; never on by default
app.include_router(admin_router)


if os.path.isdir(STATIC_DIR):
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="ui")
