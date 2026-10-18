Proposed iteration plan, awaiting approval. No feature implementation authorised by issue creation.

**Task:** T13 | **Iteration:** V2 — Reliable and measured Core | **Tier:** core | **Workstream:** C

**Dependencies (verified integrated acceptance required):** #11, #12

**Current readiness reason:** Dependency acceptance is not yet verified; coding plan approval/dispatcher grant required. T12 lifecycle interfaces; admin secret supplied securely at deployment.

**Repository specification:** [docs/tasks/T13-feedback-admin.md](https://github.com/AnAsteria/Apertus_Hack/blob/codex/backlog-plan/docs/tasks/T13-feedback-admin.md). Planning documents are published on `codex/backlog-plan` for review; links resolve after planning branch publication. Required architecture/contract sections and file ownership appear below.

**Agent claim instructions:** Read the workflow; request a task with a unique session ID and WAIT for the sole dispatcher's explicit recorded grant. READY/account assignment/comments are not atomic locks. No active dispatcher means wait. No automatic self-claim.

# T13 — Persist analyst feedback and protected operator administration

## A. Identity and prerequisites

Iteration: V2 — Reliable and measured Core. Scope tier: **core**. Proposed workstream: **C**. Estimated active effort: **4 person-hours**, an unmeasured planning estimate excluding access waits/model download time. Dependencies: T11, T12

Objective/outcome: Add needs edits, select/exclude, relevance and wrong-fact feedback persistence tied to request/result/claim. Build non-ML admin source configuration, coverage, failed jobs, redacted logs, freshness and bounded manual refresh. Protect writes/refresh with server-side admin authentication and appropriate browser request protection. No automatic retraining or scheduler.

Access/policy prerequisites and limitations: T12 lifecycle interfaces; admin secret supplied securely at deployment.

## B. Context and contracts

Read [AGENTS.md](../../AGENTS.md), [README](../../README.md), [architecture](../ARCHITECTURE.md) sections 1–3 and pipeline step(s) **12, 14** (numbers 1/3/9 on T01 also include the corresponding numbered architecture sections). Review architecture sections 5–9 when relevant to verification/delivery. Required [contract sections](../CONTRACTS.md): **7, 9**. The [workflow](../AGENT_WORKFLOW.md) governs claims and integration.

Inspect the current repository, integrated branch, dependency PRs and issue before editing. At backlog creation only README, AGENTS and architecture existed; no implementation, credentials, hosting, source inventory or benchmark results may be assumed. Paths below are proposed ownership boundaries, not existing code. T01 ratifies them.

## C. Scope and ownership

Owned files/modules: `app/api/admin.py; app/api/feedback.py; app/static/admin/; tests/admin/; tests/feedback/`. Shared files (`app/main.py`, `app/contracts.py`, dependency lockfile, CI, deployment configuration, shared UI shell, README and contracts) require the named owner/dispatcher's coordination before edits. Contract changes require contract-owner approval. Module owners implement partner fixes within their own granted branches.

In scope: only the objective, declared dependencies and acceptance checks below. Out of scope: unrelated features; document upload; automatic email sending/retraining; per-query crawling; full production scheduler in MVP; paid provisioning/billing acceptance; confidential company profiles. Second layer/Stretch tasks must not weaken Core or consume the submission buffer without recorded decision.

## D. Implementation and failure behavior

1. Obtain a dispatcher grant and inspect dependency evidence on the integrated branch; create the dedicated branch/worktree recorded in the grant.
2. Implement the objective above using ratified contracts and the proposed stack in the plan. Keep input/output shapes and reference integrity compatible with CONTRACTS sections listed above.
3. Validate external/model data before publishing it. Use deterministic fixtures for CI and opt-in live tests only. Log redacted metadata, not credentials/company descriptions. Apply configured timeout/retry/backoff and fail safely; unknown facts stay empty.
4. Preserve simple search when inference fails; ingestion never runs implicitly on a query. Unknown access/model/source capabilities are explicit blockers; do not substitute mocks for required live or offline evidence.
5. Coordinate shared-file changes before editing, record material deviations and rerun affected checks. Do not commit local model files, private inputs, logs or real .env files.

## E. Acceptance and verification

Feedback survives restart with identifiers and revisions; admin reads useful coverage/failure status; unauthorised refresh/config changes are refused; logs redact company input; requests stay text-only. Check contract errors, feedback persistence, admin access and browser flow against real search.

Use unit tests for meaningful deterministic risk, shared contract tests for interface changes and real-data integration checks where this objective requires them. Do not add tests that merely mirror implementation. Report exact commands, observed output/exit status, test environment, fixture-versus-real distinction and limitations. No fabricated metrics, source facts or capability claims. Targets and synthetic examples are never achieved measurements.

## F. Definition of done and handoff

Worker: run issue checks; update implemented/planned documentation; push only the task branch and open a PR if access permits; link the issue without an auto-close directive; report evidence and handoff; request REVIEW, do not close the issue.

Dispatcher/integration owner: review contracts/overlap, required CI and integrated real-data checks; integrate under the agreed PR policy; rerun acceptance on the integrated branch; close only when verified. Verify dependents before marking READY. GitHub issue state is authoritative; this document does not maintain execution status.

Completion report: **Changes; exact checks/commands; actual results; evidence URLs/paths and integrated revision; limitations; blockers; contract/deviation notes; dependent-task handoff.**

## G. Copy-paste worker prompt

> Work on T13 using `docs/tasks/T13-feedback-admin.md`, its linked GitHub issue and unique agent ID supplied by the dispatcher. Read AGENTS.md, README.md, docs/AGENT_WORKFLOW.md, the required architecture/contract sections and dependency evidence. Inspect existing work before editing. Request assignment and WAIT for an explicit dispatcher grant recording your issue, unique ID, branch, isolated worktree, claim time and files. After grant, implement ONLY this task and declared dependencies, preserve shared contracts and obtain owner approval before shared-file changes. Run appropriate deterministic and required real-data checks, update verified documentation, push your branch/open a linked PR if access permits, and report actual results using section F. Do not close the issue, merge, provision paid resources, send messages externally or submit artifacts without explicit authority. Never fabricate facts or results. Report blocked prerequisites without asking the user to repeat documented context.
