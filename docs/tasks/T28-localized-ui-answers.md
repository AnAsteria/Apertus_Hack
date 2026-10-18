# T28 — Optional localized interface, explanations and translated evidence

## A. Identity and prerequisites

Iteration: V4 — Verified release and submission. Scope tier: **stretch** (tier 3, after Core and Second layer). Proposed workstream: **C** (UI) with **B** (prompts). Estimated active effort: **3 person-hours**, an unmeasured planning estimate excluding access waits/model download time. Dependencies: T17, T19, T27

Objective/outcome: Interface strings in EN/DE/FR/IT/RU following the user's choice or query language; Apertus-generated explanations/assessments in that language; evidence shown in the original language with an optional machine translation into the query language. Translations are clearly labelled machine translations, never presented or stored as source text, never used as citations, and never used for grounding checks.

Access/policy prerequisites and limitations: Deferred like T23/T24: start only after Core acceptance (T17) and protected submission time. Generated text in the user's language is Second-layer output and must pass the same schema and grounding validation as English output.

Added in Revision R1 (2026-10-18) at Maxim's request; pending team confirmation and a GitHub issue. Architecture section 1 specifies an English-language workspace with DE↔EN retrieval; this task records an explicit scope extension, not a silent change.

## B. Context and contracts

Read [AGENTS.md](../../AGENTS.md), [README](../../README.md), [architecture](../ARCHITECTURE.md) sections 1–3 and pipeline step(s) **8, 10, 11, 12** (numbers 1/3/9 on T01 also include the corresponding numbered architecture sections). Review architecture sections 5–9 when relevant to verification/delivery. Required [contract sections](../CONTRACTS.md): **5, 6**. The [workflow](../AGENT_WORKFLOW.md) governs claims and integration.

Inspect the current repository, integrated branch, dependency PRs and issue before editing. At backlog creation only README, AGENTS and architecture existed; no implementation, credentials, hosting, source inventory or benchmark results may be assumed. Paths below are proposed ownership boundaries, not existing code. T01 ratifies them.

## C. Scope and ownership

Owned files/modules: `app/static/i18n/; app/ai/translate.py; tests/ui/test_i18n.py`. Shared files (`app/main.py`, `app/contracts.py`, dependency lockfile, CI, deployment configuration, shared UI shell, README and contracts) require the named owner/dispatcher's coordination before edits. Contract changes require contract-owner approval. Module owners implement partner fixes within their own granted branches.

In scope: only the objective, declared dependencies and acceptance checks below. Out of scope: unrelated features; document upload; automatic email sending/retraining; per-query crawling; full production scheduler in MVP; paid provisioning/billing acceptance; confidential company profiles. Second layer/Stretch tasks must not weaken Core or consume the submission buffer without recorded decision.

## D. Implementation and failure behavior

1. Obtain a dispatcher grant and inspect dependency evidence on the integrated branch; create the dedicated branch/worktree recorded in the grant.
2. Implement the objective above using ratified contracts and the proposed stack in the plan. Keep input/output shapes and reference integrity compatible with CONTRACTS sections listed above.
3. Validate external/model data before publishing it. Use deterministic fixtures for CI and opt-in live tests only. Log redacted metadata, not credentials/company descriptions. Apply configured timeout/retry/backoff and fail safely; unknown facts stay empty.
4. Preserve simple search when inference fails; ingestion never runs implicitly on a query. Unknown access/model/source capabilities are explicit blockers; do not substitute mocks for required live or offline evidence.
5. Coordinate shared-file changes before editing, record material deviations and rerun affected checks. Do not commit local model files, private inputs, logs or real .env files.

Task-specific steps:

1. Externalise UI strings; add the five locales.
2. Pass the target language to interpretation/assessment prompts; validate outputs as in T18/T19.
3. Add on-demand evidence translation via Apertus, cached per sentence ID + target language, labelled 'machine translation'.
4. Fast path and original evidence must remain usable if translation fails.

## E. Acceptance and verification

UI renders in all five locales; a sample of explanations per language is reviewed for grounding; translated evidence is visibly labelled and the original sentence/citation is unchanged; failure of translation leaves original evidence displayed. Report review sample sizes; no quality claims without review.

Use unit tests for meaningful deterministic risk, shared contract tests for interface changes and real-data integration checks where this objective requires them. Do not add tests that merely mirror implementation. Report exact commands, observed output/exit status, test environment, fixture-versus-real distinction and limitations. No fabricated metrics, source facts or capability claims. Targets and synthetic examples are never achieved measurements.

## F. Definition of done and handoff

Worker: run issue checks; update implemented/planned documentation; push only the task branch and open a PR if access permits; link the issue without an auto-close directive; report evidence and handoff; request REVIEW, do not close the issue.

Dispatcher/integration owner: review contracts/overlap, required CI and integrated real-data checks; integrate under the agreed PR policy; rerun acceptance on the integrated branch; close only when verified. Verify dependents before marking READY. GitHub issue state is authoritative; this document does not maintain execution status.

Completion report: **Changes; exact checks/commands; actual results; evidence URLs/paths and integrated revision; limitations; blockers; contract/deviation notes; dependent-task handoff.**

## G. Copy-paste worker prompt

> Work on T28 using `docs/tasks/T28-localized-ui-answers.md`, its linked GitHub issue and unique agent ID supplied by the dispatcher. Read AGENTS.md, README.md, docs/AGENT_WORKFLOW.md, the required architecture/contract sections and dependency evidence. Inspect existing work before editing. Request assignment and WAIT for an explicit dispatcher grant recording your issue, unique ID, branch, isolated worktree, claim time and files. After grant, implement ONLY this task and declared dependencies, preserve shared contracts and obtain owner approval before shared-file changes. Run appropriate deterministic and required real-data checks, update verified documentation, push your branch/open a linked PR if access permits, and report actual results using section F. Do not close the issue, merge, provision paid resources, send messages externally or submit artifacts without explicit authority. Never fabricate facts or results. Report blocked prerequisites without asking the user to repeat documented context.
