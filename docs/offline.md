# Offline and sovereign operation (T15): what is shown and what is not

Refs #15. Status 2026-10-18. Architecture section 5 asks for a **local, network-blocked query with local embeddings, indexes and Apertus 8B**. This document records what the team demonstrates instead, and the gap. Decision D13 (proposed) records the deviation.

## What is demonstrated

1. **The search fast path needs no network at query time.** Run on the real 70B index bundle (`bundle.tar.gz`, SHA-256 `9a0e0951…daed3cd`, generation `3825f2a3…`, model `intfloat/multilingual-e5-small` revision `614241f6…`), with `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1` and **every outbound socket refused inside the process**, an unseen ad hoc German query ("Nadelfreie Glukosemessung für Diabetes", not a gold query) returned 10 cards, outcome `confident`, SPN-005 first, with exact evidence from `dcberne.com`. That took 255 ms on an Apple M1 and made **0 outbound connection attempts**. Embeddings, BM25, evidence and entity fields all come from the local bundle. The deterministic test `tests/search/test_search.py::test_exact_evidence_and_no_llm_network` checks the same thing in CI.
2. **Sovereign hosting of the language model.** The deployed app (Hugging Face Space, CPU Upgrade, D9) calls Apertus only through the organiser's **CSCS/Keera gateway** (models report `location: "ch"`, `docs/access-readiness.md`). Search works when that gateway is unavailable; only enrichment stops.
3. **A local Apertus runtime exists as a fallback.** On Dimitry's laptop (Windows 11, 15.2 GB RAM, CPU only), llama.cpp `b11719` ran a community Q4_K_M GGUF of Apertus v1.5 8B at about 7 tokens/s (`docs/local-runtime-t15.md`). The app's adapter accepts a local OpenAI-compatible endpoint (`APERTUS_BASE_URL`). This path has **not** been run end to end with the app.

## What is not demonstrated (open Core gap)

- **No air-gapped run.** The process-level socket refusal is not an operating-system network block; no machine had its network physically or administratively blocked; and no recording of such a run exists.
- **No local Apertus on the query path.** The demo uses Keera; the local 8B run above is a separate feasibility probe with a community conversion, not the official weights.
- A public cloud Space cannot be air-gapped by design. The team chose the faster cloud demo over a laptop air-gap (decision by Maxim, 2026-10-18).

The submission must state this gap; it must not describe the deployment as offline-capable.

## How to reproduce item 1

```bash
gh release download temp-corpus-delete-me -R AnAsteria/Apertus_Hack -p bundle.tar.gz   # team-only, deleted before publication
mkdir serve && tar -xzf bundle.tar.gz -C serve
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 BERNMATCH_DATA_DIR=serve python -m app.search query --data-dir serve --query 'Nadelfreie Glukosemessung für Diabetes'
```

To block the network for real, turn networking off at the OS level before the query and record the screen.
