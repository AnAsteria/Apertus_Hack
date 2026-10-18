# Dispatcher and worker workflow

## Authority and status

The iteration plan and contracts are proposals awaiting approval. No coding agents are launched by backlog creation. One human-nominated dispatcher/integration owner is the sole grant authority; one explicit shared-contract owner ratifies schemas. Proposed roles: workstream C developer as dispatcher/integration owner, workstream B developer as contract owner, subject to team approval. Three developers: A sources/search (AI/ML), B Apertus/evaluation (AI/ML), C workspace/infra/submission (general CS). Names remain unassigned. Dispatcher duties take priority over C's feature work.

GitHub issues are authoritative for execution status. Closed = DONE only after integrated acceptance. Labels: `status:ready`, `status:blocked`, `status:in-progress`, `status:review`; a blocked issue stays open with a reason. Milestones are release iterations, not tiers. A task's document is its specification, not another status tracker. Local issue mappings/manifests are creation/audit records, not live status. Never infer readiness from an old local snapshot.

Flow: **READY → explicit GRANTED/IN_PROGRESS → REVIEW → CLOSED**. Non-coding discovery T01–T03 may be READY now; all code changes require plan approval, ratified contracts where applicable and a grant. Readiness is not permission to start. Deferred Stretch issues stay open/blocked until Core accepted and explicit reactivation. Dependency completion means verified integrated acceptance, not an unmerged PR or worker assertion.

## Serial grants, not locks

Assignment, labels and comments are NOT atomic locks, even when checked immediately before writing. Multiple sessions may share one GitHub account. No competing self-claim/check-then-label workflow is allowed. The dispatcher must serialize its own decisions; do not run two dispatcher sessions. Before handoff to another dispatcher, the human owner confirms the prior dispatcher is stopped and transfers the active-grant ledger.

1. Worker inspects a READY issue and posts a request identifying its unique agent/session ID. It waits without changing code. Without a running dispatcher, request assignment and wait; do not invent a lock.
2. Dispatcher checks live issue/dependency states, integrated evidence, existing grants and active-agent status; it grants only one worker per issue and no overlapping ownership without explicit coordination.
3. Dispatcher records the following grant in the issue **before** worker code edits, then applies IN_PROGRESS. Account assignee alone is insufficient.

```text
GRANT
Issue: #<number>
Agent/session ID: <unique-id>
Dispatcher ID: <single-dispatcher-id>
Branch: codex/issue-<number>-<slug>
Worktree: <absolute dedicated path>
Claim time: <UTC RFC3339>
Files/modules owned: <explicit list>
Shared-file permissions: <approved scope or none>
Dependencies verified: <issue refs + integrated revision/evidence>
Plan approval: <record link>
```

4. Worker creates/uses that dedicated branch and isolated worktree from the agreed integrated branch. Never switch branches inside another agent's worktree. Inspect existing changes; don't reset, overwrite or clean up another worker's work. Dispatcher verifies path uniqueness.
5. Contract owner explicitly owns `docs/CONTRACTS.md` and shared schema definitions. Integration owner owns `app/main.py`, dependency/CI/container configuration and integration changes; UI shell belongs to C. Proposed ownership becomes binding only after T01 records names and boundaries. Workers propose shared changes with rationale before editing; owner approves and coordinates who implements them.
6. Worker reports blockers/handoffs in the issue. Dispatcher alone releases/reassigns after checking whether the previous session is active and preserving its branch/work. Timestamp age alone is never sufficient grounds for reclaiming a task.

A release record identifies issue, prior agent, active-state check, preserved work, reason and new grant if any. Keep unique IDs even if every issue is assigned to the same GitHub account.

## Completion and integration

Worker runs task-required checks, adds meaningful risk-based tests, reports exact commands/actual outcomes and updates verified implementation docs. Push task branch and open a PR when access permits. Link the issue with `Refs #N` rather than automatic closing language; include evidence, limitations, model/fixture distinctions, deviations and integration notes. Do not push directly to main. Request/apply REVIEW after reporting; don't close merely because code exists.

Integration owner checks contract compatibility and overlapping files, required CI, real-data and release evidence. Proposed merge policy: reviewed PR, green required checks, dispatcher-controlled squash merge; T01 records actual branch protection/access and team approval. No PR is merged in this planning step. After integration, run acceptance on the integrated branch and record revision/evidence before closing the issue. A failed criterion keeps it open; label blocked with the exact reason when necessary. Recheck each dependent before applying READY; external prerequisites may still prevent readiness. Do not automatically close/depend on unverified work.

No paid provisioning/billing acceptance or secret exposure without explicit user authorisation. No real confidential inputs until processing approval. Never send external messages without human authorisation. Opt-in live API checks are separate from deterministic CI. Publish evidence with source/public or fictional inputs only.

## Reusable dispatcher prompt

```text
Act as the single Bern Match dispatcher/integration owner after the human has approved the plan and explicitly assigned you. Read AGENTS.md, README.md, docs/ARCHITECTURE.md, docs/CONTRACTS.md, docs/tasks/README.md and docs/AGENT_WORKFLOW.md. Inspect the current GitHub backlog, live worker sessions, grants, integrated branch and required checks. Do not infer live status from local manifest snapshots. If owner/approval is missing, request it and wait before granting coding work.
Serialize all grants. For each READY request recheck actual dependency acceptance, external prerequisites, file ownership and existing grants; record issue, unique session ID, branch, isolated worktree, UTC time, owned/shared files, approval and verified dependency revision before the worker edits code. One worker per issue; GitHub labels/comments/assignment are not atomic locks. Without proof a prior worker is stopped, do not reassign based on timestamp. Coordinate contract/shared-file changes through their explicit owners. Never start competing dispatchers.
Review evidence/PRs, confirm CI and integration checks, integrate only under the approved merge policy, verify acceptance on the integrated revision, then close and recheck dependents. Preserve open blockers and missing Core evidence. Protect submission buffer and tier order. Do not provision paid infrastructure, expose secrets, message outsiders or submit without authority. Report grants, checks, blockers and handoffs with actual evidence.
```

## Reusable worker prompt

```text
Issue: #<ISSUE_NUMBER>; unique agent/session ID: <AGENT_ID>.
Read AGENTS.md, README.md, docs/ARCHITECTURE.md, docs/CONTRACTS.md, docs/tasks/README.md, docs/AGENT_WORKFLOW.md and the task specification linked by this issue. Inspect live issue/dependency status and existing work. Request assignment from the sole dispatcher and WAIT for an explicit recorded grant; no dispatcher means wait, not self-claim. A READY label or same-account assignment is not a grant.
After a valid grant, work only on this task and declared dependencies in the recorded isolated worktree/branch. Keep shared contracts compatible and request owner approval before shared-file changes. Follow Core priorities, no per-query crawl, no LLM dependency on initial cards, no confidential inputs/credentials in Git/client/logs. Run issue-specific checks and meaningful tests, separating deterministic fixtures from opt-in live checks and actual offline proof. Report blockers/handoffs in the issue.
Push your task branch/open a PR if permitted, link via Refs #N, include changes, exact commands/results, evidence/revision, limitations, deviations and handoff. Request REVIEW; don't close, merge or reassign. Never fabricate source facts, benchmarks or capabilities. No paid provisioning, automatic sending or unrelated work. Preserve approval and submission boundaries.
```
