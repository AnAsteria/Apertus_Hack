"""T23/T24/T28 API: server re-reads cards by id, refuses unknown fields, and degrades without Apertus."""
import os, sys
from fastapi.testclient import TestClient
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from app import main
from app.api import brief as brief_api


def client(monkeypatch, tmp_path):
    monkeypatch.setenv("BERNMATCH_FIXTURE_MODE", "1")
    monkeypatch.setenv("BERNMATCH_DATA_DIR", str(tmp_path))
    return TestClient(main.app)


def test_brief_without_apertus_is_a_clear_503_and_unknown_ids_400(monkeypatch, tmp_path):
    c = client(monkeypatch, tmp_path)
    monkeypatch.setattr(brief_api, "_ai_ready", lambda: False)
    r = c.post("/api/v1/brief", json={"schema_version": "1", "query": "imaging", "entity_ids": ["ent_demo1"]})
    assert r.status_code == 503 and r.json()["error"]["code"] == "ENRICHMENT_UNAVAILABLE"
    r = c.post("/api/v1/brief", json={"schema_version": "1", "query": "imaging", "entity_ids": ["ent_nope"]})
    assert r.status_code == 400
    r = c.post("/api/v1/brief", json={"schema_version": "1", "query": "x", "entity_ids": ["ent_demo1"], "cards": []})
    assert r.status_code == 422   # client-sent card text is not accepted


def test_brief_uses_server_side_cards(monkeypatch, tmp_path):
    c = client(monkeypatch, tmp_path)
    monkeypatch.setattr(brief_api, "_ai_ready", lambda: True)
    seen = {}
    def fake_make(query, cards, language, note):
        seen.update(names=[x.display_name for x in cards], language=language)
        return {"kind": "brief", "entries": []}
    monkeypatch.setattr(brief_api, "make_brief", fake_make)
    r = c.post("/api/v1/brief", json={"schema_version": "1", "query": "imaging", "entity_ids": ["ent_demo1"], "language": "fr"})
    assert r.status_code == 200 and seen == {"names": ["Example Imaging Group"], "language": "fr"}
