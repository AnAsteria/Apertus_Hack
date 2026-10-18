# T06 public-source ingestion

Implemented as an operator CLI. Search imports/calls no ingestion code. This builds a persistent **corpus**, not a BM25/vector index, LLM facts, or an offline Apertus query demonstration.

## Setup and reproducible commands

From the repository root with Python 3.12 in an isolated environment:

```bash
python -m pip install -r requirements.lock -r app/ingest/requirements.txt pytest
python -m app.ingest generate
python -m app.ingest crawl --profile dev --source unibe-dbmr --source artorg --source dcb --max-pages 4
python -m app.ingest export > data/corpus.jsonl
python -m pytest tests/ingest -q
```

These commands were exercised using a separate Python 3.12.14 environment; real smoke data used `--data-dir /private/tmp/bernmatch-t06-handoff` rather than tracked repository files. The generator does not use the network. The crawl command deliberately enables public network requests; do not run it during query execution. Omitting `--source` selects all 41 included inventory domains and can take substantially longer. No domain is skipped solely for being outside focus.

Dependencies are pinned separately inside this granted module. The root requirements/pyproject/CI/container files were not edited because the dispatcher withheld shared-file permissions. **Integration owner must install `-r app/ingest/requirements.txt` in CI/container jobs that run ingestion.** New tests explicitly skip when this optional dependency set is absent; a baseline-only green CI is not proof the ingestion suite ran. The runtime search service can read `app.storage.corpus` without the parser dependencies.

## Configuration and source coverage

`config/sources/unibe_inventory.csv` remains the exact organiser input. The generator joins the reviewed `unibe_inventory_audit.csv` by inventory key, rejects mismatched/duplicate inputs and writes one YAML per included domain under `generated/`. ARTORG has `unibe` and `artorg` labels but a single source entry. `excluded.json` retains the geo2 placeholder's documented reason. `registry.json` lists the active generated YAML files, so a stale file left after an exclusion cannot silently re-enable a source. For an explicitly approved new small website, pass `--config path/to/source.yaml`; it uses the same SourceConfig/profiles/labels wrapper and pipeline, with the same scope/robots/limit checks.

`crawl_profiles.json` holds all page/depth/rate/discovery/response limits. Initial defaults are `dev`: 20 pages/focus domain, 5/outside-focus domain; `final`: 200/focus, 50/outside-focus. These final defaults are adjustable ceilings, **not measured maximum feasible coverage**. Tune against measured time/resources before a final benchmark. `--max-pages N` is an explicit override recorded in each snapshot; it does not change saved configuration. The snapshot also records actual duration, profile, limits, requests/retries, languages/types and failures/unsupported reasons. A page slot is a bounded attempt (including unsupported/failed content), not a guarantee of an indexed page.

`discovery_seeds.json` prioritises the previously verified real research pages and one ARTORG text-PDF. Other domains start at their audited effective landing URL. Default within-host path scope is `/`, filtered by robots and finite budgets; operators can narrow `allowed_paths` in a source YAML. Directories, public service pages and original passages remain available even if not routed to extraction. Research links are prioritised, but budgets can leave discovered URLs unfetched and are explicitly reported.

The sitemap index and submaps share a configurable sitemap budget separate from the page budget. Every discovered URL still passes domain/path/robots checks. Compressed sitemap input is reported unsupported rather than silently ignored; no XML sitemap path is guessed. All requests are GET; private/nonpublic resolved addresses, credentials in URLs, unexpected ports, disallowed redirects and unknown/denied robots states are rejected. Robots 404/410 is distinguished from temporary failure. Query parameters are preserved for robots and HTTP requests before document-identity normalisation; dropping trackers must not bypass a robots rule. DNS checks mitigate unsafe targets but are not a claim of fully hardened production networking.

## Persistence, immutable evidence and handoff

`$BERNMATCH_DATA_DIR` (default `data/`, or `--data-dir`) contains:

- `corpus.sqlite`: contract-validated documents, immutable versions/sentences, active-version pointers, uncertain stub entities, passage/entity links, source labels, language-variant links, cached discovery text and snapshot metadata.
- `raw/<sha256>`: original public response bytes; raw hash is separate from the **cleaned-text** hash used in D3 version IDs.
- `fetches/*.json`: requested/effective URL, redirects, fetch/lastmod dates, raw hash and evidence version for each successful stored response. Repeated identical text reuses evidence version IDs while keeping separate fetch observations.
- `snapshots/*.json`: measured per-source run report, limitations and extraction queue. Each page is committed before the progress callback, so T07/T08 can consume an early source without waiting for all domains.

Use the merged identifier helpers/models from `app/contracts.py`; ingestion does not redefine their recipes. `CorpusStore.active_records()` returns `document`, `version`, ordered `sentences`, uncertain `entities`, `source_labels` and `passage_entity_ids` for T07/T09. `get_sentence(version_id, sentence_id)` resolves exact stored text and rejects mismatched/unavailable evidence. `python -m app.ingest export` emits public JSONL with the same records, with no network access. SQLite remains the canonical store; exported JSONL is a handoff artifact.

Only the active version is served through `active_records()`. Older sentence IDs continue to resolve to their original exact text. An explicit re-fetch with changed text creates a different version. Temporary fetch failure does not remove active records. `--refresh` re-fetches selected bounded inputs; confirmed removal, suppression, retention/backup expiry and admin job execution remain **T12**, not claims of this module.

Default repeated ingestion reuses cached pages/discovered stored URLs and does not refetch their content or robots; a same-budget completed smoke run made zero HTTP requests. New source URLs or a larger budget may fetch previously unseen content. Use explicit refresh when changing parsing rules or seeking current source content; the job does not claim its old snapshot is current merely because it was reused.

HTML cleaning strips scripts/navigation/forms and known boilerplate, retains headings/paragraphs/lists, and separates related WordPress project cards from a single project. Sentence splitting is conservative and can split abbreviations: it guarantees stored substring fidelity, **not semantic completeness**. Parser changes require a new parser version. PDF passages retain page numbers and canonical form-feed boundaries; empty/scanned or encrypted PDFs are reported, not OCR'd. Language hints/local detection support DE/EN/FR/IT; uncertainty remains null. This is not a measured language-detection benchmark.

Stub entities use heading/title and cheap page type, deterministic UUID5 anchors and `resolution_state=uncertain`, `status=unknown`, no claims or contacts. They are not resolved people or validated expertise. Directory/PDF stubs are provisional retrieval anchors; T08 merges/replaces through aliases. Explicit language selectors and identical-text candidates link document records without overwriting their evidence language/text; they do not establish entity equivalence.

## Checks and limitations

The deterministic ingestion suite covers URL/scope/private-address handling; robots wildcards, terminal anchors and group merging; robots-aware redirects; bounded retry/rate/size limits; tracker-query bypass prevention; main-text/version stability; cross-version citation rejection; bilingual document linking; HTML routing/related-card separation; PDF page evidence/scanned reporting; four-language detection; sitemap allowlists; persistent restart with no HTTP; configurable page limits; inventory/profile generation; and preservation of active evidence after failed refresh.

No confidential inputs or paid inference are used. Public snapshots, extracted contact text, SQLite files, logs and models are never committed. Real smoke results and integration notes are recorded separately below; a small three-source smoke is not a full 41-domain crawl or a final benchmark.

## Verified bounded smoke — 18 October 2026

Environment: Python 3.12.14, macOS arm64; parser `t06-v4`; `dev` profile with explicit `--max-pages 4` for `artorg`, `dcb`, `unibe-dbmr`. Safe aggregate evidence is committed at `tests/ingest/evidence/t06_smoke.json`; raw corpus/data remain outside Git.

| Source | Stored pages | Source HTTP requests incl. robots/maps | Observed run duration |
| --- | --- | --- | --- |
| ARTORG | 4 | 5 | 8.396067 s |
| DCB | 4 | 7 | 17.174180 s |
| UniBE–DBMR | 4 | 5 | 8.426259 s |

Total: 12 active document versions, 971 stored sentences and 26 **uncertain retrieval anchors**, including one 13-page text-PDF. No fetch/parse failures or retries occurred in this limited run. DCB English/German project variants remained separate, explicitly linked documents. Every stored sentence was resolved again by version + sentence ID and compared exactly. PDF evidence covered pages 1–13. Each single DCB project had one provisional project anchor; unrelated project cards were excluded from its main text.

A fresh process repeated the same command/budget against the persisted store: all 12 pages reused and **zero HTTP requests**. JSONL export produced 12 contract-backed records and preserved ARTORG's dual source labels. No `READY` search-index marker was created. Corpus path for local handoff: `/private/tmp/bernmatch-t06-handoff`; export: `/private/tmp/bernmatch-t06-handoff.jsonl`. These local temporary paths are development evidence, not a production deployment/persistence promise.

Final local full suite: **87 passed, 1 skipped** (the opt-in live inference test), one upstream Starlette/AnyIO deprecation warning. All **23 ingestion cases** ran with parser dependencies installed. No LLM/paid inference or confidential profiles were used. Baseline CI without optional ingestion dependencies skips the ingestion module: integration owner must add the dependency-install command before claiming CI acceptance for T06.

This is a small three-source integration smoke, not the full 41-domain `dev`/`final` crawl, a Recall@10 result, a latency-target benchmark or air-gapped Apertus proof. Final-profile budgets and coverage remain to be measured on the intended demo/evaluation corpus. Retention/removal execution, admin refresh wiring, search indexes and structured model extraction remain their declared later tasks.
