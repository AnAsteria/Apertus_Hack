"""T33: per-client rate limit on /api/ routes."""
import os
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app import main
from app.api import ratelimit, search as search_api

BODY = {"schema_version": "1", "query": "imaging", "revision": 1, "entity_type": None,
        "company_context": None, "needs": [], "enrichment_requested": False}


def _client(monkeypatch, tmp_path, limit):
    monkeypatch.setenv("BERNMATCH_FIXTURE_MODE", "1")
    monkeypatch.setenv("BERNMATCH_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BERNMATCH_RATE_LIMIT_PER_MIN", str(limit))
    search_api.set_backend(None)
    ratelimit.reset()
    return TestClient(main.app)


def test_limit_returns_429_with_retry_after_and_is_per_client(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path, 3)
    a = {"X-Forwarded-For": "198.51.100.1, 10.0.0.1"}
    assert [c.post("/api/v1/search", json=BODY, headers=a).status_code for _ in range(3)] == [200] * 3
    r = c.post("/api/v1/search", json=BODY, headers=a)
    assert r.status_code == 429 and r.json()["error"]["code"] == "RATE_LIMITED"
    assert int(r.headers["Retry-After"]) >= 1
    # another client is not affected
    assert c.post("/api/v1/search", json=BODY, headers={"X-Forwarded-For": "198.51.100.2"}).status_code == 200


def test_ui_and_health_are_never_limited(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path, 1)
    for _ in range(5):
        assert c.get("/healthz").status_code == 200
        assert c.get("/").status_code == 200


def test_zero_turns_it_off(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path, 0)
    assert all(c.post("/api/v1/search", json=BODY).status_code == 200 for _ in range(10))


def test_window_slides():
    ratelimit.reset()
    assert ratelimit.allow("k", 2, now=0)[0] and ratelimit.allow("k", 2, now=1)[0]
    assert not ratelimit.allow("k", 2, now=2)[0]
    assert ratelimit.allow("k", 2, now=61)[0]


def test_healthz_reports_revision_or_none():
    assert "revision" in TestClient(main.app).get("/healthz").json()
