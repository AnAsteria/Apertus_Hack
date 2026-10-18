# Report sections: data, evidence and search (Maxim, T22)

Draft for the technical report; Maxim owns the final layout. Every number below comes from a stored run, log or issue record; sample sizes are given. Ruihan's sections (`ai-evaluation-cost.md`) cover Apertus use, the T20 comparison and cost.

## Data: one crawl, stored evidence, no per-query fetching

Sources come from the organisers' inventory (42 rows: 41 public `unibe.ch` subdomains plus `dcberne.com`; ARTORG is one source with two labels). A one-time bounded crawl (`final` profile, robots-aware, per-host rate limits, no OCR or browser rendering) stored **2,811 pages, 148,404 sentences, 19,141 passages** (T06, #6). Unsupported or failed responses are reported, not hidden (593 unsupported, 135 other failures). Queries never fetch a source: they search this stored snapshot. New sources go through the same YAML and pipeline.

Each page version is immutable (`ver_` = hash of document, cleaned-text hash and parser version); sentences are numbered inside that version. A citation is a (version, sentence) pair, and the quote shown to the user is copied by code from storage, never written by a model. A removed or suppressed page returns `410 EVIDENCE_REMOVED` instead of being re-bound to new text (exercised on the real index, #12).

Apertus 70B extracted facts from the 799 routed person/unit/project/service/infrastructure pages; entity resolution and support checks kept **4,289 supported claims on 2,543 indexed entities (674 with card fields)** (T07/T08, #7, #8). Cards show only supported fields; a field always cites its sentence.

## Search: fast, multilingual, explainable

The fast path uses **no LLM**. BM25 (SQLite FTS5, Snowball stemming for EN/DE/FR/IT, German compound grams) and multilingual dense retrieval (`multilingual-e5-small`, int8 ONNX on CPU) each take the **maximum score per entity**, so a prolific page cannot add votes. They are then fused by reciprocal-rank fusion, with BM25 weighted 0.25 against dense; relevance-aware MMR diversifies the results, and at most ten distinct entities are returned. Listing, news and report pages are ranked lower but stay searchable.

Every response carries an **outcome**: `confident`, `low_confidence` (with a visible label and narrowing suggestions), `too_broad` (five examples plus institution/type suggestions) or `no_evidence` (no card, with the corpus coverage stated). Every card explains itself from stored data: which channel found it and at what rank, the matched query words, and the language path ("German request, English evidence") (T31, T36).

When Apertus is available, its validated query expansions drive a second retrieval pass in the background (T30). The first cards are never delayed, and **expansion never overrides an abstention or a too-broad outcome** of the original query. That guard was added after the cross-check showed expansion pulling near-miss pages into the absent queries (#16).

## Measured results

Frozen gold 0.3 (36 queries; 17 development, 19 evaluation, grouped by intent; EN/DE/FR/IT/RU). Thresholds were chosen on the development split and on non-gold probes only.

| Evaluation split, live Space (HTTP, n = 17 scored) | Baseline (before T31/T30/fusion) | Current |
|---|---|---|
| Recall@10 | 0.47 | **0.76** |
| cross-lingual (n = 9) | 0.33 | 0.67 |
| misleading near-match avoided (n = 1) | 0.0 | 1.0 |
| correct abstention, zero cards (n = 2) | 1.0 | 0.0 (both labelled *low confidence*) |
| queries with no card | 7 of 19 | 1 of 19 |
| client latency median / p95 (n = 19) | 191 / 506 ms | 229 / 448 ms |

**Why two numbers exist for the same configuration (G2, #147).** The live HTTP re-score on the Space (x86) gives 0.76. An in-process run on an arm64 Mac with the same bundle and code gives 0.65, at both BM25 weights 1.0 and 0.25, and that is also the T20 "hybrid" row. Only two queries differ: I11-ru and I18-fr are hits on the Space and misses locally. In both, the expected entity sits at the edge of the top ten, and the int8 ONNX embedding scores differ by a few thousandths between the two CPU types. Both numbers are measured. **The shipped service is the 0.76 one**; the in-process 0.65 is the comparable baseline for the T20 configurations, which ran on the same machine. Edge-of-list results this sensitive are another reason not to over-read n = 17.

By query language (current, non-absent): EN 0.88 (n = 8), DE 0.40 (n = 5), FR 1.00 (n = 2), IT 1.00 (n = 1), RU 1.00 (n = 1). The FR/IT/RU samples are far too small for a language claim (T27, #39). Server-side search time on the development split is median 126 ms, p95 184 ms. With Apertus expansion, evaluation Recall@10 reaches 0.82 in Ruihan's in-process run (`ai-evaluation-cost.md`).

**Grounding (T37):** an automatic check found **0 problems** across 674 entities with fields, 1,523 field values and 1,695 claim sentences in the index, and across 350 served cards with 2,754 quotes from the development and evaluation runs. Every quote is byte-identical to the stored sentence of its cited version. This shows citation integrity only; whether a sentence semantically supports a claim needs the human-rated sample.

**Exposure across institutions (D3, #136).** Across all 350 cards served in the development and evaluation runs, 34 of 41 sources appear. The top three hosts get 40% of the cards: medizin.unibe.ch 15.1% (6.1% of pages), neuroscience.unibe.ch 12.9% (6.7%), dcberne.com 11.7% (3.0%). DBMR (0.41× its page share) and ISPM (0.48×) are under-exposed. These shares follow the gold topics, which are diabetes, oncology, neurology and medtech by design, so they are **not** a fairness verdict. The system deliberately has no equal-exposure target, and relevance comes first. What the numbers show is that no single institution dominates and that per-entity max aggregation keeps page-rich hosts such as DBMR or ISPM from flooding results.

## Limitations and honest gaps

- **Abstention versus recall.** No dense-similarity threshold separates nonsense from valid typed or cross-lingual requests (development hits 0.831–0.909, nonsense probes 0.835–0.870, `app/search/README.md`). At 0.83 we keep recall; nonsense is labelled low confidence, not refused. A semantic scope check in the Apertus interpretation is planned (T39).
- **Small samples.** 17 scored evaluation queries; one person query; one misleading query. One evaluation intent (I17) was viewed before the re-score and was not used for tuning (`docs/evaluation-protocol.md`).
- **Coverage.** The corpus is a bounded snapshot of public pages; absence means "not found in the indexed corpus", never absence at the University.
- **Offline.** The search fast path runs with every outbound socket refused (0 attempts on the real index). An air-gapped run with local Apertus 8B was **not** demonstrated (`docs/offline.md`, D13).
- **Partner review** of expected matches did not take place (T21).
