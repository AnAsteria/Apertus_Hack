"""Contract and API-skeleton tests. Fixtures are synthetic (tests/fixtures/README.md)."""
import json
import os
import sys

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app import main
from app.contracts import (AssessmentPayload, Feedback, Result, SearchRequest, SearchResponse,
                           SourceConfig, SseEvent)
from app.repository import IdempotencyConflict, SqliteRepository

FIX = os.path.join(os.path.dirname(__file__), "..", "fixtures")


def fx(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("BERNMATCH_DATA_DIR", str(tmp_path))
    return TestClient(main.app)


def test_fixtures_match_contracts():
    SearchRequest(**fx("search_request.json"))
    SearchResponse(**fx("search_response_empty.json"))
    SseEvent(**fx("sse_assessment.json"))
    AssessmentPayload(**fx("sse_assessment.json")["payload"])
    Feedback(**fx("feedback.json"))
    SourceConfig(**fx("source_config.json"))


def test_unknown_fields_and_wrong_version_are_rejected():
    body = fx("search_request.json")
    with pytest.raises(ValidationError):
        SearchRequest(**body, upload="x")
    with pytest.raises(ValidationError):
        SearchRequest(**{**body, "schema_version": "2"})
    with pytest.raises(ValidationError):
        SearchRequest(**{**body, "revision": 0})


def test_result_without_evidence_is_rejected():
    with pytest.raises(ValidationError):
        Result(entity_id="e", entity_type="unit", rank=1, display_name="x", reason="r",
               evidence=[], freshness="unknown")


def test_response_caps_results_at_ten():
    one = {"entity_id": "e", "entity_type": "unit", "rank": 1, "display_name": "x", "reason": "r",
           "freshness": "unknown",
           "evidence": [{"version_id": "v", "sentence_id": "v:s1", "text": "t", "url": "https://x"}]}
    base = fx("search_response_empty.json")
    with pytest.raises(ValidationError):
        SearchResponse(**{**base, "results": [one] * 11})


def test_readiness_false_until_marker(client, tmp_path):
    assert client.get("/healthz").status_code == 200
    r = client.get("/readyz")
    assert r.status_code == 503 and r.json()["error"]["code"] == "INDEX_NOT_READY"
    (tmp_path / "READY").write_text("")
    assert client.get("/readyz").status_code == 200


def test_search_unavailable_when_not_ready_and_never_invents_results(client, tmp_path):
    r = client.post("/api/v1/search", json=fx("search_request.json"))
    assert r.status_code == 503
    (tmp_path / "READY").write_text("")
    r = client.post("/api/v1/search", json=fx("search_request.json"))
    assert r.status_code == 501 and "results" not in r.json()


def test_oversized_input_is_413_before_anything_else(client):
    body = {**fx("search_request.json"), "company_context": "x" * 8001}
    assert client.post("/api/v1/search", json=body).status_code == 413


def test_validation_error_does_not_echo_input(client):
    secret = "ACME-CONFIDENTIAL-PLAN"
    r = client.post("/api/v1/search", json={**fx("search_request.json"), "revision": 0, "company_context": secret})
    assert r.status_code == 422
    assert secret not in r.text


def test_feedback_idempotency(tmp_path):
    repo = SqliteRepository(str(tmp_path / "t.sqlite"))
    repo.init()
    fb = Feedback(**fx("feedback.json"))
    fid, created = repo.put_feedback(fb)
    assert created
    assert repo.put_feedback(fb) == (fid, False)
    with pytest.raises(IdempotencyConflict):
        repo.put_feedback(Feedback(**{**fx("feedback.json"), "action": "not_relevant"}))
