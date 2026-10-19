# Report sections: AI, evaluation, cost (Ruihan, T22)

Draft for the ≤ 6-page technical report (Maxim owns structure and final layout). Target length: about 2 pages. Every number traces to `docs/MEASUREMENTS.md`, `docs/costs.md` or a T20 run record under `evaluation/results/full/`.

## How Apertus is used, and where it is not

Bern Match keeps **search free of LLM calls**. A query runs BM25 plus local multilingual embeddings over a stored corpus and returns cards in milliseconds, so the analyst never waits for a model. Apertus does only the work that needs language understanding, either offline or in the background:

| Step | When | Model | What Apertus does | What code guarantees |
| --- | --- | --- | --- | --- |
| Structured extraction (T07) | offline, once per page version | 70B (D10) | Reads a page as numbered sentences and returns people, units, projects, infrastructure, roles, expertise and relations, citing sentence numbers | Numbers map to stored sentence IDs; names must appear in the cited sentence; roles must be verbatim; contacts are read by regex, never from model text; a group's expertise is never transferred to a member; instruction-like page text is withheld |
| Support check (T08) | offline | rules + 70B judge | Decides whether the cited sentences actually state a claim, including reversed relations | Only supported claims reach cards; if the judge fails, claims stay pending and hidden |
| Interpretation (T18) | after first cards, over SSE | 70B | Turns a company description into editable needs and EN/DE/FR/IT search terms | Analyst needs kept first and unchanged; suggested constraints dropped unless stated; expansions tied to a source term |
| Assessment (T19) | after first cards, over SSE | 8B | Labels candidates direct / related / insufficient, with per-need coverage and questions for the analyst | Evidence must be the candidate's own sentences; category must agree with coverage; explanations with facts not in the evidence are replaced |

All structured output uses the gateway's JSON-schema constrained decoding, still validated with Pydantic (fallback mode reported as weaker). Building on the shared Keera gateway taught us concrete schema rules, because the decoder produced endless whitespace with integer lists, mis-sorted list keys and nested object lists. We moved to flat schemas with short string labels.

## Model choice was measured, not assumed

- **Extraction, 11 real pages, hand-checked:** 70B ≈ 97% claim precision and 24 persons found, vs 8B ≈ 48% and 0 persons. 70B is ~7× slower, but runs offline and cached, so we chose it (D10).
- **Assessment of 8 candidates:** 8B finishes in about 6 s (inside the 15 s target), 70B in 18 s, with similar decisions on clear cases. We kept 8B.

## Evaluation

**Protocol (T14):** 36 gold queries in intent groups (professional, lay, synonym, misleading, partial, absent; EN/DE/FR/IT/RU). Expected entities are keyed by source URL and written from corpus evidence by the search owner. They were reviewed against the corpus and frozen (gold 0.3, hash `340c4b0a…`) before any evaluation-split run.

**Component comparison (T20):** the same frozen queries under five configurations, run on the deployed index bundle (2,543 entities, 22,179 vectors; abstention threshold 0.83).

| Configuration (frozen evaluation split, 17 scored queries) | Recall@10 | Median latency | Apertus tokens/query |
| --- | --- | --- | --- |
| BM25 only | 0.29 | 53 ms | 0 |
| Dense only | 0.59 | 24 ms | 0 |
| Hybrid, in-process on the bundle | 0.65 | 56 ms | 0 |
| **Hybrid + Apertus expansion (70B)** | **0.82** | 4.9 s (background) | 700 |
| Hybrid + expansion with 8B instead | 0.65 | 1.3 s (background) | 580 |
| + Apertus assessment (8B) | same ranking; 86% of expected answers labelled direct/related (n = 14) | 18.6 s (background) | 2,880 |

*Note on the hybrid row:* the same frozen evaluation split re-scored over HTTP against the live service gives **0.76** (#16), while the in-process run on the bundle gives **0.65** at both BM25 weights tested (1.0 and 0.25). The gap is not the BM25 weight; it lies between the in-process path and the live service (API wrappers, the x86 ONNX build or configuration) and is being investigated (G2 #147). Neither number should be read as "the shipped" result without this note. The expansion gain (+0.17 to +0.18) is measured within one consistent setup.

**Apertus query expansion raised Recall@10 on the frozen evaluation split from 0.65 to 0.82.** On the development split it raised recall from 0.59 to 0.76 on an earlier local index, with all of the gain coming from German and French queries that the fast path missed; Apertus added the English research terms used on the pages, e.g. "cancer therapy resistance". The **model choice was measured**: 8B expansion was four times faster but added nothing over plain hybrid on the evaluation split, so expansion uses 70B. Assessment does not reorder results, so it gets no recall credit.

**Abstention trade-off.** The two "no answer" queries (quantum satellite communication, antifouling ship coatings) test that the system does not invent matches. With the abstention threshold at 0.865, both returned no cards (correct abstention 1.0) but hybrid recall was only 0.41; at 0.83, recall rises to 0.65 but both return low-confidence cards (correct abstention 0.0 under the metric, which counts any card as a failure). Expansion never overrides the original query's abstention or too-broad outcome, so at 0.865 expansion kept abstention at 1.0 while raising recall from 0.41 to 0.59. This trade-off is disclosed rather than tuned on the evaluation queries.

**Live latency on the deployed Space** (10 fictional companies): first cards median 0.5 s; 70B interpretation median 4.9 s; full enrichment median 13.2 s, meeting the 15 s target at the median, but p95 34 s because 2 of 10 assessment calls timed out on the shared gateway. Enrichment runs after the first cards, so the analyst is never blocked.

**Grounding at corpus scale:** of 5,130 extracted claims, 4,314 passed the support checks and 816 were rejected (469 by code rules, 347 by the judge, including 3 reversed relations). Every surfaced fact links to an exact stored sentence and URL.

## Cost and scale

- **One-off processing of the whole 41-domain corpus** (2,811 pages): ≈ 1.05M input + 0.39M output tokens, ≈ 30 min extraction plus 2.3 min support checking, at concurrency 4. Re-runs only touch changed pages.
- **A search costs 0 LLM tokens.** An enriched case costs ≈ 1.7k input + 1.2k output tokens.
- **300 cases per year are negligible in tokens.** The cost is dominated by hosting, which is a sovereignty choice: Swiss VM vs. demo host. See `docs/costs.md`; Keera token prices are not public to us, so we report tokens and formulas.

## Limitations

Small samples for the 8B/70B comparisons; single-rater hand checks; latency measured from one location on a shared gateway (70B ranged 1.5–52 s); 3 of 799 long pages couldn't be extracted; FR/IT corpus content is sparse; the gold set was written by a team member, with no partner review yet.
