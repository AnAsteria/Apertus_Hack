# Local Apertus runtime check (T15 input)

Refs #15. Measured by Dimitry on 2026-10-18 on his own laptop. This is a **feasibility probe**, not the T15 air-gapped proof: no network isolation was applied, only one prompt was run, and the model is a community conversion.

## Machine

Windows 11, 15.2 GB usable RAM, 166 GB free disk, NVIDIA RTX 3050 Laptop GPU (4 GB). CPU-only run; the GPU was not used.

## What was run

| Item | Value |
| --- | --- |
| Model file | `apertus-v1.5-8b-text-q4_k_m.gguf`, 5,059,027,136 bytes |
| SHA-256 | `a037df8d87ff6caacee794ee85f55342f2152e0d359b7389033300c3bee5f299` |
| Source | Hugging Face `Colby/apertus-v1.5-8b-text-Q4_K_M-GGUF` (community conversion, **not official**) |
| Declared base | `andreasmartin/apertus-v1.5-8b-text` (text-only; itself derived from the official `swiss-ai/Apertus-v1.5-8B` per the card tags; not independently verified) |
| Licence (HF metadata) | apache-2.0; not gated |
| Runtime | llama.cpp release `b11719`, `llama-b11719-bin-win-cpu-x64.zip`, `llama-completion.exe` |

The official collection (`swiss-ai/apertus-v1.5`) has no GGUF. The official 8B is about 9B parameters in safetensors, which does not fit this laptop's RAM unquantised.

## Observed result (n = 1)

Prompt: "Name one Swiss city known for research:", 24 tokens requested, context 512, default sampling. The output was coherent text naming Zürich and ETH Zurich.

| Measure | Observed |
| --- | --- |
| Model load | 13.9 s |
| Prompt processing | 9 tokens, 19.5 tokens/s |
| Generation | 23 tokens, 7.1 tokens/s |

## Limits of this evidence

- One short prompt on one machine. Not a benchmark; T16 owns measurements.
- No JSON-schema-constrained decoding, long context, concurrency or embedding model was tried, and none of the app pipeline was run against it.
- The model is a community text-only conversion of v1.5. Whether it matches the model used through the Keera gateway is unverified, so extraction quality here must not be assumed equal.
- Network access was not blocked, so this does not show air-gapped operation.

## Still needed for T15

Run the app and embedding model together, block network access with a documented method, query an unseen question, and record latency and isolation proof. `llama-server.exe` in the same release should provide an OpenAI-compatible endpoint for `APERTUS_BASE_URL`; that has not been tested.
