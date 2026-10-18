# Deployment to a Hugging Face Docker Space (T11 preparation)

Refs #11. Decision D6: free Hugging Face Space (Docker) for the app, organiser Keera endpoint for Apertus, no paid resources. **Deployed skeleton (2026-10-18):** https://kaktamsdengami-bern-match.hf.space (Space `kaktamsdengami/bern-match`, CPU Upgrade, see D9). Probed from outside: `/healthz` 200, UI 200, `/readyz` 503 and search 503 (no index yet, by design), admin coverage 401 without a token (so the admin secret is set). Real search, restart test and persistence are still open.

## What is prepared and verified

| Item | State |
| --- | --- |
| `deploy/hf-space/Dockerfile` (user 1000, port 7860, writable data dir) | CI job `hf-space-image` builds it, starts it as uid 1000 and probes `/healthz` 200 and `/readyz` 503. Check the CI run for the result; a green run is the only evidence. |
| `deploy/hf-space/README.md` (Space header: `sdk: docker`, `app_port: 7860`) | Written from the Hugging Face Docker Spaces docs read on 2026-10-18; not yet accepted by a real Space. |
| Main image (`Dockerfile`, port 8000) | Built and probed in CI (job `container`). |

## What Hugging Face's docs say (read 2026-10-18)

- A Docker Space is configured by the YAML header at the top of the Space's `README.md`; default port is 7860, changeable with `app_port`.
- The container runs as user ID 1000; create that user and set `WORKDIR` before `COPY`.
- Variables and secrets set in the Space settings arrive as environment variables at runtime.
- **Disk is ephemeral**: data written to disk is lost whenever the Space restarts. Persistence needs a Storage Bucket mounted at runtime, or an external store. Datasets and models can also be mounted read-only.
- Not verified from the docs: the free tier's CPU/RAM/disk limits, cost of a Storage Bucket, sleep-on-inactivity behaviour.

## Conflict to decide before T11 and T13

Feedback is stored in SQLite under `BERNMATCH_DATA_DIR`, and the index must survive restarts (T11, T13 acceptance). On a free Space the local disk is wiped on restart. Options, none tested:

1. **Bake the index into the image** at build time. Index survives restarts; feedback and admin job records do not (ephemeral).
2. **Mount a private dataset or model repo read-only** for the index. Index survives; feedback still ephemeral.
3. **Attach a Storage Bucket** for `BERNMATCH_DATA_DIR`. Everything survives; the price and free-tier availability are unknown and may cost money, which needs explicit authorisation.
4. **Push feedback snapshots to a private dataset repo** on a schedule. Free, but a restart can lose the latest entries.

Until one is chosen, state in the report that feedback persistence on the hosted demo is limited.

## Steps used to create it (done once, by Dimitry)

1. Create the Space (SDK: Docker, public or private as decided) under the team's Hugging Face account.
2. In the Space settings add secrets, never in Git: `APERTUS_BASE_URL`, `APERTUS_API_KEY`, `BERNMATCH_ADMIN_TOKEN`; variables: `APERTUS_MODEL`.
3. Push these files to the Space repository: `deploy/hf-space/README.md` as `README.md`, `deploy/hf-space/Dockerfile` as `Dockerfile`, plus `app/` and `requirements.lock`. The Space builds from that repository, not from GitHub.
4. Wait for the build, open the Space URL, check `/healthz`, then `/readyz`.
5. Real search also needs the T06/T09 index in place; until then `/readyz` stays 503 by design.

Record the actual Space URL, build log and restart test in the T11 issue before calling it deployed.

## Updating the Space

From the repository root, after `hf auth login` with a write token:

```bash
git archive origin/main app requirements.lock | tar -x -C /tmp/hfspace
cp deploy/hf-space/Dockerfile deploy/hf-space/README.md /tmp/hfspace/
hf upload kaktamsdengami/bern-match /tmp/hfspace . --repo-type space
```

The Space rebuilds on every upload. Never upload `.env`, `data/` or `models/`.
