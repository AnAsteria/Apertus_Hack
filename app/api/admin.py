"""Protected operator routes (CONTRACTS sections 4 and 9).

Auth is a server-side secret in `BERNMATCH_ADMIN_TOKEN`, sent as the `X-Admin-Token` header.
No token configured means the admin API is disabled (403), never open. A custom header is not
sent by cross-site forms or image tags, which gives the browser request protection T13 asks for.

Refresh only records a queued job: the executor is T12's and does not exist yet, so the
response never claims a crawl ran.
"""
import hmac
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from ..contracts import Job, error
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


@router.get("/api/v1/admin/coverage")
def coverage(x_admin_token: Optional[str] = Header(default=None)):
    if (d := _denied(x_admin_token)) is not None:
        return d
    jobs = get_repo().list_jobs()
    by_state: dict[str, int] = {}
    for j in jobs:
        by_state[j.state] = by_state.get(j.state, 0) + 1
    return {"schema_version": "1", "jobs_by_state": by_state,
            "failed_jobs": [j.model_dump() for j in jobs if j.state == "failed"][:50],
            "note": "Corpus coverage counts arrive with T06/T12; zero counts here do not mean coverage."}


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
