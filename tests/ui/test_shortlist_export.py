"""T38: shortlist export is source-only, notes are labelled text, request text only on opt-in."""
import json
import os
import shutil
import subprocess

import pytest

HARNESS = os.path.join(os.path.dirname(__file__), "shortlist_harness.js")
RESULT = {
    "entity_id": "ent_spn005", "entity_type": "project", "rank": 1,
    "display_name": "SPN-005 Pilot study on painless glucose monitoring",
    "fields": {"expertise": [{"claim_id": "clm_1", "value": "non-invasive glucose monitoring"}], "role": []},
    "reason": "Found by keyword match.", "freshness": "fresh", "retrieval": {},
    "evidence": [
        {"version_id": "v1", "sentence_id": "s1", "url": "https://www.dcberne.com/en/project/spn-005/",
         "text": "This project evaluates a novel non-invasive technology — without finger pricks.",
         "content_date": None, "last_modified": "2026-10-09T01:12:42+00:00", "fetched_at": "2026-10-18T14:35:17+00:00"},
        {"version_id": "v1", "sentence_id": "s2", "url": "https://www.dcberne.com/en/project/spn-005/",
         "text": "Second sentence.", "content_date": None, "last_modified": None, "fetched_at": "2026-10-18T14:35:17+00:00"},
        {"version_id": "v1", "sentence_id": "s3", "url": "https://www.dcberne.com/en/project/spn-005/",
         "text": "Third sentence is not exported.", "content_date": None, "last_modified": None, "fetched_at": None},
    ],
}
NOTE = "<b>call them</b> <script>alert(1)</script>"


def run(opt):
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump({"result": RESULT, "note": NOTE}, f, ensure_ascii=False)
    try:
        out = subprocess.run([node, HARNESS, f.name, opt], capture_output=True, check=True).stdout
    finally:
        os.remove(f.name)
    return json.loads(out.decode("utf-8"))


def test_export_is_source_only_and_quotes_are_byte_identical():
    out = run("no-request")
    e = out["data"]["entries"][0]
    assert [q["text"] for q in e["evidence"]] == [RESULT["evidence"][0]["text"], RESULT["evidence"][1]["text"]]
    assert all(q["url"] == RESULT["evidence"][0]["url"] for q in e["evidence"])
    assert e["fields"] == {"expertise": ["non-invasive glucose monitoring"]}  # empty fields are not exported
    assert out["printed"] == 1
    assert RESULT["evidence"][0]["text"] in out["printText"]


def test_request_text_only_with_opt_in():
    assert "CONFIDENTIAL" not in json.dumps(run("no-request"))
    assert run("with-request")["data"]["request"].startswith("CONFIDENTIAL")


def test_notes_are_labelled_plain_text_and_facts_are_not_editable():
    out = run("no-request")
    assert out["data"]["entries"][0]["analyst_note"] == NOTE
    flat = json.dumps(out["printView"])
    assert "Analyst note (not a source fact)" in flat
    # the note is a text node, never parsed: no element was created from its markup
    assert '"tag": "SCRIPT"' not in flat and '"tag": "B"' not in flat
    assert "No AI-generated text is included." in out["printText"]
    # an entry offers field-visibility checkboxes and the note box only; quotes and facts have no inputs
    assert sorted(set(out["controls"])) == ["INPUT:checkbox", "TEXTAREA:"]


def test_apertus_assessment_only_with_opt_in_and_labelled():
    off = run("no-request")
    assert "AI_TEXT_MARKER" not in json.dumps(off)
    assert off["data"]["entries"][0]["apertus_assessment"] is None and off["data"]["includes_ai_text"] is False
    on = run("with-ai")
    a = on["data"]["entries"][0]["apertus_assessment"]
    assert a["ai_generated"] is True and a["is_source_fact"] is False and a["generated_by"].startswith("Apertus")
    assert "AI_TEXT_MARKER" in on["printText"]
    assert "AI-generated assessment (Apertus), not source text" in on["printText"]
    assert "No AI-generated text is included." not in on["printText"]  # the footer must not lie
    assert "not the person" in on["printText"]


def test_no_contact_field_points_to_the_source_page():
    e = run("no-request")["data"]["entries"][0]
    assert e["start_from"] == RESULT["evidence"][0]["url"]


def test_verdict_from_an_earlier_search_is_not_exported():
    out = run("older")
    e = out["data"]["entries"][0]
    assert e["apertus_assessment"] is None and e["apertus_assessment_from_earlier_search"] is True
    assert "AI_TEXT_MARKER" not in json.dumps(out)
    assert "from an earlier search" in out["printText"]
    assert "No AI-generated text is included." in out["printText"]


def test_new_verdict_for_the_current_request_replaces_an_older_one_and_exports_cited_sentences():
    out = run("newer")
    e = out["data"]["entries"][0]
    a = e["apertus_assessment"]
    assert e["apertus_assessment_from_earlier_search"] is False
    assert "AI_TEXT_MARKER" not in json.dumps(out)  # the older verdict is gone
    # the exact stored sentence Apertus cited, once; an id that is not on the card is left out
    assert a["cited"] == [{"text": RESULT["evidence"][2]["text"], "url": RESULT["evidence"][2]["url"]}]
    assert RESULT["evidence"][2]["text"] in out["printText"] and "Cited by Apertus:" in out["printText"]
    # the server's fixed sentence is not Apertus' own text, and the export says so
    assert a["explanation_by"].startswith("Bern Match standard sentence")
    assert "Standard sentence from Bern Match" in out["printText"]
