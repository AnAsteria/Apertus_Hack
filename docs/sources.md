# T02 — Public source audit and proposed discovery inventory

Related issue: [#2](https://github.com/AnAsteria/Apertus_Hack/issues/2). Audit date: **18 October 2026**. This is a bounded source inspection, not crawler implementation, an indexed corpus, coverage measurement or legal approval. The user explicitly authorised this task without a separate dispatcher grant; this exception applies only to #2.

## 1. Inventory status and handoff boundary

No organiser-supplied URL inventory was found among the tracked repository files or the specifications supplied in this chat. The approved architecture names UniBE, ARTORG and Diabetes Center Berne but does not supply their complete allowed paths. The inventory below is therefore **proposed from inspected public institutional pages**, not represented as the missing organiser inventory.

**Outstanding acceptance dependency:** the partner/organiser or authorised project owner must confirm this inventory or provide the original list. Do not mark #2 fully accepted merely because this audit is prepared. T06 must also wait for its T04 dependency and an explicit task authorisation. No crawling or indexing is implemented here.

UniBE is represented initially by a bounded Department for BioMedical Research (DBMR) slice. This is not full University coverage. ARTORG belongs to UniBE institutionally but is a separate required source label: store each document once, preserve affiliations and prevent double-counting the same entity across source labels. DCB links to university/partner sites; a link does not expand the allowlist.

## 2. Inspected seed pages

IDs here are human-readable audit references, **not production entity/document/sentence IDs**. Language and page classification describe the inspected main content. Links are primary institutional sources. All dates below distinguish inspection time from source age.

| Audit ID | Source / language / type | Inspected URL | Purpose and boundary |
| --- | --- | --- | --- |
| S00 | UniBE / EN / directory | [Faculties & Institutes](https://www.unibe.ch/facultiesinstitutes/index_eng.html) | Institutional discovery reference; not a seed for crawling the entire university. |
| S01 | UniBE–DBMR / EN / directory | [Research](https://www.dbmr.unibe.ch/research/index_eng.html) | Initial discovery entry; useful links exist in server-returned HTML. |
| S02 | UniBE–DBMR / EN / programme directory | [Research Programs](https://www.dbmr.unibe.ch/research/research_programs/index_eng.html) | Cancer Therapy Resistance and Regenerative Neuroscience unit candidates; one long page contains several programmes, so headings and passage boundaries matter. |
| S03 | ARTORG / EN / group directory | [Research](https://www.artorg.unibe.ch/research/index_eng.html) | Group discovery, affiliated groups and explicitly former groups; external affiliations are not crawl permission. |
| S04 | ARTORG / DE / group directory | [Forschung](https://www.artorg.unibe.ch/forschung/index_ger.html) | Linked language variant of S03; lists differ, so do not collapse text as identical. |
| S05 | ARTORG / EN / group | [AI in Health and Nutrition](https://www.artorg.unibe.ch/research/aihn/index_eng.html) | Group identity and official contact; linked research activity supplies more specific expertise. |
| S06 | ARTORG / EN / research activity | [Adaptive Diabetes Management](https://www.artorg.unibe.ch/research/aihn/research_activities/adaptive_diabetes_management/index_eng.html) | Diabetes/medtech seed linked from S05; retain page-to-group relationship. |
| S07 | ARTORG / EN / group | [Neuro Robotics Group](https://www.artorg.unibe.ch/research/nrg/index_eng.html) | Neurosurgical robotics unit; contact role is separate from personal expertise. |
| S08 | DCB / EN / project directory | [Research](https://www.dcberne.com/en/projects/) | Project discovery; publication abstracts and project cards share the page and should not be conflated. |
| S09 | DCB / DE / project directory | [Forschung](https://www.dcberne.com/de/projekte/) | Linked language variant of S08; German path is not a mechanical translation of English path. |
| S10 | DCB / EN / project | [SPN-005 pilot study](https://www.dcberne.com/en/project/spn-005-pilot-study-on-painless-glucose-monitoring/) | Diabetes/medtech project with explicit limits on readiness; displayed publication date 9 October 2025, project years 2023–2024. |
| S11 | DCB / DE / project | [SPN-005 Pilotstudie](https://www.dcberne.com/de/project/spn-005-pilotstudie-zur-schmerzfreien-blutzuckermessung/) | Linked German project evidence for EN→DE retrieval; preserve wording separately from S10. |
| S12 | ARTORG / EN / PDF | [Research Portfolio, filename dated 2025-08-25](https://www.artorg.unibe.ch/unibe/portal/fak_medizin/dept_weitere/ins_artorg/content/e212002/e861724/20250825_ARTORG_ResearchPortfolio_web_eng.pdf) | Linked from S03/S04; PDF reader exposed text on a 13-page document. Use as a text-PDF parser candidate, not proof that T06 already extracts pages correctly. Filename date is not verified lastmod. |

The English project date and project-period fields on S10 illustrate why a new fetch cannot establish current activity. Do not infer current availability, market readiness, personal expertise or consent to outreach from these sources. Necessary professional-contact information may be read from official pages later; no bulk contact list is copied into this audit.

## 3. Proposed bounded source configuration

The JSON below is also valid YAML 1.2. It follows the required fields in [CONTRACTS §2](CONTRACTS.md#2-source-configuration-and-discovery), but is documentation only: **not an installed configuration or an approved organiser inventory**. Budgets are conservative proposed limits, not observed coverage. Each source needs its own robots check; caps apply across all jobs on a domain. No automatic refresh scheduler is introduced.

```json
[
  {
    "schema_version": "1",
    "source_id": "unibe-dbmr",
    "label": "UniBE — DBMR initial slice",
    "start_urls": ["https://www.dbmr.unibe.ch/research/index_eng.html", "https://www.dbmr.unibe.ch/research/research_programs/index_eng.html"],
    "allowed_domains": ["www.dbmr.unibe.ch"],
    "allowed_paths": ["/research/"],
    "languages": ["en"],
    "max_pages": 25,
    "max_depth": 2,
    "requests_per_second": 0.5,
    "focus_areas": ["diabetes", "oncology", "neurology", "medtech"],
    "refresh_default_hours": 24
  },
  {
    "schema_version": "1",
    "source_id": "artorg",
    "label": "ARTORG",
    "start_urls": ["https://www.artorg.unibe.ch/research/index_eng.html", "https://www.artorg.unibe.ch/forschung/index_ger.html"],
    "allowed_domains": ["www.artorg.unibe.ch"],
    "allowed_paths": ["/research/", "/forschung/", "/unibe/portal/fak_medizin/dept_weitere/ins_artorg/content/e212002/e861724/"],
    "languages": ["en", "de"],
    "max_pages": 30,
    "max_depth": 2,
    "requests_per_second": 0.5,
    "focus_areas": ["diabetes", "oncology", "neurology", "medtech"],
    "refresh_default_hours": 24
  },
  {
    "schema_version": "1",
    "source_id": "dcb",
    "label": "Diabetes Center Berne",
    "start_urls": ["https://www.dcberne.com/en/projects/", "https://www.dcberne.com/de/projekte/"],
    "allowed_domains": ["www.dcberne.com"],
    "allowed_paths": ["/en/projects/", "/de/projekte/", "/en/project/", "/de/project/"],
    "languages": ["en", "de"],
    "max_pages": 20,
    "max_depth": 2,
    "requests_per_second": 0.5,
    "focus_areas": ["diabetes", "oncology", "neurology", "medtech"],
    "refresh_default_hours": 24
  }
]
```

Path matching must be prefix-boundary aware, with domain checks before and after redirects. Keep query/fragment URL normalisation compatible with T01; never use string-substring host matching. Refuse private/internal addresses and unsupported redirect destinations. Drop fragments for fetch identity but keep section locators for evidence review. Same-page programme anchors in S02 are not separate fetched documents.

Discover internal links within these budgets; S12 is an explicitly reviewed asset exception, not permission for all of `/unibe/`. DCB's sitemap can suggest URLs, but every URL still passes the project-path/domain allowlist. Do not recursively follow partner domains, DOI publishers, social media, login pages or patient-data systems. A denied/unknown robots state is recorded and resolved before automated crawl rather than bypassed.

## 4. Robots and discovery observations

Direct HTTPS checks of [DBMR robots](https://www.dbmr.unibe.ch/robots.txt), [ARTORG robots](https://www.artorg.unibe.ch/robots.txt) and [DCB robots](https://www.dcberne.com/robots.txt) returned **200 text/plain**. The DBMR and ARTORG responses had identical SHA-256 `ef2b9b85becda1061225cf59e6445ccb1c77031e1dbd057bfe3ac499fcf4d9ab` during this audit. Fetch again before ingestion; this is a snapshot, not permanent authorisation.

DBMR/ARTORG wildcard rules exclude service/AJAX/schema endpoints, management/preview routes, `index.html`, print variants and search/navigation pages. They also exclude language-specific **HTML sitemap pages**, not all possible XML sitemap paths. Do not use the forbidden HTML sitemaps for discovery. No XML sitemap was declared in the inspected DBMR/ARTORG robots bodies; use allowed internal links rather than inventing a sitemap URL. Their bot-specific full-deny rules apply to named bots; do not impersonate a different bot to evade restrictions. Use an honest project user agent and apply the applicable wildcard group.

DCB excludes WordPress administration/includes/plugins/themes/cache, CGI/feed/comment/search routes and several event-query patterns; uploads are explicitly allowed by robots but still require the project's allowlist. Multiple wildcard groups must be combined correctly. It declares [sitemap_index.xml](https://www.dcberne.com/sitemap_index.xml). Neither a robots allow rule nor public accessibility establishes legal compliance.

T06 must handle wildcard `*`, terminal `$`, group merging and allow/disallow precedence using a suitable tested parser. Do not assume a simplistic standard-library parser matches all observed patterns. Manually reviewed seed paths above avoid the observed exclusions; this does not validate a future crawler's robots implementation.

## 5. Classification, formats and coverage gaps

- Focus candidates: S06/S10/S11 diabetes and medtech; S07 neurology-related surgical robotics/medtech; S02 oncology and regenerative neuroscience. These are evidence-based routing candidates, not exhaustive domain labels or clinical endorsements.
- Outside-focus example: S02 also includes infection/nephrology programmes. Preserve usable passages and report outside-focus counts after ingestion rather than excluding them invisibly. No indexed counts exist yet.
- Direct HTML responses expose the audited headings/content without a browser adapter. Do not conclude every page on these sites is server-rendered. Boilerplate, nested headings, repeated programme labels, project-card summaries and publication abstracts need separation.
- S03 explicitly separates former research groups; S04 is not identical to S03. Historical programme/portfolio content must not automatically become current contacts.
- S12 is a verified PDF/text-extraction candidate. A complete local PDF extraction/page-number test belongs to T06. No scanned-PDF or JS-only research page was confirmed in this bounded sample: **unknown, not zero unsupported pages**. On discovery, list those cases in coverage; OCR/browser-rendering implementation is not added here.
- External affiliated labs on other domains are excluded until specifically configured and approved. Their links can remain provenance, but cannot silently widen three-source coverage.

## 6. Verification record and unresolved decisions

The appendix below records direct HTTP probes, distinct from search-engine cached text inspection. A temporary audit script used `curl -sS -L --max-time 25 -A 'BernMatchSourceAudit/0.1 (bounded public source inspection)'` with a two-second delay between requests; it recorded status, effective URL, content type, body SHA-256 and main text. It followed only this enumerated list, not discovered links. It did not ingest a corpus or retain cookies/secrets in Git.

The first Python urllib attempt failed certificate verification because its local CA bundle was unavailable; no TLS verification was disabled. The retry used system curl with normal TLS verification. PDF page/text readability was inspected through the web PDF reader, not a local T06 parser. No application/unit tests were needed for two documentation files; structural/manifest/evidence checks are recorded below.

Open decisions: confirm original/proposed inventory; approve narrow budgets and scope; agree contact freshness/retention policies through T01; approve any external-domain adapters; perform T06 real corpus/parser checks and T14 full gold-set review. Keep these limitations in issue #2 and the PR; do not close automatically.


### HTTP audit appendix

Successful curl pass: **2026-10-18 12:31:03–12:31:38 UTC** (14:31 Zurich). All 17 listed URLs returned HTTP 200 with unchanged effective URLs. No response headers/cookies or full third-party pages are committed. The hashes identify only the inspected response bytes; they are not production version IDs.

| URL | Content type | Bytes | SHA-256 |
| --- | --- | --- | --- |
| [https://www.dbmr.unibe.ch/robots.txt](https://www.dbmr.unibe.ch/robots.txt) | text/plain | 1190 | `ef2b9b85becda1061225cf59e6445ccb1c77031e1dbd057bfe3ac499fcf4d9ab` |
| [https://www.artorg.unibe.ch/robots.txt](https://www.artorg.unibe.ch/robots.txt) | text/plain | 1190 | `ef2b9b85becda1061225cf59e6445ccb1c77031e1dbd057bfe3ac499fcf4d9ab` |
| [https://www.dcberne.com/robots.txt](https://www.dcberne.com/robots.txt) | text/plain | 1031 | `f6bd42e3550e21eec766c86219cebd5b4ab3d320a7ab04c3767e67eb023fb2fd` |
| [https://www.unibe.ch/facultiesinstitutes/index_eng.html](https://www.unibe.ch/facultiesinstitutes/index_eng.html) | text/html | 57859 | `0c290786cb13c7a8b0e46946ea39f8cb61609972bbf2bc493f5a5695a56b0c1f` |
| [https://www.dbmr.unibe.ch/research/index_eng.html](https://www.dbmr.unibe.ch/research/index_eng.html) | text/html | 42713 | `9f98e5b7e7d343da115ad4e01c42e781919d9b2d59a948216753a67ac059d7c4` |
| [https://www.dbmr.unibe.ch/research/research_programs/index_eng.html](https://www.dbmr.unibe.ch/research/research_programs/index_eng.html) | text/html | 112569 | `c470d611117d71b0bda884a193c5356d7cb66664363ba3d9122dc3aab08813e5` |
| [https://www.artorg.unibe.ch/research/index_eng.html](https://www.artorg.unibe.ch/research/index_eng.html) | text/html | 29405 | `a03b4d2537a9a591d74beec75c43f10632d45d95a63e1c36729a9f09476f7569` |
| [https://www.artorg.unibe.ch/forschung/index_ger.html](https://www.artorg.unibe.ch/forschung/index_ger.html) | text/html | 28560 | `e7137d9bd011eba0df49e58bea7976b58c594ad3cb7cb21b40c62f522b535868` |
| [https://www.artorg.unibe.ch/research/aihn/index_eng.html](https://www.artorg.unibe.ch/research/aihn/index_eng.html) | text/html | 33664 | `0ec28d74ff305b22c1d621e0f0d66ecfc19ddca6b7ffc123e2f8e96f426c3c51` |
| [https://www.artorg.unibe.ch/research/aihn/research_activities/adaptive_diabetes_management/index_eng.html](https://www.artorg.unibe.ch/research/aihn/research_activities/adaptive_diabetes_management/index_eng.html) | text/html | 30862 | `994e35863b785b18cfdc790f3bdae24013497f874f91352dd47a73fbcac599f2` |
| [https://www.artorg.unibe.ch/research/nrg/index_eng.html](https://www.artorg.unibe.ch/research/nrg/index_eng.html) | text/html | 28230 | `96505982ec329ef2fbd40be5b2bfb51e5a1e1f7762cb28c8158831b43243d19c` |
| [https://www.dcberne.com/en/projects/](https://www.dcberne.com/en/projects/) | text/html | 353390 | `a35c9b11b4ac8bff698e05af5c011828911a11c31c671610954132d1f7a30786` |
| [https://www.dcberne.com/de/projekte/](https://www.dcberne.com/de/projekte/) | text/html | 445562 | `2cd04dd20a1a8fb67635e5fb4d61c2e2a15bd9d2410e421358a27c462451efe3` |
| [https://www.dcberne.com/en/project/spn-005-pilot-study-on-painless-glucose-monitoring/](https://www.dcberne.com/en/project/spn-005-pilot-study-on-painless-glucose-monitoring/) | text/html | 133984 | `d3e6f373a7f022bf974a4299a50de7703e3ecd91cb662e5c495ea5dec3d7ba9d` |
| [https://www.dcberne.com/de/project/spn-005-pilotstudie-zur-schmerzfreien-blutzuckermessung/](https://www.dcberne.com/de/project/spn-005-pilotstudie-zur-schmerzfreien-blutzuckermessung/) | text/html | 226210 | `e3ab05347a87c496efe9b45c851e3e552e79a4880f06a911daa5d003447d51b9` |
| [https://www.artorg.unibe.ch/unibe/portal/fak_medizin/dept_weitere/ins_artorg/content/e212002/e861724/20250825_ARTORG_ResearchPortfolio_web_eng.pdf](https://www.artorg.unibe.ch/unibe/portal/fak_medizin/dept_weitere/ins_artorg/content/e212002/e861724/20250825_ARTORG_ResearchPortfolio_web_eng.pdf) | application/pdf | 786059 | `c5ea77a298f7a4309af7f176461a0e25abbce165d011815b3ee0571fddda91ec` |
| [https://www.dcberne.com/sitemap_index.xml](https://www.dcberne.com/sitemap_index.xml) | text/xml | 783 | `8881c38e0ed71ca347d71655a36569dc039e506b7f4f2266b5b887642f69c18b` |

For each URL above, reproduce status/effective URL/type with `curl -sS -L --max-time 25 -A 'BernMatchSourceAudit/0.1 (bounded public source inspection)' -o /tmp/bern-source-body -w '%{http_code} %{url_effective} %{content_type}\n' URL`, then `shasum -a 256 /tmp/bern-source-body`. Wait at least two seconds between requests to a domain. Hashes can change with source updates or dynamic content; a mismatch is a reason to inspect/version, not evidence of a retrieval failure.

Verification completed on the prepared documentation: JSON registry parses; three unique source IDs and required source fields exist; start URLs fit their configured host/path boundaries; all inspected URLs have successful audit records; direct HTML contains the reviewed programme/group/project locators; DCB sitemap is parseable XML; PDF response has `%PDF-` signature; local Markdown links resolve; whitespace check passes. These checks validate this audit artifact, not application functionality or the completeness of the future corpus. No bulk crawl, benchmark, model inference or local PDF-parser test was run.

