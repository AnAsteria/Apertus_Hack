"""T10 API behaviour in SYNTHETIC fixture mode. Says nothing about real-data search quality."""
import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app import main
from app.api import search as search_api
from app.contracts import SearchResponse

BODY = {"schema_version": "1", "query": "imaging", "revision": 3, "entity_type": None,
        "company_context": None, "needs": [], "enrichment_requested": False}


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("BERNMATCH_FIXTURE_MODE", "1")
    monkeypatch.setenv("BERNMATCH_DATA_DIR", str(tmp_path))
    search_api.set_backend(None)
    return TestClient(main.app)


def test_fixture_response_is_contract_valid_and_labelled_synthetic(client):
    r = client.post("/api/v1/search", json=BODY)
    assert r.status_code == 200
    out = SearchResponse(**r.json())
    assert out.revision == 3
    assert "SYNTHETIC" in out.limitations[0]
    assert 1 <= len(out.results) <= 10
    assert all(res.evidence for res in out.results)


def test_entity_type_is_respected_and_ranks_renumbered(client):
    out = client.post("/api/v1/search", json={**BODY, "entity_type": "person"}).json()
    assert [r["entity_type"] for r in out["results"]] == ["person"]
    assert out["results"][0]["rank"] == 1


def test_no_match_is_success_with_limitation_not_404(client):
    out = client.post("/api/v1/search", json={**BODY, "entity_type": "service"})
    assert out.status_code == 200
    assert out.json()["results"] == []
    assert any("indexed corpus" in l for l in out.json()["limitations"])


def test_source_and_fetch_dates_are_kept_separate(client):
    ev = client.post("/api/v1/search", json=BODY).json()["results"][0]["evidence"][0]
    assert ev["content_date"] != ev["fetched_at"]


def test_fixture_mode_is_off_by_default(monkeypatch, tmp_path):
    monkeypatch.delenv("BERNMATCH_FIXTURE_MODE", raising=False)
    monkeypatch.setenv("BERNMATCH_DATA_DIR", str(tmp_path))
    search_api.set_backend(None)
    assert TestClient(main.app).post("/api/v1/search", json=BODY).status_code == 503


def test_real_backend_replaces_fixture(client):
    class Fake:
        def search(self, req):
            return SearchResponse(schema_version="1", request_id="r", revision=req.revision, results=[],
                                  limitations=["real"], enrichment_state="not_requested")
    search_api.set_backend(Fake())
    try:
        out = client.post("/api/v1/search", json=BODY)
        # a real backend still needs ready indexes
        assert out.status_code == 503
    finally:
        search_api.set_backend(None)


def test_static_ui_has_no_inline_script_injection_sink():
    js = open(os.path.join(os.path.dirname(__file__), "..", "..", "app", "static", "app.js"), encoding="utf-8").read()
    assert "innerHTML" not in js and "document.write" not in js


def _static(name):
    return open(os.path.join(os.path.dirname(__file__), "..", "..", "app", "static", name), encoding="utf-8").read()


def test_ui_has_no_markup_sinks_and_no_external_requests():
    js, html, css = _static("app.js"), _static("index.html"), _static("style.css")
    for sink in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
        assert sink not in js
    for text in (html, css, js):
        assert "http://" not in text.replace("http://www.w3.org", "") or "https?" in text
        assert "//cdn" not in text and "googleapis" not in text


def test_ui_hides_empty_fields_and_shows_one_not_stated_line():
    js = _static("app.js")
    # empty fields are skipped (no per-field "not stated" row) and collapsed into one line
    assert "not stated in sources\"" not in js
    assert "Not stated in sources: " in js


def test_ui_respects_reduced_motion_and_dark_mode():
    css = _static("style.css")
    assert "prefers-reduced-motion" in css and "prefers-color-scheme: dark" in css
