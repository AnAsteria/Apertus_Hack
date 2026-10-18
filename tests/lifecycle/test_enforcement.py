"""T12 enforcement: serving filter, 410 evidence, crawler skip. All names/URLs are SYNTHETIC."""
import json
import os
import sys

import httpx
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app import main
from app.api import search as search_api
from app.lifecycle import serving
from app.storage.corpus import CorpusStore


def write_list(path, **identifiers):
    path.write_text(json.dumps({"schema_version": "1", "entries": [{
        "entry_id": "s1", "reason_category": "removal_request", "action": "suppress",
        "confirmed_at": "2026-10-18T12:00:00Z", "confirmed_by_role": "operator", "identifiers": identifiers}]}))


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("BERNMATCH_FIXTURE_MODE", "1")
    monkeypatch.setenv("BERNMATCH_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BERNMATCH_SUPPRESSION_FILE", str(tmp_path / "supp.json"))
    search_api.set_backend(None)
    serving._cache.update(path=None, mtime=None)
    return tmp_path


BODY = {"schema_version": "1", "query": "imaging", "revision": 1, "entity_type": None,
        "company_context": None, "needs": [], "enrichment_requested": False}


def names(resp):
    return [r["display_name"] for r in resp["results"]]


def test_missing_list_suppresses_nothing(env):
    assert len(TestClient(main.app).post("/api/v1/search", json=BODY).json()["results"]) == 3


def test_suppressed_url_prefix_removes_card_and_renumbers_ranks(env):
    write_list(env / "supp.json", url_prefixes=["https://example.org/research/sensors"])
    out = TestClient(main.app).post("/api/v1/search", json=BODY).json()
    assert "Example Sensor Lab" not in names(out) and len(out["results"]) == 2
    assert [r["rank"] for r in out["results"]] == [1, 2]
    assert not any("reason" in l.lower() and "suppress" in l.lower() for l in out["limitations"])  # never says why


def test_suppressed_name_removes_card_even_without_url_match(env):
    write_list(env / "supp.json", names=["dr. a. example"])
    assert "Dr. A. Example" not in names(TestClient(main.app).post("/api/v1/search", json=BODY).json())


def test_list_edits_apply_without_restart(env):
    c = TestClient(main.app)
    assert len(c.post("/api/v1/search", json=BODY).json()["results"]) == 3
    write_list(env / "supp.json", entity_ids=["ent_demo2"])
    assert len(c.post("/api/v1/search", json=BODY).json()["results"]) == 2


def test_invalid_list_fails_loudly_instead_of_silently_serving(env):
    (env / "supp.json").write_text(json.dumps({"schema_version": "1", "entries": [{"entry_id": "x"}]}))
    with pytest.raises(ValueError):
        serving.load_suppression()


def make_corpus(tmp_path, url="https://example.org/people/a"):
    CorpusStore(tmp_path)  # creates the schema
    import sqlite3
    db = sqlite3.connect(tmp_path / "corpus.sqlite")
    db.execute("INSERT INTO versions VALUES (?,?,?)", ("ver_1", "doc_1", json.dumps({"url": url})))
    db.execute("INSERT INTO sentences VALUES (?,?,?)",
               ("ver_1:s1", "ver_1", json.dumps({"text": "The group researches imaging.", "page_number": None})))
    db.commit()
    db.close()


def test_evidence_returns_exact_text_when_not_suppressed(env):
    make_corpus(env)
    r = TestClient(main.app).get("/api/v1/evidence/ver_1/ver_1:s1")
    assert r.status_code == 200 and r.json()["text"] == "The group researches imaging."
    assert r.json()["url"] == "https://example.org/people/a"


def test_evidence_is_410_when_suppressed_and_when_missing(env):
    make_corpus(env)
    write_list(env / "supp.json", url_prefixes=["https://example.org/people/a"])
    c = TestClient(main.app)
    gone = c.get("/api/v1/evidence/ver_1/ver_1:s1")
    assert gone.status_code == 410 and gone.json()["error"]["code"] == "EVIDENCE_REMOVED"
    assert "imaging" not in gone.text  # no text leaks
    assert c.get("/api/v1/evidence/ver_1/ver_1:s9").status_code == 410
    assert c.get("/api/v1/evidence/ver_9/ver_9:s1").status_code == 410


def test_evidence_does_not_create_a_corpus_when_none_exists(env):
    r = TestClient(main.app).get("/api/v1/evidence/ver_1/ver_1:s1")
    assert r.status_code == 503 and not (env / "corpus.sqlite").exists()


# --- crawler skip -------------------------------------------------------------------------
pytest.importorskip("protego", reason="Install app/ingest/requirements.txt")
pytest.importorskip("yaml")
pytest.importorskip("bs4")
pytest.importorskip("langdetect")
pytest.importorskip("pypdf")

from app.contracts import SourceConfig  # noqa: E402
from app.ingest.network import Fetcher  # noqa: E402
from app.ingest.pipeline import crawl  # noqa: E402
from app.ingest.types import Source  # noqa: E402

HOME = ('<html lang="en"><title>Home</title><body><main><h1>Research</h1><p>We study glucose sensors for '
        'diabetes patients in Bern.</p><a href="/research/people/a-muster">A Muster</a>'
        '<a href="/research/projects">Projects</a></main></body></html>')
PAGE = ('<html lang="en"><title>Page</title><body><main><h1>Page</h1><p>Some research text about '
        'glucose monitoring in diabetes.</p></main></body></html>')


def src():
    return Source(config=SourceConfig(schema_version="1", source_id="t", label="T", start_urls=["https://example.org/research/"],
                  allowed_domains=["example.org"], allowed_paths=["/research/"], languages=["en"], max_pages=10,
                  max_depth=2, requests_per_second=.5, focus_areas=["diabetes"]), labels=["unibe"], tier="focus", profile="dev")


def test_crawler_never_requests_suppressed_urls(tmp_path):
    requested = []

    def handler(req):
        requested.append(req.url.path)
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /")
        body = HOME if req.url.path == "/research/" else PAGE
        return httpx.Response(200, text=body, headers={"content-type": "text/html"})
    supp = {"schema_version": "1", "entries": [{"entry_id": "s", "reason_category": "removal_request",
            "action": "suppress", "confirmed_at": "x", "confirmed_by_role": "operator",
            "identifiers": {"url_prefixes": ["https://example.org/research/people/a-muster"]}}]}
    store = CorpusStore(tmp_path)
    fetch = Fetcher(httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False),
                    resolver=lambda h: [], sleep=lambda n: None)
    report = crawl(src(), store, fetch, suppression=supp)
    assert "/research/people/a-muster" not in requested
    assert "/research/projects" in requested
    assert report["counts"]["suppressed"] == 1
    urls = {r["document"].canonical_url for r in store.active_records()}
    assert not any("a-muster" in u for u in urls)


def test_refresh_with_changed_text_makes_a_new_version_and_old_citation_keeps_its_text(tmp_path):
    state = {"html": PAGE}

    def handler(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /")
        return httpx.Response(200, text=state["html"], headers={"content-type": "text/html"})

    def run(refresh):
        fetch = Fetcher(httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False),
                        resolver=lambda h: [], sleep=lambda n: None)
        return crawl(src(), CorpusStore(tmp_path), fetch, refresh=refresh, suppression={"entries": []})

    run(False)
    before = CorpusStore(tmp_path).active_records()[0]
    old_version, old_sentence = before["version"].version_id, before["sentences"][0]
    state["html"] = PAGE.replace("Some research text about glucose monitoring", "Completely rewritten text about heart imaging")
    report = run(True)
    after = CorpusStore(tmp_path).active_records()[0]
    assert report["counts"]["new_versions"] == 1
    assert after["version"].version_id != old_version  # new version became active
    kept = CorpusStore(tmp_path).get_sentence(old_version, old_sentence.sentence_id)
    assert kept.text == old_sentence.text  # the old citation is never rebound to new text
    assert "heart imaging" in " ".join(s.text for s in after["sentences"])
