# Bern Match

Team solution for the Bern Economic Development Agency Research & Expertise Navigator (repository: `Apertus_Hack`).

Bern Match is a planned English-language search workspace for agency analysts finding research partners across the University of Bern (UniBE), ARTORG and Diabetes Center Berne. It addresses fragmented institutional information and the gap between a company's business language and researchers' terminology. German-to-English and English-to-German search are required.

An analyst enters keywords, a question or a pasted company description; receives up to ten distinct, evidence-backed entities; inspects exact source sentences and URLs; edits needs; selects or excludes results; and records relevance or factual corrections. Simple searches run without waiting for an LLM. Optional asynchronous Apertus interpretation and assessment enrich the results. A one-page brief and email draft are Stretch features. Document upload is out of scope.

- [Architecture and approved pipeline](docs/ARCHITECTURE.md): requirements, acceptance gates, data relationships, evaluation, operating assumptions and unresolved dependencies.
- [Proposed delivery plan and GitHub backlog](docs/tasks/README.md), [shared contracts](docs/CONTRACTS.md), and [dispatcher/worker workflow](docs/AGENT_WORKFLOW.md). Plan approval and role assignment remain pending; issue creation does not authorise coding.

Current status: documentation and proposed backlog only. Repository inspection found only the original README before this documentation update. No application, crawler, corpus, search index, Apertus integration, evaluation results, deployment or offline demonstration is implemented or verified. All functionality described above and in the architecture is planned unless later accompanied by verification evidence. Core search and measurement take priority over Second layer enrichment and Stretch exports.

Required submission deliverables are a public GitHub repository, demo video **≤2 minutes**, pitch PDF **≤10 slides**, and technical report PDF **≤6 pages**. Public repository availability and submission are not verified. Deadline: **19 October 2026, 14:30 Europe/Zurich**. The team has three developers: two with AI/ML backgrounds and one with general CS experience; names and ownership are not assigned here.

Planned data handling: collect necessary professional information and official contacts from public sources only. Provide an operator-accessible removal-request route and a suppression list preventing re-ingestion. Confirmed retired records must leave serving indexes; stored copies and backups must expire under a documented retention policy. The route, verification procedure and public-record/backup retention periods remain undecided and are not operational. Proposed defaults are session-only company inputs unless explicitly saved, company-input redaction from logs, and 30-day operational-log retention. These defaults require implementation and verification. Use fictional company profiles until approval for processing real confidential inputs is confirmed. This is a design commitment, not a claim of legal compliance.

## Running the skeleton

Verified: the app skeleton (contracts, health/readiness, a synthetic-fixture search workspace and the inference adapter) runs and passes its tests. Real search, ingestion and deployment are **not** implemented yet.

```bash
python -m venv .venv && .venv/Scripts/python -m pip install -r requirements.lock pytest   # Linux/macOS: .venv/bin/python
.venv/Scripts/python -m pytest -q                                   # deterministic tests, no network
BERNMATCH_FIXTURE_MODE=1 .venv/Scripts/python -m uvicorn app.main:app --port 8000   # UI with SYNTHETIC cards
```

Without `BERNMATCH_FIXTURE_MODE=1`, `/readyz` and search return 503 until `$BERNMATCH_DATA_DIR/READY` exists, and search returns 501 because retrieval is not wired in yet. Container: `docker build -t bernmatch . && docker run -p 8000:8000 -v bernmatch-data:/data bernmatch`; the CI `container` job builds it and probes `/healthz` and `/readyz`. Inference configuration (server-side only) is described in [docs/inference.md](docs/inference.md); copy `env.example` to a real `.env`, which is git-ignored.

## Removal requests

Anyone named in the index can ask for removal. The route, verification steps, suppression-list format and retention periods are in [docs/data-policy.md](docs/data-policy.md). **The route is not operational yet**: the operator contact in that document is still unset, and no enforcement code exists, so this is a design commitment and not a working service.

## Roadmap notes

There is no verified deployment yet. The MVP will crawl once and query persistent local indexes, with manual refresh; configurable daily refresh and selected hourly refresh are production requirements. Local offline readiness requires a separately evidenced air-gapped query demonstration.
