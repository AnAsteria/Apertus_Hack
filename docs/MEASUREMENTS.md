# Measurements (T16)

Refs #16. Owner: workstream B (Ruihan). Every number here was **observed**; nothing is copied from the illustrative model in ARCHITECTURE §7. Sample sizes are small unless stated, so treat them as indicative. Fictional prompts were used for probes; the corpus runs used the shared public corpus.

## Test environment

| Item | Value |
| --- | --- |
| Inference | Organiser CSCS/Keera gateway `gateway.keera.ch/api/v1`, models `apertus-v1-5-8b` and `apertus-v1-5-70b`. Shared endpoint, so latency varies with other teams' load |
| Client / indexing machine | Apple M3 MacBook Air, 8 cores, 8 GB RAM, macOS 14.6, Python 3.12 |
| Concurrency | `APERTUS_MAX_CONCURRENCY=4` unless stated |
| Corpus | Shared release `corpus.jsonl` (sha256 `e3d8a170…5d1c58`): 2,811 pages, 148,404 sentences, 41 inventory domains |
| Embeddings | `intfloat/multilingual-e5-small` ONNX int8 (pinned in `app/search/models.json`), CPU |
| Dates | 2026-10-18, 12:00–18:50 UTC |

## 1. Endpoint probes (T03/T05, fictional prompts)

| Measure | 8B | 70B |
| --- | --- | --- |
| Time to first token, streamed (n = 2) | 0.06–0.08 s | 0.10–0.26 s |
| Total, ~50–70 output tokens (n = 2) | 0.38–0.68 s | 1.55–1.59 s |
| Cold start (first call of the session, n = 1) | — | 49 s |
| 6 parallel short calls | wall 0.78 s, no 429 | — |
| Strict `json_schema` under an adversarial prompt | 15/15 valid | 14/15 valid |

Time to first token is the best available proxy for prefill. The gateway exposes no separate prefill/generation timings.

## 2. Offline: T07 extraction on the full corpus (70B, D10)

| Measure | Value |
| --- | --- |
| Pages routed / model calls (windows ≤ 80 sentences) | 799 / 861 windows, 832 successful calls |
| Outcome | 730 pages with facts, 66 empty, 3 quarantined (very long pages, output budget exhausted after 3 attempts) |
| Output | 3,532 provisional entities (1,110 persons), 6,022 pending claims |
| Tokens | **915,428 input + 358,924 output** (≈ 1,146 in / 449 out per page) |
| Latency per call | median **3.9 s**, p95 **28.3 s** (n = 832) |
| Retries | schema-invalid outputs on a handful of long pages (`finish_reason=length`); 3 pages quarantined after 3 calls each |
| Wall time | ≈ 30 min at concurrency 4 (interrupted once at 718/861 windows; resumed from the content-hash cache with no repeated calls) |

Comparison on 11 real pages (dev crawl, one run each, hand-checked; `docs/extraction.md`):

| | 8B | 70B |
| --- | --- | --- |
| Wall time, 11 pages | 9.2 s | 62.1 s |
| Tokens in / out | 13.3k / 5.3k | 15.4k / 6.8k |
| Hand-checked claim precision | ~48% | ~97% |

## 3. Offline: T08 resolution and support judge (full corpus)

| Measure | Value |
| --- | --- |
| Entities after resolution | 4,374 (merges: page anchor 551, language variant 370, organisation 1,061, person 3; 95 same-name persons kept apart) |
| Claims | 5,130 → 4,314 supported, 816 unsupported, 0 pending |
| Decided by code rules | 3,468 (469 rejected) |
| 70B judge | 1,662 claims in **139 calls** (batches of 12, concurrency 4): **133,825 input + 27,983 output tokens**; 347 rejected (3 reversed relations) |
| Wall time | **138.9 s** for the whole T08 run |

## 4. Offline: search index build (T09, full corpus + T08 knowledge)

| Measure | Value |
| --- | --- |
| Entries / vectors | 21,684 entries (19,141 passages + 2,543 profiles) / 22,179 vectors, 384 dimensions |
| Entities indexed / with card fields | 2,543 / 674 (validated supported claims: 4,289) |
| Build wall time (CPU, e5-small) | **1,129 s (18.8 min)** on the laptop CPU (8 cores, ~3.3 cores busy on average) |
| Peak memory | **1.23 GB** resident |
| Index size on disk | **234 MB** (one generation, including the 130 MB model) |

## 5. Online: fast path (no LLM)

Server-side compute per query, measured in-process on the full index with the frozen gold set's development queries (`evaluation/ablation.py`). This excludes network; client-side latency against the live Space is T14's HTTP runner.

| Mode | Median | p95 | n |
| --- | --- | --- | --- |
| keyword (BM25) | 33 ms | 202 ms | 17 |
| dense | 23 ms | 41 ms | 17 |
| hybrid | 42 ms | 137 ms | 17 |

Target "< 3 s to first cards": **met with a large margin** for server compute (p95 ≤ 0.2 s in every mode). Client latency to the live Space, including network, remains to be measured by T14 once the full index is deployed.

## 6. Online: optional Apertus enrichment

| Stage | Model | Latency | Tokens | n |
| --- | --- | --- | --- | --- |
| Interpretation (T18) | 70B | 1.5–52.5 s (gateway variance); typical 5–10 s | ~400 in / ~200 out | 6 live calls |
| Interpretation (T18) | 8B | 1.4–13.6 s | ~400 in / ~200 out | 6 live calls |
| Assessment of 8 candidates (T19) | 8B | **5.7–6.3 s** total (2 batches of 4, 2.5–3.6 s each) | ~1.3k in / ~1.0k out | 3 runs |
| Assessment of 8 candidates (T19) | 70B | 18.1 s | ~1.35k in / ~1.1k out | 1 valid run |
| Interpretation + expansion fan-out in search (T20 ablation) | 70B | median **5.1 s**, p95 7.5 s per query | 708 tokens/query | 17 |
| Expansion (cached) + assessment of top 10 (T20 ablation) | 8B | median **18.6 s**, p95 23.8 s per query (2–3 sequential batches; median batch 9.3 s, max 12.0 s) | 2,783 tokens/query incl. expansion | 17 |

Target "complete enrichment < 15 s": **not met on the full corpus.** With real cards (longer evidence), 8B assessment batches took a median 9.3 s instead of 2.5–3.6 s on the earlier 8-candidate sample, so assessing the top 10 alone took a median 18.6 s. Interpretation adds 1.5–52 s (shared-gateway variance). Mitigations: assess fewer candidates, run batches concurrently, or trim evidence per candidate. The first cards never wait for enrichment (T18/T19 run over SSE), so this delay affects only the suggestions panel and assessment labels.

## Not measured (and why)

- **Concurrent load on the live Space:** the deployed index wasn't available when this sheet was written; to be added from the Space once T11 deploys the full index.
- **Separate prefill/generation throughput:** the gateway doesn't expose it; time to first token is reported instead.
- **Keera price:** not published to us, so the cost worksheet keeps it as a variable.
