# Evaluation protocol (T14)

Refs #14. Written by Dimitry (T14 reassigned from Maxim, see the grant on #14). This document fixes every definition **before** any benchmark run. It contains **no results**: the harness has only been tested on synthetic cards (`tests/evaluation/`), never on real retrieval.

## Status

| Part | State |
| --- | --- |
| Harness (metrics, runner, report, sample sheet, CLI) | implemented, 15 unit tests pass; expected values in the tests are worked out by hand |
| Gold set `evaluation/gold/gold.json` | **seed only: 18 queries, 11 intent groups, not frozen.** Below the 30-50 target; `python -m evaluation validate --final` fails by design |
| Review by Ruihan (workstream B), as required by R1 | not done |
| Partner review of expected matches | not done, not assumed |
| Measured results | none. T16 and T20 own them |

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
