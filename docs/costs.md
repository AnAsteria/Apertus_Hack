# Cost worksheet (T16)

Refs #16. Owner: workstream B (Ruihan). **Measured** quantities come from `docs/MEASUREMENTS.md`. **Prices** are marked with their source; the Keera token price is unknown to us, so it stays a variable `P_in` / `P_out` (CHF per 1M tokens). Nothing here is a quote.

## 1. Measured workload

| Item | Measured |
| --- | --- |
| One-off corpus processing (2,811 pages) | T07 extraction 70B: 0.915M in + 0.359M out tokens. T08 judge 70B: 0.134M in + 0.028M out tokens. **Total ≈ 1.05M in + 0.39M out** |
| Incremental refresh | Only new or changed pages are re-extracted (cache key = content hash + model + schema + prompt), so a daily refresh costs proportionally to changed pages |
| Per search, fast path | **0 LLM tokens** (BM25 + local embeddings) |
| Per search, with interpretation (T18, 70B) | ≈ 0.4k in + 0.2k out |
| Per search, with assessment of 8 candidates (T19, 8B) | ≈ 1.3k in + 1.0k out |
| Per analyst case (assumption: 3 searches, 1 enriched) | ≈ 1.7k in + 1.2k out tokens |

## 2. Formulas

```
corpus_cost   = 1.05 × P_in(70B) + 0.39 × P_out(70B)                          [CHF, one-off]
case_cost     = 0.0004 × P_in(70B) + 0.0002 × P_out(70B)
              + 0.0013 × P_in(8B)  + 0.0010 × P_out(8B)                        [CHF per enriched case]
yearly_tokens = corpus_cost + refreshes + 300 cases × case_cost
hosting       = hours × hourly_rate
```

## 3. Example with a stated price assumption

To show the order of magnitude only, assume **CHF 1 per 1M input tokens and CHF 3 per 1M output tokens for 70B, and a third of that for 8B**. These are placeholder numbers, not Keera prices.

| Item | Tokens | Cost at the placeholder price |
| --- | --- | --- |
| Full corpus processing (one-off) | 1.05M in + 0.39M out | ≈ CHF 2.2 |
| 300 enriched cases per year | 0.51M in + 0.36M out | ≈ CHF 0.9 |
| 12 full re-processings per year (upper bound; incremental is far less) | 12.6M in + 4.7M out | ≈ CHF 27 |

Even with a full monthly re-processing, LLM tokens are a few tens of CHF per year at these assumed prices. **Hosting dominates**, not inference.

## 4. Hosting

| Option | Price source | Monthly (730 h) | Notes |
| --- | --- | --- | --- |
| Hugging Face Space, CPU Upgrade (current demo, D9) | Hugging Face docs, $0.03/h | ≈ USD 22 | Not Swiss-hosted; demo only |
| Swiss GPU VM, RTX 4090, for local Apertus 8B (ARCHITECTURE §7 reference) | Pipeline reference, CHF 0.40/h, unverified | ≈ CHF 292 + electricity | Needed only for fully local/offline inference |
| Swiss CPU VM for search + UI, LLM via Keera | Not priced yet | — | Search runs on CPU (index build and queries measured on a laptop CPU) |

## 5. What the numbers say

- **Offline processing is cheap and one-off.** About 1.4M tokens for the whole 41-domain corpus, cached and re-run only for changed pages.
- **A typical search costs nothing in LLM tokens.** Apertus is used only where language understanding adds value (extraction, support checking, interpretation, assessment), not for ranking.
- **300 cases/year is a tiny token load.** The cost driver is the hosting choice, which is a sovereignty decision (Swiss VM vs. demo host), not a scaling problem.

## Open items

- Keera price per token (organiser): replaces `P_in` / `P_out`.
- Measured CPU/RAM of the deployed Space under concurrent load: to be added once T11 serves the full index.
- Electricity and idle capacity for a self-hosted GPU option are excluded here.
