# Data policy: removal, retention and freshness (T12 policy part)

Refs #12. Drafted by Dimitry on 2026-10-18 as the policy half of T12 and **adopted by the dispatcher the same day under the team's trust model (no separate sign-off was waited for)**; Maxim owns part of the enforcement code. This is a **design commitment, not a claim of legal compliance**. Nothing here has been exercised against real data: the suppression list ships empty, and no removal request has been handled. **Still open: the operator contact below (needs a real, monitored address).**

## What we collect

Only public information from the configured UniBE, ARTORG and Diabetes Center Berne web pages: names, roles, affiliations, research descriptions and official professional contact details as published there. We do not infer personal contact details, and we do not collect from logins, private pages or social media. Crawling respects robots.txt and per-host rate limits, and never bypasses access controls.

## Removal requests

**Who can ask:** anyone named in the index or acting for an organisation listed in it.

**Route:** the operator contact below. The README links here.

> **Operator contact: NOT SET.** A person must publish a monitored address before the submission (the repository owner, Dimitry, unless the team decides otherwise). Until this line holds a real address the route is **not operational**, and the README must not claim otherwise. Do not use public GitHub issues for requests that name a person.

**Handling steps**

1. Acknowledge the request. Target: **within 2 working days** (a goal, not yet demonstrated).
2. **Verify identity or authority.** For a person: the request comes from an institutional address of the same person, or is confirmed through the institution's own published contact. For an organisation: from a published contact of that organisation. Record **who confirmed and when, by role only**; do not store ID documents or private details.
3. Add an entry to `config/suppression.json` (format below) and merge it by pull request. The merge commit is the audit record.
4. **Suppress before ingestion:** the crawler skips suppressed URLs, so the page is not fetched or stored again.
5. **Retire from serving:** the affected entities, claims and index entries stop appearing in results at once (target: the next index rebuild or the retire action). A citation to removed evidence returns HTTP 410 `EVIDENCE_REMOVED`, never replacement text.
6. Tell the requester what was done, and what could not be done (for example, copies the source site itself still publishes).

**Operator commands (EXTRA F4, #144).** These were checked on the real index on 2026-10-18, with a temporary entry and in-process (#12):

```bash
# 1. add the entry (reason_category: removal_request; confirmed_at / confirmed_by_role are required)
$EDITOR config/suppression.json
# 2. check that the list is valid before deploying (an invalid list fails loudly at load)
python -c "from app.lifecycle.suppression import load; load('config/suppression.json'); print('ok')"
# 3. deploy main (the serving filter and the 410 route read the list at query time; no index rebuild needed)
scripts/deploy_space.sh main
# 4. verify: the page no longer appears; its evidence returns 410
curl -s https://kaktamsdengami-bern-match.hf.space/api/v1/evidence/<version_id>/<sentence_id>   # → 410 EVIDENCE_REMOVED
# 5. stored copies: dry run first, then apply; derived files are removed by the next rebuild
python -m app.lifecycle.purge --data-dir <corpus dir>          # dry run
python -m app.lifecycle.purge --data-dir <corpus dir> --apply
```

Observed in the 2026-10-18 check: before the entry, the person's card was in the results. With the entry, the card was gone (10 other cards), and its sentence returned `410 EVIDENCE_REMOVED` (200 without the entry). The purge step has not been run on the real corpus, because there has been no real request.

Out of scope: judging whether the source site must remove its own page. We only control our copy and our index.

## Suppression list format

`config/suppression.json`, validated by `app/lifecycle/suppression.py` (the shipped file is empty and valid):

```json
{
  "schema_version": "1",
  "entries": [
    {
      "entry_id": "sup_0001",
      "reason_category": "removal_request",
      "action": "suppress",
      "confirmed_at": "2026-10-20T09:00:00Z",
      "confirmed_by_role": "operator",
      "identifiers": {
        "names": ["Example Person"],
        "urls": [],
        "url_prefixes": ["https://example.org/people/example-person"],
        "entity_ids": []
      }
    }
  ]
}
```

- `reason_category`: `removal_request`, `former_staff`, `inaccurate` or `other`. **No free-text reason about a person is stored.**
- `action`: `suppress` (never ingest or serve) or `retire` (stop serving what is stored; also stops re-ingestion).
- Matching: URLs ignore scheme, `www.`, fragment and trailing slash, and prefixes stop at a path boundary; names ignore case, accents and spacing; any one identifier is enough. A name-only match removes a card. That is intentional, because wrongly hiding a card costs less than wrongly keeping one (merging identities on a name alone remains forbidden).
- JSON, not YAML, so the serving image needs no extra dependency. Revision R1 mentioned YAML; Maxim may switch if he adds PyYAML to the serving image.

## Retention (proposed, to be approved)

| Data | Rule |
| --- | --- |
| Public source snapshots and the search index | Kept for the duration of the project and the judging period. **Retired or suppressed content is removed from serving immediately and from stored copies within 30 days.** |
| Backups | The Space and the repository keep no data backups: the index is rebuilt from a crawl. If the team creates any backup, it must be deleted within 30 days of a removal and listed here. |
| Operational logs | 30 days, with no company input and no request text (already in `DECISIONS.md`). |
| Company inputs | In memory only, expiring 60 minutes after last use. Never written to disk, logs or the index (already in `DECISIONS.md`). |
| Feedback | Structured actions only. Free-text comments and saved needs are refused until retention is approved. |
| Exports and evaluation files | Contain source URLs and counts, not personal contact data. Raw crawl data stays outside Git. |

## Freshness

Evidence is `fresh` when its content or last-modified date is within **365 days**, `stale` when older, and `unknown` when neither is known. A recent fetch date alone never makes evidence `fresh`. People documented as former staff are never shown as current contacts. These rules come from `DECISIONS.md` and are not yet exercised against real data.

## Enforcement (implemented, tested on synthetic data only)

| Rule | Where | Test |
| --- | --- | --- |
| Suppressed URLs are never fetched, stored or reused from cache; counted as `suppressed` in the crawl report | `app/ingest/pipeline.py` | `tests/lifecycle/test_enforcement.py` (fake network) |
| Suppressed cards are removed from search results before they are served, ranks renumbered, no reason shown | `app/lifecycle/serving.py`, called from `app/api/search.py` | same file |
| A citation to suppressed or missing evidence returns HTTP 410 `EVIDENCE_REMOVED` with no text; a corpus is never created by this read-only route | `app/api/evidence.py` | same file |
| Changed page text creates a new version; the old citation still resolves to its old text and is never rebound | existing T06 versioning, now covered by a refresh test | same file |
| The list is re-read when the file changes, a missing file suppresses nothing, an invalid file raises instead of silently serving | `app/lifecycle/serving.py` | same file |

**Retire** means adding a suppression entry: serving and the crawler honour it at once. **Purge** removes the stored copies: `python -m app.lifecycle.purge --data-dir data` shows what would go (dry run); add `--apply` to delete the documents, versions, sentences, entities, cached pages, variants and labels of every suppressed URL and VACUUM the database file. A test shows the removed text is no longer in the file's bytes. Run it after every merged suppression entry, and within the 30-day target at the latest. The command does **not** touch derived files (`data/extraction/`, `data/knowledge/`, search indexes, exports) or backups: it lists the derived directories it finds, and those must be rebuilt from the purged corpus by hand. Both Dockerfiles copy `config/suppression.json`; if a deployment forgets to, nothing is suppressed, so check it after every deploy.

## Personal-data audit of what is served (EXTRA F5, #145, 2026-10-18)

Real 70B bundle (`9a0e0951…`) and the 350 cards served in the development and evaluation runs on the live Space:

| Item | Count |
|---|---|
| Distinct e-mail addresses in stored sentences | 313 (mostly `unibe.ch`, `insel.ch`, institute subdomains, `dcberne.com`) |
| Stored sentences with an e-mail or phone-like string | 6,971 of 148,404 |
| Persons in the index | 559 (all with status `unknown` or `former`; none `current`) |
| **Cards with an official-contact field served** | **0** (contacts are shown only for `current` persons) |
| Served quotes (2,754) containing an e-mail | 15 |
| Served quotes containing a phone-like string | 51 (noisy pattern: it also matches year ranges and numbers) |

**Finding:** card fields withhold contacts, but an evidence quote can still show an institutional e-mail or phone number, because quotes are byte-identical copies of source sentences. Masking would break quote fidelity. The proposed fix is to **not select contact-only sentences as evidence** for a card, unless the card shows a supported, current official contact. Only public institutional pages were crawled, and no private contact data was inferred. This is a minimisation gap to report, not a legal finding.

**Follow-up implemented on branch `EXTRA`:** a card that has no supported current official-contact field no longer uses contact-bearing sentences (an e-mail, or a phone number next to tel/phone/fax/+41) as quotes when other evidence exists. Development split, in-process on the bundle: Recall@10 unchanged at 0.824, and quotes containing an e-mail went to **0 of 1,273**. Quotes stay byte-identical; only the choice of sentences changes.

## What is not done

- A real operator contact (see above).
- Enforcement against the **real index**: the search index (T09) does not exist yet, so the serving filter has only been tested on the synthetic fixture cards and the 410 route on a hand-built corpus file.
- Purging derived files and indexes automatically (the command only reports them), and automatic expiry of backups.
