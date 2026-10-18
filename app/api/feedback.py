"""POST /api/v1/feedback (CONTRACTS section 7).

Structured feedback only (DECISIONS.md): free-text comments and saved needs stay disabled
until retention is approved, so they are refused rather than silently dropped.
"""
import os

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..contracts import Feedback, error
from ..repository import IdempotencyConflict, SqliteRepository

router = APIRouter()


def get_repo() -> SqliteRepository:
    path = os.path.join(os.environ.get("BERNMATCH_DATA_DIR", "data"), "bernmatch.sqlite")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    repo = SqliteRepository(path)
    repo.init()
    return repo


@router.post("/api/v1/feedback")
def post_feedback(fb: Feedback):
    if fb.comment is not None or fb.needs is not None:
        return JSONResponse(
            error("VALIDATION_ERROR", "Free-text comments and saved needs are not accepted yet."),
            status_code=422)
    try:
        fid, created = get_repo().put_feedback(fb)
    except IdempotencyConflict:
        return JSONResponse(error("IDEMPOTENCY_CONFLICT", "Idempotency key reused with a different body."),
                            status_code=409)
    return JSONResponse({"schema_version": "1", "feedback_id": fid}, status_code=201 if created else 200)
