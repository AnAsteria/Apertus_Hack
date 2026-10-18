"""T18: asynchronous enrichment over Server-Sent Events (CONTRACTS sections 4 and 6).

Flow, after the first cards from POST /api/v1/search have rendered:

1. POST /api/v1/search/{request_id}/enrichment with the same SearchRequest body
   (same revision). The context is held in memory only for this session and
   expires 60 minutes after last use (DECISIONS); it is never written to disk or logs.
2. GET  /api/v1/search/{request_id}/events?revision=N streams SseEvent records:
   progress -> interpretation -> progress -> assessment* -> complete.
   A failed stage emits an `error` event (payload.stage says which) and the
   stream moves on; `complete` closes it. STALE_REVISION ends it immediately.

A newer revision for the same request makes older streams stop with a
STALE_REVISION error, so late results never overwrite a newer search. Any
failure is an SSE error event; it never touches the initial search response.

Integration (shared file, owner: Dimitry): `app.include_router(enrichment.router)`
in app/main.py, and the UI calls step 1 then opens step 2 with fetch/EventSource.
"""
from __future__ import annotations

import os
import re
import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from typing import Callable, Iterator

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse, StreamingResponse

from ..ai.assess import assess
from ..ai.client import InferenceError
from ..ai.config import InferenceConfig
from ..ai.interpret import Interpretation, interpret
from ..contracts import (MAX_CONTEXT_CHARS, MAX_NEEDS, MAX_QUERY_CHARS, SCHEMA_VERSION, Result, SearchRequest,
                         SseEvent, error)

router = APIRouter()

CONTEXT_TTL_S = 3600      # DECISIONS: company context lives in memory, 60 min after last use
JOB_LIFETIME_S = 600      # DECISIONS: enrichment job lifetime 10 minutes
INTERPRET_TIMEOUT_S = float(os.environ.get("BERNMATCH_INTERPRET_TIMEOUT_S", "60"))  # first cards are unaffected
# 70B interpretation took ~47-52 s on the gateway on 2026-10-18 (vs ~5 s earlier): measure in T16.
REQUEST_ID_RE = re.compile(r"^req_[A-Za-z0-9]{1,64}$")

ASSESS_TIMEOUT_S = float(os.environ.get("BERNMATCH_ASSESS_TIMEOUT_S", "45"))

Interpreter = Callable[[SearchRequest], Interpretation]
CandidateProvider = Callable[[SearchRequest], list[Result]]
Assessor = Callable  # (query, needs, candidates, on_result) -> (payloads, stats)


def _default_interpreter(req: SearchRequest) -> Interpretation:
    return interpret(req.query, req.company_context, req.needs)


def _default_candidates(req: SearchRequest) -> list[Result]:
    """Re-run the same search to get cards whose evidence text was resolved by code.
    Client-sent card text is never trusted for assessment."""
    from .search import get_backend, index_ready, FixtureBackend

    backend = get_backend()
    if backend is None or (not isinstance(backend, FixtureBackend) and not index_ready()):
        return []
    return list(backend.search(req).results)


def _default_reranker(req: SearchRequest, expansions: list[str]) -> tuple[list[Result], list[str]]:
    """T30: original query plus validated expansions, fused at entity level (served == measured)."""
    from ..search.expansion import expanded_search
    from .search import get_backend, index_ready, FixtureBackend

    backend = get_backend()
    if backend is None or (not isinstance(backend, FixtureBackend) and not index_ready()):
        return [], []
    return expanded_search(backend, req, expansions)


def _default_assessor(query, needs, candidates, on_result):
    return assess(query, needs, candidates, on_result=on_result)


_interpreter: Interpreter = _default_interpreter
_candidates: CandidateProvider = _default_candidates
_assessor: Assessor = _default_assessor
_reranker = _default_reranker
RERANK_TIMEOUT_S = float(os.environ.get("BERNMATCH_RERANK_TIMEOUT_S", "10"))
_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="enrich")


def set_interpreter(fn: Interpreter | None) -> None:
    """Tests and integration may replace the interpreter."""
    global _interpreter
    _interpreter = fn or _default_interpreter


def set_candidate_provider(fn: CandidateProvider | None) -> None:
    global _candidates
    _candidates = fn or _default_candidates


def set_reranker(fn=None) -> None:
    global _reranker
    _reranker = fn or _default_reranker


def set_assessor(fn: Assessor | None) -> None:
    global _assessor
    _assessor = fn or _default_assessor


class Registry:
    """In-memory, per-process request context. Not persisted anywhere."""

    def __init__(self):
        self._lock = threading.Lock()
        self._items: dict[str, dict] = {}

    def _purge(self, now: float) -> None:
        for rid in [r for r, v in self._items.items() if v["expires"] < now]:
            del self._items[rid]

    def register(self, request_id: str, req: SearchRequest) -> bool:
        """False if a newer revision is already registered (the caller is stale)."""
        now = time.monotonic()
        with self._lock:
            self._purge(now)
            cur = self._items.get(request_id)
            if cur and cur["request"].revision > req.revision:
                return False
            self._items[request_id] = {"request": req, "expires": now + CONTEXT_TTL_S}
            return True

    def get(self, request_id: str) -> SearchRequest | None:
        now = time.monotonic()
        with self._lock:
            self._purge(now)
            item = self._items.get(request_id)
            if item:
                item["expires"] = now + CONTEXT_TTL_S
            return item["request"] if item else None

    def latest_revision(self, request_id: str) -> int | None:
        with self._lock:
            item = self._items.get(request_id)
            return item["request"].revision if item else None

    def clear(self) -> None:
        with self._lock:
            self._items.clear()


registry = Registry()


def _sse(request_id: str, revision: int, seq: int, event_type: str, payload: dict) -> str:
    ev = SseEvent(schema_version=SCHEMA_VERSION, request_id=request_id, revision=revision, event_sequence=seq,
                  event_type=event_type, payload=payload)
    return f"event: {event_type}\ndata: {ev.model_dump_json()}\n\n"


def _error_payload(code: str, message: str, retryable: bool) -> dict:
    return {"code": code, "message": message, "retryable": retryable}


@router.post("/api/v1/search/{request_id}/enrichment", status_code=202)
def start_enrichment(request_id: str, req: SearchRequest):
    if not REQUEST_ID_RE.match(request_id):
        return JSONResponse(error("BAD_REQUEST", "Unknown request id format."), status_code=400)
    if (len(req.query) > MAX_QUERY_CHARS or len(req.company_context or "") > MAX_CONTEXT_CHARS
            or len(req.needs) > MAX_NEEDS):
        return JSONResponse(error("INPUT_TOO_LARGE", "Input exceeds the configured limit."), status_code=413)
    if not registry.register(request_id, req):
        return JSONResponse(error("REVISION_CONFLICT", "A newer revision of this search exists."), status_code=409)
    return {"schema_version": SCHEMA_VERSION, "request_id": request_id, "revision": req.revision,
            "events_url": f"/api/v1/search/{request_id}/events?revision={req.revision}"}


@router.get("/api/v1/search/{request_id}/events")
def enrichment_events(request_id: str, revision: int = Query(ge=1)):
    req = registry.get(request_id)
    if req is None:
        return JSONResponse(error("BAD_REQUEST", "No enrichment registered for this search."), status_code=404)
    if req.revision != revision:
        return JSONResponse(error("REVISION_CONFLICT", "Revision does not match the registered search."),
                            status_code=409)
    return StreamingResponse(_stream(request_id, req), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _stream(request_id: str, req: SearchRequest) -> Iterator[str]:
    rev, seq = req.revision, 0
    started = time.monotonic()
    timings: dict = {}

    def event(event_type: str, payload: dict) -> str:
        nonlocal seq
        out = _sse(request_id, rev, seq, event_type, payload)
        seq += 1
        return out

    def stale() -> bool:
        return registry.latest_revision(request_id) != rev

    # Stage 1: interpretation.
    yield event("progress", {"stage": "interpretation", "state": "started"})
    t0 = time.monotonic()
    interp = None
    future = _pool.submit(_interpreter, req)
    try:
        interp = future.result(timeout=min(INTERPRET_TIMEOUT_S, JOB_LIFETIME_S))
    except FutureTimeout:
        future.cancel()
        yield event("error", _error_payload("ENRICHMENT_TIMEOUT", "Interpretation took too long; initial results are unaffected.", True) | {"stage": "interpretation"})
    except InferenceError as e:
        yield event("error", _error_payload("ENRICHMENT_UNAVAILABLE", "Interpretation is unavailable; initial results are unaffected.", e.retryable) | {"stage": "interpretation"})
    except Exception:  # never leak details (they may contain company text)
        yield event("error", _error_payload("ENRICHMENT_FAILED", "Interpretation failed; initial results are unaffected.", False) | {"stage": "interpretation"})
    timings["interpretation_ms"] = int((time.monotonic() - t0) * 1000)
    if stale():
        yield event("error", _error_payload("STALE_REVISION", "A newer revision replaced this search.", False))
        return
    if interp is not None:
        payload = interp.payload()
        payload["decoding_mode"] = interp.decoding_mode
        yield event("interpretation", payload)

    # Stage 1b (T30): enriched second retrieval pass over the validated expansions. The first
    # cards stay as they are until this validated ranking arrives; failure leaves them untouched.
    candidates = None
    expansions = [e.get("text") for e in (interp.expanded_queries if interp is not None else []) if e.get("text")]
    if expansions:
        t2 = time.monotonic()
        future = _pool.submit(_reranker, req, expansions)
        try:
            reranked, used = future.result(timeout=min(RERANK_TIMEOUT_S, JOB_LIFETIME_S))
        except Exception:
            future.cancel()
            reranked, used = [], []
            yield event("error", _error_payload("RERANK_FAILED", "The expanded search failed; initial results are unaffected.", True) | {"stage": "reranked"})
        timings["rerank_ms"] = int((time.monotonic() - t2) * 1000)
        if stale():
            yield event("error", _error_payload("STALE_REVISION", "A newer revision replaced this search.", False))
            return
        if reranked:
            candidates = reranked
            yield event("reranked", {"results": [r.model_dump() for r in reranked], "expanded_queries": used,
                                     "elapsed_ms": timings["rerank_ms"]})

    # Stage 2: batched assessment of the current candidates.
    if candidates is None:
        try:
            candidates = _candidates(req)
        except Exception:
            candidates = []
    needs = interp.needs if interp is not None else list(req.needs)
    if not candidates:
        yield event("progress", {"stage": "assessment", "state": "skipped", "reason": "no_candidates"})
    elif _assessor is _default_assessor and not InferenceConfig.from_env().enabled:
        # Fixture mode / no key: say so instead of emitting a model error.
        yield event("progress", {"stage": "assessment", "state": "skipped", "reason": "inference_disabled"})
    else:
        yield event("progress", {"stage": "assessment", "state": "started", "candidates": min(len(candidates), 8)})
        t1 = time.monotonic()
        ready: "queue.Queue" = queue.Queue()
        future = _pool.submit(_assessor, req.query, needs, candidates, ready.put)
        deadline = t1 + min(ASSESS_TIMEOUT_S, JOB_LIFETIME_S)
        stats, assessed = None, 0
        while True:
            try:
                item = ready.get(timeout=0.05)
            except queue.Empty:
                item = None
            if item is not None:
                if stale():
                    yield event("error", _error_payload("STALE_REVISION", "A newer revision replaced this search.", False))
                    return
                yield event("assessment", item.model_dump())
                assessed += 1
                continue
            if future.done():
                while not ready.empty():  # drain anything published just before completion
                    if stale():
                        yield event("error", _error_payload("STALE_REVISION", "A newer revision replaced this search.", False))
                        return
                    yield event("assessment", ready.get().model_dump())
                    assessed += 1
                try:
                    _, stats = future.result()
                except InferenceError as e:
                    yield event("error", _error_payload("ASSESSMENT_UNAVAILABLE", "Assessment is unavailable; initial results are unaffected.", e.retryable) | {"stage": "assessment"})
                except Exception:
                    yield event("error", _error_payload("ASSESSMENT_FAILED", "Assessment failed; initial results are unaffected.", False) | {"stage": "assessment"})
                break
            if time.monotonic() > deadline:
                future.cancel()
                yield event("error", _error_payload("ASSESSMENT_TIMEOUT", "Assessment took too long; initial results are unaffected.", True) | {"stage": "assessment"})
                break
        timings["assessment_ms"] = int((time.monotonic() - t1) * 1000)
        timings["assessed"] = assessed
        if stats is not None:
            timings.update(batches=len(stats.latency_s), prompt_tokens=stats.usage.prompt_tokens,
                           completion_tokens=stats.usage.completion_tokens, decoding_modes=stats.decoding_modes,
                           corrections=stats.corrections)
    yield event("complete", {"elapsed_ms": int((time.monotonic() - started) * 1000)} | timings)
