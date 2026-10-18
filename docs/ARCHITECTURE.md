# Bern Match architecture and approved implementation reference

## 1. Authority, status and scope

This document translates the supplied **Bern Match — final pipeline** into an implementation reference. A proposed implementation plan, concrete contracts and linked GitHub backlog now exist in [docs/tasks/README.md](tasks/README.md), [docs/CONTRACTS.md](CONTRACTS.md) and [docs/AGENT_WORKFLOW.md](AGENT_WORKFLOW.md); they await approval and do not establish implemented capabilities. Approved requirements below retain the pipeline's tier labels, priorities and limitations. The architecture itself does not assign tasks or select a stack; the separate proposed plan records those choices for review.

**Observed repository facts:** inspection on 18 October 2026 found only a two-line README and no application files. This documentation update adds no application code. No ingestion, search, endpoint capability, throughput, quality, deployment or offline result has been measured or verified. Acceptance criteria describe future gates, not achieved results.

The product is an English-language search workspace for Bern Economic Development Agency analysts. It finds research partners across UniBE, ARTORG and Diabetes Center Berne, including German-to-English and English-to-German retrieval. Inputs are keywords, questions or pasted company descriptions. Document upload is out of scope.

| Priority | Approved scope |
| --- | --- |
| Core | Ingestion, persistent local indexes, hybrid retrieval, grounded structured cards, evaluation, demonstrated local air-gapped querying; the extraction, administration, maintenance and delivery requirements in Core steps below. |
| Second layer | Apertus request interpretation, terminology expansion and batched candidate assessment. |
| Stretch | Personalised one-page brief, email drafting last, tracked prose edits. No automatic sending. |

A working, measured search takes priority over a brief built on fragile retrieval. Second layer status does not remove its required evaluation comparisons: the evaluation must either exercise those components or explicitly report missing comparisons. Missing Core evidence remains a limitation, not an implicit scope cut.

Team: three developers, two with AI/ML backgrounds and one with general CS experience. Submission deadline: **19 October 2026, 14:30 Europe/Zurich**. Required artifacts: public GitHub repository, video ≤2 minutes, pitch PDF ≤10 slides, technical report PDF ≤6 pages. Delivery planning and proposed ownership are recorded in the linked plan; human approval and assignment remain pending.

## 2. Execution boundaries and lifecycle

### Offline ingestion and persistent state

Source YAML and the supplied inventory → discovery → bounded public fetch → versioned snapshot and coverage → cleaned passages and sentences → cheap page classification → selective Apertus 70B extraction (8B fallback; [D10](DECISIONS.md)) → entity resolution and grounding → persistent vector and BM25 indexes plus structured records and evidence.

The MVP performs **one initial crawl** and queries the stored corpus. Both entity profiles and original passages must be searchable. Ingestion requires source network access; calling it an offline processing phase does not imply air-gapped crawling. Cache enrichment by content hash, with invalidation when relevant extraction configuration changes; precise cache keys are a pending implementation choice. Unsupported pages remain visible in coverage reporting.

### Online query execution

Text input → multilingual BM25/dense retrieval → fair entity aggregation → deduplication and relevance-aware diversification → validated initial cards. The initial path must not call or await request interpretation or candidate assessment. An unavailable enrichment endpoint must not prevent keyword search or hide available cards. Query execution performs no crawling.

In parallel after a request, optional Second layer interpretation produces editable needs and expanded queries; validated enrichment may update results without blocking the first cards. A bounded candidate batch feeds asynchronous assessment. Progress and validated assessments appear as ready. Correlate enrichment to the originating request and needs revision so late results cannot overwrite a newer search; transport and cancellation mechanics remain undecided.

### Refresh, freshness and removal

MVP: manual refresh is sufficient; no scheduler is required. Production: configurable daily recrawls by default and hourly for selected sources. Reprocess changed content and derived indexes. Temporary fetch failures cause retries, not immediate deletion. Confirmed removed/retired content must leave serving records and derived indexes. Confirmation/retry rules remain to be agreed.

Stable citations reference immutable document versions and sentence IDs; they must not silently move to new text after refresh. Retired versions are unavailable to live retrieval, with historical evidence subject to retention/removal policy. A citation whose text has expired or been removed must be reported unavailable, never rebound to replacement text. This preserves reference identity without promising indefinite personal-data retention.

Distinguish source content date/lastmod from fetch date. Flag stale evidence using a documented threshold, still to be chosen. A recent fetch is not proof of current content. Known former staff cannot appear as current contacts. Removal requests require a reachable route, an operational process and a suppression list applied before re-ingestion; exact route and retention periods need decisions.

## 3. Conceptual data contracts and relationships

These are approved information requirements and derived integrity rules, **not final API schemas or storage choices**. Proposed concrete field names, identifier formats, null semantics and schema versions are now in `docs/CONTRACTS.md`, pending T01 ratification. Missing source facts stay empty; absence must never be filled with plausible model output. Keep public-source data separate from company inputs.

| Record | Required information and relationships |
| --- | --- |
| Source configuration | Stable source identity, label, starting URLs, allowed domains/paths, language handling, crawl limits; discovery rules; production refresh settings when implemented. Links to fetch jobs and document versions. New sources enter through YAML; adapters are documented exceptions. |
| Document and document version | Canonical document identity with linked language variants; immutable version identity, source identity, requested/final URL, redirects, fetch date, available modification/content dates, hash, language, type and lifecycle state. Multiple versions belong to a document; citations bind to one version. |
| Passage and sentence | Passage identity, parent version, ordered text; numbered sentences with immutable version-scoped IDs and exact source text. Preserve text-PDF page numbers. Passage-to-entity links support search aggregation. Cleaning must preserve evidence meaning and traceability to the source. |
| Entity | Stable identity and type: person, unit/group, project, infrastructure or service as appropriate; canonical profiles/identifiers, names, affiliations, resolution confidence/conflicts, current/retired status, professional contacts. Units may have leaders/contacts without transferring unit expertise to those people. |
| Claim/fact and relationship | Subject entity, predicate/field, value or object entity, evidence references to version + sentence IDs, provenance and validation/support state. Explicit relationships only; preserve disagreement and uncertain identity rather than force a merge. Dates and contact status require evidence. |
| Search request/context | Text, requested entity type, optional company context, optional edited needs and explicit constraints; request/revision association for enrichment. User requirements and model suggestions remain distinguishable. Company context follows separate session/save rules and must not enter the public corpus or logs. |
| Search result | Ranked primary entity, linked supporting passages/claims, source URLs and exact sentences, score provenance sufficient for evaluation, dates/freshness, supported card fields, relevance reason and limitations. Up to ten distinct primary entities. Assessment is optional and separately validated; lack of enrichment is not a failed search. |
| Interpretation/assessment | Needs and expansions, or candidate category, need-by-need coverage, explanation, evidence references and unresolved questions. Bound to request revision and existing candidate identities. Schema-valid data still requires grounding checks. |
| Analyst feedback | Request/result/entity or claim reference as applicable; relevant / not relevant / wrong fact, selected/excluded state and needs edits as appropriate. Retain enough context for review/evaluation under the agreed retention policy; feedback does not trigger automatic retraining. |
| Coverage/job status | Source and job identity, snapshot scope, fetched/indexed/excluded/failed/unsupported counts and reasons, focus-area coverage including outside-focus content, timestamps, retries and freshness. Operator-visible logs must redact company inputs. |

Core integrity: a claim references existing entities and existing sentences in the cited version. Search results cannot cite another version's identically numbered sentence. A claim's exact quotation is resolved by code from evidence storage, never accepted as model-authored text. **Valid citation IDs and exact quotations do not establish semantic support.** Check the relation and interpretation separately; qualify or remove unsupported statements.

Resolution uses canonical profiles, identifiers and corroborated names plus affiliations. Do not merge on name alone. Preserve uncertain matches and conflicts for inspection. Necessary official professional contact details only; no inferred personal contact information. Suppression must cover relevant aliases/URLs/identities sufficiently to prevent re-ingestion; its representation and identity verification procedure remain undecided.

## 4. Approved numbered pipeline

The following step numbers match the approved pipeline. Every gate requires observable evidence before implementation can be called complete.

### Step 1 — Core: register sources and discovery rules

**Inputs:** supplied source inventory, starting URLs, allowed source boundaries and priorities.

**Processing:** load YAML configurations with labels, domain/path rules, language handling and crawl limits. Prioritise diabetes, oncology, neurology and medtech while covering all three required sources. New sources use this pipeline; document adapters for unusual layouts.

**Outputs:** source registry and discovery queue.

**Acceptance:** configurations represent UniBE, ARTORG and Diabetes Center Berne; discovery obeys boundaries and limits; a new small source can be configured through YAML; coverage explicitly reports indexed material outside focus areas. The actual inventory is an outstanding dependency.

### Step 2 — Core: fetch public content once

**Inputs:** discovery queue and source configurations.

**Processing:** use sitemaps and internal links; respect robots.txt, apply per-domain rate limits and never bypass access controls. Fetch HTML and text-based PDFs with page numbers. Preserve URLs, redirects, fetch dates, available modification dates and hashes. Enumerate scanned PDFs and unsupported JS-rendered pages; add adapters only where necessary.

**Outputs:** persistent local source snapshot and coverage report.

**Acceptance:** real pages from all required sources are traceable through stored provenance; exclusions/failures and unsupported formats are visible; crawl limits and rate policies are testable; subsequent searches use stored content with no per-query source fetch. No OCR or general browser-rendering capability is implied.

### Step 3 — Core: clean, classify and identify evidence

**Inputs:** versioned HTML/PDF text and provenance.

**Processing:** remove boilerplate, identify language duplicates, retain language variants under linked canonical records. Use URL patterns, headings and structure for cheap pre-LLM classification. Route person, group, project, infrastructure and service pages to Apertus; retain other usable pages as searchable passages. Split passages into numbered sentences.

**Outputs:** cleaned passages, immutable version-scoped sentence IDs, page types and extraction queue.

**Acceptance:** sample sentences resolve to exact stored text and PDF pages where applicable; recrawl versions cannot change old citation text; German/English variants stay traceable; usable non-extraction pages remain searchable; extraction routing is observable.

### Step 4 — Core: extract structured knowledge with Apertus 70B (8B fallback)

**Inputs:** routed passages, sentence IDs and extraction schema.

**Processing:** extract people, roles, affiliations, units, expertise, projects, infrastructure, services and explicit relationships. Use Apertus 70B for bulk extraction, with 8B as fallback (amended by D10, see note below). Require backend JSON-schema-constrained decoding, such as guided decoding or Outlines. Probe Keera capabilities before depending on them. Model responses contain sentence IDs, not quotations; code resolves text. Missing fields stay empty and group expertise is not assigned automatically to members.

**Outputs:** structured facts and relationships with sentence evidence.

> **Amendment D10 (2026-10-18; proposed by Ruihan, approved by Maxim and Dimitry).** The approved pipeline originally named 8B for bulk extraction. It was changed to 70B on this measured basis, recorded in [docs/extraction.md](extraction.md): same 11 real T06 `dev` pages (6 DBMR, 2 ARTORG, 3 DCB incl. one German), prompt `p2`, schema `x2`, one run per model. **Hand-checked non-name claim precision: 70B ~35/36 (~97%) vs 8B ~13/27 (~48%); persons found: 24 vs 0; wall time 62.1 s vs 9.2 s (~7× slower); tokens in/out 15,363/6,845 vs 13,314/5,304.** Limits of this metric: n = 11 pages, single run, single rater (Ruihan), no person-profile pages in the sample, 7 of the 70B correct claims are low-value (prize amounts); it is a decision input, not a benchmark. Extraction is offline and cached by content hash, so query latency is unaffected; the full-corpus run is bounded, resumable and announced to the team before use of the shared Keera key. T16/T20 re-measure extraction quality, tokens and cost on the `final` corpus; section 7 assumptions remain 8B-based and must be replaced by these measurements.

**Acceptance:** record endpoint capability probe and decoding mode; outputs pass schema and reference checks; samples preserve missingness and relationship boundaries. If the endpoint lacks constrained decoding, use schema validation with bounded retries, reject/quarantine invalid output and retain searchable passages. Report this as a weaker fallback, **not equivalent constrained-decoding compliance**. Retry bounds and schemas are pending choices. Never expose unvalidated extraction as fact.

### Step 5 — Core: resolve entities and minimise personal data

**Inputs:** extracted records, profile URLs/identifiers, names/affiliations and evidence.

**Processing:** merge corroborated identities; preserve uncertain matches and conflicting evidence. For units, display a documented leader or official professional contact where available, explicitly distinguishing that role from personal expertise. Store necessary professional information only. Establish a removal route and suppression list.

**Outputs:** consolidated evidence-backed entity profiles, conflicts and suppression controls.

**Acceptance:** duplicate and ambiguous-name cases show defensible resolution; contacts have supporting role evidence; a group match does not imply a person's expertise; removal/suppression can be exercised and documented in README; uncertain identities remain inspectable.

### Step 6 — Core: build persistent local search indexes

**Inputs:** entities, claims, passages, sentences and content hashes.

**Processing:** persist a local vector database or embedding index, BM25 index, structured entities and source evidence. Index profiles and original passages; cache enrichment by hash. Support changed-content reprocessing, removal retirement and failure retries. MVP manual refresh; production daily default and selected hourly refresh are configurable.

**Outputs:** reusable local knowledge base.

**Acceptance:** a restart can query stored state without another crawl; both passage and profile search work; changed/removed data updates derived indexes; transient failures do not immediately delete records. Document manual MVP operations separately from production refresh requirements and unimplemented automation.

### Step 7 — Core: accept requests through the fast path

**Inputs:** keywords, short questions or pasted company descriptions.

**Processing:** send plain queries directly to multilingual hybrid retrieval. Render initial cards without awaiting interpretation/assessment. Reserve clarification for genuinely broad requests and never block simple search on it.

**Outputs:** immediate search request and optional separately handled company context.

**Acceptance:** keyword search still returns cards with the LLM endpoint unavailable or slow; no query causes crawling; ordinary searches need no clarification; input supports text/paste and excludes document upload.

### Step 8 — Second layer: interpret needs and expand terminology

**Inputs:** request text, optional company context and user edits.

**Processing:** Apertus returns schema-constrained editable product/problem/competency needs, desired entity type and explicit constraints. Distinguish user requirements from suggestions. Expand across languages without adding requirements. Broad requests may receive a focused business-language clarification. Apply the constrained-decoding probe/fallback policy from step 4.

**Outputs:** editable needs and expanded queries.

**Acceptance:** suggestions are visibly separable and editable; terminology changes preserve original constraints; German/English variants work; interpretation failure leaves initial retrieval usable; schema and grounding validation apply before publication.

### Step 9 — Core: retrieve, consolidate and diversify

**Inputs:** original query, optional expansions, requested result type and local indexes.

**Processing:** combine BM25 and multilingual dense retrieval. Aggregate passage scores per entity using maximum or bounded top-k averaging, never an unrestricted sum that rewards prolific pages. Deduplicate entities and diversify near-equivalent candidates across units with relevance-aware MMR. Do not equalise institutional representation by sacrificing strong relevance.

**Outputs:** ranked candidates and source evidence, up to ten distinct primary entities of the requested type.

**Acceptance:** test prolific-entity bias and duplicates; requested types are respected; aggregation and diversification are documented and evaluated against relevance/coverage. Target first cards **within 3 seconds** under documented conditions, measuring median and p95. Fusion, aggregation selection, k and MMR parameters remain decisions; the latency target is not a guarantee.

### Step 10 — Second layer: assess candidates in batches

**Inputs:** bounded candidate batch, evidence and current needs.

**Processing:** use one batched assessment approach rather than one call per candidate. Default 8B; optional 70B only if measured benefits justify it. Produce schema-constrained direct match / related capability / insufficient evidence categories, need-by-need coverage, business-language explanations, sentence IDs and unresolved questions. Stream progress and publish validated assessments as ready. Apply step 4's constrained-decoding fallback and disclose it.

**Outputs:** personalised asynchronous assessments.

**Acceptance:** initial cards remain available throughout endpoint delay/failure; invalid assessments are withheld; category and need coverage are reviewable against evidence; batching and tokens are measured. Target complete enrichment **within 15 seconds**, subject to endpoint performance. Define timing boundaries and report median/p95; do not promise attainment without measurement.

### Step 11 — Core: validate grounding

**Inputs:** extracted facts, candidate claims, assessments and their evidence references.

**Processing:** validate entity IDs, sentence IDs and document versions; insert exact sentences through code. Check semantic support with deterministic relationship checks and optionally Apertus or an open NLI model. Remove or qualify unsupported claims. Treat source text as data, never system instructions. If evidence is absent, state that support was not found **in the indexed corpus**, offering narrowing or labelled related capabilities.

**Outputs:** grounded results with explicit limitations.

**Acceptance:** reject invalid/cross-version references; quotation fidelity is exact; a valid citation attached to a misleading claim can still fail support validation; unsupported claims are not presented confidently. Record sample-based support errors and limitations. No zero-hallucination claim follows from citation validity.

### Step 12 — Core: render structured cards and collect feedback

**Inputs:** validated entities, claims, evidence, dates and optional assessments.

**Processing:** display supported person/contact, role, affiliation, department/institute/group, expertise, projects, infrastructure/services, relevance reason, exact evidence and original URLs. Show source content/lastmod and fetch dates separately; flag stale evidence using the agreed threshold. Exclude known former staff from current contacts. Allow needs edits, result selection/exclusion and relevant / not relevant / wrong fact feedback; store for review and future evaluation, not automatic retraining.

**Outputs:** inspectable cards, analyst selections and reviewable feedback.

**Acceptance:** missing fields are empty rather than invented; evidence links and dates resolve; stale/former-staff cases behave correctly; feedback references the reviewed result/fact and can be retrieved for review; simple-card relevance explanations do not depend on generative enrichment.

### Step 13 — Stretch: export a concise brief

**Inputs:** analyst-selected validated results and reviewed needs.

**Processing:** generate a personalised one-page brief with optional references, supported matches, practical relevance and open discussion points. Email drafting comes last. Tracked edits distinguish analyst prose from source-backed facts. No automatic sending.

**Outputs:** reviewed brief/PDF and optional email draft.

**Acceptance:** one-page export uses selected validated content, unsupported additions are removed/qualified and provenance survives edits. This work starts after Core acceptance; its absence does not imply missing Core search.

### Step 14 — Core: demonstrate sovereign operation and maintenance

**Inputs:** corpus snapshot, local model/index/runtime assets, development endpoint and operator configuration.

**Processing:** use CSCS/Keera for development. Demonstrate local air-gapped querying using local embeddings, indexes and Apertus 8B with dependencies preloaded, network blocked and an unseen query. Provide a simple non-ML operator admin view for source configuration, coverage, failed jobs, logs and freshness. Expose manual refresh for MVP. Proposed defaults: session-only company inputs unless explicitly saved, redact them from logs and retain operational logs for 30 days. Retired public records leave serving indexes; copies/backups expire under a documented policy.

**Outputs:** tested deployment, operating instructions, lifecycle controls and offline proof.

**Acceptance:** satisfy the offline evidence protocol in section 5; operator can inspect coverage/failures/freshness and execute bounded refresh; verify redaction and removal behavior. Publish the retention decisions and limitations. If local Apertus cannot run, disclose that gap and do not call the full offline requirement satisfied. These controls do not constitute a legal-compliance claim.

### Step 15 — Core: measure throughput and estimate cost

**Inputs:** real extraction/query workload, endpoint/local configuration, token counts and billing assumptions.

**Processing:** benchmark Apertus 8B prefill and generation separately; measure batching, retries, embeddings and concurrent load. Replace illustrative assumptions with measurements. Distinguish marginal compute from allocated hosting and Keera pricing.

**Outputs:** measured latency/throughput and transparent cost worksheet.

**Acceptance:** report test environment, samples, workload, raw timings/token counts and calculation assumptions; costs include relevant idle capacity or clearly exclude it. Estimates in section 7 cannot be relabelled measured results.

### Step 16 — Core: evaluate quality, fairness and Apertus contribution

**Inputs:** 30–50 source-grounded queries, predefined gold entities and fixed corpus/configuration.

**Processing:** follow section 6: grouped development/evaluation split, variants/negative cases, entity-aware scoring, full component ablations and open cross-encoder comparison on a subset. Evaluate explanations, need coverage and direct/related/insufficient categories as Apertus contributions beyond ranking.

**Outputs:** reproducible evaluation, failure cases and component comparisons.

**Acceptance:** publish protocol, query/gold provenance, metrics with denominators/sample sizes, configurations and observed failures; preserve holdout independence and disclose missing components/comparisons. Building an evaluation harness alone is not producing evaluation results.

### Step 17 — Core: deliver demo and adoption evidence

**Inputs:** working source-grounded search, measured results, operating evidence and submission artifacts.

**Processing:** tell the fictional-company narrative in section 8; prepare recorded backup and Q&A. Explain Apertus's Swiss development, open weights, documented training provenance and multilingual design, and its documented respect for training-data opt-outs as analogous to responsible crawling. Verify those model claims against authoritative documentation before presenting them; embeddings also contribute to cross-lingual search, so measure Apertus separately. Include a pitch slide on professional-data minimisation, removal and retention.

**Outputs:** working demo, backup video, pitch, technical report and public repository.

**Acceptance:** artifacts meet deadline and size limits in section 1; demos use real source evidence and fictional company input; all jury claims have the evidence in section 8; backup video plays; submission availability is verified. Intended capabilities must not be presented as completed work.

## 5. Air-gapped query verification protocol

Preload a versioned public corpus snapshot; structured entities and sentence evidence; persisted BM25 and vector indexes; local multilingual embedding weights/tokenizer; Apertus 8B weights/tokenizer and local inference runtime; application dependencies, configuration and UI assets. Include any support model used on the demonstrated path. A cross-encoder/NLI dependency cannot silently call a remote service. Required hardware, quantisation, model licenses, memory fit and resource availability must be confirmed.

Prepare reproducible local startup/query instructions after implementation. Record model/index versions and machine specifications. Block network access with a documented method, including inference and telemetry paths. Run an unseen query and inspect initial cards, exact evidence and local Apertus behavior. Record observed latency and proof of network isolation/no remote calls. Capture logs or a recording that omit confidential inputs. Define how unseen queries are selected so they are not cached answers.

This demonstrates querying a snapshot, not offline crawling, current web coverage or general production readiness. A remote CSCS/Keera inference session alone is not air-gapped local proof. Missing local Apertus is an explicit unmet requirement, even if index-only querying works.

## 6. Evaluation protocol and targets

1. Freeze a documented corpus snapshot and define expected entities **before testing**. Obtain partner review of a small expected-match set when available; record reviewer/provenance and uncertainties.
2. Build 30–50 source-grounded queries spanning professional, lay and synonym wording; German/English cross-lingual variants; partial matches; absent-evidence queries needing abstention; and misleading near-matches. Group related variants in the same development/evaluation partition to avoid leakage.
3. Normalise equivalent identifiers/names with affiliation checks. A unit counts as an expected person only if the gold set explicitly accepts substitution; otherwise report a separate unit match. Do not improve Recall@10 through arbitrary person/unit substitution.
4. Keep evaluation conditions comparable across components. Record corpus, embedding model, Apertus version/quantisation, prompts/schemas, fusion/aggregation/MMR settings, batch limits and retrieval budgets. Use fixed gold labels and report subset selection for additional comparisons.
5. Run **BM25 → dense → hybrid → hybrid + Apertus expansion → hybrid + Apertus expansion + Apertus assessment**. Compare an open cross-encoder reranker on a documented subset. Report each configuration's measured quality and cost/latency; do not imply every step must improve ranking.
6. Review citation validity separately from semantic support and quote fidelity. Evaluate explanations, need coverage and direct/related/insufficient classifications to demonstrate purposeful AI beyond rank changes. Report error examples and sample sizes.

| Metric | Reporting requirement |
| --- | --- |
| Entity-level Recall@10 | Gold entities recovered among up to ten distinct primary entities; state aggregation across queries and handling of zero-gold queries. |
| Link coverage | Define denominator and report results with inspectable source links/evidence, plus broken/unavailable links. This is distinct from crawl coverage. |
| Evidence-support rate | Human or documented adjudication of claim support, denominator and sample size; report invalid citations and unsupported interpretations separately. |
| Field accuracy and completeness | Correctness of displayed fields and recovery of source-supported expected fields; missing evidence must not be scored as a fabricated complete answer. Define field-level denominators. |
| Correct abstention rate | Gold absent-evidence queries correctly receiving qualified absence/abstention; explicitly distinguish corpus absence from universal absence. |
| Exposure across institutes/units | Result exposure with relevance judgments and corpus coverage; no equal-exposure target regardless of relevance. |
| Performance and workload | Median/p95 first-card and enrichment latency, tokens/query, indexing time, extraction prefill/generation throughput, batching/retries and embedding time. |

Target first cards within 3 seconds and complete enrichment within 15 seconds. Measure from request acceptance to usable initial cards, and to completed validated enrichment respectively; report any different boundary explicitly. State hardware, network/endpoint, corpus size, concurrency, cold/warm cache, number of runs and failure/time-out handling. Targets are not benchmark facts. Exact metric formulas, review rubrics, success thresholds beyond the supplied targets, and evaluation split sizes require agreement during planning. No quality threshold is invented here.

## 7. Illustrative cost model — not measured facts

The approved pipeline supplies the following **illustrative assumptions requiring measurement**. They are reproduced as planning inputs, not verified throughput, current tariffs or a quote.

| Item | Illustrative value |
| --- | --- |
| Crawl | 5,000 pages |
| Routed to extraction | 40% = 2,000 pages |
| Average extraction tokens/page | 2,000 input + 300 output |
| Total extraction | 4 million input + 0.6 million output tokens |
| Assumed effective throughput | 1,000 input tokens/s; 50 output tokens/s |
| Extraction compute | About 4.4 GPU-hours; about 5.6 with 25% overhead |
| Enriched query | 8,000 input + 800 output tokens |
| Query compute | About 24 GPU-seconds at those assumed rates |

Arithmetic uses input tokens / input rate plus output tokens / output rate: 4,000 + 12,000 seconds for extraction, and 8 + 16 seconds per enriched query. Real prefill/generation, batching and concurrency may not behave like this serial approximation. These assumptions were written for 8B; after D10 bulk extraction uses 70B (~7× slower on the 11-page sample), so extraction compute must be re-measured rather than derived from this table.

The pipeline's SwissGPU reference assumes an RTX 4090 VM at **CHF 0.40/hour**, electricity separate: approximately CHF 292/month continuously running at 730 hours/month. Its illustrative total **CHF 380–445/month** assumes 0.4–0.7 kW average use, but the electricity tariff/billing basis is not specified and must be verified. Quantised 8B memory fit and throughput need tests. Current provider availability/pricing has not been verified in this documentation work; Keera pricing is separately unconfirmed.

At these assumptions, extraction compute is roughly CHF 2–3 and marginal query compute below CHF 0.005. These exclude idle capacity and are not end-to-end costs. Actual cost/query must allocate monthly hosting, include electricity and measured utilisation, embeddings, retries and other relevant operations. Report currency, price source/date, workload, hardware and inclusions/exclusions in the eventual worksheet.

## 8. Demo narrative and jury evidence

Use one fictional company story grounded in real indexed pages:

1. Run the same lay query in native site search or `site:unibe.ch` and Bern Match; label differences in source scope and snapshot timing.
2. Inspect a match, exact source sentences and original URLs.
3. Show an honest partial match or abstention with indexed-corpus limitations.
4. Run a German query retrieving English evidence; ideally demonstrate the reverse too. Both cross-lingual directions remain product/evaluation requirements even if the short demo shows only one.
5. Add a small website through YAML and perform bounded ingestion live. This is explicit source extension, not per-query crawling.
6. Show measured metrics, transparent operating cost assumptions and air-gapped evidence.

The ≤2-minute video is also the recorded backup. Prepare Q&A on LLM versus reranker, monthly cost, offline proof, removal requests, fairness and grounding limits. The pitch includes one minimisation/removal/retention slide. Claims about Apertus training provenance and opt-outs require authoritative references before inclusion in submission material.

| Jury criterion | Required evidence and supporting changes |
| --- | --- |
| Purposeful AI | Structured extraction, measured expansion/assessment contribution, business-language explanations and need coverage; constrained decoding mode/fallback disclosed; distinguish embedding and Apertus cross-lingual effects. |
| Technical rigour | Immutable sentence evidence plus semantic-support checks; benchmarks, error analysis, full ablations and cross-encoder subset; measured median/p95 latency; fair aggregation and relevance-aware diversification. |
| Value, cost & scalability | Reusable local search, selective page routing, batching and 8B default; cost worksheet including monthly allocation; observed workload and latency rather than speculative savings. |
| Sovereign deployability | Recorded local network-blocked unseen query with local models/indexes; open-component inventory and Swiss inference option; explicit gaps if local Apertus is unavailable. Crawling/data controls support the design without proving compliance. |
| Implementation feasibility | Configurable sources and live bounded extension; simple non-ML administration; manual MVP refresh versus production schedules; freshness, professional-contact rules, removal and reviewable feedback. |
| Pitch & presentation | One coherent company story, multilingual proof, inspectable evidence and honest abstention; accessible metrics; playable backup; complete size-limited artifacts. |

These evidence requirements preserve the approved changelog's rationale: fast path and tiers support feasibility; routing/batching support cost; sentence IDs/constrained outputs support rigour; exposure analysis supports adoption; multilingual ablations support purposeful AI; administration and refresh support operation; expanded gold data/live extension support demonstration quality.

## 9. Decisions, external blockers and unresolved tensions

### Approved requirements — not open for silent redesign

All 17 steps and their tier labels above; three-source coverage; four focus areas with outside-focus reporting; text-only input; one initial crawl and persistent indexes; no per-query crawling; non-blocking retrieval; sentence-ID grounding plus support checks; 70B bulk extraction with 8B fallback (D10, amended from 8B); constrained decoding with explicitly weaker fallback; multilingual hybrid retrieval and fair aggregation/MMR; manual MVP refresh; production refresh/removal policy; full evaluation comparisons; local air-gapped proof; submission requirements. Do not introduce extra infrastructure or broaden scope without a recorded decision.

### Implementation choices still to be decided

- Minimal stack, repository structure, persistent storage/index implementations, multilingual embedding model and local runtime/hardware configuration. No installation commands or deployment capability is currently established.
- Concrete contracts/identifier formats, schema versioning, error/missing-value semantics, API/asynchronous delivery transport and ownership; later planning must agree these before independent implementation.
- Extraction/assessment schemas, prompts, token/batch/retry limits; capability-probe procedure; fallback visibility and acceptance impact.
- Hybrid fusion, max versus top-k entity aggregation, k, MMR relevance tradeoff and evaluation rubrics/metric denominators.
- Source adapters and discovery limits after receiving/inspecting the inventory; focus classification and coverage definitions.
- Freshness threshold, current/former-contact adjudication, retry/removal confirmation, suppression matching, reachable removal-request route and handling responsibility.
- Public record/version/cache/backup retention periods and deletion propagation; explicit-save behavior and retention for saved company input/feedback. Thirty-day operational logs and session-only inputs are proposed defaults, not established controls.
- Public deployment target, credentials management, local assets and reproducible network-blocking proof; demo execution environment and artifact packaging.

### External blockers and dependencies

- **Source inventory:** the approved pipeline refers to a supplied inventory, but neither attachment nor the inspected repository contains its concrete URLs/rules. Coverage and crawl estimates cannot be confirmed without it.
- **CSCS/Keera endpoint:** working details, model access, practical throughput/concurrency limits, structured-output capabilities, price and continued judging availability require organiser confirmation. No credentials are present or presumed.
- **Partner review:** arrange review timing and a small expected-match set with the partner; unavailable review must be disclosed.
- **Confidential inputs:** confirm whether CSCS processing is approved for real company profiles and which logging/retention rules apply. Use fictional profiles until confirmed.
- **Local execution:** obtain suitable hardware, permitted Apertus/embedding weights, dependencies and sufficient storage before promising air-gapped proof.
- **Sources and submission:** source accessibility/robots/layout constraints, actual public hosting/repository access and organiser submission mechanism need verification.

### Important tensions to resolve before task planning

- Constrained decoding is required, yet endpoint support is unknown. Validation/retry is an approved fallback but cannot be described as the same guarantee; decide how to report the remaining requirement gap.
- Expansion and assessment are Second layer while the full ablation is required Core evaluation evidence. Allocate time to exercise them or disclose incomplete evaluation; do not silently promote them or drop comparisons.
- Full local proof includes Apertus 8B, unlike endpoint-backed development. Hardware availability is a separate blocker and cannot be hidden behind an index-only demonstration.
- Immutable evidence identity and removal/retention coexist: preserve citation identity without retaining suppressed text indefinitely. Concrete deletion and unavailable-citation behavior needs a shared contract.
- The illustrative enriched-query compute is 24 GPU-seconds, exceeding the 15-second enrichment target under a simple serial single-device interpretation. Batching/concurrency/endpoint performance may differ; only measurement can resolve this, and the target must not be claimed achieved.
- Full Core scope plus evaluation and submission work is substantial for three developers before the deadline. Assess feasibility in the next planning step, reserve delivery time and propose explicit cuts in tier order rather than silently weakening Core.

No benchmark results, legal findings, verified model/provider claims or completed deployment capabilities are established by this document. Record measured facts with reproducible evidence as implementation progresses.
