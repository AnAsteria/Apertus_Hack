# Evaluation protocol (T14)

Refs #14. Written by Dimitry (T14 reassigned from Maxim, see the grant on #14). This document fixes every definition **before** any benchmark run. It contains **no results**: the harness has only been tested on synthetic cards (`tests/evaluation/`), never on real retrieval.

## Status

| Part | State |
| --- | --- |
| Harness (metrics, runner, report, sample sheet, CLI) | implemented, 15 unit tests pass; expected values in the tests are worked out by hand |
| Gold set `evaluation/gold/gold.json` | **0.2-draft: 36 queries (17 development, 19 evaluation), 17 intent groups, not frozen.** `python -m evaluation validate --final` passes. 0.2 (Maxim, 2026-10-18) adds FR/IT/RU variants, development groups I14-I15, evaluation groups I16-I19 (incl. two person/unit-boundary and one more absent query) and language-variant URLs as `accept_also`. See the independence note below |
| Review by Ruihan (workstream B), as required by R1 | not done |
| Partner review of expected matches | not done, not assumed |
| Measured results | none. T16 and T20 own them |

## Independence note (0.2)

The 0.2 additions, including evaluation groups I16-I19 and the evaluation-split variants, were written by Maxim, who also builds and tunes T09 retrieval. Each expected entity was taken from stored T06 final-corpus sentences **before** any search run on that query; no evaluation query was run against the system while writing. Earlier, the T09 abstention threshold (0.865) was chosen on development queries and off-topic probes only. This authorship is a limitation for the report: Ruihan's review (R1) decides whether the evaluation split is accepted as written, edited, or replaced, and then freezes it.

## Disclosure: an evaluation intent was viewed before the re-score (2026-10-18)

While checking that the 70B fields reached the live Space (about 20:43 and 20:53 Zurich), Claude, working for Maxim, sent the ad hoc query "ultrasound robotics micro technologies" twice. That is close to the evaluation query **I17-en** ("A researcher who personally works on ultrasound-driven robotics and micro technologies for medicine"). The returned cards were seen; the expected person appeared at rank 4 among the first five.

The observation was **not used** for any threshold, ranking or fusion choice: T31 thresholds, the abstention value 0.83 and the dense/BM25 fusion weight were chosen on the development split and on non-gold probes only. Gold 0.3 stays frozen and unchanged; Ruihan (reviewer) decides whether I17 is kept as is, flagged in the report, or replaced in a new gold version. Any later evaluation-split result that includes I17 should carry this note.

## Gold set rules

- Expected entities are keyed by **canonical source URLs** (the profile page plus its language variants), not entity IDs, because IDs only exist after T06/T08 ran. A card matches when one of its evidence URLs is listed, its entity type is acceptable and, if `names` is given, its display name contains an alias. `names` exists because two programmes can share one page (S02: CTR and RNS), and a sibling on the same page must not count as a hit.
- A **unit never counts as a person** unless the gold lists `accept_types`. Language variants of one project count as one entity.
- Every non-absent query needs at least one expected entity and a provenance entry (source URL plus note). Absent queries list none and must return no cards; this tests corpus absence, never universal absence.
- **Intent groups** keep all wording variants (professional, lay, synonym, EN/DE) in the same split. `validate` fails when a group is split across partitions.
- `avoid` lists misleading near-matches that must not appear in the top 10.
- Development queries may be used to tune. Evaluation queries are **frozen first** (`python -m evaluation freeze`, which stores a hash of the query content in `evaluation/gold/FROZEN.json`); an evaluation-split run refuses to start if the gold file no longer matches that hash. Freezing before tuning is a rule people must follow; the hash shows a change afterwards, it does not prevent tuning.

## Metrics (definitions)

| Metric | Definition |
| --- | --- |
| Recall@10 | For each non-absent query, the share of expected entities matched by one of the first 10 cards. Mean over queries, with n, overall and per category. A failed request counts as 0. |
| Link coverage | Share of returned cards with at least one evidence sentence that carries a source URL. **Presence of links only; not evidence of support.** |
| Evidence support | A random sample of returned cards (fixed seed 20261018, default 40) goes to `python -m evaluation sample`, a human fills `supported|partly|unsupported`, and `support` computes the rates with n. Always report n and who rated. Not automatic. |
| Field completeness | Per field, the share of cards with at least one supported value. Accuracy needs adjudication and is not computed here. |
| Correct abstention | Share of `absent` queries that returned zero cards with HTTP 200. |
| Misleading avoided | Share of queries with `avoid` where no listed near-match is in the top 10. |
| Institutional exposure | Share of cards per source host. **Reported, never optimised.** |
| Latency | Client-side median and p95 per request in ms, including network. Percentile rule: nearest rank (`ceil(p/100 * n)`-th sorted value). |
| Tokens per query, indexing time | Not visible through the search API. They stay `null` in a run record until T16 fills them from server-side records. |

## Deterministic grounding checks (T37)

`python -m evaluation.grounding --index-dir <serving dir> [--run <run record>]` checks, without any model: every surfaced field cites claim sentences that exist in the index; former/retired entities show no official contact; every served quote is byte-identical to the stored sentence of the cited version, with the stored URL and no cross-version reference. First run (2026-10-18, real 70B bundle `9a0e0951…`, development run on the live Space): **0 problems** over 674 entities with fields, 1,523 field values, 1,695 claim sentences, 170 cards and 1,410 quotes. This proves citation integrity only, not semantic support; support is the human-rated sample below.

## Running it

```bash
python -m evaluation validate                  # schema, leakage, provenance checks
python -m evaluation validate --final          # also requires 30-50 queries
python -m evaluation freeze                    # before the first evaluation-split run
python -m evaluation run --base-url https://kaktamsdengami-bern-match.hf.space \
    --split development --config baseline --corpus-snapshot <id> --out runs/dev-baseline.json
python -m evaluation report runs/dev-baseline.json
python -m evaluation sample runs/dev-baseline.json --out runs/support-sheet.csv
python -m evaluation support runs/support-sheet.csv
```

A run record stores the gold hash, split, configuration name, corpus snapshot id, environment and per-query latency, status and returned cards. It never stores request bodies or error text. `report` refuses a run whose gold hash does not match the gold file.

## Known limits and next steps

1. The gold set needs about 12-30 more queries: lay and synonym variants for each group, French and Italian cases, and groups from the other inventory domains. Only seeds that Maxim actually inspected were used; none were invented.
2. I08 (person/unit boundary) and I09 (contact freshness) from the seeds are **not** in the gold: they need real person evidence in the ingested corpus before an expected answer can be defended.
3. I10's absence must be re-checked against the real corpus before freezing.
4. The 8B/70B and cross-encoder comparisons (T20) run through the same harness by changing the configuration name; the cross-encoder subset itself is not implemented here.
5. Ruihan reviews the gold before freezing; the partner session (T21) may adjust expected matches, and any change after freezing gets a new `gold_version` and is reported.
