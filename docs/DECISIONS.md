# Decisions log (T01)

**Status (2026-10-18, T01 close-out): ACCEPTED IN PRACTICE, with one stated gap.** Roles and decisions below are in force because the team has been working under them: grants were recorded on the issues and acknowledged by the workers, and shared files, contracts and merge policy were used as written. Ruihan (contract owner) explicitly approved D1 and D3-D7 and acknowledged D9; Dimitry acknowledged D8. **Maxim never posted an explicit approval of this file**; his accepted work follows it (D3 cleaned-text hashes, D8 identifier helpers, the 365-day freshness rule, the pull-request merge policy). The removal route, operator contact and retention periods are NOT settled: they stay open under T12 (#12) and `docs/data-policy.md`.

## Roles

| Role | Proposed holder | Approval |
| --- | --- | --- |
| Dispatcher / integration owner | Dimitry | accepted: acting since 2026-10-18; every grant recorded on its issue |
| Contract owner (`docs/CONTRACTS.md`, shared schemas) | Ruihan | accepted: acting; approved D1, D3-D7, acknowledged D9 (PRs #47, #64) |
| Data/search lead | Maxim | accepted in practice: acknowledged grants on #6 and #9, followed D3/D8/365-day freshness; no explicit approval posted |

Deviation recorded: Dimitry instructed T01 drafting and T04 scaffolding to start on 2026-10-18 before Maxim and Ruihan approved this file. T04 work is therefore at risk of rework if a decision below changes. The T04 PR must not merge until the rows it depends on are approved.

## Stack (from CONTRACTS section 1)

Python 3.12, FastAPI, Pydantic v2, SQLite, one container with a persistent volume. Dense retrieval, embeddings revision and the Apertus runtime are **not** pinned here: the embedding model revision and the 8B quantisation need a verified license/memory check (T03/T05). Blocker, not decided.

## Identifier recipes (proposed)

- Canonical URL: lowercase scheme and host; drop fragment and default port; drop `utm_*`, `fbclid`, `gclid` query keys; keep other query keys sorted; keep path case and trailing slash as served after redirects.
- `document_id` = `doc_` + first 32 hex of SHA-256 of `source_id + "\n" + canonical_url`.
- `version_id` = `ver_` + first 32 hex of SHA-256 of `document_id + "\n" + content_hash + "\n" + parser_version`.
- Passage `<version_id>:pN`, sentence `<version_id>:sN`, N starting at 1. Separator is always `\n` before hashing.

## Limits and semantics (proposed)

| Item | Value |
| --- | --- |
| `query` max length | 2 000 characters |
| `company_context` max length | 8 000 characters |
| `needs` max items | 10 |
| Oversized input | HTTP 413, code `INPUT_TOO_LARGE`, checked before any inference |
| Result limit | 10 distinct entities |
| Stale evidence | `content_date` (else `last_modified`) older than 365 days = `stale`; both null = `unknown`; fetch date alone never makes evidence `fresh` |
| Company context lifetime | in memory only, expires 60 minutes after last use, never written to disk or logs |
| SSE replay | none; client reruns enrichment; job lifetime 10 minutes |
| Operational log retention | 30 days, no company input |
| Feedback storage | structured actions only; free-text comments and saved needs disabled until retention is approved |

## Error codes (proposed, extends CONTRACTS section 9)

`BAD_REQUEST` 400, `UNAUTHORIZED` 401, `FORBIDDEN` 403, `REVISION_CONFLICT` / `IDEMPOTENCY_CONFLICT` 409, `EVIDENCE_REMOVED` 410, `INPUT_TOO_LARGE` 413, `VALIDATION_ERROR` 422, `RATE_LIMITED` 429, `INDEX_NOT_READY` 503, `NOT_IMPLEMENTED` 501. All use the envelope in CONTRACTS section 9 and never echo input text.

## Metrics definitions

Deferred to T14, which freezes Recall@10, support-rate and latency formulas before T16/T20 run.

## Merge policy (proposed)

Branch `codex/issue-<n>-<slug>`, pull request referencing `Refs #n`, green CI, dispatcher squash merge. No direct pushes to `main`. Actual branch protection and repository access are **unverified**.

## Still open (blocks dependent work)

- Removal/suppression route, identity verification and backup retention period.
- Hosting selection (T03).
- Embedding model revision and Apertus quantisation.

## Deviations

- **D1 (T10, APPROVED by Ruihan as contract owner, 2026-10-18):** `Result.fields` values changed from bare claim-id strings to `{claim_id, value}` objects, so a card can show a supported claim's text without the UI resolving claims. Implemented in `app/contracts.py`; `docs/CONTRACTS.md` section 5 updated. Condition: `value` is copied by code from the stored claim (`Claim.value`, or the object entity's name for relation claims) and only for surfaceable (`supported`/`qualified`) claims. It is never model-authored text. Producers of `Result` (T09/T11) must use this shape.
- **D2 (T10):** the search route moved to `app/api/search.py` with a pluggable backend. Fixture mode (`BERNMATCH_FIXTURE_MODE=1`) serves synthetic cards for UI work only; it is off by default and labels its output synthetic.
- **D3 (R1, proposed by Maxim; APPROVED by Ruihan, 2026-10-18):** `content_hash` = SHA-256 of the cleaned main text, not raw response bytes.
- **D4 (R1, proposed by Maxim; APPROVED by Ruihan, 2026-10-18):** crawl budget profiles `dev` (small, development) and `final` (maximum feasible, for final runs/benchmarks/demo); limits live in configuration.
- **D5 (R1, proposed by Maxim; APPROVED by Ruihan, 2026-10-18):** T06 stub entities let T09 v1 ship before T07/T08; cards may be evidence-only. Stubs use the section 3 `Entity` model with `resolution_state: uncertain` and no claims until T07/T08.
- **D6 (R1, team decision; APPROVED by Ruihan, 2026-10-18):** hosting on a free Hugging Face Space (Docker) with the organiser Keera endpoint; no paid resources.
- **D7 (R1, proposed by Maxim; APPROVED by Ruihan, 2026-10-18):** multilingual scope extension — T27 Core query languages EN/DE/FR/IT/RU; T28 Stretch localized output.
- **D8 (contract owner Ruihan, 2026-10-18; acknowledged by Dimitry as integration owner, 2026-10-18; Maxim's confirmation pending):** CONTRACTS section 3 corpus models and identifier helpers added to `app/contracts.py`, with the enum, predicate and integrity choices listed under section 3 of `CONTRACTS.md`. Additive: no existing model changes. Needs Maxim's (T06) and Dimitry's (integration) acknowledgement.
- **D9 (T11, Dimitry, 2026-10-18; deviation from D6):** creating a Docker Space on free CPU Basic now requires a paid Hugging Face plan, so the Space runs on paid **CPU Upgrade** hardware (8 vCPU, 32 GB; $0.03/hour per Hugging Face's docs, about $0.70 until the deadline) billed to Dimitry's prepaid balance. Apertus still runs on the organiser Keera endpoint. Acknowledged by Ruihan (2026-10-18) and Maxim (2026-10-18).
- **D10 (T07, Ruihan, 2026-10-18, proposed; deviation from architecture step 4):** use `apertus-v1-5-70b` for offline T07 extraction instead of 8B, keeping 8B as fallback. Measured on 11 real T06 pages: 70B ~97% hand-checked claim precision and 24 persons found, vs 8B ~48% and 0 persons; 70B is ~7× slower (62 s vs 9 s), but extraction is offline and cached, so query latency is unaffected. Evidence: `docs/extraction.md`. Acknowledged by Dimitry (2026-10-18, condition: bounded, resumable, announced full run) and **APPROVED by Maxim (2026-10-18)**, including the go-ahead for the full-corpus 70B run under that condition. Architecture step 4 amended accordingly, with the metric and its limits.
- **D11 (T31, Maxim, 2026-10-18, proposed; additive contract change, contract owner Ruihan to confirm):** `SearchResponse` gains optional `outcome` and `suggestions` (CONTRACTS section 5). Deterministic classes: `no_evidence` (no card, or best dense similarity below `BERNMATCH_ABSTAIN_DENSE`), `too_broad` (at most `BERNMATCH_BROAD_MAX_TERMS` topic words, cards spread over at least `BERNMATCH_BROAD_MIN_HOSTS` sources, dense spread at most `BERNMATCH_BROAD_MAX_GAP`; five example cards plus narrowing suggestions), `low_confidence` (best dense below `BERNMATCH_CONFIDENT_DENSE`, or keyword-only mode), else `confident`. Thresholds are chosen on development queries and ad hoc probes only.
- **D12 (T30, Maxim, 2026-10-18, proposed; additive contract change, contract owner Ruihan to confirm):** SSE gains event type `reranked` (CONTRACTS section 6). After the interpretation event, the server searches the original query plus up to `BERNMATCH_MAX_EXPANSIONS` (4) validated T18 expansions with the same request constraints, fuses them by entity-level RRF (the T20 `rrf_fuse`, now shared from `app/search/expansion.py`) and streams the cards as `{results, expanded_queries, elapsed_ms}`. T19 assessment then uses these cards. Failure emits `RERANK_FAILED` and leaves the first cards untouched.
- **D12 amendment (T30 guard, Maxim, 2026-10-18):** the enriched pass never overrides the original query's outcome `no_evidence` or `too_broad`; the stream then emits `progress {stage: reranked, state: skipped, reason: original_outcome_kept}`. Reason: Ruihan's baseline cross-check (#16) found that expansion made both absent evaluation queries (I10, I19) stop abstaining. `evaluation/ablation.py` applies the same guard, so measured = served.
- **D13 (T15, Maxim, 2026-10-18, proposed; deviation from architecture section 5):** the demo runs on the cloud Space with Apertus through the Swiss CSCS/Keera gateway. Offline evidence is limited to a process-level no-network run of the search fast path on the real index bundle (0 outbound attempts, `docs/offline.md`). The air-gapped query with local Apertus 8B is **not demonstrated** and is reported as an open Core gap.
- **D14 (EXTRA B2 #127, Ruihan as contract owner, 2026-10-19, on `EXTRA-ruihan`; additive):** the SSE `interpretation` payload gains `model` (`primary` = 70B or `fallback` = fast 8B), and a `progress {stage: interpretation, state: fallback, reason}` event announces the switch. The primary model gets `BERNMATCH_INTERPRET_DEADLINE_S` (12 s) before the fast model takes over within the overall interpretation budget; fallback results are not cached. Assessment deadline `BERNMATCH_ASSESS_TIMEOUT_S` 45 → 30 s. Clients that ignore unknown fields are unaffected.
- **D15 (T39 #100, Ruihan as contract owner, 2026-10-19, on `EXTRA-ruihan`; additive):** the SSE `interpretation` payload gains `scope` (`in_scope|out_of_scope|unclear`), `scope_reason` and `outcome_update` (`null` or `out_of_scope`). `outcome_update` is set only when `BERNMATCH_SCOPE_REFUSAL=1`, the primary (70B) model says `out_of_scope` and the first response was `low_confidence` or `no_evidence`; then rerank and assessment are skipped. **Update 2026-10-19:** refusal is **on by default** since prompt `i3` (`BERNMATCH_SCOPE_REFUSAL=0` turns it off). Prompt i3 was tuned only on the stored development set `tools/scope_dev_set.json` (12 commercially worded research requests, 10 nonsense/consumer probes) plus the development split: 0/29 in-scope refused, 9/10 out-of-scope refused (two identical runs). One evaluation-split check afterwards, without tuning: 0/19 refused (I07-en now in scope). The earlier i2 prompt had refused I07-en.
- **D16 (EXTRA B3 #128, Ruihan as contract owner, 2026-10-19, on `EXTRA-ruihan`; additive):** the SSE `interpretation` payload gains `clarification_suggestion` (string or `null`). It is set only when T18 returned a validated clarification (broad request, no company text, at most one user need) **and** the fast path's outcome for the same request is `too_broad`. It is model-generated text and must be shown as a suggestion; it never blocks or changes the cards. Revision/stale handling is unchanged (late events of an older revision are discarded).
