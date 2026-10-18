"""GET /api/v1/evidence/{version_id}/{sentence_id}: resolve a citation to its exact stored sentence.

Returns HTTP 410 `EVIDENCE_REMOVED` when the evidence is suppressed or no longer stored. A citation
is never rebound to different text (CONTRACTS section 3, docs/data-policy.md). Reads the corpus
database read-only and never creates it.
"""
import json
import os
import sqlite3

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..contracts import error
from ..lifecycle import serving, suppression
from ..storage.indexes import current_generation

router = APIRouter()


def _corpus_path() -> str:
    """An operator's real corpus when present; otherwise the evidence tables inside the current
    search generation (same sentence/version layout), so a query-only serving directory works
    without a symlink or a second copy."""
    root = os.environ.get("BERNMATCH_DATA_DIR", "data")
    corpus = os.path.join(root, "corpus.sqlite")
    if os.path.exists(corpus):
        return corpus
    current = current_generation(root)
    return str(current[0] / "search.sqlite") if current else corpus


@router.get("/api/v1/evidence/{version_id}/{sentence_id:path}")
def evidence(version_id: str, sentence_id: str):
    path = _corpus_path()
    if not os.path.exists(path):
        return JSONResponse(error("INDEX_NOT_READY", "Search indexes are not ready.", True), status_code=503)
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        row = db.execute("SELECT body FROM sentences WHERE id=? AND version_id=?", (sentence_id, version_id)).fetchone()
        ver = db.execute("SELECT body FROM versions WHERE id=?", (version_id,)).fetchone()
    finally:
        db.close()
    gone = JSONResponse(error("EVIDENCE_REMOVED", "This evidence is no longer available."), status_code=410)
    if row is None or ver is None:
        return gone
    sent, version = json.loads(row[0]), json.loads(ver[0])
    url = version.get("url", "")
    if suppression.is_suppressed_url(serving.load_suppression(), url):
        return gone
    return {"schema_version": "1", "version_id": version_id, "sentence_id": sentence_id,
            "text": sent["text"], "url": url, "page_number": sent.get("page_number")}
