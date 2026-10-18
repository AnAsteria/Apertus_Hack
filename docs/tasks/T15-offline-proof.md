# T15 — Preload local assets and prove air-gapped unseen querying

## A. Identity and prerequisites

Iteration: V2 — Reliable and measured Core. Scope tier: **core**. Proposed workstream: **A**. Estimated active effort: **5 person-hours**, an unmeasured planning estimate excluding access waits/model download time. Dependencies: T03, T05, T09

Objective/outcome: Begin model/runtime/dependency downloads as soon as T03 access permits, before full application integration. Preload corpus, local embedding weights/tokenizer, indexes, evidence, Apertus 8B weights/tokenizer/runtime and UI/support assets. Record hardware, model licenses/quantisation and versions. Block outbound traffic by documented mechanism, run a new uncached query with local inference and capture isolation and successful operation.

Access/policy prerequisites and limitations: Suitable authorised local hardware/model access and preload bandwidth; start preparation early, not at V2 end.

**Revision R1 (2026-10-18, proposed by Maxim; pending team confirmation — see [README §Revision R1](README.md#revision-r1-2026-10-18)):**
- Hardware: Dimitry's 16 GB machine (T03 found the 8 GB laptops unsuitable). A prepares scripts, asset list and instructions; the run/recording is done on that machine with C. Record its specs.
- T03 findings: official Apertus v1.5 weights are gated (licence/AUP acceptance on Hugging Face is a human action); unofficial quantisations must be named with provenance. Verify that the chosen runtime (llama.cpp GGUF or MLX on Apple Silicon) supports the Apertus architecture before relying on it. Start downloads today.
- Isolation method on macOS: Wi-Fi/Ethernet off plus `HF_HUB_OFFLINE=1`/`TRANSFORMERS_OFFLINE=1`, with a recorded failing outbound check; document it.

## B. Context and contracts

Read [AGENTS.md](../../AGENTS.md), [README](../../README.md), [architecture](../ARCHITECTURE.md) sections 1–3 and pipeline step(s) **14** (numbers 1/3/9 on T01 also include the corresponding numbered architecture sections). Review architecture sections 5–9 when relevant to verification/delivery. Required [contract sections](../CONTRACTS.md): **2–6, 9**. The [workflow](../AGENT_WORKFLOW.md) governs claims and integration.

Inspect the current repository, integrated branch, dependency PRs and issue before editing. At backlog creation only README, AGENTS and architecture existed; no implementation, credentials, hosting, source inventory or benchmark results may be assumed. Paths below are proposed ownership boundaries, not existing code. T01 ratifies them.

## C. Scope and ownership

Owned files/modules: `docs/offline.md; deploy/offline/; evidence/offline/`. Shared files (`app/main.py`, `app/contracts.py`, dependency lockfile, CI, deployment configuration, shared UI shell, README and contracts) require the named owner/dispatcher's coordination before edits. Contract changes require contract-owner approval. Module owners implement partner fixes within their own granted branches.

In scope: only the objective, declared dependencies and acceptance checks below. Out of scope: unrelated features; document upload; automatic email sending/retraining; per-query crawling; full production scheduler in MVP; paid provisioning/billing acceptance; confidential company profiles. Second layer/Stretch tasks must not weaken Core or consume the submission buffer without recorded decision.

## D. Implementation and failure behavior

1. Obtain a dispatcher grant and inspect dependency evidence on the integrated branch; create the dedicated branch/worktree recorded in the grant.
2. Implement the objective above using ratified contracts and the proposed stack in the plan. Keep input/output shapes and reference integrity compatible with CONTRACTS sections listed above.
3. Validate external/model data before publishing it. Use deterministic fixtures for CI and opt-in live tests only. Log redacted metadata, not credentials/company descriptions. Apply configured timeout/retry/backoff and fail safely; unknown facts stay empty.
4. Preserve simple search when inference fails; ingestion never runs implicitly on a query. Unknown access/model/source capabilities are explicit blockers; do not substitute mocks for required live or offline evidence.
5. Coordinate shared-file changes before editing, record material deviations and rerun affected checks. Do not commit local model files, private inputs, logs or real .env files.

## E. Acceptance and verification

Recording/logs show network blocked, unseen query, local embedding/index/evidence and actual local Apertus execution, with measured timings. No mocked inference/cached answers; no remote telemetry/runtime fetch. Offline snapshot querying does not prove offline crawl. Missing local 8B is a blocker and explicit unmet gate.

Use unit tests for meaningful deterministic risk, shared contract tests for interface changes and real-data integration checks where this objective requires them. Do not add tests that merely mirror implementation. Report exact commands, observed output/exit status, test environment, fixture-versus-real distinction and limitations. No fabricated metrics, source facts or capability claims. Targets and synthetic examples are never achieved measurements.

## F. Definition of done and handoff

Worker: run issue checks; update implemented/planned documentation; push only the task branch and open a PR if access permits; link the issue without an auto-close directive; report evidence and handoff; request REVIEW, do not close the issue.

Dispatcher/integration owner: review contracts/overlap, required CI and integrated real-data checks; integrate under the agreed PR policy; rerun acceptance on the integrated branch; close only when verified. Verify dependents before marking READY. GitHub issue state is authoritative; this document does not maintain execution status.

Completion report: **Changes; exact checks/commands; actual results; evidence URLs/paths and integrated revision; limitations; blockers; contract/deviation notes; dependent-task handoff.**

## G. Copy-paste worker prompt

> Work on T15 using `docs/tasks/T15-offline-proof.md`, its linked GitHub issue and unique agent ID supplied by the dispatcher. Read AGENTS.md, README.md, docs/AGENT_WORKFLOW.md, the required architecture/contract sections and dependency evidence. Inspect existing work before editing. Request assignment and WAIT for an explicit dispatcher grant recording your issue, unique ID, branch, isolated worktree, claim time and files. After grant, implement ONLY this task and declared dependencies, preserve shared contracts and obtain owner approval before shared-file changes. Run appropriate deterministic and required real-data checks, update verified documentation, push your branch/open a linked PR if access permits, and report actual results using section F. Do not close the issue, merge, provision paid resources, send messages externally or submit artifacts without explicit authority. Never fabricate facts or results. Report blocked prerequisites without asking the user to repeat documented context.
