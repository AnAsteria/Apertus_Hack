"""Purge tests on a corpus built by the real crawler against a FAKE network (synthetic pages)."""
import json
import os
import sqlite3
import sys

import httpx
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
for mod in ("protego", "yaml", "bs4", "langdetect", "pypdf"):
    pytest.importorskip(mod, reason="Install app/ingest/requirements.txt")

from app.contracts import SourceConfig
from app.ingest.network import Fetcher
from app.ingest.pipeline import crawl
from app.ingest.types import Source
from app.lifecycle import purge as P
from app.storage.corpus import CorpusStore

HOME = ('<html lang="en"><title>Home</title><body><main><h1>Research</h1><p>We study glucose sensors for '
        'diabetes patients in Bern.</p><a href="/research/people/a-muster">A Muster</a>'
        '<a href="/research/projects">Projects</a></main></body></html>')
PAGE = ('<html lang="en"><title>Page</title><body><main><h1>Page</h1><p>Some research text about '
        'glucose monitoring in diabetes.</p></main></body></html>')
NONE = {"schema_version": "1", "entries": []}


def supp(prefix):
    return {"schema_version": "1", "entries": [{"entry_id": "s", "reason_category": "removal_request",
            "action": "suppress", "confirmed_at": "x", "confirmed_by_role": "operator",
            "identifiers": {"url_prefixes": [prefix]}}]}


@pytest.fixture
def corpus(tmp_path):
    def handler(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /")
        if req.url.path.endswith("a-muster"):
            body = PAGE.replace("Some research text", "UNIQUEMARKERZ research text")
        else:
            body = HOME if req.url.path == "/research/" else PAGE
        return httpx.Response(200, text=body, headers={"content-type": "text/html"})
    src = Source(config=SourceConfig(schema_version="1", source_id="t", label="T", start_urls=["https://example.org/research/"],
                 allowed_domains=["example.org"], allowed_paths=["/research/"], languages=["en"], max_pages=10,
                 max_depth=2, requests_per_second=.5, focus_areas=["diabetes"]), labels=["unibe"], tier="focus", profile="dev")
    fetch = Fetcher(httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False),
                    resolver=lambda h: [], sleep=lambda n: None)
    crawl(src, CorpusStore(tmp_path), fetch, suppression=NONE)  # stored BEFORE the removal request arrived
    return tmp_path


def counts(path):
    db = sqlite3.connect(path / "corpus.sqlite")
    out = {t: db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
           for t in ("documents", "versions", "sentences", "pages", "active_versions", "labels")}
    db.close()
    return out


def test_dry_run_reports_but_changes_nothing(corpus):
    before = counts(corpus)
    rep = P.purge(str(corpus), supp("https://example.org/research/people/a-muster"))
    assert rep["applied"] is False and rep["documents"] == 1 and rep["sentences"] >= 1
    assert counts(corpus) == before


def test_apply_removes_only_the_suppressed_document_everywhere(corpus):
    before = counts(corpus)
    assert before["documents"] == 3  # home, a-muster, projects
    rep = P.purge(str(corpus), supp("https://example.org/research/people/a-muster"), apply=True)
    after = counts(corpus)
    assert rep["applied"] and rep["removed_urls"] == ["https://example.org/research/people/a-muster"]
    assert after["documents"] == 2 and after["versions"] == 2 and after["pages"] == 2
    assert after["active_versions"] == 2 and after["labels"] < before["labels"]
    db = sqlite3.connect(corpus / "corpus.sqlite")
    texts = " ".join(json.loads(r[0])["text"] for r in db.execute("SELECT body FROM sentences"))
    db.close()
    assert "glucose" in texts  # the other pages' sentences are intact


def test_purge_makes_citations_unavailable_not_rebound(corpus):
    db = sqlite3.connect(corpus / "corpus.sqlite")
    ver, sent = db.execute("SELECT v.id, s.id FROM versions v JOIN sentences s ON s.version_id=v.id "
                           "JOIN documents d ON d.id=v.document_id WHERE d.url LIKE '%a-muster'").fetchone()
    db.close()
    P.purge(str(corpus), supp("https://example.org/research/people/a-muster"), apply=True)
    with pytest.raises(KeyError):
        CorpusStore(corpus).get_sentence(ver, sent)


def test_removed_text_is_physically_gone_from_the_database_file(corpus):
    """The property that matters: after purge the bytes are gone, not just unreachable by queries."""
    raw = lambda: (corpus / "corpus.sqlite").read_bytes()
    assert b"UNIQUEMARKERZ" in raw()  # stored before the removal request
    P.purge(str(corpus), supp("https://example.org/research/people/a-muster"), apply=False)
    assert b"UNIQUEMARKERZ" in raw()  # dry run leaves it alone
    P.purge(str(corpus), supp("https://example.org/research/people/a-muster"), apply=True)
    assert b"UNIQUEMARKERZ" not in raw()
    assert b"glucose" in raw()  # unrelated pages are still stored


def test_report_lists_derived_directories_that_must_be_rebuilt_by_hand(corpus):
    (corpus / "knowledge").mkdir()
    (corpus / "extraction").mkdir()
    rep = P.purge(str(corpus), supp("https://example.org/research/people/a-muster"), apply=True)
    assert rep["must_rebuild_by_hand"] == ["extraction", "knowledge"]
    assert "backups" in rep["note"]


def test_missing_corpus_is_reported_not_created(tmp_path):
    rep = P.purge(str(tmp_path), supp("https://example.org/x"), apply=True)
    assert rep["corpus"] == "none" and not (tmp_path / "corpus.sqlite").exists()


def test_empty_list_purges_nothing(corpus):
    before = counts(corpus)
    assert P.purge(str(corpus), NONE, apply=True)["documents"] == 0
    assert counts(corpus) == before
