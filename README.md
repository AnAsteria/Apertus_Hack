# Bern Match

Search tool for the Bern Economic Development Agency: an analyst describes a company's need in plain language and gets up to ten research groups, people, projects or infrastructure at the University of Bern (UniBE), ARTORG and Diabetes Center Berne. Every card quotes the exact source sentence and links to the page it came from.

**Live demo:** https://kaktamsdengami-bern-match.hf.space (Hugging Face Docker Space). AI features use [Apertus](https://huggingface.co/swiss-ai), the Swiss open model, through the hackathon organisers' Keera gateway. The first results never wait for the AI.

## What works today

Status as of 2026-10-18. "Measured" numbers come from the issues and docs linked next to them.

| Area | Implemented | Evidence |
| --- | --- | --- |
| Corpus | Crawl of 41 supplied UniBE, ARTORG and DCB domains: 2,811 pages, 148,404 sentences, with fetch dates and content hashes. Respects robots.txt, never crawls per query | [docs/sources.md](docs/sources.md), #6 |
| Facts | Apertus 70B extracts entities and claims offline; code checks every claim against its source sentence. 4,374 entities, 5,130 claims (4,314 supported) | [docs/extraction.md](docs/extraction.md), [docs/grounding.md](docs/grounding.md), #7, #8 |
| Search | Hybrid BM25 + multilingual dense retrieval (multilingual-e5-small, CPU), fused ranking, at most 10 distinct entities, exact evidence sentences | [app/search/README.md](app/search/README.md), #9 |
| Honest answers | Deterministic outcome policy: confident / low confidence / too broad / no evidence, with narrowing suggestions; no card without evidence | #82, [docs/DECISIONS.md](docs/DECISIONS.md) D11 |
| AI enrichment (optional) | Apertus interprets the request into editable needs and expansions, re-ranks with them, and attaches per-card assessments. All streamed after the first results, validated against schemas, labelled as generated text | [docs/interpretation.md](docs/interpretation.md), [docs/assessment.md](docs/assessment.md), #18, #19, #81 |
| UI | Search workspace: example queries (EN/DE/FR), type chips, cards with supported fields only, highlighted evidence, source tags, shortlist, outcome states, dark mode | #80 |
| Data policy | Suppression list, crawler skip, serving filter, `410` for removed records, purge | [docs/data-policy.md](docs/data-policy.md), #12 |
| Deployment | One-command deploy with smoke test and rollback; index restored from a bucket in seconds; feedback survives restarts | [docs/deployment.md](docs/deployment.md), #84 |
| Evaluation | Gold set 0.3 (frozen), harness for Recall@10, abstention and latency | [docs/evaluation-protocol.md](docs/evaluation-protocol.md), #14 |

**Measured so far (small samples, development split only):** Recall@10 0.56 on 9 development queries against the first evidence-only index, search latency median about 250 ms and p95 about 420 ms (#9, #14). German-to-English queries were the weak spot. Newer runs on the current index are posted on #14. AI cost and latency figures are in [docs/MEASUREMENTS.md](docs/MEASUREMENTS.md) and [docs/costs.md](docs/costs.md).

## Planned or not done

- **Operator contact for removal requests** is still unset in [docs/data-policy.md](docs/data-policy.md), so the removal route is designed and coded but not staffed.
- **Admin interface** (#13): the feedback API and protected admin routes exist; there is no admin UI.
- **Offline / air-gapped run** (#15): on hold.
- **Server-side filters and facets** (#86), **query normalisation** (#85), **new source domains** (#83), **localised interface** (#40): not built.
- **One-page brief and email draft** (#23, #24): optional, not built. Nothing is ever sent automatically.
- Coverage is uneven: medical and biomedical sites got larger crawl budgets than other faculties.

## Run it locally

Python 3.12.

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.lock -r app/search/requirements.txt -r app/ingest/requirements.txt pytest httpx   # Linux/macOS: .venv/bin/python
.venv/Scripts/python -m pytest -q                      # deterministic tests, no network
```

**UI with synthetic data** (no index, no keys):

```bash
BERNMATCH_FIXTURE_MODE=1 .venv/Scripts/python -m uvicorn app.main:app --port 8000
```

**Real search** needs an index. Build one from a corpus export (and optionally the T08 knowledge files):

```bash
.venv/Scripts/python -m app.search fetch-model --model small --model-dir models/e5-small
.venv/Scripts/python -m app.search build --corpus-jsonl corpus.jsonl --knowledge-dir knowledge --model-dir models/e5-small --data-dir data
BERNMATCH_DATA_DIR=data .venv/Scripts/python -m uvicorn app.main:app --port 8000
```

The corpus itself is not in this repository because it contains names and professional contact details from public pages; crawl it with `python -m app.ingest crawl --profile final` (see [app/ingest/README.md](app/ingest/README.md)). AI features need `APERTUS_BASE_URL`, `APERTUS_API_KEY` and `APERTUS_MODEL` in a git-ignored `.env` (template: [env.example](env.example), details: [docs/inference.md](docs/inference.md)). Without them search still works and the AI parts report themselves unavailable.

**Evaluation** against a running instance:

```bash
.venv/Scripts/python -m evaluation run --base-url http://127.0.0.1:8000 --split development --out runs/dev.json
.venv/Scripts/python -m evaluation report runs/dev.json
```

**Container:** `docker build -t bernmatch . && docker run -p 8000:8000 -v bernmatch-data:/data bernmatch`. The Hugging Face Space uses `deploy/hf-space/`; see [docs/deployment.md](docs/deployment.md).

## Data handling

Only public professional information from the listed institutional sites is collected. Company descriptions typed into the search are not stored and are kept out of logs. Anyone named in the index can ask for removal: suppressed records are skipped by the crawler, filtered at serving time and answered with `410`. See [docs/data-policy.md](docs/data-policy.md). This is a design commitment, not a claim of legal compliance.

## Documentation

[Architecture](docs/ARCHITECTURE.md) · [Contracts](docs/CONTRACTS.md) · [Decisions](docs/DECISIONS.md) · [Measurements](docs/MEASUREMENTS.md) · [Deployment](docs/deployment.md) · [Attribution and licences](docs/attribution.md) · [Team plan](docs/TEAM_PLAN.md)

## Team

Built for the Apertus hackathon (deadline 19 October 2026) by Dimitry ([@kaktamsdengami](https://github.com/kaktamsdengami)), Maxim ([@maxim451](https://github.com/maxim451)) and Ruihan ([@AnAsteria](https://github.com/AnAsteria)).
