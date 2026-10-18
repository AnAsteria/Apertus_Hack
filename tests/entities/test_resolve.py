"""T08 entity resolution on SYNTHETIC records (example.org)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.contracts import Claim, Entity, content_hash, make_document_id, make_sentence_id, make_version_id
from app.entities.resolve import PageInput, finalize, resolve


def ver(tag):
    doc = make_document_id("demo", f"https://example.org/{tag}")
    return doc, make_version_id(doc, content_hash(tag), "p1")


def ent(eid, name, etype="unit", profiles=()):
    return Entity(schema_version="1", entity_id=eid, entity_type=etype, name=name, canonical_profiles=list(profiles),
                  status="unknown", resolution_state="uncertain")


def claim(cid, subj, pred, vid, n=1, value=None, obj=None, support="pending"):
    return Claim(schema_version="1", claim_id=cid, subject_entity_id=subj, predicate=pred, value=value,
                 object_entity_id=obj, evidence=[{"version_id": vid, "sentence_id": make_sentence_id(vid, n)}],
                 support=support)


def page(tag, stubs=(), entities=(), claims=(), labels=("demo",), variants=()):
    doc, vid = ver(tag)
    return PageInput(version_id=vid, document_id=doc, url=f"https://example.org/{tag}", source_labels=list(labels),
                     variant_document_ids=list(variants), stubs=list(stubs), entities=list(entities),
                     claims=list(claims))


def test_page_anchor_merges_extraction_into_stub_and_rewrites_claims():
    _, vid = ver("spn")
    stub = ent("ent_stub1", "SPN-005 – Pilot study on painless glucose monitoring", "project",
               ["https://example.org/spn"])
    x = ent("ent_x1", "SPN-005", "project")
    p = page("spn", [stub], [x], [claim("clm_1", "ent_x1", "expertise", vid, value="glucose monitoring")])
    entities, claims, rep = resolve([p])
    assert [e.entity_id for e in entities] == ["ent_stub1"]
    assert entities[0].alias_entity_ids == ["ent_x1"] and entities[0].resolution_state == "confirmed"
    assert claims[0].subject_entity_id == "ent_stub1" and rep.merges == {"A_page_anchor": 1}


def test_ambiguous_page_anchor_is_not_merged():
    _, vid = ver("two")
    p = page("two", [ent("ent_s1", "Imaging Group Alpha"), ent("ent_s2", "Imaging Group Beta")],
             [ent("ent_x1", "Imaging Group")])
    entities, _, rep = resolve([p])
    assert len(entities) == 3 and rep.merges == {}


def test_language_variant_stubs_merge():
    d_en, _ = ver("en")
    d_de, _ = ver("de")
    en = page("en", [ent("ent_en", "SPN-005 – Pilot study", "project")], variants=[d_de])
    de = page("de", [ent("ent_de", "SPN-005 – Pilotstudie", "project")], variants=[d_en])
    entities, _, rep = resolve([en, de])
    assert len(entities) == 1 and rep.merges == {"B_language_variant": 1}


def test_organisations_need_shared_site_or_profile():
    same_site = resolve([page("a", entities=[ent("ent_a", "Diabetes Center Berne (DCB)")], labels=["dcb"]),
                         page("b", entities=[ent("ent_b", "DCB")], labels=["dcb"])])
    assert len(same_site[0]) == 1 and same_site[2].merges == {"C_org_name_and_site": 1}
    other_site = resolve([page("a", entities=[ent("ent_a", "Imaging Group")], labels=["artorg"]),
                          page("b", entities=[ent("ent_b", "Imaging Group")], labels=["dcb"])])
    assert len(other_site[0]) == 2


def test_same_name_persons_merge_only_with_shared_affiliation():
    _, va = ver("pa")
    _, vb = ver("pb")
    lab = ent("ent_lab", "Example Lab")
    a = page("pa", [lab], [ent("ent_p1", "Prof. Anna Example", "person")],
             [claim("clm_a", "ent_p1", "member_of", va, obj="ent_lab")])
    b = page("pb", [], [ent("ent_p2", "Anna Example", "person"), ent("ent_lab2", "Example Lab")],
             [claim("clm_b", "ent_p2", "member_of", vb, obj="ent_lab2")])
    entities, _, rep = resolve([a, b])
    assert sum(e.entity_type == "person" for e in entities) == 1  # lab merged by C, then persons by D
    assert "D_person_name_and_affiliation" in rep.merges and rep.possible_duplicates == []

    c = page("pc", [], [ent("ent_p3", "Anna Example", "person")])
    entities, _, rep = resolve([page("pa", [], [ent("ent_p1", "Anna Example", "person")]), c])
    assert sum(e.entity_type == "person" for e in entities) == 2
    assert rep.possible_duplicates == [["ent_p1", "ent_p3"]]


def test_duplicate_claims_merge_evidence_and_collapsed_relations_drop():
    _, vid = ver("dup")
    stub = ent("ent_s", "Example Lab")
    x = ent("ent_x", "Example Lab")
    p = page("dup", [stub], [x], [claim("clm_1", "ent_x", "expertise", vid, 1, value="Sensors"),
                                  claim("clm_2", "ent_s", "expertise", vid, 2, value="sensors"),
                                  claim("clm_3", "ent_x", "part_of", vid, 3, obj="ent_s")])
    _, claims, _ = resolve([p])
    assert len(claims) == 1 and len(claims[0].evidence) == 2


def test_finalize_lists_claims_and_only_supported_affiliations():
    _, vid = ver("fin")
    entities = [ent("ent_p", "Anna Example", "person"), ent("ent_u", "Example Lab")]
    claims = [claim("clm_1", "ent_p", "member_of", vid, obj="ent_u", support="supported"),
              claim("clm_2", "ent_p", "affiliation", vid, 2, obj="ent_u", support="unsupported"),
              claim("clm_3", "ent_u", "official_contact", vid, 3, value="lab@example.org", support="supported")]
    out = {e.entity_id: e for e in finalize(entities, claims)}
    assert out["ent_p"].affiliation_entity_ids == ["ent_u"] and out["ent_p"].claim_ids == ["clm_1", "clm_2"]
    assert out["ent_u"].contact_claim_ids == ["clm_3"]


def test_page_anchor_is_one_to_one_and_prefers_the_best_name():
    stub = ent("ent_stub", "Prize for Best DBMR Publication - Department for BioMedical Research")
    prize = ent("ent_prize", "Prize for Best DBMR Publication")
    dbmr = ent("ent_dbmr", "DBMR")
    entities, _, rep = resolve([page("prize", [stub], [prize, dbmr])])
    by_id = {e.entity_id: e for e in entities}
    assert by_id["ent_stub"].alias_entity_ids == ["ent_prize"] and "ent_dbmr" in by_id
    assert by_id["ent_stub"].name == "Prize for Best DBMR Publication"  # extracted name, not page title


def test_short_name_inside_a_longer_title_does_not_anchor():
    stub = ent("ent_stub", "Prize for Best DBMR Publication")
    entities, _, rep = resolve([page("p", [stub], [ent("ent_dbmr", "DBMR")])])
    assert len(entities) == 2 and rep.merges == {}
