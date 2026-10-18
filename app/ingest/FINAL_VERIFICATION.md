# T06 final-profile verification — 18 October 2026

Measured against integrated revision `372b59c`, parser `t06-v4`, Python 3.12.14 on macOS arm64. This report adds verification evidence; it does not change application behavior. GitHub issue #6 remains subject to dispatcher acceptance.

## Scope and measured result

All **41 included sources** from the 42-row supplied inventory completed a bounded initial crawl and produced documents. The existing `geo2.unibe.ch` placeholder exclusion remains visible. The workbook Notes claim of 71 domains remains an input discrepancy. No additional rows were invented.

The unmodified `final` profile allowed 200 page attempts/depth 4 for 14 focus sources, 50/depth 2 for 27 other sources: a combined ceiling of 4,150 attempts. Eight distinct source hosts ran concurrently, each with its configured 0.5 requests/second limit. No source exceeded its page budget; 25 reached it. No unhandled source exception occurred.

- Wall time: **1273.258 s (21.22 min).
- **3,563 page attempts**, 3,419 fetched responses, 2,826 successful parses, 9 cached alias reuses, 593 unsupported responses, 135 other unsuccessful attempts. The latter includes scope/robots exclusions as well as HTTP/network/size failures.
- **2,811 unique active documents/versions**, 19,141 passages, **148,404 sentences**, 2,827 uncertain entity anchors; 366 text-PDF documents with sentences on 3,080 pages.
- **3,643 HTTP requests** including robots, maps, redirects and retries; 4 retries.
- Active-document language detection: EN 1,710; DE 1,058; FR 22; unknown 21; IT 0. These labels are automated, not a reviewed language benchmark.
- 1,971 successful page visits had no focus-keyword match. Routing tags do not establish expertise.
- 8,058 queue entries remained across the source snapshots. This is not a unique URL count and does not imply complete site coverage.

Page attempts, successful parses, visits, and unique documents are different denominators. Redirect aliases and identical versions explain the differences; do not sum them as independent research records. Safe machine-readable aggregates are in [`tests/ingest/evidence/t06_final.json`](../../tests/ingest/evidence/t06_final.json).

## Per-source coverage

| Source | Attempted / ceiling | Parsed | Unique documents | Unsupported | Other unsuccessful |
| --- | ---: | ---: | ---: | ---: | ---: |
| artorg | 200 / 200 | 166 | 166 | 27 | 7 |
| dcb | 200 / 200 | 85 | 85 | 114 | 1 |
| unibe | 50 / 50 | 45 | 45 | 4 | 1 |
| unibe-aiub | 50 / 50 | 40 | 40 | 7 | 3 |
| unibe-bcpm | 200 / 200 | 71 | 71 | 95 | 34 |
| unibe-biology | 38 / 50 | 36 | 35 | 2 | 0 |
| unibe-cde | 50 / 50 | 50 | 50 | 0 | 0 |
| unibe-csh | 50 / 50 | 49 | 49 | 0 | 1 |
| unibe-dbmr | 200 / 200 | 176 | 176 | 16 | 8 |
| unibe-dcbp | 50 / 50 | 46 | 46 | 4 | 0 |
| unibe-geo | 50 / 50 | 45 | 45 | 5 | 0 |
| unibe-iap | 34 / 50 | 30 | 30 | 4 | 0 |
| unibe-ibmm | 137 / 200 | 84 | 84 | 46 | 1 |
| unibe-iee | 50 / 50 | 36 | 36 | 12 | 2 |
| unibe-ifik | 200 / 200 | 158 | 156 | 38 | 4 |
| unibe-ikim | 135 / 200 | 106 | 106 | 8 | 21 |
| unibe-img | 36 / 50 | 33 | 33 | 2 | 1 |
| unibe-iml | 50 / 50 | 42 | 42 | 0 | 8 |
| unibe-inf | 45 / 50 | 36 | 36 | 9 | 0 |
| unibe-ips | 40 / 50 | 39 | 39 | 1 | 0 |
| unibe-irm | 50 / 50 | 46 | 46 | 3 | 1 |
| unibe-ispm | 200 / 200 | 186 | 185 | 10 | 2 |
| unibe-ita-vetsuisse | 30 / 50 | 29 | 29 | 1 | 0 |
| unibe-itp | 33 / 50 | 29 | 29 | 4 | 0 |
| unibe-izb | 32 / 50 | 27 | 27 | 3 | 2 |
| unibe-math | 41 / 50 | 35 | 34 | 6 | 0 |
| unibe-mediarelations | 50 / 50 | 34 | 34 | 15 | 1 |
| unibe-medizin | 200 / 200 | 175 | 172 | 17 | 8 |
| unibe-mic | 200 / 200 | 179 | 177 | 7 | 13 |
| unibe-neuroscience | 200 / 200 | 189 | 189 | 7 | 4 |
| unibe-ngs | 23 / 200 | 10 | 10 | 13 | 0 |
| unibe-oeschger | 50 / 50 | 46 | 46 | 3 | 1 |
| unibe-philnat | 50 / 50 | 47 | 47 | 1 | 2 |
| unibe-phinst | 31 / 50 | 29 | 29 | 2 | 0 |
| unibe-physik | 50 / 50 | 48 | 48 | 2 | 0 |
| unibe-pki | 200 / 200 | 127 | 127 | 69 | 4 |
| unibe-psy | 31 / 50 | 30 | 30 | 1 | 0 |
| unibe-soz | 50 / 50 | 41 | 41 | 8 | 1 |
| unibe-strada | 28 / 50 | 28 | 27 | 0 | 0 |
| unibe-tki | 99 / 200 | 70 | 66 | 26 | 3 |
| unibe-vetsuisse | 50 / 50 | 48 | 48 | 1 | 1 |

## Unsuccessful/unsupported reasons

| Reason | Count |
| --- | ---: |
| `http_401` | 1 |
| `http_404` | 91 |
| `http_500` | 2 |
| `invalid_pdf` | 1 |
| `no_usable_text` | 439 |
| `outside_scope` | 19 |
| `redirect_limit` | 1 |
| `response_too_large` | 6 |
| `robots_disallowed` | 15 |
| `scanned_or_empty_pdf` | 12 |
| `unsupported_media_type` | 141 |

These are observed outcomes, not repaired source content. `no_usable_text` means fewer than 40 characters after current cleaning, not proof the original page is empty or JavaScript-only. For example BCPM yielded 71 unique documents from 200 attempts, with 95 low-text responses and 34 HTTP 404 responses. Unsupported/scanned PDFs were reported without OCR. Access and robots restrictions were preserved.

## Exact evidence and restart checks

A fresh process disabled socket creation, loaded every active record, and checked:

- All 148,404 sentence lookups by the original version + sentence ID returned equal stored sentence objects.
- Every sentence is a substring of the corresponding cached cleaned text; all 2,811 document text hashes match their versions.
- Identifier recipes, sentence ordering, passage membership, page-number relationships, and passage/entity references hold for all active documents.
- All 166 ARTORG documents retain both `artorg` and `unibe` source labels.
- Every entity remains uncertain with no claims; a deliberately cross-version citation lookup was rejected.
- SQLite integrity check returned `ok`. No search `READY` marker was created.

A separate fresh-process export produced **2,811 records, 60,518,422 bytes**. Its version/sentence metadata fingerprint exactly matched the stored-corpus check while sockets were disabled. Export SHA-256: `e3d8a1702624f50dc5c2a345620fdc945a2ff7dd86aef2d27f51995ca75d1c58`. Evidence fingerprint: `d90a53dbeb3e8f05d958be0c330a2cc446bbc1cb12eff68dae9332cf45685272`.

A cache-only replay of the original final-profile configuration reused **2,843 page visits**, made **zero actual HTTP requests**, preserved all 2,811 versions, and **blocked 880 uncached URL attempts**. This replay intentionally forbade the network. A normal repeated crawl may fetch failed or newly discovered URLs within its bounds; the final snapshot is not the whole website. Opening/reading the persisted corpus is independent of this operator crawl. This is a storage/replay check, not an air-gapped application-search or Apertus demonstration.

## Commands, tests and handoff

Actual one-off verification commands, run from the repository root:

```bash
/private/tmp/bernmatch-ingest-venv/bin/python -u /private/tmp/bernmatch-t06-verification/run.py
/private/tmp/bernmatch-ingest-venv/bin/python /private/tmp/bernmatch-t06-verification/verify.py
/private/tmp/bernmatch-ingest-venv/bin/python /private/tmp/bernmatch-t06-verification/replay.py
/private/tmp/bernmatch-ingest-venv/bin/python -m app.ingest export --data-dir /private/tmp/bernmatch-t06-verification/corpus > /private/tmp/bernmatch-t06-verification/corpus.jsonl
PYTHONDONTWRITEBYTECODE=1 /private/tmp/bernmatch-ingest-venv/bin/python -m pytest -q -p no:cacheprovider
/private/tmp/bernmatch-ingest-venv/bin/python -m pip check
```

The temporary operator driver calls the existing `crawl()` once per configured source with a separate `Fetcher`, one shared `CorpusStore`, eight workers, no refresh and no page override. It writes per-source snapshots and catches/reports source exceptions. The source host sets were checked disjoint before starting. The verifier uses `get_sentence()` for every sentence, `restore_parsed()` for cached text and the shared identifier/hash helpers. The cache-only fetcher rejects missing-cache requests instead of using HTTP. An additional fresh-process JSONL check compared the complete document/version/sentence metadata fingerprint. These one-off scripts and detailed raw/provenance logs are local verification artifacts, not repository runtime code.

For a sequential operator reproduction with the same source/profile budgets, use the supported CLI (wall time/concurrency will differ):

```bash
python -m app.ingest crawl --profile final --data-dir /path/to/local-corpus
python -m app.ingest export --data-dir /path/to/local-corpus > /path/to/local-corpus.jsonl
```

The full test suite on the integrated revision returned **87 passed, 1 skipped**, including all **23 ingestion cases**; the skip is the opt-in live inference test. One upstream Starlette/AnyIO deprecation warning occurred. `pip check` found no broken requirements. CI now installs the ingestion requirements through PR #51.

Local handoff: `/private/tmp/bernmatch-t06-verification/corpus` (SQLite, raw hashes, fetch provenance and snapshots) and `/private/tmp/bernmatch-t06-verification/corpus.jsonl` (export). Raw source/contact text, databases, exports, model files and detailed logs are outside Git. Temporary local paths are not a production durability or hosting-transfer promise.

T09 consumes `CorpusStore.active_records()` and exact `get_sentence(version_id, sentence_id)`. No vector/BM25 index, LLM extraction, supported claims, semantic-support score, retrieval quality/latency benchmark, suppression/retention execution or air-gapped application-query readiness is demonstrated here. Those remain their declared tasks; no paid inference or confidential company input was used.
