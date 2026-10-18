"""POST /api/v1/search. Retrieval backend is pluggable: T09 supplies the real one.

Fixture mode (BERNMATCH_FIXTURE_MODE=1) serves SYNTHETIC cards so the UI can be built and
tested before the backend exists. It is never on by default and the response says so.
"""
import json
import os
import uuid
from typing import Optional, Protocol

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..contracts import (MAX_CONTEXT_CHARS, MAX_NEEDS, MAX_QUERY_CHARS, MAX_RESULTS, SearchRequest,
                         SearchResponse, error)

router = APIRouter()
FIXTURE = os.path.join(os.path.dirname(__file__), "..", "..", "tests", "fixtures", "search_response_cards.json")


class SearchBackend(Protocol):
    def search(self, req: SearchRequest) -> SearchResponse: ...


class FixtureBackend:
    """Deterministic synthetic results. Honours the requested entity type; no real data."""

    def search(self, req: SearchRequest) -> SearchResponse:
        with open(FIXTURE, encoding="utf-8") as f:
            data = json.load(f)
        results = [r for r in data["results"] if req.entity_type in (None, r["entity_type"])][:MAX_RESULTS]
        for i, r in enumerate(results, 1):
            r["rank"] = i
        data.update(request_id="req_" + uuid.uuid4().hex, revision=req.revision, results=results)
        if not results:
            data["limitations"].append("Support was not found in the indexed corpus.")
        return SearchResponse(**data)


_backend: Optional[SearchBackend] = None


def set_backend(backend: Optional[SearchBackend]) -> None:
    """Called by the T09 integration to plug in real retrieval."""
    global _backend
    _backend = backend


def get_backend() -> Optional[SearchBackend]:
    if _backend is not None:
        return _backend
    return FixtureBackend() if os.environ.get("BERNMATCH_FIXTURE_MODE") == "1" else None


def index_ready() -> bool:
    return os.path.exists(os.path.join(os.environ.get("BERNMATCH_DATA_DIR", "data"), "READY"))


@router.post("/api/v1/search")
def search(req: SearchRequest):
    if (len(req.query) > MAX_QUERY_CHARS or len(req.company_context or "") > MAX_CONTEXT_CHARS
            or len(req.needs) > MAX_NEEDS):
        return JSONResponse(error("INPUT_TOO_LARGE", "Input exceeds the configured limit."), status_code=413)
    backend = get_backend()
    if isinstance(backend, FixtureBackend):
        return backend.search(req).model_dump()
    if not index_ready():
        return JSONResponse(error("INDEX_NOT_READY", "Search indexes are not ready.", True), status_code=503)
    if backend is None:
        # Never invent results.
        return JSONResponse(error("NOT_IMPLEMENTED", "Retrieval is not implemented yet."), status_code=501)
    return backend.search(req).model_dump()
