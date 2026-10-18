# Submission preparation (T22, Dimitry's part)

Refs #22. **Skeleton only.** Every evidence cell below is empty until a real measurement, deployment or artifact exists. Nothing here is a result. Deadline: **19 October 2026, 14:30 Europe/Zurich**; the 13:30-14:30 buffer is for submitting, not for building.

## 1. Deliverables and limits

| Deliverable | Limit | Owner | State |
| --- | --- | --- | --- |
| Public GitHub repository | public, readable by the jury | Dimitry (T25) | not verified public |
| Demo video | ≤ 2 minutes, public link + backup file | Dimitry | not recorded |
| Pitch PDF | ≤ 10 slides, includes data minimisation, removal route, retention | Maxim leads | not started |
| Technical report PDF | ≤ 6 pages | Ruihan: AI/evaluation/cost; Maxim: structure | not started |
| ZIP of required PDFs | exact manifest in section 5 | Dimitry (T26) | not built |
| Submission confirmation | screenshot or receipt of the actual submission | Dimitry (T26) | not submitted |

## 2. Jury criteria to real evidence

| Criterion | What we must show | Evidence needed (fill only with real artifacts) | Status |
| --- | --- | --- | --- |
| Purposeful AI | Apertus turns business wording into research needs and explains evidence-backed matches | T18/T19 outputs; T20 comparison of retrieval alone vs Apertus-assisted | empty |
| Technical rigour | Reproducible ingestion, validated structured output, grounded citations, evaluated retrieval | T14 protocol; T16 Recall@10 with sample size; support-rate sample; CI run link | empty |
| Value, cost, scalability | Short usable shortlist; measured runtime, tokens, storage | T16 cost worksheet; latency median/p95 | empty |
| Sovereign deployability | Open replaceable components; controlled deployment; local air-gapped query | T15 proof; `docs/local-runtime-t15.md` is a feasibility probe only | partial (probe only) |
| Implementation feasibility | Simple operation, documented configuration, manageable review | README run steps; `docs/inference.md`; new-source-by-config demo | empty |
| Pitch and presentation | One clear fictional-company story, working search, evidence inspection, an honest partial-match case | Recorded demo; slides | empty |

## 3. Demo story (draft, fictional company only)

Target ≤ 2 minutes, one continuous flow on the deployed URL, no real confidential input.

1. 0:00 Problem in one sentence: companies and researchers use different words.
2. 0:15 Analyst types a lay-language need for a **fictional** company; cards appear without waiting for any LLM.
3. 0:40 Open one card: exact source sentence, original URL, source date vs fetch date.
4. 1:00 Show an honest partial match or "support not found in the indexed corpus" case.
5. 1:20 German or French wording of the same need reaches the same evidence (only if T27 is verified).
6. 1:40 Enrichment arriving afterwards (only if T18/T19 are verified); otherwise say it is not part of this build.
7. 1:55 One line each on data minimisation and the removal route.

Rule: show only what was verified on the final deployment. Cut a step rather than fake it. Record a backup video as a local file in case the live URL fails.

## 4. Dependencies and licences (inventory)

| Component | Version | Licence (to confirm from upstream) |
| --- | --- | --- |
| FastAPI | 0.115.6 | MIT |
| Pydantic | 2.14.1 | MIT |
| Uvicorn | 0.34.0 | BSD-3-Clause |
| httpx / httpcore | 0.28.1 / 1.0.9 | BSD-3-Clause |
| Apertus 8B/70B (via CSCS/Keera gateway) | `apertus-v1-5-8b`, `apertus-v1-5-70b` | Apache-2.0 per Hugging Face metadata; acceptable-use terms to read |
| Local GGUF probe model | `Colby/apertus-v1.5-8b-text-Q4_K_M-GGUF` | Apache-2.0 per HF metadata; unofficial conversion |
| Embedding model | not pinned (T09) | to record when chosen |
| llama.cpp | b11719 | MIT |

Licences marked "to confirm" must be checked at the source before the report states them. Authoritative Apertus provenance and opt-out references are still to be collected from the Swiss AI Initiative's own publication and model card.

## 5. Required ZIP manifest (proposed; confirm against the organisers' rules)

```
bern-match-submission.zip
  pitch.pdf          (≤ 10 slides)
  report.pdf         (≤ 6 pages)
  README-links.txt   (repository URL, deployed URL, video URL, backup video location)
```

Open question for the organisers: whether the video file itself must be inside the ZIP or only linked.

## 6. Submission checklist (tick only after verifying on the final state)

- [ ] **Delete the temporary corpus release first** (it holds personal contact data): `gh release delete temp-corpus-delete-me --cleanup-tag --yes`, then `gh release list` must be empty (issue #73).
- [ ] Repository is public; open it logged out.
- [ ] No secrets in tracked files; CI green on `main`.
- [ ] Final deployed URL answers `/healthz` and a real search from outside the network.
- [ ] Demo video ≤ 2:00, plays logged out, backup copy saved.
- [ ] Pitch PDF ≤ 10 slides, page count checked on the exported file.
- [ ] Report PDF ≤ 6 pages, page count checked on the exported file.
- [ ] Every number in slides and report traces to a stored run record; unmeasured items are labelled as such.
- [ ] Limitations stated: sample sizes, one-location latency, unofficial local model, unverified items.
- [ ] ZIP opens and contains exactly the manifest.
- [ ] Submission made before 13:30; confirmation saved.
