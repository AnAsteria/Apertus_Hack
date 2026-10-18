"""Protected operator routes (CONTRACTS sections 4 and 9).

Auth is a server-side secret in `BERNMATCH_ADMIN_TOKEN`, sent as the `X-Admin-Token` header.
No token configured means the admin API is disabled (403), never open. A custom header is not
sent by cross-site forms or image tags, which gives the browser request protection T13 asks for.

Refresh only records a queued job: the executor is T12's and does not exist yet, so the
response never claims a crawl ran.
"""
import hmac
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlsplit

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from ..contracts import Job, error
from .evidence import _corpus_path as corpus_path
from .feedback import get_repo

router = APIRouter()


def _denied(token: Optional[str]) -> Optional[JSONResponse]:
    expected = os.environ.get("BERNMATCH_ADMIN_TOKEN")
    if not expected:
        return JSONResponse(error("FORBIDDEN", "Admin API is not enabled."), status_code=403)
    if not token or not hmac.compare_digest(token.encode(), expected.encode()):
        return JSONResponse(error("UNAUTHORIZED", "Missing or invalid admin token."), status_code=401)
    return None


class RefreshRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str
    source_id: str


def source_counts(path: str) -> Optional[list[dict]]:
    """Per source host: stored pages by state, sentences, first and last fetch time.

    Read from the served corpus (the same database the evidence links use), so the numbers are
    what search can actually quote. None when no corpus is loaded."""
    if not os.path.exists(path):
        return None
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        sentences = dict(db.execute("SELECT version_id, COUNT(*) FROM sentences GROUP BY version_id").fetchall())
        rows = db.execute("SELECT id, json_extract(body,'$.url'), json_extract(body,'$.state'), "
                          "json_extract(body,'$.fetched_at') FROM versions").fetchall()
    finally:
        db.close()
    hosts: dict[str, dict] = {}
    for vid, url, state, fetched in rows:
        host = (urlsplit(url or "").hostname or "unknown").lower()
        h = hosts.setdefault(host, {"source": host, "pages": 0, "active": 0, "retired": 0, "suppressed": 0,
                                    "sentences": 0, "fetched_first": None, "fetched_last": None})
        h["pages"] += 1
        if state in ("active", "retired", "suppressed"):
            h[state] += 1
        h["sentences"] += sentences.get(vid, 0)
        if fetched:
            h["fetched_first"] = min(filter(None, (h["fetched_first"], fetched)))
            h["fetched_last"] = max(filter(None, (h["fetched_last"], fetched)))
    return sorted(hosts.values(), key=lambda h: (-h["pages"], h["source"]))


def feedback_counts(path: str) -> dict[str, int]:
    """Structured feedback received, by action. No free text exists to show (DECISIONS)."""
    if not os.path.exists(path):
        return {}
    with sqlite3.connect(path) as db:
        return dict(db.execute("SELECT json_extract(body,'$.action'), COUNT(*) FROM feedback GROUP BY 1").fetchall())


@router.get("/api/v1/admin/coverage")
def coverage(x_admin_token: Optional[str] = Header(default=None)):
    if (d := _denied(x_admin_token)) is not None:
        return d
    repo = get_repo()
    jobs = repo.list_jobs()
    by_state: dict[str, int] = {}
    for j in jobs:
        by_state[j.state] = by_state.get(j.state, 0) + 1
    sources = source_counts(corpus_path())
    out = {"schema_version": "1", "jobs_by_state": by_state,
           "failed_jobs": [j.model_dump() for j in jobs if j.state == "failed"][:50],
           "recent_jobs": [j.model_dump() for j in sorted(jobs, key=lambda j: j.started_at or "", reverse=True)][:20],
           "feedback_by_action": feedback_counts(repo.path),
           "sources": sources or []}
    if sources is None:
        out["note"] = "No corpus is loaded, so there are no coverage counts yet; zero here does not mean zero coverage."
    else:
        out["totals"] = {k: sum(s[k] for s in sources) for k in ("pages", "active", "retired", "suppressed", "sentences")}
        out["note"] = "Counts are the pages and sentences the live index can quote, grouped by host."
    return out


@router.post("/api/v1/admin/refresh", status_code=202)
def refresh(req: RefreshRequest, x_admin_token: Optional[str] = Header(default=None)):
    if (d := _denied(x_admin_token)) is not None:
        return d
    if req.schema_version != "1":
        return JSONResponse(error("VALIDATION_ERROR", "Unsupported schema_version."), status_code=422)
    repo = get_repo()
    if any(j.state in ("queued", "running") and j.source_id == req.source_id and j.kind == "refresh"
           for j in repo.list_jobs()):
        return JSONResponse(error("RATE_LIMITED", "A refresh for this source is already pending.", True),
                            status_code=429)
    job = Job(job_id="job_" + uuid.uuid4().hex, source_id=req.source_id, kind="refresh", state="queued",
              started_at=datetime.now(timezone.utc).isoformat())
    repo.put_job(job)
    return {"schema_version": "1", "job_id": job.job_id, "state": job.state,
            "note": "Queued only; the refresh executor is not implemented yet (T12)."}
