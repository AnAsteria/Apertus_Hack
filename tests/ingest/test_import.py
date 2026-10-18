"""Round trip: crawl a fake site -> export JSONL -> import into a fresh database -> identical records."""
import io
import json
import sys
from contextlib import redirect_stdout

import httpx
import pytest

for mod in ("protego", "yaml", "bs4", "langdetect", "pypdf"):
    pytest.importorskip(mod, reason="Install app/ingest/requirements.txt")

from app.contracts import SourceConfig
from app.ingest import __main__ as cli
from app.ingest.network import Fetcher
from app.ingest.pipeline import crawl
from app.ingest.types import Source
from app.storage.corpus import CorpusStore

HOME = ('<html lang="en"><title>Home</title><body><main><h1>Research Group</h1><p>We study glucose sensors for '
        'diabetes patients.</p><a href="/research/people/a">A</a></main></body></html>')
PAGE = ('<html lang="de"><title>Seite</title><body><main><h1>Seite</h1><p>Forschung zu Glukosemessung bei '
        'Diabetes.</p></main></body></html>')


def make_corpus(tmp_path):
    def handler(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /")
        return httpx.Response(200, text=HOME if req.url.path == "/research/" else PAGE,
                              headers={"content-type": "text/html"})
    src = Source(config=SourceConfig(schema_version="1", source_id="t", label="T", start_urls=["https://example.org/research/"],
                 allowed_domains=["example.org"], allowed_paths=["/research/"], languages=["en", "de"], max_pages=10,
                 max_depth=2, requests_per_second=.5, focus_areas=["diabetes"]), labels=["unibe"], tier="focus", profile="dev")
    fetch = Fetcher(httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False),
                    resolver=lambda h: [], sleep=lambda n: None)
    store = CorpusStore(tmp_path / "a")
    crawl(src, store, fetch, suppression={"entries": []})
    return store


def run(monkeypatch, *argv):
    monkeypatch.setattr(sys, "argv", ["ingest", *argv])
    buf = io.StringIO()
    with redirect_stdout(buf):
        cli.main()
    return buf.getvalue()


def snapshot(records):
    return sorted((r["document"].document_id, r["version"].version_id, r["version"].content_hash,
                   tuple(s.sentence_id + "|" + s.text for s in r["sentences"]),
                   tuple(sorted(e.entity_id for e in r["entities"])),
                   tuple(sorted((k, tuple(sorted(v))) for k, v in r["passage_entity_ids"].items())),
                   tuple(r["source_labels"])) for r in records)


def test_export_then_import_gives_the_same_records_and_ids(tmp_path, monkeypatch):
    original = make_corpus(tmp_path)
    jsonl = tmp_path / "corpus.jsonl"
    jsonl.write_text(run(monkeypatch, "export", "--data-dir", str(tmp_path / "a")), encoding="utf-8")
    expected_docs = len(original.active_records())
    assert expected_docs >= 2 and jsonl.read_text(encoding="utf-8").count("\n") == expected_docs
    out = json.loads(run(monkeypatch, "import", "--jsonl", str(jsonl), "--data-dir", str(tmp_path / "b")))
    assert out["documents"] == expected_docs and out["sentences"] > 0
    restored = CorpusStore(tmp_path / "b")
    assert snapshot(restored.active_records()) == snapshot(original.active_records())


def test_import_is_repeatable_and_exact_sentences_resolve(tmp_path, monkeypatch):
    original = make_corpus(tmp_path)
    jsonl = tmp_path / "corpus.jsonl"
    jsonl.write_text(run(monkeypatch, "export", "--data-dir", str(tmp_path / "a")), encoding="utf-8")
    for _ in range(2):  # importing twice must not duplicate anything
        run(monkeypatch, "import", "--jsonl", str(jsonl), "--data-dir", str(tmp_path / "b"))
    restored = CorpusStore(tmp_path / "b")
    assert snapshot(restored.active_records()) == snapshot(original.active_records())
    rec = restored.active_records()[0]
    s = rec["sentences"][0]
    assert restored.get_sentence(rec["version"].version_id, s.sentence_id).text == s.text


def test_import_needs_a_file(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["ingest", "import", "--data-dir", str(tmp_path)])
    with pytest.raises(SystemExit):
        cli.main()


def test_export_writes_utf8_even_when_the_terminal_encoding_is_cp1252(tmp_path, monkeypatch):
    """Windows consoles default to cp1252; a minus sign (U+2212) used to crash the export."""
    store = make_corpus(tmp_path)
    with store.connect() as db:  # put a character that cp1252 cannot encode into a stored sentence
        sid, body = db.execute("SELECT id, body FROM sentences LIMIT 1").fetchone()
        row = json.loads(body); row["text"] = row["text"] + " − minus"
        db.execute("UPDATE sentences SET body=? WHERE id=?", (json.dumps(row), sid))
    raw = io.BytesIO()
    wrapper = io.TextIOWrapper(raw, encoding="cp1252", newline="\n")
    monkeypatch.setattr(sys, "argv", ["ingest", "export", "--data-dir", str(tmp_path / "a")])
    monkeypatch.setattr(sys, "stdout", wrapper)
    cli.main()
    wrapper.flush()
    text = raw.getvalue().decode("utf-8")
    assert "− minus" in text
