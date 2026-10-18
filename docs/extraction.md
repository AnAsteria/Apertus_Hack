# Structured extraction (T07) — DRAFT

Refs #7. Owner: workstream B (Ruihan). Status: **implemented and unit-tested; run once on a small real T06 `dev` crawl (11 extractable pages) with 8B and 70B and hand-checked.** Not yet run on a `final` crawl.

## Flow

`extract_page(version, sentences)` in `app/ai/extract.py`:

1. **Route:** only `active` versions with `page_type` in `person|unit|project|infrastructure|service`. Others are `skipped` with a reason and stay searchable as passages.
2. **Withhold suspicious text:** sentences that look like instructions to an AI ("ignore previous instructions", "you are an assistant", DE/FR variants) are replaced with `(sentence withheld)` and listed in `flagged_sentence_ids`.
3. **Prompt:** system rules plus one worked example, then the page as numbered sentences `[1] … [n]`, up to 80 per call (longer pages are split into windows).
4. **Call:** `client.complete_json(..., PageExtraction)` on 8B by default. Decoding mode (`backend_constrained` / `validated_retry_fallback`) is recorded per window.
5. **Ground in code:** local numbers are mapped to stored sentence IDs, and anything that fails a rule is dropped and counted in `stats`.
6. **Records:** provisional `Entity` (`resolution_state: uncertain`, `status: unknown`) and `Claim` (`support: pending`) with deterministic IDs, plus a `name` claim per entity. T08 merges entities and checks semantic support.
7. **Never raises:** endpoint or schema failure gives `status: quarantined` with `reason` (e.g. `inference_unavailable`, `inference_bad_output`).

`extract_pages()` runs pages concurrently up to `APERTUS_MAX_CONCURRENCY`. `ExtractionCache` stores validated model output per window under a key of content hash + parser version + model + schema version (`x2`) + prompt version (`p2`) + window, so a final-profile re-crawl only re-extracts new or changed pages.

## Model-facing schema (`app/ai/schemas.py`, `x2`)

Three closed lists: `entities {name, kind, sentences}`, `attributes {subject, predicate, value, sentences}`, `relations {subject, predicate, object, sentences}`. Sentence numbers only, never quotes.

Schema `x1` used a single fact type with both `value` and `object`. Live, 8B filled both in 4 of 4 facts, so code rejected them all. Splitting the lists makes the mix impossible under constrained decoding.

## Code-level grounding rules (all unit-tested)

| Rule | Drop reason |
| --- | --- |
| Sentence number outside the window or withheld | `invalid_sentence_ref` |
| Entity name not in any cited sentence | `name_not_in_cited_sentence` |
| Attribute/relation subject or object not in the entity list | `unknown_subject` / `unknown_subject_or_object` |
| Person expertise where no cited sentence names the person (full name, or surname as a whole word outside other entity names) | `group_expertise_not_transferred` |
| `role` on a non-person, or role text not verbatim in the cited sentence | `role_subject_not_person` / `role_not_verbatim` |
| `leader` / `member_of` with a non-person subject | `relation_subject_not_person` |
| `official_contact` with no email/phone in the cited sentence (the value is read by regex, never taken from the model) | `contact_not_in_sentence` |

## Live check (2026-10-18, fictional pages, n = 1 each — not a quality measurement)

Two six-sentence fictional pages (EN, DE) about a sensor group, its leader, a contact and a lab/project.

| Model / prompt | Latency | Tokens (in/out) | Observed |
| --- | --- | --- | --- |
| 8B, x2/p1 (no example) | 1.9–2.7 s | ~490 / 280–410 | Missed people; mislabelled ("role: Professor" on a unit, "service: Kontakt") |
| 70B, x2/p1 | 7.5–8.2 s | ~490 / 440–480 | Better entities and roles; one inverted `part_of`; one non-verbatim role ("Head of Group" for "geleitet") |
| **8B, x2/p2 (worked example + role checks)** | 1.4–1.9 s | ~720 / 190–270 | EN: person, leader relation, contact and group expertise correct, but merged a member's expertise into the group's. DE: still missed the person; one inverted `part_of` |

**Takeaways:**
- 8B with the worked example is usable for entities, contacts and leader relations. Person-level expertise and German pages are weak.
- 70B is ~4× slower and more accurate.
- Decide 8B vs 70B (or 8B + 70B on person pages) on **real T06 pages** with a small hand-checked sample before the full run. Architecture step 4 says 8B for bulk, so 70B needs that measured justification.

## Real-page comparison: 8B vs 70B (2026-10-18)

**Setup:** T06 `dev` crawl of `artorg`, `dcb`, `unibe-dbmr` with `--max-pages 10`: 29 pages stored in 71 s, 11 routed to extraction (6 DBMR, 2 ARTORG, 3 DCB incl. one German page). Same pages, prompt `p2`, schema `x2`, `APERTUS_MAX_CONCURRENCY=4`. One run per model; the precision numbers come from Ruihan's single-rater hand check of every non-name claim against its cited sentence. Small sample, not a benchmark.

```bash
python -m app.ingest --data-dir data --profile dev --source artorg --source dcb --source unibe-dbmr --max-pages 10 crawl
python -m app.ai.extract --data-dir data --model apertus-v1-5-8b
python -m app.ai.extract --data-dir data --model apertus-v1-5-70b
```

| | 8B | 70B |
| --- | --- | --- |
| Wall time, 11 pages | 9.2 s | 62.1 s (one long page 58 s, hit the token limit once and retried) |
| Tokens in / out | 13,314 / 5,304 | 15,363 / 6,845 |
| Entities (persons) | 44 (0) | 71 (24) |
| Non-name claims kept | 27 | 36 |
| Hand-checked correct | ~13 / 27 (~48%) | ~35 / 36 (~97%); 7 of the correct ones are low-value (prize amounts) |
| Typical errors | wrong or inverted relations ("DBMR part_of Research Programs"), facts citing unrelated sentences, study methods filed as a unit's expertise | one inverted `part_of` ("DCB part_of TIMES study") |

The figures above include the alias fix below, which recovered facts from cached output at no extra token cost (8B 63 → 71 claims, 70B 103 → 107 claims).

**Recommendation (proposed as DECISIONS D10):** use **70B for offline extraction** and keep 8B only as a fallback. Extraction runs once per page offline and is cached by content hash, so the ~7× latency doesn't touch query time. Architecture step 4 names 8B for bulk extraction, so this needs team agreement. This table is the measured justification.

**Fixes made from this run:**
- Subject/object resolution now accepts the full name, the name without its parenthetical, the abbreviation ("DBMR"), or a unique partial match (≥ 4 characters). Ambiguous references are still dropped.
- `MAX_TOKENS` raised from 1500 to 3000.

**Feedback for T06 (Maxim):** the cheap classifier labelled DBMR event/prize pages as `unit`, and the `dev` crawl reached no staff/team pages, so the sample contains no real person profile pages. A crawl that prioritises `/team`, `/people`, `/staff`, `/mitarbeitende` links would test person extraction properly.

## Known gaps / next steps

- **Relation direction** (`part_of` inverted) is not checked in code. T08's support check must catch it, or add a kind rule (e.g. a project cannot contain a unit).
- **Member → group transfer** (group attributes citing a sentence about a member) is not blocked in code yet; T08 support check.
- **Relation claims are the weakest output on both models.** T08 must verify relation direction and support before anything reaches cards.
- Re-run on a crawl that includes real person/team pages.
- Record per-page tokens/latency/retries for T16 (already in `PageResult` and `client.meter`).
