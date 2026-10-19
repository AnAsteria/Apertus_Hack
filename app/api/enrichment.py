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

import hashlib
import json
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

ASSESS_TIMEOUT_S = float(os.environ.get("BERNMATCH_ASSESS_TIMEOUT_S", "30"))  # B2: was 45; B1 p95 is ~16 s
INTERPRET_DEADLINE_S = float(os.environ.get("BERNMATCH_INTERPRET_DEADLINE_S", "12"))  # then fall back to 8B

Interpreter = Callable[[SearchRequest], Interpretation]
CandidateProvider = Callable[[SearchRequest], list[Result]]
Assessor = Callable  # (query, needs, candidates, on_result) -> (payloads, stats)


INTERPRET_CACHE_TTL_S = float(os.environ.get("BERNMATCH_INTERPRET_CACHE_TTL_S", "3600"))
INTERPRET_CACHE_MAX = 256
_interp_cache: dict[str, tuple[float, Interpretation]] = {}
_interp_cache_lock = threading.Lock()


def _interp_key(req: SearchRequest) -> str:
    """Normalised query + company context + the analyst's own needs. In memory only, with the
    same 60-minute lifetime as the session context (DECISIONS); never written to disk or logs."""
    norm = lambda t: re.sub(r"\s+", " ", (t or "").casefold()).strip()
    needs = sorted((n.kind, norm(n.text)) for n in req.needs if n.origin == "user")
    raw = json.dumps([norm(req.query), norm(req.company_context), needs], ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def _default_interpreter(req: SearchRequest) -> Interpretation:
    """B1 (#126): cache interpretations per normalised request, so a re-run or an edit that keeps
    the same text skips the 70B call (~5 s)."""
    key, now = _interp_key(req), time.monotonic()
    with _interp_cache_lock:
        hit = _interp_cache.get(key)
        if hit and now - hit[0] < INTERPRET_CACHE_TTL_S:
            return hit[1]
    result = interpret(req.query, req.company_context, req.needs)
    with _interp_cache_lock:
        if len(_interp_cache) >= INTERPRET_CACHE_MAX:
            for k in sorted(_interp_cache, key=lambda k: _interp_cache[k][0])[:INTERPRET_CACHE_MAX // 4]:
                del _interp_cache[k]
        _interp_cache[key] = (now, result)
    return result


def warm_up() -> None:
    """B1 (#126): one tiny call per model at startup, so the first analyst request doesn't pay a
    cold start (49 s observed once on 70B). Opt-in via BERNMATCH_WARMUP=1; failures are ignored."""
    from ..ai.client import get_client
    try:
        client = get_client()
        if not client.config.enabled:
            return
        for model in {client.config.quality_model, client.config.model}:
            client.chat([{"role": "user", "content": "Reply with OK."}], model=model, max_tokens=3)
    except Exception:
        pass


if os.environ.get("BERNMATCH_WARMUP") == "1":
    threading.Thread(target=warm_up, name="apertus-warmup", daemon=True).start()


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
        return [], None  # no index: nothing to report, the assessment stage says so
    return expanded_search(backend, req, expansions)


def _default_assessor(query, needs, candidates, on_result):
    return assess(query, needs, candidates, on_result=on_result)


def _default_fallback_interpreter(req: SearchRequest) -> Interpretation:
    """B2 (#127): the fast model, used only when the primary model misses its deadline or fails.
    Not cached, so a later request can still get the primary model's (better) interpretation."""
    from ..ai.client import get_client
    return interpret(req.query, req.company_context, req.needs, model=get_client().config.model)


_interpreter: Interpreter = _default_interpreter
_fallback_interpreter = _default_fallback_interpreter
_candidates: CandidateProvider = _default_candidates
_assessor: Assessor = _default_assessor
_reranker = _default_reranker
RERANK_TIMEOUT_S = float(os.environ.get("BERNMATCH_RERANK_TIMEOUT_S", "10"))
_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="enrich")


def set_interpreter(fn: Interpreter | None, fallback=...) -> None:
    """Tests and integration may replace the interpreter. Replacing it disables the 8B fallback
    unless `fallback` is given, so a fake interpreter is never silently backed by a real model."""
    global _interpreter, _fallback_interpreter
    _interpreter = fn or _default_interpreter
    if fallback is not ...:
        _fallback_interpreter = fallback
    else:
        _fallback_interpreter = None if fn else _default_fallback_interpreter


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

    # Stage 1: interpretation. B2 (#127): wait up to INTERPRET_DEADLINE_S for the primary (70B)
    # model; if it is slower or fails, fall back to the fast (8B) model within the overall budget.
    yield event("progress", {"stage": "interpretation", "state": "started"})
    t0 = time.monotonic()
    interp, used_model = None, "primary"
    budget = min(INTERPRET_TIMEOUT_S, JOB_LIFETIME_S)
    future = _pool.submit(_interpreter, req)
    failure = None
    try:
        interp = future.result(timeout=min(INTERPRET_DEADLINE_S, budget))
    except FutureTimeout:
        failure = ("ENRICHMENT_TIMEOUT", "Interpretation took too long; initial results are unaffected.", True)
    except InferenceError as e:
        failure = ("ENRICHMENT_UNAVAILABLE", "Interpretation is unavailable; initial results are unaffected.", e.retryable)
    except Exception:  # never leak details (they may contain company text)
        failure = ("ENRICHMENT_FAILED", "Interpretation failed; initial results are unaffected.", False)
    if failure is not None:
        future.cancel()  # a running primary call is not interrupted, but its result is ignored
        remaining = budget - (time.monotonic() - t0)
        if _fallback_interpreter is not None and remaining > 1:
            yield event("progress", {"stage": "interpretation", "state": "fallback", "reason": failure[0]})
            fb = _pool.submit(_fallback_interpreter, req)
            try:
                interp, used_model, failure = fb.result(timeout=remaining), "fallback", None
            except FutureTimeout:
                fb.cancel()
            except Exception:
                pass
        if failure is not None:
            yield event("error", _error_payload(*failure) | {"stage": "interpretation"})
    timings["interpretation_ms"] = int((time.monotonic() - t0) * 1000)
    timings["interpretation_model"] = used_model if interp is not None else None
    if stale():
        yield event("error", _error_payload("STALE_REVISION", "A newer revision replaced this search.", False))
        return
    if interp is not None:
        payload = interp.payload()
        payload["decoding_mode"] = interp.decoding_mode
        payload["model"] = used_model  # D14 (additive): "primary" (70B) or "fallback" (8B)
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
            reranked, used = [], None
            yield event("error", _error_payload("RERANK_FAILED", "The expanded search failed; initial results are unaffected.", True) | {"stage": "reranked"})
        timings["rerank_ms"] = int((time.monotonic() - t2) * 1000)
        if stale():
            yield event("error", _error_payload("STALE_REVISION", "A newer revision replaced this search.", False))
            return
        if reranked:
            candidates = reranked
            yield event("reranked", {"results": [r.model_dump() for r in reranked], "expanded_queries": used,
                                     "elapsed_ms": timings["rerank_ms"]})
        elif used == []:
            # Guarded original outcome (refusal / too broad) or nothing to fuse: cards stay as they are.
            yield event("progress", {"stage": "reranked", "state": "skipped", "reason": "original_outcome_kept"})

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
