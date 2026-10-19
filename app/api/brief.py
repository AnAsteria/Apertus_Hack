"""T23/T24/T28 endpoints (Stretch). Cards are re-read from the served index by entity id; client-sent
card text is never trusted. Inference errors return a plain error; nothing is sent anywhere."""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from ..ai.brief import MAX_CARDS, make_brief, make_email, translate
from ..ai.client import InferenceError
from ..ai.config import InferenceConfig
from ..contracts import MAX_QUERY_CHARS, error

router = APIRouter()
Lang = Literal["en", "de", "fr", "it"]


class BriefRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1"]
    query: str = Field(max_length=MAX_QUERY_CHARS)
    entity_ids: list[str] = Field(min_length=1, max_length=MAX_CARDS)
    language: Lang = "en"
    analyst_note: Optional[str] = Field(default=None, max_length=2000)


class EmailRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1"]
    brief: dict
    language: Lang = "en"


class TranslateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1"]
    version_id: str
    sentence_ids: list[str] = Field(min_length=1, max_length=10)
    language: Lang


def _cards(ids):
    from .search import get_backend, FixtureBackend
    backend = get_backend()
    if backend is None:
        return None
    if isinstance(backend, FixtureBackend):
        import json
        from .search import FIXTURE
        from ..contracts import Result
        data = json.load(open(FIXTURE, encoding="utf-8"))
        by = {r["entity_id"]: r for r in data["results"]}
        return [Result(**by[i]) for i in ids if i in by]
    return [c for c in (backend.card(i) for i in ids) if c is not None]


def _ai_ready():
    return InferenceConfig.from_env().enabled


@router.post("/api/v1/brief")
def post_brief(req: BriefRequest):
    cards = _cards(req.entity_ids)
    if cards is None:
        return JSONResponse(error("INDEX_NOT_READY", "Search indexes are not ready.", True), status_code=503)
    if not cards:
        return JSONResponse(error("BAD_REQUEST", "None of the selected entities is available."), status_code=400)
    if not _ai_ready():
        return JSONResponse(error("ENRICHMENT_UNAVAILABLE", "Apertus is not configured; the PDF export still works.", True), status_code=503)
    try:
        return make_brief(req.query, cards, req.language, req.analyst_note)
    except InferenceError as e:
        return JSONResponse(error("ENRICHMENT_UNAVAILABLE", "Apertus could not write the brief this time.", e.retryable), status_code=503)


@router.post("/api/v1/brief/email")
def post_email(req: EmailRequest):
    if not _ai_ready():
        return JSONResponse(error("ENRICHMENT_UNAVAILABLE", "Apertus is not configured.", True), status_code=503)
    try:
        return make_email(req.brief, req.language)
    except InferenceError as e:
        return JSONResponse(error("ENRICHMENT_UNAVAILABLE", "Apertus could not draft the e-mail this time.", e.retryable), status_code=503)


@router.post("/api/v1/translate")
def post_translate(req: TranslateRequest):
    from .search import get_backend
    backend = get_backend()
    store = getattr(backend, "store", None)
    if store is None:
        return JSONResponse(error("INDEX_NOT_READY", "Search indexes are not ready.", True), status_code=503)
    try:
        ev = store.evidence([s for s in req.sentence_ids if s.startswith(req.version_id + ":")])
    except (KeyError, ValueError):
        return JSONResponse(error("EVIDENCE_REMOVED", "Evidence is not available.", False), status_code=410)
    if not ev:
        return JSONResponse(error("BAD_REQUEST", "No sentence of that version was requested."), status_code=400)
    if not _ai_ready():
        return JSONResponse(error("ENRICHMENT_UNAVAILABLE", "Apertus is not configured.", True), status_code=503)
    try:
        out = translate([e["text"] for e in ev], req.language)
    except InferenceError as e:
        return JSONResponse(error("ENRICHMENT_UNAVAILABLE", "Translation is unavailable.", e.retryable), status_code=503)
    return {"schema_version": "1", "language": req.language,
            "label": "Machine translation by Apertus. The original sentence is the source; cite the original.",
            "items": [{"sentence_id": e["sentence_id"], "original": e["text"], "translation": tr}
                      for e, tr in zip(ev, out)]}
