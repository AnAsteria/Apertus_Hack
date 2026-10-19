# T22 — Prepare pitch, report, demo and attribution early

## A. Identity and prerequisites

Iteration: V4 — Verified release and submission. Scope tier: **core**. Proposed workstream: **C**. Estimated active effort: **4 person-hours**, an unmeasured planning estimate excluding access waits/model download time. Dependencies: T01

Objective/outcome: Start before final iteration: outline fictional-company story, ≤2-minute video/backup, ≤10-slide pitch PDF including minimisation/removal/retention, ≤6-page technical-report PDF and evidence placeholders. Map every jury criterion to real evidence; inventory dependencies/model licenses and authoritative Apertus provenance/opt-out references. Draft submission checklist and required PDF ZIP manifest; never prefill fake results.

Access/policy prerequisites and limitations: Preparation starts V1; final acceptance needs measured results, final deployment and actual artifacts.

## B. Context and contracts

Read [AGENTS.md](../../AGENTS.md), [README](../../README.md), [architecture](../ARCHITECTURE.md) sections 1–3 and pipeline step(s) **17** (numbers 1/3/9 on T01 also include the corresponding numbered architecture sections). Review architecture sections 5–9 when relevant to verification/delivery. Required [contract sections](../CONTRACTS.md): **8, 9**. The [workflow](../AGENT_WORKFLOW.md) governs claims and integration.

Inspect the current repository, integrated branch, dependency PRs and issue before editing. At backlog creation only README, AGENTS and architecture existed; no implementation, credentials, hosting, source inventory or benchmark results may be assumed. Paths below are proposed ownership boundaries, not existing code. T01 ratifies them.

## C. Scope and ownership

Owned files/modules: `submission/; docs/submission.md; docs/attribution.md`. Shared files (`app/main.py`, `app/contracts.py`, dependency lockfile, CI, deployment configuration, shared UI shell, README and contracts) require the named owner/dispatcher's coordination before edits. Contract changes require contract-owner approval. Module owners implement partner fixes within their own granted branches.

In scope: only the objective, declared dependencies and acceptance checks below. Out of scope: unrelated features; document upload; automatic email sending/retraining; per-query crawling; full production scheduler in MVP; paid provisioning/billing acceptance; confidential company profiles. Second layer/Stretch tasks must not weaken Core or consume the submission buffer without recorded decision.

## D. Implementation and failure behavior

1. Obtain a dispatcher grant and inspect dependency evidence on the integrated branch; create the dedicated branch/worktree recorded in the grant.
2. Implement the objective above using ratified contracts and the proposed stack in the plan. Keep input/output shapes and reference integrity compatible with CONTRACTS sections listed above.
3. Validate external/model data before publishing it. Use deterministic fixtures for CI and opt-in live tests only. Log redacted metadata, not credentials/company descriptions. Apply configured timeout/retry/backoff and fail safely; unknown facts stay empty.
4. Preserve simple search when inference fails; ingestion never runs implicitly on a query. Unknown access/model/source capabilities are explicit blockers; do not substitute mocks for required live or offline evidence.
5. Coordinate shared-file changes before editing, record material deviations and rerun affected checks. Do not commit local model files, private inputs, logs or real .env files.

### Required pitch/report item: local, sovereign operation (jury criterion "Sovereign deployability")

One slide and one report paragraph: Bern Match runs entirely on one machine with `docker compose up`, with no cantonal ICT, no cloud and no network. That covers search, index, embeddings and optionally Apertus 8B via llama.cpp. Use **only** the recorded T15 air-gapped run (`docs/offline-docker.md`; output and recording on #15) as evidence: show a short clip or screenshots of `NETWORK BLOCKED` plus an unseen query.
- If the run has not been recorded by the freeze, the slide must say "designed for, not yet demonstrated". It must not claim offline operation.
- The online demo uses the HF Space + CSCS Keera (Swiss-hosted Apertus). Say so, and say that the same image runs locally.

## E. Acceptance and verification

Review outlines and attribution inventory early; final deliverables are produced from real T16/T20/T25 evidence before T26. Check PDF page counts, video duration/playback, real-source citations and labelled unknowns. Early placeholders are visibly incomplete; this issue cannot close merely on outlines.

Use unit tests for meaningful deterministic risk, shared contract tests for interface changes and real-data integration checks where this objective requires them. Do not add tests that merely mirror implementation. Report exact commands, observed output/exit status, test environment, fixture-versus-real distinction and limitations. No fabricated metrics, source facts or capability claims. Targets and synthetic examples are never achieved measurements.

## F. Definition of done and handoff

Worker: run issue checks; update implemented/planned documentation; push only the task branch and open a PR if access permits; link the issue without an auto-close directive; report evidence and handoff; request REVIEW, do not close the issue.

Dispatcher/integration owner: review contracts/overlap, required CI and integrated real-data checks; integrate under the agreed PR policy; rerun acceptance on the integrated branch; close only when verified. Verify dependents before marking READY. GitHub issue state is authoritative; this document does not maintain execution status.

Completion report: **Changes; exact checks/commands; actual results; evidence URLs/paths and integrated revision; limitations; blockers; contract/deviation notes; dependent-task handoff.**

## G. Copy-paste worker prompt

> Work on T22 using `docs/tasks/T22-artifact-preparation.md`, its linked GitHub issue and unique agent ID supplied by the dispatcher. Read AGENTS.md, README.md, docs/AGENT_WORKFLOW.md, the required architecture/contract sections and dependency evidence. Inspect existing work before editing. Request assignment and WAIT for an explicit dispatcher grant recording your issue, unique ID, branch, isolated worktree, claim time and files. After grant, implement ONLY this task and declared dependencies, preserve shared contracts and obtain owner approval before shared-file changes. Run appropriate deterministic and required real-data checks, update verified documentation, push your branch/open a linked PR if access permits, and report actual results using section F. Do not close the issue, merge, provision paid resources, send messages externally or submit artifacts without explicit authority. Never fabricate facts or results. Report blocked prerequisites without asking the user to repeat documented context.
