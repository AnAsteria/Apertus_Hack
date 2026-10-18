"""T33: a small per-client rate limit on the public API routes.

Sliding one-minute window per client, kept in memory (one Space replica, so no shared store is
needed). `BERNMATCH_RATE_LIMIT_PER_MIN` sets the limit (default 120; 0 turns it off) and is read
on every request, so a Space variable change applies after the restart it triggers.

Behind the Hugging Face proxy every request arrives from a proxy address, so the client is the
first `X-Forwarded-For` entry. A client can forge that header; this limit slows scanners and
accidental loops, it is not an abuse defence. Only `/api/` paths count: the static UI, health
checks and evidence links are never limited.
"""
import os
import threading
import time
from collections import deque

from fastapi import Request
from fastapi.responses import JSONResponse

from ..contracts import error

WINDOW_S = 60.0
_hits: dict[str, deque] = {}
_lock = threading.Lock()


def limit_per_min() -> int:
    try:
        return max(0, int(os.environ.get("BERNMATCH_RATE_LIMIT_PER_MIN", "120")))
    except ValueError:
        return 120


def client_key(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def allow(key: str, limit: int, now: float | None = None) -> tuple[bool, int]:
    """Record one hit for `key`. Returns (allowed, seconds until a slot frees up)."""
    now = time.monotonic() if now is None else now
    with _lock:
        q = _hits.setdefault(key, deque())
        while q and now - q[0] >= WINDOW_S:
            q.popleft()
        if len(q) >= limit:
            return False, max(1, int(WINDOW_S - (now - q[0])) + 1)
        q.append(now)
        if len(_hits) > 10_000:  # bound memory: drop clients with no hit in the window
            for k in [k for k, v in _hits.items() if not v or now - v[-1] >= WINDOW_S]:
                del _hits[k]
        return True, 0


def reset() -> None:
    with _lock:
        _hits.clear()


async def middleware(request: Request, call_next):
    limit = limit_per_min()
    if limit and request.url.path.startswith("/api/"):
        ok, retry = allow(client_key(request), limit)
        if not ok:
            return JSONResponse(error("RATE_LIMITED", "Too many requests. Please wait a moment.", True),
                                status_code=429, headers={"Retry-After": str(retry)})
    return await call_next(request)
