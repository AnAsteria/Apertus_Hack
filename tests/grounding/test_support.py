"""T08 support checks and card fields on SYNTHETIC records with a FAKE judge endpoint."""
import json
import os
import sys

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.ai.client import ApertusClient
from app.ai.config import InferenceConfig
from app.contracts import Claim, Entity, content_hash, make_document_id, make_sentence_id, make_version_id
from app.grounding.fields import card_fields, missing_fields
from app.grounding.support import check_claims, claim_statement
from app.grounding.text import ABSENCE_TEXT

DOC = make_document_id("demo", "https://example.org/lab")
VID = make_version_id(DOC, content_hash("lab"), "p1")
SENTENCES = {
    1: "The Example Lab develops wearable glucose sensors.",
    2: "Prof. Anna Example leads the Example Lab.",
    3: "Contact: lab@example.org",
    4: "The Example Lab hosted a seminar on robotics.",
}
LOOKUP = lambda v, s: SENTENCES.get(int(s.rsplit(":s", 1)[1])) if v == VID else None

LAB = Entity(schema_version="1", entity_id="ent_lab", entity_type="unit", name="Example Lab", status="unknown",
             resolution_state="confirmed")
ANNA = Entity(schema_version="1", entity_id="ent_anna", entity_type="person", name="Anna Example",
              status="unknown", resolution_state="uncertain")
ENTS = {e.entity_id: e for e in (LAB, ANNA)}


def claim(cid, subj, pred, n, value=None, obj=None, vid=VID):
    return Claim(schema_version="1", claim_id=cid, subject_entity_id=subj, predicate=pred, value=value,
                 object_entity_id=obj, evidence=[{"version_id": vid, "sentence_id": make_sentence_id(vid, n)}],
                 support="pending")


def judge(*verdict_lists, status=200):
    calls = []

    def handler(req):
        calls.append(json.loads(req.content))
        if status != 200:
            return httpx.Response(status, json={})
        v = verdict_lists[min(len(calls), len(verdict_lists)) - 1]
        body = {"verdicts": [{"item": i, "verdict": x} for i, x in v]}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(body)}}],
                                         "usage": {"prompt_tokens": 50, "completion_tokens": 10}})

    c = ApertusClient(InferenceConfig(base_url="https://fake.test/v1", api_key="k", max_retries=0),
                      transport=httpx.MockTransport(handler), sleep=lambda s: None)
    c.calls = calls
    return c


def support_of(claims):
    return {c.claim_id: c.support for c in claims}


def test_rules_decide_names_contacts_roles_without_the_judge():
    claims = [claim("clm_name", "ent_lab", "name", 1, value="Example Lab"),
              claim("clm_badname", "ent_lab", "name", 3, value="Example Lab"),
              claim("clm_contact", "ent_lab", "official_contact", 3, value="lab@example.org"),
              claim("clm_role", "ent_anna", "role", 2, value="Prof."),
              claim("clm_rolenoname", "ent_anna", "role", 1, value="sensors")]
    c = judge()
    out, rep = check_claims(claims, ENTS, LOOKUP, client=c)
    assert support_of(out) == {"clm_name": "supported", "clm_badname": "unsupported", "clm_contact": "supported",
                               "clm_role": "supported", "clm_rolenoname": "unsupported"}
    assert c.calls == [] and rep.reasons == {"name_not_in_evidence": 1, "role_person_not_in_evidence": 1}


def test_unavailable_or_cross_version_evidence_fails():
    other = make_version_id(DOC, content_hash("other"), "p1")
    out, rep = check_claims([claim("clm_x", "ent_lab", "name", 1, value="Example Lab", vid=other),
                             claim("clm_y", "ent_lab", "name", 99, value="Example Lab")], ENTS, LOOKUP, client=judge())
    assert set(support_of(out).values()) == {"unsupported"} and rep.reasons == {"evidence_unavailable": 2}


def test_group_expertise_is_not_transferred_to_member():
    out, rep = check_claims([claim("clm_e", "ent_anna", "expertise", 1, value="glucose sensors")], ENTS, LOOKUP,
                            client=judge())
    assert support_of(out) == {"clm_e": "unsupported"} and rep.reasons == {"group_expertise_not_transferred": 1}


def test_leader_needs_person_subject():
    out, rep = check_claims([claim("clm_l", "ent_lab", "leader", 2, obj="ent_anna")], ENTS, LOOKUP, client=judge())
    assert rep.reasons == {"subject_not_person": 1}


def test_judge_maps_supported_reversed_unsupported():
    claims = [claim("clm_exp", "ent_lab", "expertise", 1, value="wearable glucose sensors"),
              claim("clm_lead", "ent_anna", "leader", 2, obj="ent_lab"),
              claim("clm_rev", "ent_lab", "part_of", 2, obj="ent_anna"),
              claim("clm_mislead", "ent_lab", "expertise", 4, value="robotics")]  # valid citation, misleading claim
    c = judge([(1, "supported"), (2, "supported"), (3, "reversed"), (4, "unsupported")])
    out, rep = check_claims(claims, ENTS, LOOKUP, client=c)
    assert support_of(out) == {"clm_exp": "supported", "clm_lead": "supported", "clm_rev": "unsupported",
                               "clm_mislead": "unsupported"}
    assert rep.reasons == {"judge_reversed": 1, "judge_unsupported": 1} and rep.judged == 4
    prompt = c.calls[0]["messages"][1]["content"]
    assert "Anna Example leads Example Lab." in prompt and "«Prof. Anna Example leads the Example Lab.»" in prompt


def test_judge_failure_or_missing_verdict_keeps_claims_pending():
    claims = [claim("clm_a", "ent_lab", "expertise", 1, value="sensors"),
              claim("clm_b", "ent_lab", "expertise", 4, value="robotics")]
    out, rep = check_claims(claims, ENTS, LOOKUP, client=judge(status=503))
    assert set(support_of(out).values()) == {"pending"} and rep.reasons == {"judge_unavailable": 2}
    out, _ = check_claims(claims, ENTS, LOOKUP, client=judge([(1, "supported"), (1, "unsupported")]))
    assert support_of(out) == {"clm_a": "supported", "clm_b": "pending"}


def test_claim_statement_templates():
    assert claim_statement(claim("clm_c1", "ent_anna", "member_of", 2, obj="ent_lab"), ENTS) == \
        "Anna Example is a member of Example Lab."


def test_card_fields_use_supported_claims_only_and_keep_roles_apart():
    claims = [claim("clm_exp", "ent_lab", "expertise", 1, value="wearable glucose sensors"),
              claim("clm_lead", "ent_anna", "leader", 2, obj="ent_lab"),
              claim("clm_contact", "ent_lab", "official_contact", 3, value="lab@example.org"),
              claim("clm_bad", "ent_lab", "expertise", 4, value="robotics")]
    claims = [c.model_copy(update={"support": "unsupported" if c.claim_id == "clm_bad" else "supported"})
              for c in claims]
    lab = card_fields(LAB, claims, ENTS)
    assert {k: [v.value for v in vs] for k, vs in lab.items()} == {
        "expertise": ["wearable glucose sensors"], "led_by": ["Anna Example"], "official_contact": ["lab@example.org"]}
    assert lab["led_by"][0].claim_id == "clm_lead"
    anna = card_fields(ANNA, claims, ENTS)
    assert {k: [v.value for v in vs] for k, vs in anna.items()} == {"leads": ["Example Lab"]}  # no lab expertise
    assert missing_fields(anna, ["expertise", "leads"]) == {"expertise": ABSENCE_TEXT}
