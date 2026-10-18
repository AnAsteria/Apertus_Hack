# Inference adapter (T05)

Refs #5. Owner: workstream B (Ruihan). Status: **implemented, unit-tested against a fake endpoint, live-probed once against Keera on 2026-10-18.** Not yet wired into any API route (T18/T19 do that).

## What it is

`app/ai/client.py` is the only place that talks to Apertus. It works with any OpenAI-compatible chat endpoint: the CSCS/Keera gateway for development, or a local server (e.g. llama.cpp) for the offline proof (T15). Switching is a configuration change.

Keyword search must never depend on it. Every failure surfaces as an `InferenceError` with a fixed code that callers turn into "enrichment unavailable".

## Configuration (`env.example`)

| Variable | Default | Notes |
| --- | --- | --- |
| `APERTUS_BASE_URL` | `https://gateway.keera.ch/api/v1` | Local replacement: `http://localhost:8080/v1` |
| `APERTUS_API_KEY` | empty → inference **disabled** | Server-side only. Never in client bundles, fixtures, issues or logs |
| `APERTUS_MODEL` | `apertus-v1-5-8b` | Bulk extraction/assessment (architecture step 4) |
| `APERTUS_QUALITY_MODEL` | `apertus-v1-5-70b` | Use only where a measured gain justifies it |
| `APERTUS_TIMEOUT_S` | 30 | Per request |
| `APERTUS_MAX_RETRIES` | 2 | Retries on 408/429/5xx/timeouts/connection errors only |
| `APERTUS_BACKOFF_BASE_S` | 0.5 | Exponential with jitter, capped at 8 s; `Retry-After` honoured (capped) |
| `APERTUS_MAX_CONCURRENCY` | 4 | Process-wide cap on in-flight requests |

The template is `env.example`, not `.env.example`: the T04 `.gitignore` ignores `.env.*` and the CI secret check fails on any tracked `.env.*` file.

## API

```python
from app.ai.client import get_client, InferenceError

client = get_client()
r = client.chat(messages)                          # ChatResult(text, usage, latency_s, attempts, ...)
j = client.complete_json(messages, MySchema)       # JsonResult(value, decoding_mode, usage, attempts)
for delta in client.stream(messages): ...          # content deltas; usage recorded in client.meter
client.probe()                                     # opt-in capability report
client.meter.snapshot()                            # per-model calls, tokens, retries, invalid outputs, median/p95 latency
```

Error codes: `DISABLED`, `AUTH` (401/403), `NOT_FOUND` (404), `BAD_REQUEST` (400), `RATE_LIMITED` (429), `TIMEOUT`, `UNAVAILABLE` (5xx, unreachable, malformed body), `BAD_OUTPUT` (no schema-valid output after bounded attempts).

## Structured output and decoding modes

`complete_json()` first sends `response_format: {type: json_schema, strict: true}` with the Pydantic schema, adding `additionalProperties: false` to every object.

- **`backend_constrained`**: the endpoint accepted the schema. Output is still validated with Pydantic, and invalid output is retried up to `1 + APERTUS_MAX_RETRIES` calls.
- **`validated_retry_fallback`**: used if the endpoint rejects `response_format` with HTTP 400. The schema goes into the prompt and output is validated and retried the same way. **This is a weaker guarantee than backend-constrained decoding and must be reported as such** (architecture step 4).

Neither mode proves that a claim is semantically supported by its evidence; that is T08's job.

Why `additionalProperties: false` matters (observed live, 8B, n = 4): without it the gateway let the model add an unrequested `explanation` key, which used the whole `max_tokens=50` budget and truncated the JSON. With it, the probe passed on both 8B and 70B.

## Streaming

`stream()` yields content deltas and records time to first token and final usage (`stream_options.include_usage`). Streams are **not retried**: a partial stream cannot be replayed safely. Callers should treat a mid-stream error as "enrichment unavailable".

## Security and logging

- Key sent only in the `Authorization` header; excluded from `repr()`, `redacted()`, error messages and probe reports (tested).
- Log lines carry model, status, error code, attempt, latency and token counts. They never carry prompts, company text, model output or the key (tested with a fictional company prompt).

## Checks run (2026-10-18)

| Check | Command | Result |
| --- | --- | --- |
| Unit tests, fake endpoint (`httpx.MockTransport`) | `python -m pytest -q` | 43 passed, 1 skipped (live test skipped by default) |
| Live probe, 8B | `BERNMATCH_LIVE_TESTS=1 APERTUS_MODEL=apertus-v1-5-8b python -m pytest tests/ai/test_live.py -s` | models listed; plain OK (0.08 s); `json_schema` supported (`backend_constrained`); streaming supported (14 chunks, 0.14 s) |
| Live probe, 70B | same with `APERTUS_MODEL=apertus-v1-5-70b` | passed; `json_schema` supported (`backend_constrained`) |

Unit tests cover: disabled without key, config validation, key never leaked, retry then success on 429/500/503, bounded retry exhaustion, `Retry-After` cap, fail-fast on 400/401/403/404, timeout and unreachable endpoint, malformed body, concurrency cap, schema sent with `additionalProperties: false`, fallback on rejected schema, invalid-then-valid retry, persistent invalid → `BAD_OUTPUT`, streaming deltas and usage, streaming error status, probe report contents.

## Limitations

- Live probe is a single run per model with fictional prompts; not a benchmark (T16).
- Rate limits, quota and pricing for the team key are still unknown (no rate-limit headers observed in T03).
- `max_concurrency` is per process. Several workers or containers multiply it.
- Thinking models bill hidden reasoning tokens; give them a generous `max_tokens` or avoid them on latency-bound paths.
- The local replacement endpoint has not been tested yet (depends on T15 hardware).

## Shared-file changes (need dispatcher approval)

- `requirements.lock` and `pyproject.toml`: add `httpx==0.28.1` (+ `httpcore==1.0.9`, `certifi==2026.7.22`) as a runtime dependency. `httpx` was already a test dependency in CI.
- Template named `env.example` instead of the spec's `.env.example` (see Configuration above).
