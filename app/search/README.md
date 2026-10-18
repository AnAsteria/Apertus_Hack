# T09 — persistent multilingual hybrid retrieval

Worker `maxim-T09`; Refs #9. Implements the accepted T06 passage/stub vertical slice. This document distinguishes implemented mechanisms from verification still in progress; the GitHub issue is authoritative for acceptance.

## Implemented

- Operator-only build from `CorpusStore.active_records()`, without crawling or LLM calls. Original passages and entity profiles are both indexed. Exact sentence records and their version/page/date provenance are retained in a serving SQLite database; raw HTML/PDF caches are not copied.
- Language-specific Snowball analysis (EN/DE/FR/IT; RU queries), with German character terms for compound matching; a persistent SQLite FTS5 BM25 index. Query-language detection is diagnostic and never a network dependency. Detection uncertainty does not discard keyword matches. BM25 is not a translator. Lexical query expansion is bounded to 512 analyzed terms; dense encoding retains all query windows. User query text is not cached in module state.
- Local multilingual E5 ONNX int8 CPU inference, `query:` / `passage:` prefixes, attention-mask mean pooling, L2 normalization. Long texts use overlapping 512-token windows (64-token overlap), rather than lose their tails. Queries average their window vectors; passage windows vote by maximum, not sum.
- Dense float32 arrays plus window-to-entry mappings, reopened with read-only NumPy mmap. Original sentence text is resolved by code. Citation identity is checked independently from semantic support; retrieval scores do not establish the latter.
- Each retrieval channel aggregates **maximum per entity before reciprocal-rank fusion** (constant 60, depth 100). Type filtering precedes aggregation; explicit T08 aliases deduplicate entity IDs. No name-only or automatic language-variant identity merging.
- Keyword retrieval keeps the best 1,000 BM25 entries. Relevance-aware MMR (relevance weight 0.85) over all fused candidates — no fused-score cut-off, which under RRF had reduced hybrid results to one card when an entity topped both channels — maximum ten distinct primary entities; no institutional quotas. Fixed initial dense threshold: 0.80. **Query-level abstention** (`BERNMATCH_ABSTAIN_DENSE`, default 0.83; was 0.865): when the best dense similarity among allowed entities is below it, the query returns no cards and says support was not found in the indexed corpus; keyword-only mode never abstains this way. **Listing-page demotion:** news/archive/annual-report/template/seminar pages and PDFs (judged from title and URL words) have their fused score halved; they stay searchable. These defaults are implementation choices, not measured optimal parameters.
- Deterministic relevance reasons and exact evidence. Unknown fields remain empty. Freshness uses source content date, else last-modified, with a 365-day threshold; fetch date alone means unknown.
- Atomic generation directories and a last-step `READY` swap. Failed builds preserve the previous ready generation; repeat identical builds verify hashes and reuse assets without encoding. Changed identity metadata can reuse public-source vectors when exact text SHA, model manifest and encoder recipe are unchanged. Explicit rebuilds omit retired/suppressed versions and retired entities, including an empty live corpus. Runtime loads a new generation when the marker changes. Old generation cleanup and live suppression/retention administration remain T12.
- API integration uses the existing `SearchBackend` hook, preserving synthetic fixture mode and 413/503/501 behavior. A legacy empty `READY` marker does not invent a backend. Accepted T12 suppression is preserved around the API response and checked before ranking, including explicit aliases, for direct backend/CLI queries as well. Missing/unavailable local embedding assets retain keyword search; corrupted evidence/vector assets reject loading. No Apertus dependency is imported on the fast path. Requested enrichment is reported unavailable until its integration task supplies it.
- Server timings include keyword, local dense, rank, backend total, and route `request_total` (including first-load work). These are actual request measurements, not target guarantees.

- **Answer policy (T31, `app/search/outcome.py`):** every response carries an `outcome`. `no_evidence` when nothing passes abstention; `too_broad` when the request has at most one topic word and the cards are spread over at least four sources (five examples plus institution / type / rephrase suggestions); `low_confidence` when the best dense similarity is below `BERNMATCH_CONFIDENT_DENSE` (default 0.885) or only keyword matching ran; otherwise `confident`. Topic words exclude quantifiers, request verbs and generic role nouns in EN/DE/FR/IT.

- **Traceable results (T36, `app/search/explain.py`):** each card's `retrieval` adds `channels`, `keyword_rank`, `dense_rank`, `matched_terms` (query words whose stem occurs in the cited evidence), `evidence_language` and `query_variant`, and `reason` is built from them (e.g. 'Found by keyword match on "insulin" (keyword rank 3) and multilingual meaning similarity (similarity rank 1) in stored source text. German request, English evidence.'). Deterministic, from stored text and retrieval signals only; no probabilities.

## Operator commands

Python 3.12; install inside an isolated environment alongside the root requirements:

```bash
python -m pip install -r requirements.lock -r app/search/requirements.txt
# Explicit network operation, operator phase only. Never called by a query:
python -m app.search fetch-model --model small --model-dir /path/to/models/e5-small
# Both corpus and model assets must already exist. No implicit source fetch:
python -m app.search build --corpus-dir /path/to/corpus --model-dir /path/to/models/e5-small --data-dir /path/to/serving
python -m app.search inspect --data-dir /path/to/serving
python -m app.search query --data-dir /path/to/serving --query 'insulin decision support'
BERNMATCH_DATA_DIR=/path/to/serving python -m uvicorn app.main:app --port 8000
```

`fetch-model` verifies pinned upstream revision, byte counts and SHA-256s; failed downloads do not replace a good directory. An existing matching model directory is reused. There is no `from_pretrained` or Hub call during serving. Serving requires the search requirements, model assets and the built generation; it does not require PyTorch, sentence-transformers, crawler parsers, original raw source files or Internet access for query embedding.

`--mode keyword|dense|hybrid` on the query CLI supports controlled ablations. The API reads `BERNMATCH_SEARCH_MODE` (default hybrid), `BERNMATCH_MIN_DENSE` (default .80), and `BERNMATCH_ORT_THREADS` (default 4); set these before starting the server and record them with measurements. Altering defaults after looking at held-out queries is prohibited. Company context/edited needs are not interpreted by this baseline; responses disclose that limitation rather than pretend to enforce unsupported constraints.

A T06 JSONL export can be transferred instead of the whole corpus directory: use `--corpus-jsonl /path/to/corpus.jsonl` instead of `--corpus-dir`. Records are validated with the same shared models, without importing the crawler parsers or fetching sources.

## Model pins and Space handoff

Primary upstream model cards: [intfloat/multilingual-e5-small](https://huggingface.co/intfloat/multilingual-e5-small), [intfloat/multilingual-e5-base](https://huggingface.co/intfloat/multilingual-e5-base). Upstream metadata labels both MIT. Exact revisions, source artifact names and measured download hashes/sizes are in `models.json`. These official ONNX qint8 artifacts are portable graphs; the filename mentions AVX512, but local macOS arm64 CPU execution has been exercised. Linux/Space execution still requires its own verification.

Initial measured model-directory sizes: small **135,929,223 bytes**; base **295,950,560 bytes**. Each initial full-record serving evidence/keyword SQLite database measures **103,968,768 bytes**. A subsequent compact serving projection omits redundant JSON IDs/passage lists (while retaining exact sentence text, SQL identities, page/provenance and canonical operator records); its measured size remains to be recorded. These measurements use the accepted 2,811-document / 148,404-sentence corpus. Dense arrays, manifests, runtime dependencies and image layers are additional; the final verification report must state measured sizes after builds finish. A vector is not required for every individual sentence: passages/profiles (plus long-text windows) are indexed.

Use `python -m app.search package --data-dir /path/to/serving --output /path/to/bernmatch-search.tar.gz` to package one generation with verified hashes and a relative `corpus.sqlite` compatibility link for T12’s read-only evidence route. Extract into a separate query-only data directory, preserving the relative symlink. This does not replace the original operator corpus.

Transfer exactly `$DATA_DIR/READY` and the referenced `$DATA_DIR/indexes/<generation>/` directory, including its `model/` subdirectory. Other model candidates, raw corpus, cached source responses and older generations are not necessary to serve this snapshot. Archive/bundle checksums and actual byte counts must accompany the handoff. Query-only code opens the bundle read-only; `app/main.py` readiness remains its existing marker check, not a deep integrity check.

Dimitry owns Dockerfile/Space integration. The serving image must install `-r app/search/requirements.txt`, copy the prebuilt generation and marker, and set `BERNMATCH_DATA_DIR`. This worker has permission only for the search module, index storage, tests, the search API hook and one CI install line. No Space image upload, remote job, billing or container-file change has been performed by this worker. Existing Space observation on 18 October: health 200, readiness 503 (`INDEX_NOT_READY`); that is not a deployed-search result.

## T08 integration boundary

V1 uses uncertain T06 anchors and evidence-only cards. The `--knowledge-dir` operator input reads the actual T08 `entities.jsonl` and `claims.jsonl` handoff. `--knowledge-file` additionally accepts an object with `entities` and `claims` arrays using the same shared models. Field and inverse-relationship mapping uses T08’s `card_fields()` helper. Explicit aliases replace provisional anchors; references and current-version sentence IDs are validated. A real full-corpus rules-only T08 run (no T07 extraction file, no judge/API call) produced 2,115 entities, 712 merges and zero claims/fields. This verifies resolution-data integration; claim-bearing real handoff verification is still pending.

Unsupported/qualified or unavailable-evidence claims are withheld and recorded in the build manifest, preserving searchable passages. Only declared, `supported` claims with available version-bound evidence enter fields/profile text; relationship values come from the referenced entity's stored name. Qualified claims are withheld until their qualifications can be shown by the shared UI. Official contacts are withheld unless entity status is current. Former entities are never presented as current contacts. An exact citation alone cannot upgrade `pending`/`unsupported` claims. Upstream T08 semantic-validation acceptance remains required; fixture tests prove interface handling only.

## Verification status and limits

Deterministic checks currently cover duplicate-page bias, relevance-aware diversity, multilingual analysis/compound handling, type and result limits, exact evidence, missing model fallback, no external network/LLM fast path, restart reuse, corrupt assets, failed rebuild atomicity, retiring the entire corpus, shared claim/alias handling, fixture/API error behavior long-text tokenizer windows/masked pooling, and extraction of the query-only archive with exact evidence resolution through the existing API. Full local suite after main integration: **201 passed, 1 skipped**, including **21 search cases**, Python 3.12.14; one upstream Starlette/AnyIO warning. The skip is opt-in live inference. `pip check` found no broken requirements.

Still pending: completion of real full-corpus model builds; real small/base development comparison; measured latency/CPU memory and final bundle size; real DE→EN and EN→DE retrieval/evidence checks; absence/near-match observations; Linux/Space deployment checks; real T08 payload integration. `tests/search/development_queries.json` contains only the five existing T14 development intent groups with agent-authored language variants requiring human review; none is a held-out evaluation query. T14 gold is currently unfrozen/unreviewed: model selection/tuning must wait for the owner to resolve the freeze prerequisite. No quality benchmark, latency target, legal-compliance claim or full air-gapped Apertus demonstration is reported as achieved.

## Live development smoke test (2026-10-18, before abstention/demotion)

Space `kaktamsdengami/bern-match`, full T06 final corpus (2,811 pages, 21,256 entries), E5-small, evidence-only cards, `python -m evaluation run --split development` (9 queries, gold 0.1-seed, not frozen). Recall@10 0.56 (lay 1.0 n=2, professional 0.67 n=3, cross-lingual 0.25 n=4); server `request_total` p50 82 ms / p95 103 ms, client p50 255 ms / p95 436 ms over the internet. Best dense similarity per development query 0.876–0.909; three ad hoc off-topic probes (not gold queries) 0.825–0.853, each returning 10 cards. The 0.865 abstention threshold sits in that gap: chosen on development queries and probes only, n is tiny, and it must be re-checked on the frozen evaluation split. 20 of 89 returned cards were listing/report pages. No evaluation-split query was used.

## T31 threshold check on the rebuilt Space (2026-10-18, 70B knowledge, development split + probes only)

Live `/api/v1/search`, 17 development gold queries plus 10 ad hoc probes (4 nonsense, 6 broad; not gold queries). With `confident 0.885`, broad = at most one topic word and cards from at least four sources (dense-spread check off, `BERNMATCH_BROAD_MAX_GAP=1.0`): broad probes 6/6 `too_broad`; nonsense 3/4 `no_evidence`, 1/4 `low_confidence` ("zeige mir alle Affen"); development hits 6 `confident`, 2 `low_confidence`; development misses 1 `confident`, 4 `low_confidence`, 4 `no_evidence`. The dense-spread gap did not separate broad from specific requests (0.029–0.078 vs 0.015–0.093), so it is off by default.

**Open problem:** with the deployed abstention threshold 0.865, 4 of 17 development queries return no card at all (I05-ru, I13-fr, I14-en, I14-de; I14 requests type `infrastructure`). Abstention is too aggressive for typed and non-EN/DE queries. Lowering it needs the best-dense values of abstained queries, which the API does not expose; to be measured on the downloaded index bundle, development split only. n is tiny throughout; re-check on the frozen evaluation split.

## Abstention threshold on the real index bundle (2026-10-18, development split + probes only)

Bundle `bundle.tar.gz` (SHA-256 `9a0e0951…daed3cd`, 2,543 entities, 22,179 vectors, 70B knowledge), queried locally with the shipped code and abstention off, best dense similarity among allowed entities per query. 17 development queries, 6 nonsense probes (not gold queries):

- Development hits: I14-de **0.831**, I14-en 0.855, I13-fr 0.866, I05-ru 0.868, I15-it 0.875, then 0.879–0.909. Development misses: 0.869–0.895.
- Nonsense probes: 0.835 (pizza), 0.836 (monkeys), 0.840 (flights), 0.856 (gearbox), 0.869 ("zeige mir alle Affen"), 0.870 (Bitcoin).
- The distributions **overlap**, so no dense threshold separates nonsense from typed or cross-lingual requests. Keyword overlap with the cited evidence does not separate them either: cross-lingual development hits (I03-de, I05-ru, I14-de) match as few topic words as the probes.
- At 0.865, 4 development hits return no card. At 0.83, all 12 development hits are kept; the nonsense probes then fall below the confident threshold (0.885) and are shown as **low confidence** with a coverage note, not refused.
- Scores differ by a few thousandths between the x86 Space and this arm64 run (int8 ONNX); thresholds near a query's score are fragile.

Decision: 0.83 favours recall; the honest label is `low_confidence`. Real refusal of out-of-scope requests needs a semantic check (Apertus scope classification in T18, asynchronous); deterministic signals alone cannot do it at this corpus size. n is tiny; re-check on the frozen evaluation split.

## Weighted fusion (2026-10-18, development split only, real index bundle)

Ruihan's T20 development run (#94) showed hybrid (0.59) below dense alone (0.71): BM25 pulled German/English listing and news pages above the cross-lingual answer. RRF now weights the BM25 channel by `BERNMATCH_KEYWORD_WEIGHT` (dense = 1). Development split, gold 0.3, 17 queries, same bundle as the Space (weight 1.0 reproduces the live Space's 0.71):

| BM25 weight | Recall@10 | cross-lingual (n=11) | misses |
| --- | --- | --- | --- |
| 1.00 | 0.706 | 0.64 | I01-de, I01-fr, I03-en, I03-de, I03-it |
| 0.50 / 0.75 | 0.765 | 0.73 | I01-de, I03-en, I03-de, I03-it |
| **0.25** / 0.00 | **0.824** | **0.82** | I03-en, I03-de, I03-it |

Default 0.25: the same development result as 0, while keyword-only hits (exact names, codes such as SPN-005) still enter the ranking. n is small and the plateau is tuned on development data; the evaluation split must confirm it. Remaining development misses are all intent I03 (AI insulin decision support).
