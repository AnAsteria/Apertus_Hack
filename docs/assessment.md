# Batched candidate assessment (T19)

Refs #19. Owner: workstream B (Ruihan). Status: **implemented, unit-tested and live-checked on 8 real candidates built from the T08 output.** Streams through the T18 SSE endpoint, which still needs the `main.py`/UI wiring described in `docs/interpretation.md` and PR #57.

## What it does

After interpretation, the enrichment stream takes the current search's cards (re-run server-side, so evidence text is code-resolved and never client-sent), and assesses up to **8 candidates in batches of 4**, one model call per batch, never per result. For each candidate:

- `category`: `direct_match` / `related_capability` / `insufficient_evidence`
- `need_coverage`: per need `supported` / `partial` / `none`, with `{version_id, sentence_id}` evidence
- `explanation`: 1–2 business-language sentences, marked as generated text in the UI
- `unresolved_questions`: up to 3 questions for the analyst to ask the candidate

Each validated `AssessmentPayload` is streamed as an `assessment` SSE event as soon as its batch returns.

Model: `BERNMATCH_ASSESS_MODEL`, default `APERTUS_MODEL` (**8B**, per architecture step 10). Timeout: `BERNMATCH_ASSESS_TIMEOUT_S` (default 45 s). With no needs, the query itself is assessed as one need (`need_query`).

## Validation before publication (`app/ai/assess.py`)

| Check | Correction recorded |
| --- | --- |
| Candidate numbers must be valid and unique (a batch numbered 0..n-1 is shifted once) | `unknown_or_duplicate_candidate`, `zero_indexed_candidates`, `candidate_not_assessed` |
| Coverage lines must parse and name a known need; missing needs are filled with `none` | `unparseable_coverage`, `unknown_or_duplicate_need` |
| Evidence labels must belong to that candidate's own sentences | `foreign_evidence_number` |
| `supported`/`partial` without valid evidence becomes `none` | `support_without_evidence` |
| Category must agree with coverage: direct needs a supported need, related needs at least partial | `category_downgraded` |
| An explanation containing an email/URL/phone or a number not in the evidence is replaced with neutral code-written text | `explanation_replaced` |

Corrections are counted in `complete.corrections` for review.

## Schema lessons from the live runs

The Keera gateway's constrained decoding produced endless whitespace until `max_tokens` in three situations (both models, real cards, 3/3 retries each):

1. **Integer lists** (`"evidence": [1, 2]`).
2. **A list key sorted alphabetically before other required keys.** Keys are emitted in alphabetical order, so the model wanted to close the object while required keys were still missing.
3. **Objects nested in lists inside lists.** The model merged every candidate's coverage into candidate 1's list and hit `maxItems`.

The fix was a flat schema with coverage as one short string per need, `"need_n1: supported: E1 E3"`, parsed in code. With uncapped evidence strings, both models also copied whole sentences; labels now go inside the coverage line. **These patterns matter for any future schema on this gateway.**

## Live check (2026-10-18; 8 candidates from the T08 real-crawl output; needs: "clinical validation of a wearable glucose sensor", "non-invasive glucose monitoring technology")

| Model | Runs | Total for 8 candidates | Per batch of 4 | Tokens in/out | Corrections |
| --- | --- | --- | --- | --- | --- |
| **8B** | 3 | 5.7 s, 6.3 s, 6.1 s | 2.5–3.6 s | ~1.3k / 0.95–1.04k | 1–5 per run (foreign evidence, unknown need IDs, one downgrade) |
| 70B | 1 valid (3 earlier attempts ran out of tokens before the budget was raised) | 18.1 s | 7.9 s, 10.3 s | 1.35k / 1.1k | 3 explanations replaced, 1 downgrade |

**Categories (hand-checked by Ruihan, single rater):**
- **Both models:** SPN-005 (non-invasive glucose pilot) and Liom Health → direct_match. Benedetta Coppe (cardiac), the menstrual-study contact card and a publication prize → insufficient_evidence. All defensible.
- **8B is more generous:** DCB and DBMR → related_capability, and Liom "supported" for clinical validation.
- **70B is stricter:** Liom clinical validation `none`, AIHN and DCB insufficient. It's arguably more accurate, but it was over the 15 s target.

**Decision:** keep **8B** as the default. It is inside the 15 s target with 2 batches and the spec names it; 70B would need a measured quality gain worth roughly 3× the latency. The median/p95 under load belong in T16/T20; these are small samples.

## SSE events (extends T18)

`progress(interpretation)` → `interpretation` → `progress(assessment, started, candidates)` → `assessment`* → `complete`.

- `complete` carries `elapsed_ms`, `interpretation_ms`, `assessment_ms`, `assessed`, `batches`, tokens, `decoding_modes` and `corrections`.
- A failed stage emits `error` with `stage` and `code` (`ASSESSMENT_UNAVAILABLE`, `ASSESSMENT_TIMEOUT`, `ASSESSMENT_FAILED`), and the stream still completes.
- If interpretation fails, assessment still runs with the request's own needs.
- No candidates → `progress(assessment, skipped)`.
- A newer revision ends the stream with `STALE_REVISION`, and late assessments are discarded.

## Checks

`python -m pytest -q`: 174 passed, 1 skipped. `tests/ai/assessment/` has 13 tests:
- evidence mapping
- foreign evidence, unsupported claims and category downgrades
- explanation replacement
- batch bounds and streaming callbacks
- query-as-need, duplicates and zero-indexing, coverage parsing
- SSE streaming, stale revision during assessment, failure/timeout completion, and assessment after an interpretation failure

## Limitations

- Candidates come from the search backend; until T09/T11 plug in real retrieval, the stream only has fixture cards or none.
- The explanation check catches foreign numbers, emails and URLs, not every unsupported paraphrase. The UI must label explanations as generated text.
- Small samples; latency varies a lot on the shared gateway.
