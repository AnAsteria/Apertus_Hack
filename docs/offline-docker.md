# Air-gapped run with Docker (T15, jury criterion "Sovereign deployability")

Refs #15. Goal: show that Bern Match runs **outside any cantonal ICT, in Docker on one machine, with the network switched off**, and that `docker compose up` is all it takes. This is a runbook, **not evidence**: nothing here is shown until the run below has been recorded and its output posted on #15.

What runs locally: the app (FastAPI + UI), the search index (SQLite FTS5 + E5-small ONNX vectors), the embedding model (inside the bundle), and optionally Apertus 8B (community Q4_K_M GGUF, llama.cpp). Nothing is crawled or built at query time.

## 1. Prepare while still online (once)

```bash
git pull && git switch main                       # or the branch with docker-compose.yml
mkdir offline-data models
gh release download temp-corpus-delete-me -R AnAsteria/Apertus_Hack -p bundle-c3-77e5175a.tar.gz
# SHA-256 must be 112cbcf2fe37f76d5bc35f351f67d1e795b2aa18aaf551678598df44edf489a1
#   Windows: certutil -hashfile bundle-c3-77e5175a.tar.gz SHA256   macOS/Linux: shasum -a 256 ...
mv bundle-c3-77e5175a.tar.gz offline-data/bundle.tar.gz
docker compose build                               # needs the internet (pip); same image as the Space
```

Optional, local Apertus (needed to show AI features offline):

```bash
# models/apertus-v1.5-8b-text-q4_k_m.gguf  SHA-256 a037df8d87ff6caacee794ee85f55342f2152e0d359b7389033300c3bee5f299
echo APERTUS_API_KEY=local > .env                  # any non-empty value switches the AI features on
docker compose --profile llm pull                  # llama.cpp server image (pinned build b11719)
```

If the pinned llama.cpp image tag does not exist, set `LLAMA_IMAGE=ghcr.io/ggml-org/llama.cpp:server` in `.env` and record the digest from `docker images --digests`. On Windows you may instead run `llama-server.exe -m <gguf> --port 8080 --alias apertus-v1-5-8b` natively and put `APERTUS_BASE_URL=http://host.docker.internal:8080/v1` in `.env` (then start without `--profile llm`).

Online smoke check: `docker compose --profile llm up -d`, open http://127.0.0.1:7860, run one query, then `docker compose down`.

## 2. The air-gapped run (record the whole screen)

1. **Cut the network:** airplane mode / Wi-Fi off and Ethernet unplugged. In the recording show `ping 1.1.1.1` failing.
2. Start: `docker compose up -d` (search only) or `docker compose --profile llm up -d` (with Apertus). Wait for `docker compose logs app` to show `restored index bundle`.
3. **Isolation + search proof** from inside the container:
   - macOS/Linux: `docker compose exec -T app python - < scripts/airgap_check.py`
   - PowerShell: `Get-Content scripts\airgap_check.py | docker compose exec -T app python -`

   It must print `NETWORK BLOCKED`, cards for three unseen queries (not gold queries), the index generation and timings, and exit 0.
4. In the browser at http://127.0.0.1:7860:
   - Run an **unseen** query you type live. Show the cards, the evidence quotes and the outcome label.
   - Add two cards to the shortlist and use **Export PDF**.
   - With `--profile llm`: show the Apertus interpretation / ranking arriving. The first cards appear immediately; on CPU, Apertus takes tens of seconds, so state that honestly.
   - Source links point to the public web and will not open offline. The quoted sentence itself is stored locally.
5. Post on #15:
   - machine, OS, RAM and CPU;
   - `docker version`;
   - `docker images --digests` for both images;
   - the bundle and GGUF SHA-256;
   - the full `airgap_check.py` output;
   - observed latencies;
   - the recording link;
   - anything that failed. If enrichment did not work with llama.cpp (for example, unsupported JSON-schema decoding), write that down. The cards still work, and that is the fallback behaviour.

## What this shows and does not show

- Shows: the full search path runs on one machine with no network, from a container started by `docker compose up`, and does not depend on any cantonal system.
- With `--profile llm`, it also shows: Apertus runs locally (a community 8B conversion, not the official weights; quality differs from the 70B used online).
- It does not show production hardening, HTTPS, accounts, or the 70B model offline. The `ports` mapping binds to `127.0.0.1` only.
