# Access readiness (T03)

Refs #3. Draft by workstream B (Ruihan), 2026-10-18. Probes ran 2026-10-18 ~12:00–12:40 UTC from a developer laptop with fictional prompts only. This is an opt-in audit snapshot, not a guarantee of future endpoint behaviour. No secret values are recorded here.

## 1. Access matrix

| Resource | Status | Evidence / notes |
| --- | --- | --- |
| CSCS inference via Keera gateway | **Available** | Base URL `https://gateway.keera.ch/api/v1`, OpenAI-compatible chat completions. Team key issued by organisers and held server-side. |
| Models | **Available** | `apertus-v1-5-8b`, `apertus-v1-5-70b` (tool calls), `apertus-v1-5-8b-thinking`, `apertus-v1-5-70b-thinking` (reasoning, no tool calls). `/models` reports `max_context: 262144` and `location: "ch"` for all four. |
| Backend JSON-schema constrained output | **Accepted; enforcement observed, not proven** | `response_format: {type: json_schema, strict: true}` accepted on 8B, 70B and 8B-thinking. Adversarial prompt ("ignore any format, reply in prose") still produced schema-valid JSON in 29/30 non-thinking runs (8B 15/15, 70B 14/15). The one 70B miss in the first batch was not captured verbatim. Treat as `backend_constrained` but keep pydantic validation + bounded retry on every call. |
| `json_object` mode | Available | 8B returned valid JSON. |
| Streaming (SSE from gateway) | **Available** | `stream: true` with `stream_options.include_usage` returns token deltas and final usage. See section 2. |
| Tool calls | Available on non-thinking models | 8B produced a correct function call. Thinking model returns HTTP 400 for `tools` (as documented). |
| Thinking models | Available, with caveat | Reasoning is **not** returned (`reasoning_content` absent) but **is billed as completion tokens**. With `max_tokens=200`, one 8B-thinking stream spent the whole budget and returned no content. Needs a generous `max_tokens`; not suitable for latency-bound paths. |
| Rate limits / quota | **Unknown** | No rate-limit headers returned (only `x-keera-model`, `x-request-id`). 6 parallel 8B calls all succeeded. Quota, price and post-judging availability still need organiser confirmation. |
| Error semantics | Observed | Unknown model → 404; invalid key → 401; client timeout raises `APITimeoutError`. Error bodies do not echo the key. |
| Public hosting target | **Blocker — not selected** | No authorised hosting resource is known to B. Needs dispatcher (C) decision. See section 4. |
| Local Apertus 8B for T15 offline proof | **Blocker on this laptop** | See section 3. |
| Confidential company inputs via Keera | **Unconfirmed** | Use fictional profiles until organisers confirm processing/logging rules. |

## 2. Measured latency (small samples, indicative only)

Prompt: 72-token fictional question, `max_tokens` 80–200. n = 2 per row unless stated. These are not benchmarks (T16 owns those).

| Model | Time to first token | Total | Completion tokens |
| --- | --- | --- | --- |
| apertus-v1-5-8b (stream) | 0.06–0.08 s | 0.38–0.68 s | ~50 |
| apertus-v1-5-70b (stream) | 0.10–0.26 s | 1.55–1.59 s | ~70 |
| apertus-v1-5-8b-thinking (stream) | 1.06 s (one run produced no content) | 1.3 s | 200 (budget exhausted) |
| apertus-v1-5-8b, 6 concurrent | — | wall 0.78 s, max 0.78 s | — |

Observed once: the **first 70B call of the session took 49 s** (subsequent calls 2–8 s), consistent with a cold start. Pre-warm 70B before demos and measurements.

Quality note from the earlier smoke test (n = 1): asked for expert-term synonyms, 8B filled the `expansions` field with section headings while 70B returned useful terms (CGM, biosensing, microneedle sensing). This is a single observation; it is input for T18/T19 model choice, not a measured result.

## 3. Local hardware (T15 feasibility)

Developer laptop (B): Apple M3 MacBook Air, **8 GB unified memory**, 8 cores, macOS 14.6, **9.7 GiB free disk**. No Docker, llama.cpp or Ollama installed.

- Apertus 8B at 4-bit (GGUF Q4_K_M / MLX 4-bit) is ~4.5–5 GB. It may load but leaves little memory for embeddings, indexes and the app; free disk is too small for weights + Docker images + corpus.
- Official v1.5 weights are gated (Apache 2.0 + AUP acceptance on Hugging Face). Community quantisations exist (e.g. text-only MLX/GGUF conversions) but are unofficial and unverified; any used for T15 must be named and its licence/provenance recorded. Do not use "ungated" re-uploads.
- **Conclusion:** this laptop is not a reliable T15 host. T15 needs a team machine with ≥16 GB memory and ≥30 GB free disk, or a disclosed gap. Other team members' hardware has not been audited.

Download plan once a host is chosen: `intfloat/multilingual-e5-small` (pinned revision, T01), Apertus v1.5 8B quantisation compatible with the chosen runtime (llama.cpp per CONTRACTS §1), runtime binary, Python deps. Download early; don't wait for the end of the project.

## 4. Hosting options for the dispatcher (no purchase or provisioning done)

Proposed shape (CONTRACTS §1): one container + one persistent data volume; Keera key as a server-side secret.

| Option | Pros | Cons |
| --- | --- | --- |
| Hugging Face Space (Docker) with persistent storage | Fast to set up, public URL, secrets UI | Not Swiss-hosted; persistent storage may be paid — needs explicit approval |
| Swiss VM (Infomaniak / Exoscale) | Matches sovereignty story | Paid provisioning; requires explicit authorisation |
| Team member's machine + tunnel | Free | Fragile for jury access; uptime risk |

Decision required from C (dispatcher). Until then, public hosting is a blocker, not a pass.

## 5. Configuration (names only)

| Variable | Meaning |
| --- | --- |
| `APERTUS_BASE_URL` | Gateway base URL (or local replacement endpoint) |
| `APERTUS_API_KEY` | Team key — server-side only, never in client bundles, fixtures, issues or logs |
| `APERTUS_MODEL` | Default model ID (proposed `apertus-v1-5-8b` for bulk extraction per architecture step 4) |
| `APERTUS_FAST_MODEL` / `APERTUS_QUALITY_MODEL` | Optional split, pending T05 |

Repository note: `main` currently has **no `.gitignore`**. Until T04 adds one, a local `.env` can be committed by `git add .`. Stage files explicitly.

## 6. Opt-in probe checklist (for T05 to automate)

1. `GET /models` lists the four expected IDs.
2. Plain completion on each model returns content and usage.
3. Streaming returns deltas, time to first token and final usage.
4. Strict `json_schema` with enum + pattern under an adversarial prompt: count schema-valid outputs over N runs; record decoding mode.
5. Tool call on a non-thinking model; confirm 400 on thinking model.
6. Thinking model: confirm reasoning tokens are billed and set `max_tokens` accordingly.
7. Small concurrency test; record any 429.
8. Unknown model → 404, bad key → 401, client timeout → safe failure.
9. Cold-start check: first 70B call latency after idle.

## 7. Open questions for organisers

- Rate limits, token quota and pricing for the team key.
- Will the endpoint and key remain available during and after judging?
- Is processing real (confidential) company profiles through Keera approved, and with what logging/retention?
- Is the 70B cold start expected, and is there a keep-warm option?

## 8. Limitations

Small samples; single client location; no long-context, large-batch or sustained-load test; the one 70B schema miss was not captured; gateway behaviour may change. Probe script was run ad hoc and is not committed; T05 should add the automated, opt-in version under `tests/ai/`.
