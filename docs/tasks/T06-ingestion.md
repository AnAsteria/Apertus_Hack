# T06 — Implement bounded initial crawl and immutable evidence storage

## A. Identity and prerequisites

Iteration: V1 — Working vertical slice. Scope tier: **core**. Proposed workstream: **A**. Estimated active effort: **5 person-hours**, an unmeasured planning estimate excluding access waits/model download time. Dependencies: T02, T04

Objective/outcome: Load YAML registry; discover via sitemaps/internal links within allowlists, robots and domain rate limits; fetch public HTML/text PDFs once. Store URL/redirect/hash/fetch/content dates, versioned passages and sentence IDs with PDF page numbers. Clean boilerplate, link language variants, classify cheaply and route eligible entity pages. Keep other usable passages searchable. Report focus/outside-focus counts and scanned/JS/failed exclusions.

Access/policy prerequisites and limitations: Confirmed inventory/allowed seeds from T02; network access for ingestion.

**Revision R1 (2026-10-18, proposed by Maxim; pending team confirmation — see [README §Revision R1](README.md#revision-r1-2026-10-18)):**
- **Crawl budget profiles (decision):** page limits are configuration, never hard-coded. `dev` profile = small, economical limit for development (proposed ~20 pages per focus domain, ~5 per outside-focus domain); `final` profile = raised to the maximum feasible for final test runs, benchmarks and the demo corpus. Record the profile, limits and measured crawl time with every snapshot. The crawl runs once into the local store; queries never fetch sources.
- Generate per-domain source YAML from T02's `config/sources/unibe_inventory.csv` and tiers.
- `content_hash` = SHA-256 of the cleaned main text (not raw bytes), so dynamic markup does not create a new version on every refresh. Raw snapshots live under `$BERNMATCH_DATA_DIR`, never in Git.
- Use a tested robots parser supporting `*`, `$` and group merging (e.g. `protego`); `urllib.robotparser` is insufficient. Language detection must cover de/en/fr/it.
- **Stub entities:** emit deterministic page/section-level entities (name = heading/title, type from the cheap classifier, `resolution_state: uncertain`) so T09 v1 does not wait for T07/T08. T08 later replaces/merges them through the alias map.
- Hand an early `dev` snapshot to T07/T08 as soon as one source works; do not wait for the full crawl.
- Dependency added: corpus boundary models (Document/Version/Passage/Sentence/Entity/Claim) in `app/contracts.py`, owned by the contract owner. Coordinate new libraries (HTML/PDF parsers, robots, language id) with the lockfile owner before adding them.

## B. Context and contracts

Read [AGENTS.md](../../AGENTS.md), [README](../../README.md), [architecture](../ARCHITECTURE.md) sections 1–3 and pipeline step(s) **1–3, 6** (numbers 1/3/9 on T01 also include the corresponding numbered architecture sections). Review architecture sections 5–9 when relevant to verification/delivery. Required [contract sections](../CONTRACTS.md): **2, 3, 9**. The [workflow](../AGENT_WORKFLOW.md) governs claims and integration.

Inspect the current repository, integrated branch, dependency PRs and issue before editing. At backlog creation only README, AGENTS and architecture existed; no implementation, credentials, hosting, source inventory or benchmark results may be assumed. Paths below are proposed ownership boundaries, not existing code. T01 ratifies them.

## C. Scope and ownership

Owned files/modules: `app/ingest/; app/storage/corpus.py; config/sources/; tests/ingest/`. Shared files (`app/main.py`, `app/contracts.py`, dependency lockfile, CI, deployment configuration, shared UI shell, README and contracts) require the named owner/dispatcher's coordination before edits. Contract changes require contract-owner approval. Module owners implement partner fixes within their own granted branches.

In scope: only the objective, declared dependencies and acceptance checks below. Out of scope: unrelated features; document upload; automatic email sending/retraining; per-query crawling; full production scheduler in MVP; paid provisioning/billing acceptance; confidential company profiles. Second layer/Stretch tasks must not weaken Core or consume the submission buffer without recorded decision.

## D. Implementation and failure behavior

1. Obtain a dispatcher grant and inspect dependency evidence on the integrated branch; create the dedicated branch/worktree recorded in the grant.
2. Implement the objective above using ratified contracts and the proposed stack in the plan. Keep input/output shapes and reference integrity compatible with CONTRACTS sections listed above.
3. Validate external/model data before publishing it. Use deterministic fixtures for CI and opt-in live tests only. Log redacted metadata, not credentials/company descriptions. Apply configured timeout/retry/backoff and fail safely; unknown facts stay empty.
4. Preserve simple search when inference fails; ingestion never runs implicitly on a query. Unknown access/model/source capabilities are explicit blockers; do not substitute mocks for required live or offline evidence.
5. Coordinate shared-file changes before editing, record material deviations and rerun affected checks. Do not commit local model files, private inputs, logs or real .env files.

## E. Acceptance and verification

Run bounded real-source ingestion with all three configured sources; verify stable same-version sentences and different changed-content versions, exact text/page provenance, scope/rate/robots behavior and unsupported reports. Restart reuses corpus without crawling. Contract tests plus a few meaningful parser/version fixtures; do not claim full coverage from a sample.

Use unit tests for meaningful deterministic risk, shared contract tests for interface changes and real-data integration checks where this objective requires them. Do not add tests that merely mirror implementation. Report exact commands, observed output/exit status, test environment, fixture-versus-real distinction and limitations. No fabricated metrics, source facts or capability claims. Targets and synthetic examples are never achieved measurements.

## F. Definition of done and handoff

Worker: run issue checks; update implemented/planned documentation; push only the task branch and open a PR if access permits; link the issue without an auto-close directive; report evidence and handoff; request REVIEW, do not close the issue.

Dispatcher/integration owner: review contracts/overlap, required CI and integrated real-data checks; integrate under the agreed PR policy; rerun acceptance on the integrated branch; close only when verified. Verify dependents before marking READY. GitHub issue state is authoritative; this document does not maintain execution status.

Completion report: **Changes; exact checks/commands; actual results; evidence URLs/paths and integrated revision; limitations; blockers; contract/deviation notes; dependent-task handoff.**

## G. Copy-paste worker prompt

> Work on T06 using `docs/tasks/T06-ingestion.md`, its linked GitHub issue and unique agent ID supplied by the dispatcher. Read AGENTS.md, README.md, docs/AGENT_WORKFLOW.md, the required architecture/contract sections and dependency evidence. Inspect existing work before editing. Request assignment and WAIT for an explicit dispatcher grant recording your issue, unique ID, branch, isolated worktree, claim time and files. After grant, implement ONLY this task and declared dependencies, preserve shared contracts and obtain owner approval before shared-file changes. Run appropriate deterministic and required real-data checks, update verified documentation, push your branch/open a linked PR if access permits, and report actual results using section F. Do not close the issue, merge, provision paid resources, send messages externally or submit artifacts without explicit authority. Never fabricate facts or results. Report blocked prerequisites without asking the user to repeat documented context.
