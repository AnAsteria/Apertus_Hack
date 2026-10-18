"""Apply the suppression list at serving time (T12 enforcement). Used by the search route.

The list path comes from BERNMATCH_SUPPRESSION_FILE, else config/suppression.json next to the
repository root. A missing file means nothing is suppressed; deployments must therefore ship the
file (both Dockerfiles copy it). The file is re-read when it changes on disk.
"""
import os
from pathlib import Path

from . import suppression as S

_EMPTY = {"schema_version": "1", "entries": []}
_cache: dict = {"path": None, "mtime": None, "data": _EMPTY}


def default_path() -> Path:
    env = os.environ.get("BERNMATCH_SUPPRESSION_FILE")
    return Path(env) if env else Path(__file__).resolve().parents[2] / "config" / "suppression.json"


def load_suppression() -> dict:
    path = default_path()
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return _EMPTY
    if _cache["path"] != str(path) or _cache["mtime"] != mtime:
        _cache.update(path=str(path), mtime=mtime, data=S.load(str(path)))  # invalid file raises: fail loudly
    return _cache["data"]


def apply(response: dict) -> dict:
    """Drop suppressed cards from a search response dict and renumber ranks. Never says why."""
    data = load_suppression()
    if not data.get("entries"):
        return response
    kept = []
    for r in response.get("results", []):
        urls = [e["url"] for e in r.get("evidence", []) if e.get("url")]
        if S.is_suppressed_entity(data, entity_id=r.get("entity_id"), names=[r.get("display_name", "")], urls=urls):
            continue
        kept.append(r)
    for i, r in enumerate(kept, 1):
        r["rank"] = i
    response["results"] = kept
    return response
