# Decisions log (T01)

**Status: PROPOSED by Dimitry on 2026-10-18. Not yet approved by Maxim or Ruihan.** Nothing below is ratified until each row is marked APPROVED with a name and date. Where `CONTRACTS.md` says "fixed in T01", this file supplies the proposed value so that independent work does not invent incompatible recipes.

## Roles (to confirm)

| Role | Proposed holder | Approval |
| --- | --- | --- |
| Dispatcher / integration owner | Dimitry | pending |
| Contract owner (`docs/CONTRACTS.md`, shared schemas) | Ruihan | pending |
| Data/search lead | Maxim | pending |

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
