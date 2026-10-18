"""CONTRACTS section 3 models and identifier recipes. Fixture is SYNTHETIC (example.org)."""
import copy
import json
import os
import sys

import pytest
from pydantic import ValidationError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.contracts import (Claim, Document, Entity, EvidencePair, Passage, Sentence, Version, content_hash,
                           make_document_id, make_passage_id, make_sentence_id, make_version_id)

FIX = os.path.join(os.path.dirname(__file__), "..", "fixtures", "corpus_synthetic.json")


@pytest.fixture
def corpus():
    with open(FIX, encoding="utf-8") as f:
        return json.load(f)


def bad(model, data, **changes):
    d = copy.deepcopy(data) | changes
    with pytest.raises(ValidationError):
        model(**d)


# --- identifier recipes (DECISIONS.md) ------------------------------------------------
def test_id_recipes_are_deterministic_and_formatted():
    doc = make_document_id("dcb", "https://www.dcberne.com/en/projects/")
    assert doc == make_document_id("dcb", "https://www.dcberne.com/en/projects/")
    assert doc.startswith("doc_") and len(doc) == 36
    assert doc != make_document_id("artorg", "https://www.dcberne.com/en/projects/")
    ver = make_version_id(doc, content_hash("text"), "parser-1")
    assert ver.startswith("ver_") and ver != make_version_id(doc, content_hash("text"), "parser-2")
    assert make_sentence_id(ver, 3) == f"{ver}:s3" and make_passage_id(ver, 1) == f"{ver}:p1"
    with pytest.raises(ValueError):
        make_sentence_id(ver, 0)


def test_separator_prevents_concatenation_collisions():
    assert make_document_id("ab", "c") != make_document_id("a", "bc")


def test_content_hash_is_over_text_not_bytes_encoding():
    assert content_hash("Zürich") == content_hash("Zürich") and len(content_hash("x")) == 64


# --- fixture round-trip --------------------------------------------------------------
def test_synthetic_corpus_matches_contracts(corpus):
    Document(**corpus["document"])
    v = Version(**corpus["version"])
    sentences = [Sentence(**s) for s in corpus["sentences"]]
    assert [s.sentence_id for s in sentences] == v.passages[0].sentence_ids
    entities = {e["entity_id"]: Entity(**e) for e in corpus["entities"]}
    claims = [Claim(**c) for c in corpus["claims"]]
    known = {s.sentence_id for s in sentences}
    for c in claims:
        assert c.subject_entity_id in entities
        assert all(e.sentence_id in known for e in c.evidence)
    assert [c.claim_id for c in claims if c.surfaceable] == ["clm_demo1", "clm_demo2"]


# --- documents and versions ----------------------------------------------------------
def test_document_rejects_bad_id_and_self_variant(corpus):
    d = corpus["document"]
    bad(Document, d, document_id="doc_demo")
    bad(Document, d, language_variant_document_ids=[d["document_id"]])
    bad(Document, d, schema_version="2")
    bad(Document, d, unexpected="x")


def test_version_id_must_follow_recipe(corpus):
    bad(Version, corpus["version"], parser_version="parser-2")  # id no longer matches
    bad(Version, corpus["version"], content_hash="A" * 64)
    bad(Version, corpus["version"], state="deleted")
    bad(Version, corpus["version"], page_type="news")


def test_version_rejects_foreign_or_shared_sentences(corpus):
    v = corpus["version"]
    other = make_version_id(v["document_id"], content_hash("other"), "parser-1")
    p = v["passages"][0]
    bad(Version, v, passages=[p | {"passage_id": make_passage_id(other, 1),
                                   "sentence_ids": [make_sentence_id(other, 1)]}])
    bad(Version, v, passages=[p, p | {"passage_id": p["passage_id"][:-1] + "2"}])


def test_passage_rejects_cross_version_and_duplicate_sentences(corpus):
    p = corpus["version"]["passages"][0]
    ver = p["passage_id"].split(":")[0]
    other = make_version_id(corpus["document"]["document_id"], content_hash("x"), "p")
    bad(Passage, p, sentence_ids=[make_sentence_id(other, 1)])
    bad(Passage, p, sentence_ids=[make_sentence_id(ver, 1)] * 2)
    bad(Passage, p, sentence_ids=[])


def test_sentence_must_belong_to_its_version(corpus):
    s = corpus["sentences"][0]
    other = make_version_id(corpus["document"]["document_id"], content_hash("x"), "p")
    bad(Sentence, s, version_id=other)
    bad(Sentence, s, text="")
    bad(Sentence, s, page_number=0)


# --- entities ------------------------------------------------------------------------
def test_entity_reference_rules(corpus):
    e = corpus["entities"][0]
    bad(Entity, e, affiliation_entity_ids=[e["entity_id"]])
    bad(Entity, e, contact_claim_ids=["clm_notowned"])
    bad(Entity, e, resolution_state="merged")
    bad(Entity, e, entity_id="person_1")


# --- claims --------------------------------------------------------------------------
def test_claim_needs_exactly_one_of_value_or_object(corpus):
    c = corpus["claims"][0]
    bad(Claim, c, value=None)
    bad(Claim, c, object_entity_id="ent_demoperson")
    bad(Claim, c, value="   ")


def test_claim_requires_evidence_and_same_version_pairs(corpus):
    c = corpus["claims"][0]
    bad(Claim, c, evidence=[])
    pair = c["evidence"][0]
    bad(Claim, c, evidence=[pair, pair])
    other = make_version_id(corpus["document"]["document_id"], content_hash("x"), "p")
    with pytest.raises(ValidationError):
        EvidencePair(version_id=other, sentence_id=pair["sentence_id"])


def test_value_predicates_cannot_point_at_entities(corpus):
    c = corpus["claims"][0]  # expertise
    bad(Claim, c, value=None, object_entity_id="ent_demoperson")
    rel = corpus["claims"][1]  # leader
    bad(Claim, rel, object_entity_id=rel["subject_entity_id"])


def test_qualified_needs_qualification_and_pending_is_not_surfaceable(corpus):
    c = corpus["claims"][0]
    bad(Claim, c, support="qualified")
    assert Claim(**(c | {"support": "qualified", "qualification": "Project ended 2024."})).surfaceable
    assert not Claim(**(c | {"support": "pending"})).surfaceable
    assert not Claim(**(c | {"support": "unsupported"})).surfaceable
