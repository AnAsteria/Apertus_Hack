"""Suppression matching tests. All names and URLs are SYNTHETIC (example.org)."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.lifecycle import suppression as S

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")


def entry(eid="s1", **ids):
    return {"entry_id": eid, "reason_category": "removal_request", "action": "suppress",
            "confirmed_at": "2026-10-18T12:00:00Z", "confirmed_by_role": "operator", "identifiers": ids}


def data(*entries):
    return {"schema_version": "1", "entries": list(entries)}


def test_shipped_list_is_valid_and_starts_empty():
    d = S.load(os.path.join(ROOT, "config", "suppression.json"))
    assert d["entries"] == []


def test_url_prefix_respects_path_boundary_and_host():
    d = data(entry(url_prefixes=["https://www.example.org/people/a-muster"]))
    assert S.is_suppressed_url(d, "http://example.org/people/a-muster")
    assert S.is_suppressed_url(d, "https://example.org/people/a-muster/publications")
    assert not S.is_suppressed_url(d, "https://example.org/people/a-muster-junior")  # different page
    assert not S.is_suppressed_url(d, "https://other.example.org/people/a-muster")  # different host


def test_exact_url_and_fragment_free_comparison():
    d = data(entry(urls=["https://example.org/p/x/"]))
    assert S.is_suppressed_url(d, "https://www.example.org/p/x")
    assert not S.is_suppressed_url(d, "https://example.org/p/x/other")


def test_names_match_ignoring_case_accents_and_spacing():
    d = data(entry(names=["Zoë  Müller"]))
    assert S.is_suppressed_entity(d, names=["zoe muller"])
    assert not S.is_suppressed_entity(d, names=["Zoe Muller-Smith"])


def test_entity_id_and_profile_url_matches():
    d = data(entry("a", entity_ids=["ent_a1"]), entry("b", url_prefixes=["https://example.org/g"]))
    assert S.is_suppressed_entity(d, entity_id="ent_a1")
    assert S.is_suppressed_entity(d, entity_id="ent_zz", urls=["https://example.org/g/team"])
    assert not S.is_suppressed_entity(d, entity_id="ent_zz", urls=["https://example.org/h"])


def test_validation_requires_recorded_verification_and_an_identifier():
    bad = entry(names=["X"])
    bad.pop("confirmed_by_role")
    assert any("verification" in p for p in S.validate(data(bad)))
    assert any("at least one identifier" in p for p in S.validate(data(entry())))
    worse = entry(names=["X"])
    worse["reason_category"] = "because he said so"
    assert any("reason_category" in p for p in S.validate(data(worse)))
    assert any("duplicate" in p for p in S.validate(data(entry("d", names=["a"]), entry("d", names=["b"]))))
    assert S.validate(data(entry(names=["X"]))) == []


def test_load_refuses_invalid_file(tmp_path):
    p = tmp_path / "s.json"
    p.write_text(json.dumps(data(entry())))  # no identifier
    with pytest.raises(ValueError):
        S.load(str(p))
