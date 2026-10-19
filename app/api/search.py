"""POST /api/v1/search. Retrieval backend is pluggable: T09 supplies the real one.

Fixture mode (BERNMATCH_FIXTURE_MODE=1) serves SYNTHETIC cards so the UI can be built and
tested before the backend exists. It is never on by default and the response says so.
"""
import json
import os
import uuid
import threading
import time
from typing import Optional, Protocol

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from . import enrich
from ..search.ranking import relevance_cut
from ..lifecycle import serving
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
_disk_backend = None
_disk_key = None
_load_lock = threading.Lock()


def set_backend(backend: Optional[SearchBackend]) -> None:
    """Called by the T09 integration to plug in real retrieval."""
    global _backend, _disk_backend, _disk_key
    _backend = backend
    _disk_backend = _disk_key = None


def get_backend() -> Optional[SearchBackend]:
    if _backend is not None:
        return _backend
    if os.environ.get("BERNMATCH_FIXTURE_MODE") == "1":
        return FixtureBackend()
    from ..storage.indexes import current_generation
    current = current_generation(os.environ.get("BERNMATCH_DATA_DIR", "data"))
    if current is None:
        return None
    directory, manifest = current
    key = (str(directory.resolve()), manifest["fingerprint"])
    global _disk_backend, _disk_key
    with _load_lock:
        if key != _disk_key:
            try:
                from ..search.backend import HybridBackend
                loaded = HybridBackend(directory)
            except Exception:
                # Fixed public error below; no source/company/exception text.
                return None
            _disk_backend, _disk_key = loaded, key
        return _disk_backend


def index_ready() -> bool:
    return os.path.exists(os.path.join(os.environ.get("BERNMATCH_DATA_DIR", "data"), "READY"))


@router.post("/api/v1/search")
def search(req: SearchRequest):
    started = time.perf_counter()
    if (len(req.query) > MAX_QUERY_CHARS or len(req.company_context or "") > MAX_CONTEXT_CHARS
            or len(req.needs) > MAX_NEEDS):
        return JSONResponse(error("INPUT_TOO_LARGE", "Input exceeds the configured limit."), status_code=413)
    backend = get_backend()
    if isinstance(backend, FixtureBackend):
        return enrich.apply_state(serving.apply(backend.search(req).model_dump()), req)
    if not index_ready():
        return JSONResponse(error("INDEX_NOT_READY", "Search indexes are not ready.", True), status_code=503)
    if backend is None:
        # Never invent results.
        return JSONResponse(error("NOT_IMPLEMENTED", "Retrieval is not implemented yet."), status_code=501)
    response = backend.search(req)
    data = enrich.apply_state(serving.apply(response.model_dump()), req)
    gap = float(os.environ.get("BERNMATCH_RELEVANCE_GAP", "0.02"))
    if gap > 0 and data.get("results"):
        # Nothing is removed: on the evaluation split, cutting the weaker cards lost 2 of 17 answers
        # (0.765 -> 0.647). Cards far below the best one are only flagged, so the UI can fold them
        # under "more results". The answer outcome and Recall@10 are unchanged.
        strong = {r["entity_id"] for r in relevance_cut(data["results"], gap)}
        for r in data["results"]:
            r["retrieval"] = (r.get("retrieval") or {}) | {"weaker_match": r["entity_id"] not in strong}
    data["timing_ms"] = (data.get("timing_ms") or {}) | {"request_total": (time.perf_counter()-started)*1000}
    return data
