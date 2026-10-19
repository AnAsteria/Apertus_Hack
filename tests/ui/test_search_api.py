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


def test_ui_hides_empty_fields_without_a_not_stated_line():
    js = _static("app.js")
    # empty fields are skipped; analysts asked not to see a list of what the sources do not say
    assert "not stated in sources" not in js.lower()


def test_ui_respects_reduced_motion_and_dark_mode():
    css = _static("style.css")
    assert "prefers-reduced-motion" in css and "prefers-color-scheme: dark" in css


def test_ui_does_not_highlight_function_words():
    import json, subprocess, shutil
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    js = _static("app.js")
    start = js.index("var STOP_WORDS")
    end = js.index("\n}\n", js.index("function termsOf")) + 3
    script = js[start:end] + "\nconsole.log(JSON.stringify(termsOf('Bildgebung in der Herzchirurgie')));"
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, check=True).stdout
    assert json.loads(out) == ["bildgebung", "herzchirurgie"]


def test_why_panel_uses_only_retrieval_signals_and_says_so():
    js = _static("app.js")
    start = js.index("function renderWhy")
    body = js[start:js.index("function renderCard(", start)]
    for key in ("keyword_rank", "dense_rank", "matched_terms", "query_language", "evidence_language"):
        assert key in body
    assert "Not a probability and not AI-generated." in body
    assert "fetch(" not in body  # built from the card payload, no extra requests


def test_rerank_animation_respects_reduced_motion():
    js = _static("app.js")
    body = js[js.index("function rerankCards"):js.index("function renderCards")]
    assert "prefers-reduced-motion: reduce" in body


def test_direct_cards_render_when_apertus_is_off_or_unavailable():
    # runSearch sets resultsShown = true; the non-pending branch must reset it, or showDirect()
    # returns at once and the cards never appear (found on main 54f77fc with Apertus unavailable).
    js = _static("app.js")
    body = js[js.index("function runSearch"):]
    branch = body[body.index("} else {", body.index('b.enrichment_state === "pending" && b.results.length')):]
    assert branch.index("resultsShown = false") < branch.index("showDirect()")


def test_ui_files_always_revalidate():
    # A stale cached style.css next to a new index.html broke the page in Chrome (19 Oct).
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    for path in ("/", "/style.css", "/app.js"):
        assert client.get(path).headers.get("cache-control") == "no-cache"
    assert 'href="style.css?v=' in _static("index.html")


def test_hero_image_is_served_as_webp():
    from fastapi.testclient import TestClient
    from app.main import app
    assert TestClient(app).get("/hero.webp").headers["content-type"] == "image/webp"


def test_enter_submits_logo_goes_home_and_transition_respects_reduced_motion():
    js, html = _static("app.js"), _static("index.html")
    # Enter submits through the form (requestSubmit), Shift+Enter keeps a new line
    key = js[js.index('getElementById("query").addEventListener("keydown"'):]
    key = key[:key.index("});")]
    assert '"Enter"' in key and "!ev.shiftKey" in key and "requestSubmit" in key
    # the logo is a real link that resets to the welcome view and invalidates the running search
    assert 'id="home"' in html and 'addEventListener("click", goHome)' in js
    home = js[js.index("function goHome"):js.index("initHero();", js.index("function goHome"))]
    for step in ("revision += 1", "closeEvents()", 'value = ""', 'classList.remove("searched"'):
        assert step in home
    # the welcome -> results glide is skipped for reduced motion
    enter = js[js.index("function enterResults"):js.index("function goHome")]
    assert "prefers-reduced-motion: reduce" in enter


def test_out_of_scope_refusal_folds_the_cards_and_hidden_always_wins():
    js, css = _static("app.js"), _static("style.css")
    handler = js[js.index('es.addEventListener("interpretation"'):js.index('es.addEventListener("reranked"')]
    assert 'outcome_update === "out_of_scope"' in handler and "renderRefusal()" in handler
    refusal = js[js.index("function renderRefusal"):js.index("function renderOutcome")]
    assert "This request is outside what the indexed corpus covers." in refusal
    assert "Show the {n} direct results anyway" in refusal  # folded, never deleted
    assert "[hidden] { display: none !important; }" in css


def test_people_strip_is_a_parallel_people_only_search_with_a_strict_rule():
    import json, subprocess, shutil
    js, html = _static("app.js"), _static("index.html")
    assert 'id="people"' in html
    body = js[js.index("function loadPeople"):js.index("function renderPeople")]
    assert 'entity_type: "person"' in body and "myRevision !== revision" in body
    assert "loadPeople(query, myRevision)" in js  # started with every search, in parallel
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    fn = js[js.index("function strongPerson"):js.index("function loadPeople")]
    cases = [{"dense_rank": 2, "keyword_rank": 38, "matched_terms": []},     # Stephan Gerber, CGM: shown
             {"dense_rank": 1, "keyword_rank": None, "matched_terms": []},   # meaning only: not shown
             {"dense_rank": 11, "keyword_rank": 4, "matched_terms": []},     # Rebecca Buller, CGM: not shown
             {"dense_rank": 9, "keyword_rank": 1, "matched_terms": ["insulin"]}]
    script = fn + "\nconsole.log(JSON.stringify(%s.map(function (s) { return !!strongPerson({ retrieval: s }); })));" % json.dumps(cases)
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, check=True).stdout
    assert json.loads(out) == [True, False, False, True]
