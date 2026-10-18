# Gold set review by Ruihan (T14, R1 requirement)

Refs #14. Reviewed `evaluation/gold/gold.json` (`gold_version` 0.1-seed, 18 queries, 11 intent groups) on 2026-10-18 against the shared release corpus (`temp-corpus-delete-me`, `corpus.jsonl` sha256 `e3d8a170…5d1c58`, imported into a local store: 2,811 pages, 148,404 sentences). This is a single-reviewer check of the existing entries. **I did not add or change any expected answer**: I wrote the T18/T19 matching prompts, so authoring gold entries would break the "expected sets by someone who did not write the matching prompts" rule.

## Result per query

| Group | Queries | Expected source in corpus | Expected name on that page | Verdict |
| --- | --- | --- | --- | --- |
| I01 cancer therapy resistance | en, de | ✅ DBMR research programmes page | ✅ "Cancer Therapy Resistance", "CTR"; the page has a T06 section stub "Cancer Therapy Resistance - CTR" | OK |
| I02 nervous-system repair | en, de | ✅ same page | ✅ "Regenerative Neuroscience", "RNS" (stub "Regenerative Neuroscience - RNS") | OK |
| I03 AI insulin decision support | en, de | ✅ AIHN group page and the Adaptive Diabetes Management activity page | ✅ "AI in Health", "AIHN" on the group page; ⚠️ **not** on the activity page | OK, but see note 1 |
| I04 neurosurgical robotics | en, de | ✅ ARTORG Neuro Robotics Group | ✅ "Neuro Robotics" | OK |
| I05 needle-free glucose pilot | en, de | ✅ SPN-005 EN and DE pages | ✅ "SPN-005" | OK |
| I06 misleading (stem-cell repair, not robotics) | en | ✅ RNS expected, Neuro Robotics as `avoid` | ✅ | OK |
| I07 partial (market-ready device) | en | ✅ SPN-005 | ✅ | OK; tests that the system doesn't claim market readiness |
| I10 absent (quantum satellite communication) | en | none expected | — | **Absence holds**: 0 sentences on quantum communication/cryptography/key distribution; 283 near-miss sentences (quantum field theory, satellite geodesy/GNSS) make it a good trap |
| I11 brain barriers / CNS immune surveillance | en, de | ✅ Theodor Kocher Institute page | ✅ "Kocher", "TKI" | OK |
| I12 cancer & inflammation pharmacology | en, de | ✅ Institute of Pharmacology page | ✅ "Pharmakologie", "PKI" | OK |
| I13 nucleic-acid sequencing platform | en | ✅ NGS platform page | ✅ "NGS", "Sequencing" | OK |

## Notes

1. **I03 second URL:** the Adaptive Diabetes Management page doesn't contain "AIHN" or "AI in Health". A card built from that page only counts if its display name contains an alias, so the second URL can never score on its own. Either add "Adaptive Diabetes Management" to `names` (if the group owner agrees it's the same capability) or drop the URL. That's the gold owner's call.
2. **Coverage before freezing** (still below the 30–50 target):
   - **No person queries.** The full corpus now has 395 person pages, so I08 (person/unit boundary) can be grounded.
   - No French or Italian queries, although D7 added FR/IT.
   - No lay/synonym variant for I11, I12, I13.
   - Nearly all groups come from DBMR/ARTORG/DCB, while the corpus covers 41 domains (775 of 799 extractable pages are labelled `unibe`).
3. Expected answers sit on `directory` and `unit` pages, which is consistent with T06 stubs. Section-level stubs make them matchable without LLM extraction.

**Recommendation:** the 18 existing entries are correct against the real corpus and can be frozen as they are once note 1 is settled. More queries should come from Maxim or Dimitry (not from me, for the reason above) before `validate --final`.
