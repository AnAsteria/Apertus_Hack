# T09 — Build persistent multilingual hybrid retrieval and fair ranking

## A. Identity and prerequisites

Iteration: V1 — Working vertical slice. Scope tier: **core**. Proposed workstream: **A**. Estimated active effort: **5 person-hours**, an unmeasured planning estimate excluding access waits/model download time. Dependencies: T06 (v1); T08 for entity-level v2 (see R1)

Objective/outcome: Persist multilingual embeddings/vector arrays and BM25 keyword index for profiles and original passages. Use reciprocal-rank fusion, max entity aggregation and relevance-aware MMR as proposed v1 choices; tune only on development queries. Deduplicate and respect requested type, at most ten entities. Return exact supporting evidence and deterministic relevance reasons without LLM calls. No per-query crawl.

Access/policy prerequisites and limitations: Local multilingual model weights must be available; selected model pinned by T01.

**Revision R1 (2026-10-18, proposed by Maxim; pending team confirmation — see [README §Revision R1](README.md#revision-r1-2026-10-18)):**
- **Dependency change:** v1 acceptance depends on T06 only and runs on passages + T06 stub entities. T08 integration (resolved entities/claims in cards and aggregation) is a v2 step inside this task, not a start blocker. Cards without supported claims show entity + exact evidence only (`fields` may be empty; evidence is mandatory).
- BM25 needs per-language analysis (German stemming/compound handling via stemmer or character n-grams; also fr/it); cross-lingual recall relies on dense retrieval, so BM25 alone is never expected to match across languages.
- Compare `multilingual-e5-small` (needs `query:`/`passage:` prefixes) with one stronger candidate (`multilingual-e5-base` or `bge-m3`) on development queries only, including EN/DE/FR/IT/RU query variants (see T27); pin the winner with licence/revision and CPU latency.
- Integrate through `SearchBackend` in `app/api/search.py`; the index build writes `$BERNMATCH_DATA_DIR/READY`. Index size must fit the free hosting target (T11).

## B. Context and contracts

Read [AGENTS.md](../../AGENTS.md), [README](../../README.md), [architecture](../ARCHITECTURE.md) sections 1–3 and pipeline step(s) **6, 7, 9, 11** (numbers 1/3/9 on T01 also include the corresponding numbered architecture sections). Review architecture sections 5–9 when relevant to verification/delivery. Required [contract sections](../CONTRACTS.md): **3–5**. The [workflow](../AGENT_WORKFLOW.md) governs claims and integration.

Inspect the current repository, integrated branch, dependency PRs and issue before editing. At backlog creation only README, AGENTS and architecture existed; no implementation, credentials, hosting, source inventory or benchmark results may be assumed. Paths below are proposed ownership boundaries, not existing code. T01 ratifies them.

## C. Scope and ownership

Owned files/modules: `app/search/; app/storage/indexes.py; tests/search/`. Shared files (`app/main.py`, `app/contracts.py`, dependency lockfile, CI, deployment configuration, shared UI shell, README and contracts) require the named owner/dispatcher's coordination before edits. Contract changes require contract-owner approval. Module owners implement partner fixes within their own granted branches.

In scope: only the objective, declared dependencies and acceptance checks below. Out of scope: unrelated features; document upload; automatic email sending/retraining; per-query crawling; full production scheduler in MVP; paid provisioning/billing acceptance; confidential company profiles. Second layer/Stretch tasks must not weaken Core or consume the submission buffer without recorded decision.

## D. Implementation and failure behavior

1. Obtain a dispatcher grant and inspect dependency evidence on the integrated branch; create the dedicated branch/worktree recorded in the grant.
2. Implement the objective above using ratified contracts and the proposed stack in the plan. Keep input/output shapes and reference integrity compatible with CONTRACTS sections listed above.
3. Validate external/model data before publishing it. Use deterministic fixtures for CI and opt-in live tests only. Log redacted metadata, not credentials/company descriptions. Apply configured timeout/retry/backoff and fail safely; unknown facts stay empty.
4. Preserve simple search when inference fails; ingestion never runs implicitly on a query. Unknown access/model/source capabilities are explicit blockers; do not substitute mocks for required live or offline evidence.
5. Coordinate shared-file changes before editing, record material deviations and rerun affected checks. Do not commit local model files, private inputs, logs or real .env files.

## E. Acceptance and verification

Restart reuses indexes; a prolific duplicate-page entity cannot win through score summation; type and ten-entity limits hold. Check DE→EN and EN→DE real evidence, absence/near-match behavior and retrieval under slow/unavailable Apertus. Instrument first-card path for later median/p95 measurement.

Use unit tests for meaningful deterministic risk, shared contract tests for interface changes and real-data integration checks where this objective requires them. Do not add tests that merely mirror implementation. Report exact commands, observed output/exit status, test environment, fixture-versus-real distinction and limitations. No fabricated metrics, source facts or capability claims. Targets and synthetic examples are never achieved measurements.

## F. Definition of done and handoff

Worker: run issue checks; update implemented/planned documentation; push only the task branch and open a PR if access permits; link the issue without an auto-close directive; report evidence and handoff; request REVIEW, do not close the issue.

Dispatcher/integration owner: review contracts/overlap, required CI and integrated real-data checks; integrate under the agreed PR policy; rerun acceptance on the integrated branch; close only when verified. Verify dependents before marking READY. GitHub issue state is authoritative; this document does not maintain execution status.

Completion report: **Changes; exact checks/commands; actual results; evidence URLs/paths and integrated revision; limitations; blockers; contract/deviation notes; dependent-task handoff.**

## G. Copy-paste worker prompt

> Work on T09 using `docs/tasks/T09-hybrid-search.md`, its linked GitHub issue and unique agent ID supplied by the dispatcher. Read AGENTS.md, README.md, docs/AGENT_WORKFLOW.md, the required architecture/contract sections and dependency evidence. Inspect existing work before editing. Request assignment and WAIT for an explicit dispatcher grant recording your issue, unique ID, branch, isolated worktree, claim time and files. After grant, implement ONLY this task and declared dependencies, preserve shared contracts and obtain owner approval before shared-file changes. Run appropriate deterministic and required real-data checks, update verified documentation, push your branch/open a linked PR if access permits, and report actual results using section F. Do not close the issue, merge, provision paid resources, send messages externally or submit artifacts without explicit authority. Never fabricate facts or results. Report blocked prerequisites without asking the user to repeat documented context.
