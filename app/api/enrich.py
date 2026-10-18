"""Optional asynchronous enrichment: Server-Sent Events (CONTRACTS section 6). T18 UI half.

The first search response never waits on this. A search that asks for enrichment gets
`enrichment_state: "pending"` and a request_id; the client then opens
`GET /api/v1/search/{request_id}/events`. Ruihan plugs the real Apertus interpretation in with
`set_enrichment_backend(...)`. Fixture mode (BERNMATCH_FIXTURE_MODE=1) emits SYNTHETIC events so the
panel can be built and tested; nothing here calls a model.

Request text is kept in memory only, for 60 minutes (DECISIONS.md), never written to disk or logs.
"""
import asyncio
import json
import os
import time
from collections import OrderedDict
from typing import AsyncIterator, Optional, Protocol

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict

from ..contracts import SCHEMA_VERSION, Need, SearchRequest, SseEvent

router = APIRouter()
TTL_SECONDS = 60 * 60
MAX_REGISTERED = 200


class ExpandedQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str
    language: str


class Clarification(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str
    options: list[str]


class InterpretationPayload(BaseModel):
    """CONTRACTS section 6. Defined here until the contract owner moves it into contracts.py."""
    model_config = ConfigDict(extra="forbid")
    needs: list[Need]
    expanded_queries: list[ExpandedQuery] = []
    clarification: Optional[Clarification] = None


class EnrichmentBackend(Protocol):
    def events(self, request_id: str, revision: int, query: str, needs: list[dict]) -> AsyncIterator[SseEvent]: ...


_backend: Optional[EnrichmentBackend] = None
_registry: "OrderedDict[str, dict]" = OrderedDict()


def set_enrichment_backend(backend: Optional[EnrichmentBackend]) -> None:
    global _backend
    _backend = backend


def fixture_mode() -> bool:
    return os.environ.get("BERNMATCH_FIXTURE_MODE") == "1"


def available() -> bool:
    return _backend is not None or fixture_mode()


def register(request_id: str, req: SearchRequest) -> None:
    now = time.time()
    for k in [k for k, v in _registry.items() if now - v["at"] > TTL_SECONDS]:
        del _registry[k]
    _registry[request_id] = {"at": now, "revision": req.revision, "query": req.query,
                             "needs": [n.model_dump() for n in req.needs]}
    while len(_registry) > MAX_REGISTERED:
        _registry.popitem(last=False)


def apply_state(response: dict, req: SearchRequest) -> dict:
    """Set enrichment_state honestly: pending only if something can actually produce events."""
    if not req.enrichment_requested:
        return response
    if available():
        register(response["request_id"], req)
        response["enrichment_state"] = "pending"
    else:
        response["enrichment_state"] = "unavailable"
    return response


async def fixture_events(request_id: str, revision: int, query: str, needs: list[dict]) -> AsyncIterator[SseEvent]:
    """SYNTHETIC interpretation. A re-run echoes the needs the analyst already edited and adds no
    new suggestions, so edits are never overwritten."""
    def ev(seq, etype, payload):
        return SseEvent(schema_version=SCHEMA_VERSION, request_id=request_id, revision=revision,
                        event_sequence=seq, event_type=etype, payload=payload)
    yield ev(0, "progress", {"stage": "interpreting", "synthetic": True})
    await asyncio.sleep(0.2)
    if needs:
        user_needs = [Need(**n) for n in needs]
        suggested = []
    else:
        user_needs = [Need(schema_version="1", need_id="n1", text=query, origin="user", kind="problem")]
        suggested = [Need(schema_version="1", need_id="n2", text="continuous monitoring technology (synthetic suggestion)",
                          origin="suggested", kind="competency")]
    payload = InterpretationPayload(needs=[*user_needs, *suggested],
                                    expanded_queries=[ExpandedQuery(text="Bildgebung (synthetic)", language="de")])
    yield ev(1, "interpretation", {**payload.model_dump(), "synthetic": True})
    yield ev(2, "complete", {})


def _sse(event: SseEvent) -> str:
    return f"event: {event.event_type}\ndata: {event.model_dump_json()}\n\n"


async def _stream(request_id: str):
    entry = _registry.get(request_id)
    if entry is None or not available():
        # EventSource cannot read HTTP error bodies, so failure is an in-stream error event.
        yield _sse(SseEvent(schema_version=SCHEMA_VERSION, request_id=request_id, revision=1, event_sequence=0,
                            event_type="error", payload={"code": "ENRICHMENT_UNAVAILABLE", "retryable": True}))
        return
    source = (_backend.events if _backend is not None else fixture_events)
    try:
        async for event in source(request_id, entry["revision"], entry["query"], entry["needs"]):
            yield _sse(event)
    except Exception:  # never leak internals or request text; initial cards are unaffected
        yield _sse(SseEvent(schema_version=SCHEMA_VERSION, request_id=request_id, revision=entry["revision"],
                            event_sequence=99, event_type="error",
                            payload={"code": "ENRICHMENT_FAILED", "retryable": True}))


@router.get("/api/v1/search/{request_id}/events")
async def events(request_id: str):
    return StreamingResponse(_stream(request_id), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
