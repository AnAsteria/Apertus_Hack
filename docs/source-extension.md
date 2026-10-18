# Adding a new source (T32 / EXTRA E2, #83)

Sources are added through a YAML file and the normal pipeline: no adapter code, and no re-crawl or re-embedding of the existing corpus. Example config: `config/sources/examples/bfh-engineering-research.yaml` (Bern University of Applied Sciences research pages). It is an extension example only, not part of the organiser inventory or the evaluated corpus.

## Commands (measured 2026-10-18, Apple M1, copy of the final corpus + the Space bundle)

```bash
# 0. check robots.txt and the allowed paths of the new site first
# 1. bounded crawl of the new source only, into the existing corpus directory
python -m app.ingest crawl --config config/sources/examples/bfh-engineering-research.yaml --data-dir <corpus dir> --profile dev
# 2. incremental index build into the serving dir that holds the current generation:
#    vectors for unchanged text are reused (text SHA + model + recipe); only new text is encoded
python -m app.search build --corpus-dir <corpus dir> --knowledge-dir <knowledge dir> \
    --model-dir <serving dir>/indexes/<current generation>/model --data-dir <serving dir>
# 3. optional: 70B extraction for the new pages only (announce first; the cache skips unchanged pages)
```

| Step | Result |
|---|---|
| Crawl (15-page budget, 0.5 req/s) | 15 pages fetched and parsed, 16 HTTP requests, 0 retries, **47 s** |
| Incremental build | **22,182 vectors reused, 160 new entries encoded, 37.6 s** (a full rebuild takes ~18.8 min on the Space) |
| New index | 2,826 versions (+15), 2,558 entities (+15), 22,343 vectors |
| Search for the new source | "BFH research in engineering and technology" → 6 BFH cards, e.g. "Research collaborations with BFH" at rank 2, with exact quotes |
| Regression checks | development Recall@10 unchanged (0.824); all 1,410 quotes of an earlier development run still resolve byte-identically (`python -m evaluation.grounding`: 0 problems) |

New pages start as evidence-only cards (no extracted fields) until step 3 runs. On the Space, an operator runs step 2 against the restored bundle and stores the new bundle. **Refresh executor (EXTRA E3, #139).** `python -m app.lifecycle.refresh_executor` runs one queued `refresh` job from the admin page: it re-fetches the source with `refresh=True`, builds an incremental generation and records counts or error codes on the job. Measured on the same copy, the BFH refresh fetched 15 pages, all 15 unchanged, so the index was kept as is; the job `succeeded` in 57 s, nearly all of it rate-limited fetching. Pages that are absent are not retired by a refresh; removal goes through the suppression list. On the Space, an operator runs it inside the container. Wiring it to run automatically after the admin button is left for later.
