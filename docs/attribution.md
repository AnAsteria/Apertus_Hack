# Attribution, licences and repository audit

Refs #25. Checked 2026-10-18.

## Models

| Model | Use | Licence | Where it runs |
| --- | --- | --- | --- |
| Apertus v1.5 8B (`apertus-v1-5-8b`), Swiss AI Initiative | live request interpretation and card assessments | Apache 2.0 plus the acceptable use policy accepted on Hugging Face ([docs/access-readiness.md](access-readiness.md)) | organisers' CSCS/Keera gateway; no weights in this repository |
| Apertus v1.5 70B (`apertus-v1-5-70b`) | offline fact extraction and grounding checks (T07/T08) | same | same |
| `intfloat/multilingual-e5-small`, revision `614241f6` (ONNX int8) | query and passage embeddings | MIT | on the server's CPU; downloaded at build time, pinned with SHA-256 in [app/search/models.json](../app/search/models.json) |
| `intfloat/multilingual-e5-base` | optional comparison only | MIT | not deployed |

Generated text (interpretations, assessments) is labelled as AI-generated in the UI and is never shown as a source fact.

## Data

Source pages are public pages of the University of Bern (including ARTORG) and the Diabetes Center Berne, listed in [config/sources/](../config/sources/). Quotes on result cards are exact sentences from those pages with their URL and fetch date. The crawled corpus and the extracted knowledge are **not** published in this repository, because they contain names and professional contact details; see [data-policy.md](data-policy.md).

## Software

Main runtime libraries (pinned in [requirements.lock](../requirements.lock), [app/search/requirements.txt](../app/search/requirements.txt), [app/ingest/requirements.txt](../app/ingest/requirements.txt)): FastAPI, Starlette, Uvicorn, Pydantic, httpx, NumPy, ONNX Runtime, Hugging Face `tokenizers` and `huggingface-hub`, Beautiful Soup, pypdf, langdetect, Protego, snowballstemmer. All are under permissive licences (MIT, BSD or Apache 2.0). The UI is plain HTML, CSS and JavaScript with no third-party code and no external requests.

Hosting: Hugging Face Docker Space and Storage Bucket. Inference: CSCS/Keera gateway provided by the hackathon organisers.

## Repository licence

**MIT** (see [LICENSE](../LICENSE)), agreed by the team on 20 October 2026. It covers this repository's code and documentation only. The content of the crawled source pages stays with the institutions that publish them, and the models and libraries above keep their own licences.

## Repository audit before going public (2026-10-18)

Run over all 151 commits on all branches:

- **Secrets:** searched every version of every file for Hugging Face, OpenAI-style, GitHub, AWS and Slack tokens, JWTs, private keys, and literal values assigned to `api_key` / `token` / `secret` / `password`. One match: `tests/ai/test_client.py` uses `sk-test-not-a-real-key-123`, a deliberate fake. No `.env` file was ever committed. Real keys live only in the Space settings and local git-ignored `.env` files.
- **Data files:** no corpus, knowledge, index, SQLite or model file was ever committed. The only data file is the supplied source inventory workbook in `config/sources/`.
- **Personal data:** `runs/dev-live-v1.json`, an evaluation run record, was committed by mistake in `c1ade0f`. It holds search-result excerpts from public pages, including names and two functional addresses (`info@dcberne.com`, a lab address at unibe.ch). It is removed from the tree and `runs/` is now git-ignored, but **it is still in the git history**. Removing it from history needs a force-push that every teammate has to pull; the team decides.
- **Temporary release:** `temp-corpus-delete-me` holds the corpus, the knowledge files and the index bundle. It must be deleted before the repository goes public (#73).
