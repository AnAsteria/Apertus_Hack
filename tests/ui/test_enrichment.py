"""T18 UI half: SSE enrichment endpoint behaviour on SYNTHETIC fixtures. No model is called."""
import json
import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app import main
from app.api import enrich, search as search_api
from app.contracts import SCHEMA_VERSION, SseEvent

BODY = {"schema_version": "1", "query": "imaging", "revision": 1, "entity_type": None,
        "company_context": None, "needs": [], "enrichment_requested": True}


def parse_sse(text):
    events = []
    for block in text.strip().split("\n\n"):
        lines = dict(l.split(": ", 1) for l in block.splitlines() if ": " in l)
        events.append((lines["event"], json.loads(lines["data"])))
    return events


@pytest.fixture(autouse=True)
def clean():
    search_api.set_backend(None)
    enrich.set_enrichment_backend(None)
    enrich._registry.clear()
    yield
    enrich.set_enrichment_backend(None)
    enrich._registry.clear()


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("BERNMATCH_FIXTURE_MODE", "1")
    monkeypatch.setenv("BERNMATCH_DATA_DIR", str(tmp_path))
    return TestClient(main.app)


def test_cards_come_back_without_waiting_and_state_is_pending(client):
    r = client.post("/api/v1/search", json=BODY).json()
    assert r["enrichment_state"] == "pending" and r["results"]


def test_not_requested_stays_not_requested(client):
    r = client.post("/api/v1/search", json={**BODY, "enrichment_requested": False}).json()
    assert r["enrichment_state"] == "not_requested"


def test_events_are_ordered_validated_and_labelled_synthetic(client):
    rid = client.post("/api/v1/search", json=BODY).json()["request_id"]
    r = client.get(f"/api/v1/search/{rid}/events")
    assert r.headers["content-type"].startswith("text/event-stream")
    evs = parse_sse(r.text)
    assert [t for t, _ in evs] == ["progress", "interpretation", "complete"]
    seqs = [d["event_sequence"] for _, d in evs]
    assert seqs == sorted(seqs) and len(set(seqs)) == 3
    for _, d in evs:
        SseEvent(**d)  # envelope validates against the contract
        assert d["request_id"] == rid and d["revision"] == 1
    assert evs[1][1]["payload"]["synthetic"] is True


def test_suggestions_are_never_presented_as_user_requirements(client):
    rid = client.post("/api/v1/search", json=BODY).json()["request_id"]
    needs = parse_sse(client.get(f"/api/v1/search/{rid}/events").text)[1][1]["payload"]["needs"]
    by_origin = {n["origin"] for n in needs}
    assert by_origin == {"user", "suggested"}
    assert [n["text"] for n in needs if n["origin"] == "user"] == ["imaging"]  # only what was typed


def test_rerun_echoes_edited_needs_and_adds_no_new_suggestions(client):
    edited = [{"schema_version": "1", "need_id": "u1", "text": "my edited need", "origin": "user", "kind": "problem"}]
    rid = client.post("/api/v1/search", json={**BODY, "revision": 2, "needs": edited}).json()["request_id"]
    needs = parse_sse(client.get(f"/api/v1/search/{rid}/events").text)[1][1]["payload"]["needs"]
    assert [n["text"] for n in needs] == ["my edited need"]
    assert all(n["origin"] == "user" for n in needs)


def test_unknown_request_id_is_an_in_stream_error_not_a_crash(client):
    evs = parse_sse(client.get("/api/v1/search/req_nope/events").text)
    assert evs[0][0] == "error" and evs[0][1]["payload"]["code"] == "ENRICHMENT_UNAVAILABLE"


def test_without_any_backend_enrichment_is_unavailable_and_cards_still_work(monkeypatch, tmp_path):
    monkeypatch.delenv("BERNMATCH_FIXTURE_MODE", raising=False)
    monkeypatch.setenv("BERNMATCH_DATA_DIR", str(tmp_path))
    (tmp_path / "READY").write_text("")

    class Real:
        def search(self, req):
            from app.contracts import SearchResponse
            return SearchResponse(schema_version="1", request_id="req_real", revision=req.revision, results=[],
                                  limitations=["x"], enrichment_state="not_requested")
    search_api.set_backend(Real())
    r = TestClient(main.app).post("/api/v1/search", json=BODY)
    assert r.status_code == 200 and r.json()["enrichment_state"] == "unavailable"


def test_plugged_backend_is_used_and_failure_becomes_generic_error_event(client):
    class Boom:
        async def events(self, request_id, revision, query, needs):
            raise RuntimeError("secret internal detail: " + query)
            yield  # pragma: no cover
    enrich.set_enrichment_backend(Boom())
    rid = client.post("/api/v1/search", json=BODY).json()["request_id"]
    text = client.get(f"/api/v1/search/{rid}/events").text
    evs = parse_sse(text)
    assert evs[-1][0] == "error" and evs[-1][1]["payload"]["code"] == "ENRICHMENT_FAILED"
    assert "secret internal detail" not in text and "imaging" not in text


def test_registry_is_bounded_and_expires(client):
    for i in range(enrich.MAX_REGISTERED + 5):
        enrich.register(f"req_{i}", enrich.SearchRequest(**{**BODY, "revision": 1}))
    assert len(enrich._registry) == enrich.MAX_REGISTERED
    first = next(iter(enrich._registry))
    enrich._registry[first]["at"] -= enrich.TTL_SECONDS + 1
    enrich.register("req_new", enrich.SearchRequest(**BODY))
    assert first not in enrich._registry
