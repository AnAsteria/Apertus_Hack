"""SQLite repository interface for jobs and feedback (CONTRACTS sections 7 and 9).

Public corpus tables belong to the ingestion/search tasks, not this skeleton.
Company context is never stored here.
"""
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Protocol

from .contracts import Feedback, Job


class IdempotencyConflict(Exception):
    pass


class Repository(Protocol):
    def init(self) -> None: ...
    def put_feedback(self, fb: Feedback) -> tuple[str, bool]: ...
    def put_job(self, job: Job) -> None: ...
    def list_jobs(self) -> list[Job]: ...
    def get_job(self, job_id: str) -> Job | None: ...


_SCHEMA = """
CREATE TABLE IF NOT EXISTS feedback (
  feedback_id TEXT PRIMARY KEY, idempotency_key TEXT UNIQUE NOT NULL,
  body TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS jobs (job_id TEXT PRIMARY KEY, body TEXT NOT NULL);
"""


class SqliteRepository:
    def __init__(self, path: str):
        self.path = path

    def _conn(self):
        return sqlite3.connect(self.path)

    def init(self) -> None:
        with self._conn() as c:
            c.executescript(_SCHEMA)

    def put_feedback(self, fb: Feedback) -> tuple[str, bool]:
        """Return (feedback_id, created). Same key + same body is a no-op; different body raises."""
        body = fb.model_dump_json(exclude={"comment"})  # free text not persisted yet
        with self._conn() as c:
            row = c.execute("SELECT feedback_id, body FROM feedback WHERE idempotency_key=?",
                            (fb.idempotency_key,)).fetchone()
            if row:
                if json.loads(row[1]) != json.loads(body):
                    raise IdempotencyConflict(fb.idempotency_key)
                return row[0], False
            fid = "fbk_" + uuid.uuid4().hex
            c.execute("INSERT INTO feedback VALUES (?,?,?,?)",
                      (fid, fb.idempotency_key, body, datetime.now(timezone.utc).isoformat()))
            return fid, True

    def put_job(self, job: Job) -> None:
        with self._conn() as c:
            c.execute("INSERT OR REPLACE INTO jobs VALUES (?,?)", (job.job_id, job.model_dump_json()))

    def list_jobs(self) -> list[Job]:
        with self._conn() as c:
            rows = c.execute("SELECT body FROM jobs").fetchall()
        return [Job.model_validate_json(r[0]) for r in rows]

    def get_job(self, job_id: str) -> Job | None:
        with self._conn() as c:
            row = c.execute("SELECT body FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        return Job.model_validate_json(row[0]) if row else None
