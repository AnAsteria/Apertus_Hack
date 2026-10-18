# Deployment (Hugging Face Docker Space)

Refs #11, #84 (T33). Live app: https://kaktamsdengami-bern-match.hf.space (Space `kaktamsdengami/bern-match`, CPU Upgrade, $0.03/h from Dimitry's HF credit, decision D9). Apertus runs on the organisers' Keera gateway; nothing model-related is hosted here.

## What runs where

| Piece | Where | Survives a restart? |
| --- | --- | --- |
| Code | Space repository, uploaded by `scripts/deploy_space.sh` | yes (the Space rebuilds the image from it) |
| Search index | built once, stored as `bundle.tar.gz` in the private bucket `kaktamsdengami/bern-match-data` (mounted at `/data`), extracted to local disk on start | yes, restored in seconds |
| Corpus and T08 knowledge | `/data/corpus.jsonl`, `/data/knowledge/` | yes (inputs for a rebuild) |
| Feedback and admin jobs | `bernmatch.sqlite` on local disk; snapshot in `/data/state/` every 60 s | yes, minus at most the last 60 s |
| Secrets | Space settings (`APERTUS_BASE_URL`, `APERTUS_API_KEY`, `BERNMATCH_ADMIN_TOKEN`) | yes, never in Git or the bucket |

Live SQLite files never sit on the mounted bucket: the app writes locally and `app/lifecycle/state_backup.py` copies a consistent snapshot (SQLite online backup, written to a temp file and renamed). On start, `entrypoint.sh` restores the bundle, then the snapshot, then starts the app.

## Deploy

From the repository root, with `hf` logged in with write access:

```bash
scripts/deploy_space.sh              # deploys origin/main
```

It uploads exactly that revision (plus `app/REVISION`), waits until the Space reports `RUNNING` on the uploaded Space commit, checks that `/healthz` reports the git revision (when that revision's code has the field), checks `/readyz` is 200 and runs one real search. Exit code 0 means all of them passed. The bundle is not touched, so no index rebuild happens. Add `--tag` to also push a `deploy-<UTC time>` tag.

Expect 1-4 minutes. The old container keeps serving while the new image builds, then there is a short gap (about 20 s measured) while the new one starts.

## Rollback

Deploy the previous revision; the index is unaffected:

```bash
scripts/deploy_space.sh <previous-sha-or-deploy-tag>
```

The Space's commit history (`Deploy <sha> (<ref>)`) lists what was deployed when. Rolling back to a revision older than T33 (`b40bbea`) also drops the feedback snapshot loop: feedback written while that old revision runs is not saved, and the next T33 deploy restores the last snapshot taken before the rollback. If the index itself is broken, copy the backup bundle back and restart:

```bash
hf buckets cp hf://buckets/kaktamsdengami/bern-match-data/backup/bundle-evidence-only.tar.gz hf://buckets/kaktamsdengami/bern-match-data/bundle.tar.gz
```

## Rebuild the index (about 17 min of 503 on search)

Only needed when the corpus or knowledge files change, or for a build-time rule (for example T37). Delete `/data/bundle.tar.gz` (keep a copy under `backup/` first), then restart the Space. `entrypoint.sh` builds on local disk from `/data/corpus.jsonl` and `/data/knowledge/`, prints a percentage every 30 s in the Space logs, and stores a new bundle. **Check that `bundle.tar.gz` is back in the bucket afterwards** (about 138 MB); without it the next restart rebuilds again.

## Settings and variables

| Setting | Value | Why |
| --- | --- | --- |
| Sleep time | never (set 2026-10-18 for judging) | no cold start for the jury. Costs $0.03/h around the clock; set back after judging. |
| `BERNMATCH_AUTO_PIPELINE` | `1` | build the index when no bundle exists |
| `APERTUS_MODEL` | `apertus-v1-5-8b` | |
| `BERNMATCH_ABSTAIN_DENSE` | unset (code default 0.83) | set only while tuning (#82), then remove |
| `BERNMATCH_RATE_LIMIT_PER_MIN` | unset (default 120 per client per minute on `/api/`) | slows scanners and loops; `0` turns it off. The client is the first `X-Forwarded-For` entry, which can be forged, so this is not an abuse defence |
| `BERNMATCH_STATE_BACKUP_SECONDS` | unset (default 60) | feedback snapshot interval |

Admin token rotation: create a new random value, replace `BERNMATCH_ADMIN_TOKEN` in the Space secrets (the Space restarts), and hand it only to operators.

## Checks

```bash
curl -s https://kaktamsdengami-bern-match.hf.space/healthz     # {"status":"ok","revision":"<sha>"}
curl -s -o /dev/null -w "%{http_code}\n" https://kaktamsdengami-bern-match.hf.space/readyz   # 200
hf buckets ls kaktamsdengami/bern-match-data -R                # bundle.tar.gz, state/bernmatch.sqlite
```

The Space logs show public scanner traffic (`/.env`, `secrets.toml`, ...). Those all return 404: only `app/static/` is served and secrets are environment variables, not files.

## Record (T33 acceptance)

- **Deploy, 2026-10-18 19:55 UTC:** `scripts/deploy_space.sh origin/main --tag` deployed `b40bbea` (Space commit `47ac401a`, tag `deploy-20261018-1955`). `/healthz` reported `b40bbea`, `/readyz` 200, smoke search 10 results. Exit 0 in 32 s (cached image layers).
- **Restart test, 2026-10-18 19:56-19:57 UTC:** posted one feedback record marked `t33-restart-test` (201, `fbk_bb0e7f0d…`); the snapshot reached `/data/state/bernmatch.sqlite` at 19:56:51 and held it. Restarted the Space at 19:57:11; back at 19:57:34 (`/readyz` 200, log: bundle restored, state restored). Re-posting the same feedback returned **200 with the same id**, so the record survived. The test record stays in the feedback table and is marked by its `entity_id`.
- **Rollback:** recorded on #84 (run after this change merged, because the first version of the script could only verify revisions that report `/healthz` revision).
- Not done: external uptime check from a second network; cost to date (needs the HF billing page).
