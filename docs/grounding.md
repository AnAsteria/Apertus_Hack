# Entity resolution and grounding (T08)

Refs #8. Owner: workstream B (Ruihan). Status: **implemented and unit-tested; run once on the small real T06 `dev` crawl + T07 70B extraction and hand-checked.** Stacked on T07 (#52).

## Flow

```bash
python -m app.grounding --data-dir data --extraction data/extraction/apertus-v1-5-70b.jsonl
```

1. **Load** every active page from `CorpusStore.active_records()` (T06 stubs, language-variant links, source labels) plus T07's per-page entities and pending claims.
2. **Resolve entities** (`app/entities/resolve.py`). Every rule needs corroboration; a bare name match is never enough:
   - **A, page anchor:** a T07 entity and a T06 stub on the same page, same type, each the other's *unique best* name match. Partial matches count only for similar-length names, or when the short name is a whole segment of a "Name – Subtitle" page title.
   - **B, language variant:** the single stub of a type on two pages that T06 linked as variants.
   - **C, organisations:** same type, same name or alias (incl. parenthetical abbreviation), and a shared source label or canonical profile.
   - **D, persons:** same title-free full name (≥ 2 tokens) and a shared profile or shared affiliation/membership target. Same-name persons without that are kept apart and listed in `possible_duplicates`.

   The canonical ID is a stub ID when one exists, so T09 v1 references stay valid. All merged-away IDs go in `alias_entity_ids`. The display name is the extracted name rather than the page title ("Department for BioMedical Research (DBMR)", not "Research - Department for BioMedical Research"). Claims are rewritten to canonical IDs, duplicates merge their evidence, and relations collapsed by a merge are dropped.
3. **Check support** (`app/grounding/support.py`). Every claim starts `pending`:
   1. **Evidence:** every evidence pair must resolve through `CorpusStore.get_sentence` to stored text. Cross-version or missing IDs give `unsupported` (`evidence_unavailable`).
   2. **Rules** for what code can decide alone:
      - `name` and `official_contact` must appear verbatim in the evidence.
      - `role` must be verbatim AND the person must be named in the same evidence.
      - Person `expertise` requires the person to be named, so a group's expertise is never transferred to its members. The surname check ignores other entities' names, so "Example" inside "Example Lab" doesn't count.
      - `leader`, `member_of` and `role` require a person subject.
   3. **Batched Apertus judge** (default `APERTUS_QUALITY_MODEL`, 12 claims per call, prompt `j1`) for expertise/project/infrastructure/service and all relations. It sees a code-built statement ("Anna Example leads Example Lab.") and the exact evidence sentences. Verdict `supported`, `reversed` or `unsupported`; reversed and unsupported both become `unsupported`. If the judge is unavailable, claims **stay `pending`** and never reach cards.
4. **Finalize:** `claim_ids`, `contact_claim_ids`, and `affiliation_entity_ids` from *supported* relations only.
5. **Card fields** (`app/grounding/fields.py`): `{field: [{claim_id, value}]}` from supported/qualified claims only, with values copied by code (D1). Fields: `role`, `expertise`, `projects`, `infrastructure`, `services`, `official_contact`, `affiliation`, `part_of`, `leads`, plus inverse fields on the object's card (`led_by`, `members`, `includes`). A unit's leader or contact is shown as such, never as expertise. `missing_fields()` returns the absence text "Not found in the indexed sources."

**Output** in `data/knowledge/` (git-ignored), the handoff for T09 v2 / T11: `entities.jsonl`, `claims.jsonl`, `cards.jsonl` (`{entity_id, fields}`), `report.json`.

## Real run (2026-10-18, single run, hand-checked by Ruihan)

Input: 29 stored pages (artorg, dcb, unibe-dbmr; `dev`, `--max-pages 10`), 43 T06 stubs, T07 70B extraction of the 11 routed pages (71 entities, 107 claims).

| | Result |
| --- | --- |
| Entities in → out | 114 → 97 (merges: A 3, B 3, C 11; persons D 0) |
| Possible duplicates kept apart | 1 ("Benedetta Coppe" on two pages without shared affiliation) |
| Claims in → out | 107 → 101 (duplicates merged) |
| Support | 97 supported, 4 unsupported (all by the judge); 0 left pending |
| Judge | 3 calls, ~3.2k / 0.5k tokens; whole run ~120–140 s, almost all judge latency |
| Cards with fields | 27 |

**What the hand check found:**
- **Caught by the judge:** the inverted relation from T07 ("DCB part_of TIMES study"), and a project claim whose only evidence was the page title.
- **Arguably too strict:** one rejection, "SPN-005 expertise: painless glucose monitoring", where the project description supports it.
- **Bugs fixed during the run, each with a regression test:**
  1. The page-anchor rule attached both "DBMR" and "Prize for Best DBMR Publication" to one stub, and a short name inside a long title anchored ("dbmr" in "Prize for Best DBMR Publication").
  2. T07 resolved a misspelled prize subject to DBMR by containment. That T07 fix (`app/ai/extract.py`, `_contains_name`) is included in this branch.

  Before the fixes, the DBMR card wrongly listed "projects: CHF 2'000 prize"; it now shows only its three expertise values.
- **Remaining low-value cards:** prize entities with "projects: CHF 1'000/2'000 prize". They're correctly attributed, but come from T06 routing event/prize pages as `unit` (feedback in #52).

## Limitations / next steps

- Small sample with no real person profile pages, so rule D was not exercised on real data.
- Judge latency (~40 s per 70B batch observed here) must be measured in T16. Extraction and grounding are offline, so query latency is unaffected, but a `final` crawl needs a time budget. 8B as judge is untested.
- `qualified` support is not produced yet (claims are supported or unsupported).
- Current/former contact status stays `unknown`; no source here documents it.
- Removal/suppression is T12's scope; resolution keeps alias IDs so suppressed records can be traced.
