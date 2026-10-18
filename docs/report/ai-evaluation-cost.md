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

**Protocol (T14):** 36 gold queries in intent groups (professional, lay, synonym, misleading, partial, absent; EN/DE/FR/IT/RU). Expected entities are keyed by source URL and written from corpus evidence by the search owner. They were reviewed against the corpus and frozen (gold 0.2, hash `693d4695…`) before any evaluation-split run.

**Component comparison (T20):** the same frozen queries under five configurations:

| Configuration | Recall@10 | Correct abstention | Median latency | Tokens/query |
| --- | --- | --- | --- | --- |
| BM25 only | T20_KEYWORD | | | 0 |
| Dense only | T20_DENSE | | | 0 |
| Hybrid (shipped fast path) | T20_HYBRID | | | 0 |
| Hybrid + Apertus expansion | T20_EXPANSION | | | |
| + Apertus assessment (category quality) | same ranking | | | |

T20_INTERPRETATION

**Grounding at corpus scale:** of 5,130 extracted claims, 4,314 passed the support checks and 816 were rejected (469 by code rules, 347 by the judge, including 3 reversed relations). Every surfaced fact links to an exact stored sentence and URL.

## Cost and scale

- **One-off processing of the whole 41-domain corpus** (2,811 pages): ≈ 1.05M input + 0.39M output tokens, ≈ 30 min extraction plus 2.3 min support checking, at concurrency 4. Re-runs only touch changed pages.
- **A search costs 0 LLM tokens.** An enriched case costs ≈ 1.7k input + 1.2k output tokens.
- **300 cases per year are negligible in tokens.** The cost is dominated by hosting, which is a sovereignty choice: Swiss VM vs. demo host. See `docs/costs.md`; Keera token prices are not public to us, so we report tokens and formulas.

## Limitations

Small samples for the 8B/70B comparisons; single-rater hand checks; latency measured from one location on a shared gateway (70B ranged 1.5–52 s); 3 of 799 long pages couldn't be extracted; FR/IT corpus content is sparse; the gold set was written by a team member, with no partner review yet.
