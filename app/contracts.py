"""Shared boundary records, CONTRACTS.md sections 1-9 (proposed v1; see docs/DECISIONS.md).

Owner: contract owner. Change only with their approval.
"""
import hashlib
import re
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


class Suggestion(BaseModel):
    """A way to narrow or rephrase the request (T31). `value` is what a client may apply
    (entity type, source host or query text); labels are fixed text or stored names."""
    model_config = ConfigDict(extra="forbid")
    kind: Literal["entity_type", "institution", "rephrase", "coverage"]
    label: str
    value: Optional[str] = None


class SearchResponse(Strict):
    request_id: str
    revision: int = Field(ge=1)
    results: list[Result] = Field(max_length=MAX_RESULTS)
    limitations: list[str]
    enrichment_state: Literal["not_requested", "pending", "unavailable"]
    timing_ms: Optional[dict] = None  # actual measured values only
    # T31 (proposed D11, additive): deterministic answer policy. Optional with defaults, so
    # existing producers and clients stay valid.
    outcome: Optional[Literal["confident", "low_confidence", "too_broad", "no_evidence"]] = None
    suggestions: list[Suggestion] = []


# --- section 6: SSE envelope --------------------------------------------------
class SseEvent(Strict):
    request_id: str
    revision: int = Field(ge=1)
    event_sequence: int = Field(ge=0)
    event_type: Literal["progress", "interpretation", "reranked", "assessment", "complete", "error"]  # reranked: T30 (D12)
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


# --- section 3: public corpus, entities and claims ---------------------------
# Identifier recipes: docs/DECISIONS.md "Identifier recipes". Use the helpers below;
# do not re-implement them. URL canonicalisation itself belongs to ingestion (T06).
_HEX32 = r"[0-9a-f]{32}"
DOCUMENT_ID_RE = rf"^doc_{_HEX32}$"
VERSION_ID_RE = rf"^ver_{_HEX32}$"
PASSAGE_ID_RE = rf"^ver_{_HEX32}:p[1-9][0-9]*$"
SENTENCE_ID_RE = rf"^ver_{_HEX32}:s[1-9][0-9]*$"
# Assigned IDs: prefix + lowercase alphanumerics (UUID hex in production; short demo ids in fixtures).
ENTITY_ID_RE = r"^ent_[a-z0-9]+$"
CLAIM_ID_RE = r"^clm_[a-z0-9]+$"

PageType = Literal["person", "unit", "project", "infrastructure", "service", "directory", "other"]
Predicate = Literal["name", "role", "affiliation", "expertise", "project", "infrastructure", "service",
                    "official_contact", "leader", "member_of", "part_of", "related_to"]
# Predicates whose object is another entity rather than a literal value.
RELATION_PREDICATES = frozenset({"affiliation", "leader", "member_of", "part_of", "related_to"})


def _sha256_32(*parts: str) -> str:
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:32]


def content_hash(cleaned_text: str) -> str:
    """D3: full SHA-256 hex of the cleaned main text (not raw response bytes)."""
    return hashlib.sha256(cleaned_text.encode("utf-8")).hexdigest()


def make_document_id(source_id: str, canonical_url: str) -> str:
    return "doc_" + _sha256_32(source_id, canonical_url)


def make_version_id(document_id: str, content_hash_hex: str, parser_version: str) -> str:
    return "ver_" + _sha256_32(document_id, content_hash_hex, parser_version)


def make_passage_id(version_id: str, n: int) -> str:
    if n < 1:
        raise ValueError("passage numbers start at 1")
    return f"{version_id}:p{n}"


def make_sentence_id(version_id: str, n: int) -> str:
    """N is global within the version, starting at 1."""
    if n < 1:
        raise ValueError("sentence numbers start at 1")
    return f"{version_id}:s{n}"


def version_of(passage_or_sentence_id: str) -> str:
    return passage_or_sentence_id.split(":", 1)[0]


class EvidencePair(BaseModel):
    """A claim's pointer to one stored sentence. Text is resolved by code, never by the model."""
    model_config = ConfigDict(extra="forbid")
    version_id: str = Field(pattern=VERSION_ID_RE)
    sentence_id: str = Field(pattern=SENTENCE_ID_RE)

    @model_validator(mode="after")
    def _same_version(self):
        if version_of(self.sentence_id) != self.version_id:
            raise ValueError("sentence_id belongs to a different version")
        return self


class Document(Strict):
    document_id: str = Field(pattern=DOCUMENT_ID_RE)
    source_id: str = Field(min_length=1)
    canonical_url: str = Field(min_length=1)
    language_variant_document_ids: list[str] = []  # links only; never replaces evidence text

    @model_validator(mode="after")
    def _no_self_variant(self):
        if self.document_id in self.language_variant_document_ids:
            raise ValueError("a document cannot be its own language variant")
        return self


class Sentence(Strict):
    sentence_id: str = Field(pattern=SENTENCE_ID_RE)
    version_id: str = Field(pattern=VERSION_ID_RE)
    passage_id: str = Field(pattern=PASSAGE_ID_RE)
    text: str = Field(min_length=1)  # exact cleaned text; evidence quotes come from here
    page_number: Optional[int] = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _same_version(self):
        if version_of(self.sentence_id) != self.version_id or version_of(self.passage_id) != self.version_id:
            raise ValueError("sentence and passage ids must belong to version_id")
        return self


class Passage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    passage_id: str = Field(pattern=PASSAGE_ID_RE)
    sentence_ids: list[str] = Field(min_length=1)  # ordered
    page_number: Optional[int] = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _sentences_in_version(self):
        v = version_of(self.passage_id)
        for sid in self.sentence_ids:
            if not re.match(SENTENCE_ID_RE, sid) or version_of(sid) != v:
                raise ValueError("passage sentence ids must be valid and belong to the same version")
        if len(set(self.sentence_ids)) != len(self.sentence_ids):
            raise ValueError("duplicate sentence id in passage")
        return self


class Version(Strict):
    version_id: str = Field(pattern=VERSION_ID_RE)
    document_id: str = Field(pattern=DOCUMENT_ID_RE)
    url: str = Field(min_length=1)
    redirects: list[str] = []
    fetched_at: str
    content_date: Optional[str] = None
    last_modified: Optional[str] = None
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    parser_version: str = Field(min_length=1)
    language: Optional[str] = None
    media_type: str = Field(min_length=1)
    page_type: PageType
    state: Literal["active", "retired", "suppressed"]
    passages: list[Passage] = []

    @model_validator(mode="after")
    def _ids_and_passages(self):
        if make_version_id(self.document_id, self.content_hash, self.parser_version) != self.version_id:
            raise ValueError("version_id does not match the identifier recipe")
        seen: set[str] = set()
        for p in self.passages:
            if version_of(p.passage_id) != self.version_id:
                raise ValueError("passage belongs to a different version")
            if seen.intersection(p.sentence_ids):
                raise ValueError("a sentence appears in more than one passage")
            seen.update(p.sentence_ids)
        return self


class Identifier(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scheme: Literal["profile_url", "orcid", "email", "other"]
    value: str = Field(min_length=1)


class Entity(Strict):
    entity_id: str = Field(pattern=ENTITY_ID_RE)
    entity_type: EntityType
    name: str = Field(min_length=1)
    canonical_profiles: list[str] = []
    identifiers: list[Identifier] = []
    affiliation_entity_ids: list[str] = []
    status: Literal["current", "former", "unknown", "retired"]
    claim_ids: list[str] = []
    contact_claim_ids: list[str] = []
    resolution_state: Literal["confirmed", "uncertain", "conflicting"]
    alias_entity_ids: list[str] = []  # merged-away ids; references to them stay resolvable

    @model_validator(mode="after")
    def _references(self):
        ids = self.affiliation_entity_ids + self.alias_entity_ids
        if self.entity_id in ids:
            raise ValueError("an entity cannot reference itself as affiliation or alias")
        if not set(self.contact_claim_ids) <= set(self.claim_ids):
            raise ValueError("contact_claim_ids must be a subset of claim_ids")
        return self


class Claim(Strict):
    claim_id: str = Field(pattern=CLAIM_ID_RE)
    subject_entity_id: str = Field(pattern=ENTITY_ID_RE)
    predicate: Predicate
    value: Optional[str] = None
    object_entity_id: Optional[str] = Field(default=None, pattern=ENTITY_ID_RE)
    evidence: list[EvidencePair] = Field(min_length=1)
    support: Literal["supported", "qualified", "unsupported", "pending"]
    qualification: Optional[str] = None

    @model_validator(mode="after")
    def _shape(self):
        if (self.value is None) == (self.object_entity_id is None):
            raise ValueError("exactly one of value or object_entity_id is required")
        if self.value is not None and not self.value.strip():
            raise ValueError("value must not be blank")
        if self.object_entity_id is not None and self.predicate not in RELATION_PREDICATES:
            raise ValueError(f"predicate {self.predicate!r} takes a value, not an entity")
        if self.object_entity_id == self.subject_entity_id:
            raise ValueError("a claim cannot relate an entity to itself")
        if self.support == "qualified" and not self.qualification:
            raise ValueError("qualified claims need a qualification")
        if len({(e.version_id, e.sentence_id) for e in self.evidence}) != len(self.evidence):
            raise ValueError("duplicate evidence pair")
        return self

    @property
    def surfaceable(self) -> bool:
        """Only supported or qualified claims may appear on cards as facts."""
        return self.support in ("supported", "qualified")


def error(code: str, message: str, retryable: bool = False) -> dict:
    """Error envelope. Messages are fixed text: never echo input, keys or prompts."""
    return {"schema_version": SCHEMA_VERSION, "error": {"code": code, "message": message, "retryable": retryable}}
