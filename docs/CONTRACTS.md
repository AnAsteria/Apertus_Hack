# Proposed shared contracts v1

## 1. Status, stack and common rules

**Proposal requiring T01 ratification; no API or schema implementation exists.** This is the smallest shared interface for independent work. Architecture remains authoritative. Contract owner: one developer nominated in T01, not yet assigned. Proposed stack: Python/FastAPI with Pydantic validation, SQLite for metadata/feedback, local persisted NumPy vectors and BM25 index, sentence-transformers multilingual embeddings, HTML/text-PDF parsers, static HTML/CSS/JavaScript served by the same application, HTTP inference adapter and Server-Sent Events (SSE). Proposed embedding model: `intfloat/multilingual-e5-small`, pinned to a verified revision by T01. Proposed local Apertus runtime: llama.cpp server with a compatible authorised 8B quantisation. These are selections for approval, not claims of tested compatibility, memory fit, licenses or installed dependencies. One container plus a persistent data volume avoids extra services. No Redis, distributed queue or separate frontend service is proposed. Hardware/host access remains T03's gate.

All boundary records carry `schema_version: "1"`. UTF-8, UTC RFC3339 timestamps, ordered arrays and explicit enums; unknown scalar source fields are `null`, unknown/empty collections are `[]`. Required fields cannot be omitted; optional fields may be absent. Empty strings do not stand for known facts. Invalid required fields reject the record, not silently coerce it. API rejects unknown request fields; future incompatible changes require a new version and coordinated migration. These rules apply to examples and later schemas.

Proposed IDs: source is stable configured slug; document is `doc_` + SHA256(source ID + canonical URL); version is `ver_` + SHA256(document ID + content hash + parser version); passage is version + `:pN`; sentence is version + `:sN` numbered globally within the version. Entity uses assigned `ent_` UUID, with alias/merge map and conflict records. Claims/jobs/requests/feedback use prefixed UUIDs. Hash separators and URL canonicalisation must be fixed in T01; don't implement incompatible independent recipes. Sentences cannot be rebound after updates. Suppressed/expired text is unavailable without changing reference identity.

## 2. Source configuration and discovery

Required: `schema_version`, `source_id`, `label`, `start_urls`, `allowed_domains`, `allowed_paths`, `languages`, `max_pages`, `max_depth`, `requests_per_second`, `focus_areas`. URLs are public HTTP(S); disallowed redirects are rejected, robots respected and private/internal network targets excluded. Rate/concurrency caps apply per domain across jobs. Production settings `refresh_default_hours: 24` and source override `refresh_hours: 1` are configuration intent; MVP runs manual jobs, not a scheduler. Adapter name is optional and documented. Missing/blocked inventory is not an empty successful crawl.

**Synthetic example, not an approved real source:**
```json
{"schema_version":"1","source_id":"example","label":"Example institute","start_urls":["https://example.org/research/"],"allowed_domains":["example.org"],"allowed_paths":["/research/"],"languages":["de","en"],"max_pages":20,"max_depth":2,"requests_per_second":0.5,"focus_areas":["diabetes","oncology","neurology","medtech"],"refresh_default_hours":24}
```

## 3. Public corpus, entities and claims

Document fields: `document_id`, `source_id`, `canonical_url`, `language_variant_document_ids`. Version fields: `version_id`, `document_id`, `url`, `redirects`, `fetched_at`, `content_date`, `last_modified`, `content_hash`, `parser_version`, `language`, `media_type`, `page_type`, `state` (`active|retired|suppressed`), `passages`. Dates unknown are null. Passages contain `passage_id`, ordered sentence references and nullable PDF `page_number`; sentence contains `sentence_id`, `version_id`, exact cleaned `text`, `passage_id`, nullable PDF page. Language variants link records; they do not replace evidence text. Persist raw public snapshots under the approved retention policy, outside Git.

Entity fields: `entity_id`, `entity_type` (`person|unit|project|infrastructure|service`), `name`, `canonical_profiles`, `identifiers`, `affiliation_entity_ids`, `status` (`current|former|unknown|retired`), `claim_ids`, `contact_claim_ids`, `resolution_state` (`confirmed|uncertain|conflicting`). A named unit leader is a relation; it does not confer expertise. Merges retain alias IDs and supporting evidence; ambiguous names are not auto-merged.

Claim fields: `claim_id`, `subject_entity_id`, `predicate`, exactly one of `value` or `object_entity_id`, `evidence` (one or more version/sentence pairs), `support` (`supported|qualified|unsupported|pending`), nullable `qualification`. Predicates cover name/role/affiliation/expertise/project/infrastructure/service/official contact/leader and explicit source relationships. Supported claims require existing evidence plus semantic checking. Pending/unsupported claims are not surfaced as facts. Contradictory supported claims remain marked conflicts. Current contacts require documented role/status support; unknown does not mean current.

**Synthetic fragment; abbreviated IDs stand for format examples only:**
```json
{"schema_version":"1","entity_id":"ent_demo","entity_type":"unit","name":"Example Imaging Group","canonical_profiles":["https://example.org/research/imaging"],"identifiers":[],"affiliation_entity_ids":[],"status":"unknown","claim_ids":["clm_demo"],"contact_claim_ids":[],"resolution_state":"confirmed"}
```
```json
{"schema_version":"1","claim_id":"clm_demo","subject_entity_id":"ent_demo","predicate":"expertise","value":"medical imaging","evidence":[{"version_id":"ver_demo","sentence_id":"ver_demo:s1"}],"support":"supported","qualification":null}
```

The example evidence sentence would be stored as “The group researches medical imaging.” Code returns that stored text; model quotation text is never trusted. IDs and quote validity do not prove support for a different claim such as a named person's current clinical service.

**Implemented in `app/contracts.py` (contract owner, 2026-10-18; see DECISIONS D8):** `Document`, `Version`, `Passage`, `Sentence`, `Entity`, `Claim`, `EvidencePair`, `Identifier`, and the ID helpers `content_hash`, `make_document_id`, `make_version_id`, `make_passage_id`, `make_sentence_id`. Producers must use these helpers rather than re-implementing the recipes. Concrete choices beyond the text above:
- `page_type`: `person|unit|project|infrastructure|service|directory|other`.
- `predicate`: `name|role|affiliation|expertise|project|infrastructure|service|official_contact|leader|member_of|part_of|related_to`. Only `affiliation|leader|member_of|part_of|related_to` may take `object_entity_id`; the rest take `value`.
- `content_hash`: 64 lowercase hex characters (SHA-256 of the cleaned main text, D3). `Version` rejects a `version_id` that does not match the recipe.
- Sentences and passages must belong to their version; a sentence appears in at most one passage; `EvidencePair.sentence_id` must belong to `EvidencePair.version_id`.
- `Entity.identifiers` items are `{scheme: profile_url|orcid|email|other, value}`; `alias_entity_ids` keeps merged-away IDs resolvable; `contact_claim_ids` must be a subset of `claim_ids`.
- `qualified` claims require `qualification`. Only `supported` and `qualified` claims are surfaceable (`Claim.surfaceable`).
- Entity/claim IDs: `ent_`/`clm_` + lowercase alphanumerics (UUID hex in production, short demo IDs in fixtures). Document/version/passage/sentence IDs are strictly the computed formats.
- Cross-record integrity (claim subject exists, evidence sentence exists in storage) is checked by producers and the grounding step (T08), not by single-record validation.

## 4. Search request and fast path

Proposed routes: `POST /api/v1/search`, `GET /api/v1/search/{request_id}/events`, `POST /api/v1/feedback`, protected `GET /api/v1/admin/coverage`, protected `POST /api/v1/admin/refresh`; `/healthz` is liveness and `/readyz` requires corpus/index readiness. No crawl on search. No LLM call awaited by initial response. The local embedding runtime must be loaded for dense retrieval without network fetches at query time.

Required search fields: `schema_version`, `query`, `revision` (positive integer). Optional `entity_type` (enum or null), `company_context` (text or null), `needs` (array), `enrichment_requested` (default false). Response limit is capped at 10. Needs contain `need_id`, `text`, `origin` (`user|suggested`), `kind` (`product|problem|competency|entity_type|constraint`); suggestions are not silently promoted to constraints. Request text length/token/batch limits are configuration ratified in T01, validated before inference; oversized input returns 413. Text/paste only, no upload route.

**Synthetic request:**
```json
{"schema_version":"1","query":"imaging partners","revision":1,"entity_type":"unit","company_context":null,"needs":[],"enrichment_requested":false}
```

Requests/company context are session-only by proposed default, excluded from public corpus/vector/keyword indexes and operational logs. Client carries needed context on edits; server request context expires with the session policy agreed in T01. Explicit-save behavior is not implemented or implicitly enabled. No confidential smoke-test data.

## 5. Initial search response and evidence

Required response: `schema_version`, `request_id`, `revision`, `results`, `limitations`, `enrichment_state` (`not_requested|pending|unavailable`), `timing_ms` (actual values only). Each result: `entity_id`, `entity_type`, `rank`, `display_name`, `fields`, `reason`, `evidence`, `freshness`, `retrieval`. Fields reference supported claims as `{claim_id, value}` objects (DECISIONS D1): `value` is copied by code from the stored claim, never model-authored, and only supported/qualified claims appear. A displayed contact must distinguish contact role from expertise. Evidence includes `version_id`, `sentence_id`, `text` resolved by code, `url`, nullable PDF page, source/content/lastmod/fetch dates. Freshness is `fresh|stale|unknown`, according to an explicit threshold, never fetch date alone. Retrieval includes BM25/dense/fusion/aggregation diagnostics for evaluation, not fabricated probabilities.

**Synthetic empty response, with illustrative timing omitted as null:**
```json
{"schema_version":"1","request_id":"req_demo","revision":1,"results":[],"limitations":["Support was not found in the indexed corpus."],"enrichment_state":"not_requested","timing_ms":null}
```

**T31 answer policy (proposed D11, additive):** the response may carry `outcome` (`confident|low_confidence|too_broad|no_evidence`, or absent from older producers) and `suggestions`, a list of `{kind: entity_type|institution|rephrase|coverage, label, value}`. `value` is something a client can apply (an entity type, a source host or query text); labels are fixed text or stored names, never model output. `too_broad` returns at most five example cards. The policy is deterministic and works without an LLM.

A no-match query is a successful response, not 404; it does not claim global absence. Result entities are distinct; max aggregation proposed for v1, never unlimited score summation. Required type is respected. API serves source text only as escaped data; no HTML/model instruction execution.

## 6. Optional asynchronous enrichment and inference

SSE events contain `schema_version`, `request_id`, `revision`, monotonically increasing `event_sequence`, `event_type` (`progress|interpretation|assessment|complete|error`), `payload`. Discard stale revisions on client and server. Streaming transport never publishes raw unvalidated model JSON as facts. Disconnection/replay policy and job lifetime are fixed by T01; provisional choice: no replay requirement, client can rerun enrichment without duplicate feedback.

**T30 `reranked` event (proposed D12, additive):** payload `{results, expanded_queries, elapsed_ms}`. `results` are ordinary validated cards (same schema as the search response, evidence resolved by code) from the original query plus the validated expansions, fused at entity level. Each card's `retrieval.query_variants` names the variants that found it. The client replaces its cards only when the revision matches.

Interpretation payload contains editable `needs`, `expanded_queries` with language and `clarification` (nullable). Assessment contains `entity_id`, `category` (`direct_match|related_capability|insufficient_evidence`), `need_coverage` with need IDs/support/evidence, `explanation`, `evidence` ID pairs and `unresolved_questions`. Batch size/token budgets bounded and configured. Unknown entity/need/evidence IDs reject or quarantine the assessment; don't replace them with invented IDs. Code resolves quotes and checks semantic support before publication. A generic failure event leaves initial cards intact.

**Synthetic assessment envelope:**
```json
{"schema_version":"1","request_id":"req_demo","revision":1,"event_sequence":2,"event_type":"assessment","payload":{"entity_id":"ent_demo","category":"insufficient_evidence","need_coverage":[],"explanation":"Evidence for the requested capability was not found in the indexed corpus.","evidence":[],"unresolved_questions":["Can the unit confirm this capability?"]}}
```

Backend inference configuration: endpoint/base URL, server-only API key, model IDs, timeout, retry/backoff/concurrency caps and local replacement endpoint. Probe connectivity/models, backend constrained JSON and streaming separately. Schema validation/retry fallback has explicit decoding mode `validated_retry_fallback`; supported backend constraints use `backend_constrained`. Neither mode guarantees semantic support. Never put a real key in fixtures/issues/client bundles. Production defaults and actual endpoint schema remain probe-dependent.

## 7. Feedback and sensitive-data lifecycle

Required feedback: `schema_version`, `request_id`, `revision`, `entity_id`, `action` (`relevant|not_relevant|wrong_fact|select|exclude|edit_needs`), client-generated `idempotency_key`; optional `claim_id`, revised `needs`, and comment. Store `feedback_id` and timestamp server-side. Wrong-fact reports should link a claim where available. Repeated key/body returns same result; conflicting reuse returns 409. Persist reviewable feedback separately from public records, without retaining company context by default. Do not retrain automatically.

**Synthetic feedback:**
```json
{"schema_version":"1","request_id":"req_demo","revision":1,"entity_id":"ent_demo","action":"relevant","idempotency_key":"demo-feedback-1"}
```

Select/exclude states and edits are revision-aware. After session context expiration, feedback can reference retained non-sensitive result/entity IDs; retaining the original company description is not necessary. Saved needs/comments may be sensitive: retention/access/redaction must be decided in T01 before enabling durable free-text storage. Proposed safe MVP choice is structured feedback only and session-only needs edits unless explicitly approved.

Removal/suppression entries record identity/aliases/URLs, reason category, confirmation and action timestamps with restricted operator access. Suppress before ingestion; retire serving documents/entities/derived indexes and expire text/caches/backups according to ratified policy. Operational log default: 30 days with no company input; policy values are proposals until ratified. No legal compliance guarantee.

## 8. Evaluation records

Query record: `query_id`, `intent_group_id`, `split` (`development|evaluation`), `text`, `language`, source snapshot, expected entity IDs/types and explicitly allowed unit substitutions, source evidence/provenance, category tags and expected abstention. Group all intent variants together across split. Never automatically count units as people.

Run record: revision/corpus/model/prompt/schema/config IDs, timestamp, environment/concurrency/cache, component configuration, query IDs, retrieved entity IDs/ranks/evidence, measured durations/tokens, failures and adjudicated support/field judgments. Store fictional/public evaluation inputs only. No result exists until execution. T14 freezes formulas, sample/rubric and cross-encoder subset before T16/T20 runs.

## 9. Coverage, jobs and errors

Job record: `job_id`, `source_id`, `kind` (`ingest|refresh|extract|index|enrich`), `state` (`queued|running|succeeded|partial|failed`), start/end times, counts, retry count and redacted error codes. Coverage includes discovered/fetched/indexed/excluded/failed/unsupported counts with reasons, per-source/language/focus/outside-focus counts and dates. Zero counts do not imply successful coverage. Manual refresh returns 202 with job ID; public clients cannot trigger it. Production schedules are settings, not claimed MVP automation.

Errors: envelope `{"schema_version":"1","error":{"code":"INDEX_NOT_READY","message":"Search indexes are not ready.","retryable":true}}` (synthetic). 400 malformed request; 401/403 protected admin failures; 409 revision/idempotency conflict; 410 removed evidence; 413 oversized input; 422 schema validation; 429 rate/concurrency cap; 503 indexes unavailable. Enrichment endpoint failure is an SSE error/availability state, not failure of already completed search. Error responses/logs must not echo keys, company text or model prompts. Temporary fetch failure retries; retirement requires separate confirmation.

Fixtures: frontend owner can create synthetic records conforming to sections 4–7 in `tests/fixtures/` after T01, clearly labelled synthetic. Deterministic mocked transport enables independent UI work. Fixtures never establish real-source quality, endpoint support, deployment or offline proof. Shared schema/fixture edits require the contract owner's approval.
