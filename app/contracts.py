"""Shared boundary records, CONTRACTS.md sections 1-9 (proposed v1; see docs/DECISIONS.md).

Owner: contract owner. Change only with their approval.
"""
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "1"
MAX_QUERY_CHARS = 2000
MAX_CONTEXT_CHARS = 8000
MAX_NEEDS = 10
MAX_RESULTS = 10

EntityType = Literal["person", "unit", "project", "infrastructure", "service"]


class Strict(BaseModel):
    """Unknown fields are rejected (section 1)."""
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1"]


# --- section 4: search request ------------------------------------------------
class Need(Strict):
    need_id: str
    text: str
    origin: Literal["user", "suggested"]
    kind: Literal["product", "problem", "competency", "entity_type", "constraint"]


class SearchRequest(Strict):
    # Length limits are enforced by the route (HTTP 413), not here (422): see DECISIONS.md.
    query: str
    revision: int = Field(ge=1)
    entity_type: Optional[EntityType] = None
    company_context: Optional[str] = None
    needs: list[Need] = []
    enrichment_requested: bool = False


# --- section 5: search response ----------------------------------------------
class EvidenceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version_id: str
    sentence_id: str
    text: str  # resolved by code from storage, never model-authored
    url: str
    page_number: Optional[int] = None
    content_date: Optional[str] = None
    last_modified: Optional[str] = None
    fetched_at: Optional[str] = None


class FieldValue(BaseModel):
    """Proposed additive change (docs/DECISIONS.md, deviation D1): a card field carries the
    supported claim id AND its display value so the UI need not resolve claims itself."""
    model_config = ConfigDict(extra="forbid")
    claim_id: str
    value: str


class Result(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entity_id: str
    entity_type: EntityType
    rank: int = Field(ge=1)
    display_name: str
    fields: dict[str, list[FieldValue]] = {}  # supported claims only
    reason: str
    evidence: list[EvidenceRef]
    freshness: Literal["fresh", "stale", "unknown"]
    retrieval: dict = {}

    @model_validator(mode="after")
    def _needs_evidence(self):
        if not self.evidence:
            raise ValueError("a result must carry at least one evidence sentence")
        return self


class SearchResponse(Strict):
    request_id: str
    revision: int = Field(ge=1)
    results: list[Result] = Field(max_length=MAX_RESULTS)
    limitations: list[str]
    enrichment_state: Literal["not_requested", "pending", "unavailable"]
    timing_ms: Optional[dict] = None  # actual measured values only


# --- section 6: SSE envelope --------------------------------------------------
class SseEvent(Strict):
    request_id: str
    revision: int = Field(ge=1)
    event_sequence: int = Field(ge=0)
    event_type: Literal["progress", "interpretation", "assessment", "complete", "error"]
    payload: dict


class NeedCoverage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    need_id: str
    support: Literal["supported", "partial", "none"]
    evidence: list[dict] = []


class AssessmentPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entity_id: str
    category: Literal["direct_match", "related_capability", "insufficient_evidence"]
    need_coverage: list[NeedCoverage]
    explanation: str
    evidence: list[dict]
    unresolved_questions: list[str]


# --- section 7: feedback ------------------------------------------------------
class Feedback(Strict):
    request_id: str
    revision: int = Field(ge=1)
    entity_id: str
    action: Literal["relevant", "not_relevant", "wrong_fact", "select", "exclude", "edit_needs"]
    idempotency_key: str = Field(min_length=1)
    claim_id: Optional[str] = None
    needs: Optional[list[Need]] = None
    comment: Optional[str] = None  # durable free text disabled until retention approved


# --- section 9: errors, jobs --------------------------------------------------
class ErrorBody(BaseModel):
    code: str
    message: str
    retryable: bool


class ErrorEnvelope(Strict):
    error: ErrorBody


class Job(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: str
    source_id: str
    kind: Literal["ingest", "refresh", "extract", "index", "enrich"]
    state: Literal["queued", "running", "succeeded", "partial", "failed"]
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    counts: dict[str, int] = {}
    retry_count: int = 0
    error_codes: list[str] = []


# --- section 2: source configuration -----------------------------------------
class SourceConfig(Strict):
    source_id: str
    label: str
    start_urls: list[str] = Field(min_length=1)
    allowed_domains: list[str] = Field(min_length=1)
    allowed_paths: list[str] = Field(min_length=1)
    languages: list[str]
    max_pages: int = Field(ge=1)
    max_depth: int = Field(ge=0)
    requests_per_second: float = Field(gt=0)
    focus_areas: list[str]
    refresh_default_hours: Optional[int] = None
    refresh_hours: Optional[int] = None
    adapter: Optional[str] = None


def error(code: str, message: str, retryable: bool = False) -> dict:
    """Error envelope. Messages are fixed text: never echo input, keys or prompts."""
    return {"schema_version": SCHEMA_VERSION, "error": {"code": code, "message": message, "retryable": retryable}}
