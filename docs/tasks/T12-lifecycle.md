# T12 — Implement freshness, manual refresh, retirement and suppression

## A. Identity and prerequisites

Iteration: V2 — Reliable and measured Core. Scope tier: **core**. Proposed workstream: **A**. Estimated active effort: **4 person-hours**, an unmeasured planning estimate excluding access waits/model download time. Dependencies: T09

Objective/outcome: Implement documented freshness threshold, separate fetch/content dates, manual changed-content refresh, transient failure retry and confirmed retirement propagation to serving indexes. Add removal-request route/process and suppression pre-ingestion, copy/cache/backup expiration policy, former-contact exclusion and session/log retention rules. Represent production daily/default and selected hourly settings without building a full MVP scheduler.

Access/policy prerequisites and limitations: Freshness/retention/removal-confirmation decisions and reachable operator route from T01.

**Revision R1 (2026-10-18, proposed by Maxim; pending team confirmation — see [README §Revision R1](README.md#revision-r1-2026-10-18)):**
- **MVP reduction:** suppression list in YAML applied before ingestion and at serving time; protected retire action propagating to serving indexes; HTTP 410 `EVIDENCE_REMOVED` for removed citations; removal-request contact in README; one controlled refresh test (changed text → new version, old citation keeps identity). Freshness uses the DECISIONS threshold (365 days on content/last-modified date, else `unknown`). No scheduler; backup/expiry policy is documented text, not automation.

## B. Context and contracts

Read [AGENTS.md](../../AGENTS.md), [README](../../README.md), [architecture](../ARCHITECTURE.md) sections 1–3 and pipeline step(s) **5, 6, 12, 14** (numbers 1/3/9 on T01 also include the corresponding numbered architecture sections). Review architecture sections 5–9 when relevant to verification/delivery. Required [contract sections](../CONTRACTS.md): **2, 3, 7, 9**. The [workflow](../AGENT_WORKFLOW.md) governs claims and integration.

Inspect the current repository, integrated branch, dependency PRs and issue before editing. At backlog creation only README, AGENTS and architecture existed; no implementation, credentials, hosting, source inventory or benchmark results may be assumed. Paths below are proposed ownership boundaries, not existing code. T01 ratifies them.

## C. Scope and ownership

Owned files/modules: `app/lifecycle/; app/storage/removal.py; docs/data-policy.md; tests/lifecycle/`. Shared files (`app/main.py`, `app/contracts.py`, dependency lockfile, CI, deployment configuration, shared UI shell, README and contracts) require the named owner/dispatcher's coordination before edits. Contract changes require contract-owner approval. Module owners implement partner fixes within their own granted branches.

In scope: only the objective, declared dependencies and acceptance checks below. Out of scope: unrelated features; document upload; automatic email sending/retraining; per-query crawling; full production scheduler in MVP; paid provisioning/billing acceptance; confidential company profiles. Second layer/Stretch tasks must not weaken Core or consume the submission buffer without recorded decision.

## D. Implementation and failure behavior

1. Obtain a dispatcher grant and inspect dependency evidence on the integrated branch; create the dedicated branch/worktree recorded in the grant.
2. Implement the objective above using ratified contracts and the proposed stack in the plan. Keep input/output shapes and reference integrity compatible with CONTRACTS sections listed above.
3. Validate external/model data before publishing it. Use deterministic fixtures for CI and opt-in live tests only. Log redacted metadata, not credentials/company descriptions. Apply configured timeout/retry/backoff and fail safely; unknown facts stay empty.
4. Preserve simple search when inference fails; ingestion never runs implicitly on a query. Unknown access/model/source capabilities are explicit blockers; do not substitute mocks for required live or offline evidence.
5. Coordinate shared-file changes before editing, record material deviations and rerun affected checks. Do not commit local model files, private inputs, logs or real .env files.

## E. Acceptance and verification

Real/controlled refresh demonstrates changed evidence, stable historical citation identity, unavailable removed evidence, retry without premature deletion, suppression across re-ingestion and former-staff filtering. Verify expiration/redaction behavior and update README removal route. Exact policy values need recorded approval, not invented legal claims.

Use unit tests for meaningful deterministic risk, shared contract tests for interface changes and real-data integration checks where this objective requires them. Do not add tests that merely mirror implementation. Report exact commands, observed output/exit status, test environment, fixture-versus-real distinction and limitations. No fabricated metrics, source facts or capability claims. Targets and synthetic examples are never achieved measurements.

## F. Definition of done and handoff

Worker: run issue checks; update implemented/planned documentation; push only the task branch and open a PR if access permits; link the issue without an auto-close directive; report evidence and handoff; request REVIEW, do not close the issue.

Dispatcher/integration owner: review contracts/overlap, required CI and integrated real-data checks; integrate under the agreed PR policy; rerun acceptance on the integrated branch; close only when verified. Verify dependents before marking READY. GitHub issue state is authoritative; this document does not maintain execution status.

Completion report: **Changes; exact checks/commands; actual results; evidence URLs/paths and integrated revision; limitations; blockers; contract/deviation notes; dependent-task handoff.**

## G. Copy-paste worker prompt

> Work on T12 using `docs/tasks/T12-lifecycle.md`, its linked GitHub issue and unique agent ID supplied by the dispatcher. Read AGENTS.md, README.md, docs/AGENT_WORKFLOW.md, the required architecture/contract sections and dependency evidence. Inspect existing work before editing. Request assignment and WAIT for an explicit dispatcher grant recording your issue, unique ID, branch, isolated worktree, claim time and files. After grant, implement ONLY this task and declared dependencies, preserve shared contracts and obtain owner approval before shared-file changes. Run appropriate deterministic and required real-data checks, update verified documentation, push your branch/open a linked PR if access permits, and report actual results using section F. Do not close the issue, merge, provision paid resources, send messages externally or submit artifacts without explicit authority. Never fabricate facts or results. Report blocked prerequisites without asking the user to repeat documented context.
