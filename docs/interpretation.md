# Request interpretation and enrichment (T18)

Refs #18. Owner: workstream B (Ruihan). Status: **interpreter and SSE endpoint implemented and unit-tested; live-checked on fictional EN/DE/broad requests. Not yet wired into `app/main.py` or the UI**, which are shared files owned by Dimitry (see Integration).

## What it does

After the first cards from `POST /api/v1/search` have rendered, Apertus turns the request (plus an optional company description and the analyst's own needs) into:

- **Editable needs:** the analyst's needs (`origin: user`) come back unchanged and first, followed by up to 6 model suggestions (`origin: suggested`). Kinds: product, problem, competency, entity_type, constraint.
- **Expanded queries:** single search terms in EN/DE (FR/IT if useful), each tied to the exact source term it expands. They are a separate list used for retrieval recall only; they are never needs or requirements.
- **Clarification:** one focusing question, only for broad requests with no company text and at most one need.

## Rules enforced in code (`app/ai/interpret.py`)

| Rule | Why |
| --- | --- |
| Only `origin: user` needs from the request are trusted and kept first; suggestions are deduplicated against them | Suggestions stay visibly separable and editable |
| A suggested `constraint` is dropped unless its words appear in the request, company text or a user need (`constraint_not_stated`) | Live: 8B invented "located in Bern" |
| Expansions whose source term isn't in the request, company text or a need are dropped | No new requirements via expansion |
| Comma/semicolon-packed expansions are split into single terms; a cut-off last fragment is dropped | Live: 70B packed lists and hit the length cap |
| Clarification kept only if the model marks the request broad, there is no company text, and ≤ 1 user need | "Broad-query clarification only" |
| Company text is never logged | Session-only context (DECISIONS) |

Model: `BERNMATCH_INTERPRET_MODEL`, default `APERTUS_QUALITY_MODEL` (70B). Decoding mode is reported in the payload (`backend_constrained`, or `validated_retry_fallback` labelled as weaker).

## SSE API (`app/api/enrichment.py`)

1. `POST /api/v1/search/{request_id}/enrichment`, body = the same `SearchRequest` (same `revision`) → `202 {request_id, revision, events_url}`. The context is held **in memory only** and expires 60 min after last use. 400 for a bad request ID, 413 for oversized input, 409 if a newer revision is already registered.
2. `GET /api/v1/search/{request_id}/events?revision=N` → `text/event-stream` of `SseEvent` records:
   - success: `progress` (seq 0) → `interpretation` (payload: `needs`, `expanded_queries`, `clarification`, `decoding_mode`) → `complete`
   - failure: `progress` → `error` with `code`:
     - `ENRICHMENT_TIMEOUT` (default 60 s, `BERNMATCH_INTERPRET_TIMEOUT_S`)
     - `ENRICHMENT_UNAVAILABLE` (endpoint down or no key)
     - `ENRICHMENT_FAILED` (unexpected, no details leaked)
     - `STALE_REVISION` (a newer revision was registered while running, so the late result is discarded)

   404 if nothing is registered; 409 on revision mismatch.

Initial cards never depend on this: every failure is an SSE error event only. T19 extends the same stream with batched `assessment` events after `interpretation`; see `docs/assessment.md` for the full event order.

## Integration (needs Dimitry)

- `app/main.py`: `from .api.enrichment import router as enrichment_router` and `app.include_router(enrichment_router)` before the static mount.
- UI (`app/static/app.js`), after rendering cards:
  1. If enrichment is wanted, `POST` the same body to `/api/v1/search/${request_id}/enrichment`, then read the stream from `events_url` (`EventSource` works, since it's a GET).
  2. On `interpretation`, show `needs` with user/suggested styling, editable.
  3. Optionally re-run search with `expanded_queries` (T09 decides how to use them).
  4. Ignore events whose `revision` is older than the current search.

## Live check (2026-10-18, fictional requests, one run each — not a benchmark)

| Request | Model | Latency | Result |
| --- | --- | --- | --- |
| "partners for our glucose sensor" + fictional startup text | 70B | 52.5 s (1st run), 6.0 s (after fixes) | 2 needs (clinical validation; EU partners); 6 single-term EN/DE expansions incl. "kontinuierliche Glukosemessung"; no invented constraints |
| same | 8B | 2.1 s, then 12.4 s | 3–4 needs; 1st run invented "located in Bern" (now dropped by code); 1–2 expansions |
| "Forschungspartner für Bildgebung bei Hirntumoren" | 70B | 46.8 s | 2 needs; 10 EN/DE expansions (brain tumor imaging, neuro-oncology imaging, MRT bei Hirntumoren, …) |
| same | 8B | 1.8 s, then 13.6 s | 2–3 needs; 1–4 expansions |
| "medtech partners" (broad) | 70B | 1.5 s | Clarification: which medtech area or clinical need |
| same | 8B | 1.4–10 s | No clarification (missed) |

**Takeaways:**
- 70B is clearly better (bilingual expansions, correct clarification) and stays the default.
- Gateway latency varied from 1.5 s to 52 s for the same model within an hour. That is why there is a 60 s timeout and why the first cards never wait. Measure in T16.

## Checks

`python -m pytest -q`: 154 passed, 1 skipped. T18 tests (`tests/ai/interpretation/`, 15 tests) cover:
- user-need preservation and deduplication
- expansion grounding and splitting
- unstated constraints
- clarification gating
- fallback labelling and no company text in logs
- the SSE happy path
- stale revisions, older-revision conflict, timeout, unavailable endpoint, no detail leakage, and request validation

## Limitations

- Not wired into `main.py` or the UI yet (shared files).
- Expanded queries are produced but not used by retrieval until T09/T11 consume them.
- Single-process in-memory registry: several workers or containers would each hold their own context.
- No replay after disconnect (DECISIONS): the client reruns enrichment.
