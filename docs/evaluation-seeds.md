# T02 — Source-grounded evaluation seed candidates

Related issue: [#2](https://github.com/AnAsteria/Apertus_Hack/issues/2). Inspected **18 October 2026**. Source locators S00–S12 refer to [sources.md](sources.md#2-inspected-seed-pages). These are **candidate queries and human-reviewed source locators**, not a completed 30–50-query gold set, production entity IDs, model outputs or measured retrieval results. T14 defines/finalises the gold set, split and scoring before benchmark runs. All company needs below are fictional.

## 1. Entity candidates and support boundaries

| Candidate key | Expected entity type / affiliation | Evidence locator and reviewed support | Do not infer |
| --- | --- | --- | --- |
| U-CTR | Unit/programme, Cancer Therapy Resistance, UniBE–DBMR | [S02](https://www.dbmr.unibe.ch/research/research_programs/index_eng.html), heading “Cancer Therapy Resistance - CTR”: resistant cancers, functional screens and model systems. | Any programme contact personally supplies every programme capability. |
| U-RNS | Unit/programme, Regenerative Neuroscience, UniBE–DBMR | [S02](https://www.dbmr.unibe.ch/research/research_programs/index_eng.html), heading “Regenerative Neuroscience - RNS”: neural repair and stem/progenitor-cell approaches. | A clinical treatment is proven or commercially available. |
| U-AIHN | Unit/group, AI in Health and Nutrition, ARTORG | [S05](https://www.artorg.unibe.ch/research/aihn/index_eng.html) establishes group identity; linked [S06](https://www.artorg.unibe.ch/research/aihn/research_activities/adaptive_diabetes_management/index_eng.html), “Adaptive Diabetes Management”, supports insulin decision-support research. | Group expertise automatically belongs to the listed contact. |
| U-NRG | Unit/group, Neuro Robotics Group, ARTORG | [S07](https://www.artorg.unibe.ch/research/nrg/index_eng.html), group description: neurosurgical instruments, robotics and micromechatronics. | A general robot lab is a direct match for every neurological disease. |
| P-SPN005 | Project, SPN-005, DCB | [S10 EN](https://www.dcberne.com/en/project/spn-005-pilot-study-on-painless-glucose-monitoring/) and [S11 DE](https://www.dcberne.com/de/project/spn-005-pilotstudie-zur-schmerzfreien-blutzuckermessung/), project description and conclusion: non-invasive glucose pilot and need for further work. | Market readiness, current recruitment or a partner person's contact details. |

These candidate keys will be mapped to actual resolved entity IDs after ingestion/extraction; do not fabricate IDs now. The same project in two languages is one expected primary entity, with two evidence versions. Programme and lab are different levels: do not treat any member lab as automatically equivalent to its programme.

## 2. Candidate query families

Variants within each family must remain in the **same intent-group partition**. Do not split English/German paraphrases between development and evaluation. “Expected” below is a proposed source-grounded relevance judgment, not observed Recall@10 or an exhaustive gold set.

| Intent group | English / German candidate query | Requested type | Proposed expected target and constraint |
| --- | --- | --- | --- |
| I01 — oncology | “Research partners studying why cancers resist treatment” / “Forschungspartner für Therapieresistenz bei Krebs” | Unit | U-CTR, S02 named section; do not substitute a person. |
| I02 — neural repair | “Research on repairing the nervous system after brain injury” / “Forschung zur Reparatur des Nervensystems nach Hirnverletzungen” | Unit | U-RNS, S02 named section; research capability, no treatment-outcome promise. |
| I03 — diabetes AI | “AI decision support for adapting insulin therapy” / “KI-Entscheidungsunterstützung zur Anpassung der Insulintherapie” | Unit | U-AIHN through S05→S06. German query against English S06 is an explicit cross-lingual case. |
| I04 — surgical robotics | “Robotics and tiny instruments for neurosurgery” / “Robotik und kleine Instrumente für die Neurochirurgie” | Unit | U-NRG, S07. Preserve the surgical scope. |
| I05 — glucose sensing | “Pilot research on measuring glucose without needle pricks” / “Pilotforschung zur Glukosemessung ohne Fingerstich” | Project | P-SPN005. Exercise DE→EN using S10 and EN→DE using S11 in controlled language-filtered subsets; record those subsets. |
| I06 — misleading near-match | “Brain stem-cell repair research, not neurosurgical robotic instruments” | Unit | U-RNS is a candidate; U-NRG is a misleading near-match. Preserve explicit exclusion. |
| I07 — partial match | “A needle-free glucose device already ready for market launch” | Project | P-SPN005 is only a related research candidate; its conclusion does not establish the requested readiness. Reject a confident direct-match claim. |
| I08 — person/unit boundary | “Find a named researcher with personally documented expertise in neurosurgical microrobotics” | Person | The unit description alone cannot satisfy the request. Review actual person evidence before adding any expected person; do not use U-NRG as a person substitution. |
| I09 — contact freshness | “Who is the current contact for the former Image-guided Therapy group?” | Person/contact | S03 marks this as a former group. Do not label its former leader a current contact on that basis. Current contact expectation remains unlabelled pending evidence review. |
| I10 — absent evidence | “Research expertise in quantum communication between satellites” | Unit | Negative candidate for the frozen T02 seed subset only. Check the ingested subset before assigning expected abstention; no claim of absence across UniBE or a future broader corpus. |

I07/I08/I09 measure support and interpretation boundaries, not merely lexical ranking. I10 is a proposed negative awaiting corpus review, not an established universal negative. Person substitution is permitted only when explicitly recorded in the final gold set with source-backed identity/affiliation checks. No personal contact fields are reproduced here.

## 3. Format and evidence checks for downstream tasks

- **HTML directory versus entity:** S02 contains multiple programmes on one URL. Segment by headings; do not conflate evidence from different sections or create duplicate fetch versions for anchors.
- **Bilingual variants:** S03/S04 and S08/S09 are linked language variants, but lists differ. S10/S11 refer to the same project; preserve both texts, dates and explicit limitation wording. Do not assume translations express identical claims.
- **Text PDF:** S12 is a 13-page portfolio with extractable text visible to the web reader. T06 must verify its own parser's sentence/page provenance; no page-number citations are invented here.
- **Exact text versus support:** the short locator phrase “surgical instruments for neurosurgery” occurs on S07. Its presence does not support a claim of stem-cell therapy expertise. Later sentence IDs must come from the persisted document version, not these audit keys or arbitrary web-reader line numbers.
- **Former/current:** S03's former-group section is evidence for a temporal warning, not a complete personnel history. A recent fetch cannot establish current employment.

## 4. T14/T16 handoff

T14 must expand to 30–50 source-grounded queries, freeze expected entities before running retrieval, document adjudication and partner review, map stable entity IDs/aliases, group variants by intent, set development/evaluation separation and define person/unit equivalence. Review ambiguous negative/current-contact cases before final gold labels. Preserve real-source dates and snapshot/version references after ingestion.

T16 executes actual Core evaluation; T20 adds expansion/assessment and the cross-encoder subset comparisons. Report entity Recall@10, link coverage, sampled evidence support with denominator/sample size, field accuracy/completeness, abstention, relevance-aware institutional exposure and actual median/p95 latency, tokens and indexing time. This seed document reports **no system quality, latency or throughput results**.

## 5. R1 inventory extension candidates

The [complete supplied-inventory audit](sources.md#r1--complete-supplied-inventory-audit) inspects 42 landing pages, not a finished research corpus. Additional source-grounded candidate intents below extend the earlier seeds without fabricating production entity IDs or gold labels. They are independent intent groups; T14 must review equivalence, freeze evidence versions after ingestion and keep language variants in one partition.

| Intent group | Candidate query | Proposed target / type | Landing evidence and limitation |
| --- | --- | --- | --- |
| I11 — brain barriers | “Find research on brain barriers and CNS immune surveillance” / “Forschung zu Hirnschranken und Immunüberwachung im ZNS” | Theodor Kocher Institute / unit | [TKI](https://www.tki.unibe.ch/): inspected introductory text describes brain barriers, CNS and imaging. A German query can retrieve English evidence; no person's expertise is inferred. |
| I12 — cancer pharmacology | “Find a unit researching cancer and inflammation pharmacology” / “Forschungsgruppe für Pharmakologie von Krebs und Entzündungen” | Institute of Pharmacology / unit | [PKI](https://www.pki.unibe.ch/): inspected German introduction names those research topics. Test an English query against German evidence; a unit match is not a named-person match. |
| I13 — sequencing access | “Which platform offers access to nucleic-acid sequencing technologies?” | NGS Platform / infrastructure or service | [NGS](https://www.ngs.unibe.ch/): inspected landing text describes technology access and invites external service enquiries. This does not establish free access, availability or a particular price; T14 must fix the accepted entity type before scoring. |

Negative/unsupported source case: `geo2.unibe.ch` responds HTTP 200 but has only a Home placeholder and no useful discovery links in the audit. It is excluded from this input snapshot with a recorded reason, not counted as indexed research or automatically treated as an alias of `geo.unibe.ch`. The 42 supplied rows versus 71 claimed in Notes remains a coverage limitation, not a benchmark result.
