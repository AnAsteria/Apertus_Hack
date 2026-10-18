"""T18 integration: search -> POST enrichment -> SSE events, with the SYNTHETIC fixture interpreter.
Ruihan's router and interpreter have their own tests (tests/ai/interpretation); no model is called here."""
import json
import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app import main
from app.api import enrich, enrichment, search as search_api
from app.contracts import SseEvent

BODY = {"schema_version": "1", "query": "imaging", "revision": 1, "entity_type": None,
        "company_context": None, "needs": [], "enrichment_requested": True}


def parse_sse(text):
    out = []
    for block in text.strip().split("\n\n"):
        lines = dict(l.split(": ", 1) for l in block.splitlines() if ": " in l)
        out.append((lines["event"], json.loads(lines["data"])))
    return out


@pytest.fixture(autouse=True)
def clean():
    search_api.set_backend(None)
    enrichment.registry.clear()
    enrichment.set_interpreter(None)
    yield
    search_api.set_backend(None)
    enrichment.registry.clear()
    enrichment.set_interpreter(None)


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("BERNMATCH_FIXTURE_MODE", "1")
    monkeypatch.setenv("BERNMATCH_DATA_DIR", str(tmp_path))
    enrichment.set_interpreter(enrich.fixture_interpreter)
    return TestClient(main.app)


def start(client, body=BODY):
    rid = client.post("/api/v1/search", json=body).json()["request_id"]
    r = client.post(f"/api/v1/search/{rid}/enrichment", json=body)
    assert r.status_code == 202
    return rid, r.json()["events_url"]


def test_cards_come_back_first_and_state_is_pending(client):
    r = client.post("/api/v1/search", json=BODY).json()
    assert r["enrichment_state"] == "pending" and r["results"]


def test_not_requested_stays_not_requested(client):
    r = client.post("/api/v1/search", json={**BODY, "enrichment_requested": False}).json()
    assert r["enrichment_state"] == "not_requested"


def test_full_flow_events_are_ordered_and_contract_valid(client):
    rid, url = start(client)
    evs = parse_sse(client.get(url).text)
    assert [t for t, _ in evs] == ["progress", "interpretation", "complete"]
    for _, d in evs:
        SseEvent(**d)
        assert d["request_id"] == rid and d["revision"] == 1
    assert [d["event_sequence"] for _, d in evs] == sorted(d["event_sequence"] for _, d in evs)


def test_suggestions_are_never_presented_as_user_requirements(client):
    _, url = start(client)
    payload = parse_sse(client.get(url).text)[1][1]["payload"]
    assert {n["origin"] for n in payload["needs"]} == {"suggested"}  # the analyst typed nothing as a need
    assert payload["expanded_queries"][0]["source"] == "imaging"      # each expansion names its source term
    assert payload["decoding_mode"] == "synthetic"                    # the UI keys its SYNTHETIC banner off this


def test_rerun_echoes_the_analysts_needs_and_adds_no_suggestions(client):
    edited = [{"schema_version": "1", "need_id": "u1", "text": "my edited need", "origin": "user", "kind": "problem"}]
    body = {**BODY, "revision": 2, "needs": edited}
    _, url = start(client, body)
    needs = parse_sse(client.get(url).text)[1][1]["payload"]["needs"]
    assert [(n["text"], n["origin"]) for n in needs] == [("my edited need", "user")]


def test_stale_revision_cannot_overwrite_a_newer_search(client):
    rid = client.post("/api/v1/search", json=BODY).json()["request_id"]
    assert client.post(f"/api/v1/search/{rid}/enrichment", json={**BODY, "revision": 2}).status_code == 202
    assert client.post(f"/api/v1/search/{rid}/enrichment", json={**BODY, "revision": 1}).status_code == 409


def test_without_key_or_fixture_mode_enrichment_is_unavailable_and_cards_still_work(monkeypatch, tmp_path):
    monkeypatch.delenv("BERNMATCH_FIXTURE_MODE", raising=False)
    monkeypatch.delenv("APERTUS_API_KEY", raising=False)
    monkeypatch.setenv("BERNMATCH_DATA_DIR", str(tmp_path))
    (tmp_path / "READY").write_text("")
    from app.contracts import SearchResponse

    class Real:
        def search(self, req):
            return SearchResponse(schema_version="1", request_id="req_real", revision=req.revision, results=[],
                                  limitations=["x"], enrichment_state="not_requested")
    search_api.set_backend(Real())
    r = TestClient(main.app).post("/api/v1/search", json=BODY)
    assert r.status_code == 200 and r.json()["enrichment_state"] == "unavailable"


def test_card_field_labels_cover_the_t08_card_fields():
    js = open(os.path.join(os.path.dirname(__file__), "..", "..", "app", "static", "app.js"), encoding="utf-8").read()
    for name in ("official_contact", "services", "role", "leads", "led_by", "members", "part_of", "includes"):
        assert name + ":" in js, name  # a T08 field the UI would otherwise silently not show
    assert "Official contact (role only, not expertise)" in js  # D1: a contact is labelled as a contact
