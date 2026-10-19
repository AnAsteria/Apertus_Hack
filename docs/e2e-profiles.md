# End-to-end test on three fictional company descriptions (EXTRA B4, #129)

Run 2026-10-19 ~09:30 Zurich, branch `EXTRA-ruihan` (`8acd5bd`), local server on bundle `9a0e0951…`, Keera 70B interpretation + 8B assessment. Fictional profiles only (see `PROFILE_CASES` in `tools/enrichment_check.py`). One run each (n = 1 per profile), so this is indicative, not a benchmark.

```bash
python tools/enrichment_check.py --base-url http://127.0.0.1:8765 --cases profiles --out data/runs/b4-profiles.json
```

| Profile | Fast-path outcome | First cards / interpretation / reranked / complete | Assessment tokens (in/out) |
| --- | --- | --- | --- |
| Diabetes medtech (needle-free optical glucose monitor) | confident | 1.6 s / 10.0 s / 10.5 s / 18.7 s | 2,565 / 1,752 |
| Oncology diagnostics (liquid biopsy, resistance) | low_confidence | 0.1 s / 6.1 s / 6.4 s / 14.2 s | 2,301 / 1,684 |
| Neuro-robotics (surgical robots) | confident | 0.1 s / 6.0 s / 6.4 s / 14.7 s | 2,101 / 1,726 |

## What worked

- **Interpretation** turned each pasted description into 4–5 editable needs (all marked `suggested`, since the analyst typed none) and 6–8 EN/DE expansions in the right vocabulary. Examples: "CGM comparative clinical trial", "closed-loop insulin delivery algorithms", "ctDNA-Sequenzierung", "robot-assisted surgery", "intraoperative Bildführung".
- **Neuro-robotics, end to end:** the expansion pass moved **Neuro Robotics Group to rank 1**, and assessment labelled it **direct_match**, with ARTORG Spin-Offs direct and Motor Learning and Robotic Neurorehabilitation related.
- **Diabetes:** reranking replaced generic first cards ("Research Networks and Partners", "Research Group Heads") with Diabetes Center Berne pages, including SPN-005.
- The first cards came back in ≤ 1.6 s in every case, without waiting for any model.

## Failures (to fix, not shipped)

1. **Long descriptions weaken the fast path.** The first cards for the diabetes and oncology profiles were generic directory pages, because the query text is long and unspecific. Expansion helps, but only after ~6–10 s.
2. **Diabetes: assessment missed the best match.** SPN-005 (needle-free glucose measurement through the skin) was labelled **insufficient_evidence**, although it matches the product closely. The AIHN / Adaptive Diabetes Management group (insulin-dosing algorithms) didn't reach the top 10 at all.
3. **Oncology:** outcome `low_confidence`. Cancer Therapy Resistance (DBMR) didn't appear; irrelevant neuro labs were assessed. Only Molecular Diagnostics, the Core Facilities and Clinical Neurovirology were labelled related.
4. **Need kinds:** "access to patient cohorts in Switzerland" and "R&D site in Bern" were typed `entity_type` instead of `constraint`.
5. **Latency:** the diabetes profile took 18.7 s (interpretation 10 s on the longer text), over the 15 s target.

## Suggested next steps

- Run the fast path on the extracted **needs** as well as the raw description, which needs a T30 change (Maxim's area).
- Give assessment the profile's product sentence explicitly, and re-check SPN-005-type misses on a small labelled set before changing the prompt.

## Follow-up: root causes (2026-10-19, Maxim's request)

**SPN-005 labelled `insufficient_evidence`: evidence selection.** Assessment showed the model the card's first 4 sentences in page order. For the English SPN-005 card those were the title, a byline ("by … | Oct 9, 2025"), a navigation line and a generic intro. The decisive sentences (non-invasive light + AI measurement through the skin, compared with CGM) were never in the prompt. That card is also the English page's entity without fields; its German language twin carries the supported facts. The prompt is not the cause.

*Tried:* selecting the 4 sentences most related to the request and needs (`select_evidence`, `BERNMATCH_ASSESS_EVIDENCE=relevant`). It fixes this case by construction, but on the development split it **lowered** the share of expected answers labelled direct/related from **0.82 to 0.71** (same cached interpretations, n = 17; Recall@10 unchanged 0.824). So it stays **opt-in, off by default**, per the "development numbers must not drop" rule.

**AIHN missing from the top 10: retrieval and entity fragmentation.** The group exists as **5 separate entities** ("AIHN", "AI in Health and Nutrition", "Artificial Intelligence in Health and Nutrition (AIHN) research group", "Adaptive Diabetes Management", and an AIHN news item), so its retrieval signal is split. It ranks 8 for the extracted need "help with insulin-dosing algorithms" and 6/9 for "AI insulin dosing decision support", but it is not in the top 10 for the pasted description or for most expansions, where Diabetes Center Berne news pages win. Fixing it needs a T08 merge rule (abbreviation ↔ full name across pages; A6 #124) and a T08 re-run plus index rebuild, which is not cheap before the freeze. **Documented, not fixed.**
