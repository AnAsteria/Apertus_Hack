"""T13 skeleton behaviour. Feedback ids/requests here are synthetic; no real search is involved."""
import json
import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app import main

FIX = os.path.join(os.path.dirname(__file__), "..", "fixtures", "feedback.json")
FB = json.load(open(FIX, encoding="utf-8"))
TOKEN = "test-admin-token"


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("BERNMATCH_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BERNMATCH_ADMIN_TOKEN", TOKEN)
    return TestClient(main.app)


def test_feedback_created_then_idempotent_then_conflict(client):
    a = client.post("/api/v1/feedback", json=FB)
    assert a.status_code == 201
    b = client.post("/api/v1/feedback", json=FB)
    assert b.status_code == 200 and b.json()["feedback_id"] == a.json()["feedback_id"]
    c = client.post("/api/v1/feedback", json={**FB, "action": "not_relevant"})
    assert c.status_code == 409 and c.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_feedback_survives_restart(monkeypatch, tmp_path):
    monkeypatch.setenv("BERNMATCH_DATA_DIR", str(tmp_path))
    first = TestClient(main.app).post("/api/v1/feedback", json=FB).json()["feedback_id"]
    again = TestClient(main.app).post("/api/v1/feedback", json=FB)  # fresh client, same file
    assert again.status_code == 200 and again.json()["feedback_id"] == first


def test_free_text_and_needs_are_refused_not_silently_dropped(client):
    assert client.post("/api/v1/feedback", json={**FB, "idempotency_key": "k2", "comment": "secret plan"}).status_code == 422
    needs = [{"schema_version": "1", "need_id": "n1", "text": "x", "origin": "user", "kind": "problem"}]
    assert client.post("/api/v1/feedback", json={**FB, "idempotency_key": "k3", "needs": needs}).status_code == 422


def test_unknown_field_rejected(client):
    assert client.post("/api/v1/feedback", json={**FB, "idempotency_key": "k4", "extra": 1}).status_code == 422


def test_admin_disabled_without_token_configured(monkeypatch, tmp_path):
    monkeypatch.setenv("BERNMATCH_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("BERNMATCH_ADMIN_TOKEN", raising=False)
    c = TestClient(main.app)
    assert c.get("/api/v1/admin/coverage", headers={"X-Admin-Token": ""}).status_code == 403
    assert c.post("/api/v1/admin/refresh", json={"schema_version": "1", "source_id": "s"}).status_code == 403


def test_admin_rejects_missing_or_wrong_token(client):
    assert client.get("/api/v1/admin/coverage").status_code == 401
    assert client.get("/api/v1/admin/coverage", headers={"X-Admin-Token": "nope"}).status_code == 401
    r = client.post("/api/v1/admin/refresh", json={"schema_version": "1", "source_id": "s"})
    assert r.status_code == 401


def test_refresh_queues_one_job_per_source_and_never_claims_a_crawl(client):
    h = {"X-Admin-Token": TOKEN}
    r = client.post("/api/v1/admin/refresh", json={"schema_version": "1", "source_id": "unibe"}, headers=h)
    assert r.status_code == 202 and r.json()["state"] == "queued"
    again = client.post("/api/v1/admin/refresh", json={"schema_version": "1", "source_id": "unibe"}, headers=h)
    assert again.status_code == 429
    cov = client.get("/api/v1/admin/coverage", headers=h).json()
    assert cov["jobs_by_state"] == {"queued": 1}


def _corpus(path):
    import sqlite3
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE versions (id TEXT PRIMARY KEY, body TEXT NOT NULL)")
    db.execute("CREATE TABLE sentences (id TEXT PRIMARY KEY, version_id TEXT NOT NULL, body TEXT NOT NULL)")
    pages = [("v1", "https://www.artorg.unibe.ch/a", "active", "2026-10-18T10:00:00+00:00"),
             ("v2", "https://www.artorg.unibe.ch/b", "retired", "2026-10-18T12:00:00+00:00"),
             ("v3", "https://www.dcberne.com/x", "active", None)]
    for vid, url, state, fetched in pages:
        db.execute("INSERT INTO versions VALUES (?,?)", (vid, json.dumps({"url": url, "state": state, "fetched_at": fetched})))
    for i, vid in enumerate(["v1", "v1", "v2", "v3"]):
        db.execute("INSERT INTO sentences VALUES (?,?,?)", (f"s{i}", vid, "{}"))
    db.commit(); db.close()


def test_coverage_counts_pages_and_sentences_per_source(client, tmp_path):
    _corpus(tmp_path / "corpus.sqlite")
    client.post("/api/v1/feedback", json=FB)
    cov = client.get("/api/v1/admin/coverage", headers={"X-Admin-Token": TOKEN}).json()
    art, dcb = cov["sources"]
    assert art == {"source": "www.artorg.unibe.ch", "pages": 2, "active": 1, "retired": 1, "suppressed": 0,
                   "sentences": 3, "fetched_first": "2026-10-18T10:00:00+00:00", "fetched_last": "2026-10-18T12:00:00+00:00"}
    assert dcb["pages"] == 1 and dcb["sentences"] == 1 and dcb["fetched_last"] is None
    assert cov["totals"] == {"pages": 3, "active": 2, "retired": 1, "suppressed": 0, "sentences": 4}
    assert cov["feedback_by_action"] == {FB["action"]: 1}


def test_coverage_without_corpus_says_so(client):
    cov = client.get("/api/v1/admin/coverage", headers={"X-Admin-Token": TOKEN}).json()
    assert cov["sources"] == [] and "totals" not in cov and "No corpus is loaded" in cov["note"]


def test_admin_page_keeps_the_token_in_memory_and_renders_text_only():
    js = open(os.path.join(os.path.dirname(__file__), "..", "..", "app", "static", "admin.js"), encoding="utf-8").read()
    for bad in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "localStorage", "sessionStorage", "document.cookie", "?token", "&token"):
        assert bad not in js
    assert '"X-Admin-Token": token' in js
