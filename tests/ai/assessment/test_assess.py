"""T19 batched assessment and its SSE streaming, with FAKE endpoints. Synthetic example.org data only."""
import json
import os
import sys
import time

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from app.ai.assess import QUERY_NEED_ID, BatchStats, assess
from app.ai.client import ApertusClient, InferenceError
from app.ai.config import InferenceConfig
from app.ai.interpret import Interpretation
from app.api import enrichment
from app.contracts import AssessmentPayload, Need, Result, SseEvent

V = "ver_" + "a" * 32
NEEDS = [Need(schema_version="1", need_id="need_u1", text="wearable glucose sensing", origin="user", kind="competency"),
         Need(schema_version="1", need_id="need_u2", text="clinical validation", origin="user", kind="competency")]


def card(i, *sentences, fields=None):
    return Result(entity_id=f"ent_c{i}", entity_type="unit", rank=i, display_name=f"Example Group {i}",
                  fields=fields or {}, reason="", freshness="unknown", retrieval={},
                  evidence=[{"version_id": V, "sentence_id": f"{V}:s{i * 10 + n}", "text": t,
                             "url": "https://example.org"} for n, t in enumerate(sentences, start=1)])


C1 = card(1, "The group develops wearable glucose sensors.", "It runs clinical studies with 40 patients.")
C2 = card(2, "The group hosted a seminar on robotics.")


def verdict(cand, category, coverage, explanation="Fits.", questions=()):
    return {"candidate": cand, "category": category, "explanation": explanation,
            "unresolved_questions": list(questions),
            "coverage": [f"{n}: {s}: " + " ".join(f"E{x}" for x in e) for n, s, e in coverage]}


def fake(*batches, status=200):
    calls = []

    def handler(req):
        calls.append(json.loads(req.content))
        if status != 200:
            return httpx.Response(status, json={})
        body = {"assessments": batches[min(len(calls), len(batches)) - 1]}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(body)}}],
                                         "usage": {"prompt_tokens": 400, "completion_tokens": 150}})

    c = ApertusClient(InferenceConfig(base_url="https://fake.test/v1", api_key="k", max_retries=0),
                      transport=httpx.MockTransport(handler), sleep=lambda s: None)
    c.calls = calls
    return c


def test_evidence_numbers_map_to_the_candidates_own_sentences():
    c = fake([verdict(1, "direct_match", [("need_u1", "supported", [1]), ("need_u2", "partial", [2])],
                      "Develops wearable glucose sensors and runs clinical studies.", ["Open to industry projects?"]),
              verdict(2, "insufficient_evidence", [("need_u1", "none", []), ("need_u2", "none", [])],
                      "No evidence of glucose sensing.")])
    out, stats = assess("glucose sensor", NEEDS, [C1, C2], client=c)
    a1, a2 = out
    assert isinstance(a1, AssessmentPayload) and a1.category == "direct_match"
    assert a1.need_coverage[0].evidence == [{"version_id": V, "sentence_id": f"{V}:s11"}]
    assert a1.evidence == [{"version_id": V, "sentence_id": f"{V}:s11"}, {"version_id": V, "sentence_id": f"{V}:s12"}]
    assert a2.category == "insufficient_evidence" and stats.corrections == {}
    prompt = c.calls[0]["messages"][1]["content"]
    assert "E1: The group develops wearable glucose sensors." in prompt and "E3: The group hosted a seminar" in prompt


def test_foreign_evidence_and_unsupported_claims_are_corrected():
    c = fake([verdict(2, "direct_match", [("need_u1", "supported", [1]), ("need_x", "supported", [3])])])
    out, stats = assess("glucose sensor", NEEDS, [C1, C2], client=c)
    a2 = next(a for a in out if a.entity_id == "ent_c2")
    assert a2.category == "insufficient_evidence" and all(n.support == "none" for n in a2.need_coverage)
    assert {n.need_id for n in a2.need_coverage} == {"need_u1", "need_u2"}
    assert stats.corrections == {"foreign_evidence_number": 1, "support_without_evidence": 1,
                                 "unknown_or_duplicate_need": 1, "category_downgraded": 1,
                                 "candidate_not_assessed": 1}


def test_related_capability_needs_partial_support():
    c = fake([verdict(1, "direct_match", [("need_u1", "partial", [1])])])
    out, stats = assess("glucose sensor", NEEDS, [C1], client=c)
    assert out[0].category == "related_capability" and stats.corrections == {"category_downgraded": 1}


def test_explanation_with_facts_not_in_evidence_is_replaced():
    c = fake([verdict(1, "direct_match", [("need_u1", "supported", [1])],
                      "Prof. X (x@example.org) has run 12 trials since 2015.")])
    out, stats = assess("glucose sensor", NEEDS, [C1], client=c)
    assert "x@example.org" not in out[0].explanation and stats.corrections["explanation_replaced"] == 1
    ok = fake([verdict(1, "direct_match", [("need_u1", "supported", [1, 2])], "Clinical studies with 40 patients.")])
    assert assess("glucose sensor", NEEDS, [C1], client=ok)[0][0].explanation == "Clinical studies with 40 patients."


def test_batches_are_bounded_and_results_stream_as_ready():
    cands = [card(i, f"Sentence about topic {i}.") for i in range(1, 11)]
    batch = [verdict(i, "insufficient_evidence", []) for i in range(1, 5)]
    c = fake(batch, batch)
    seen = []
    out, stats = assess("topic", NEEDS, cands, client=c, on_result=seen.append)
    assert len(c.calls) == 2 and len(out) == 8 and seen == out and stats.candidates == 8
    assert stats.usage.prompt_tokens == 800 and len(stats.latency_s) == 2


def test_query_is_the_need_when_none_given_and_duplicates_ignored():
    c = fake([verdict(1, "related_capability", [(QUERY_NEED_ID, "partial", [1])]),
              verdict(1, "direct_match", [(QUERY_NEED_ID, "supported", [1])]),
              verdict(7, "direct_match", [])])
    out, stats = assess("glucose sensor", [], [C1], client=c)
    assert len(out) == 1 and out[0].category == "related_capability"
    assert stats.corrections == {"unknown_or_duplicate_candidate": 2}


def test_endpoint_failure_propagates():
    with pytest.raises(InferenceError):
        assess("glucose sensor", NEEDS, [C1], client=fake(status=503))


# --- SSE ------------------------------------------------------------------------------
BODY = {"schema_version": "1", "query": "glucose sensor", "revision": 1, "entity_type": None,
        "company_context": None, "needs": [n.model_dump() for n in NEEDS], "enrichment_requested": True}


@pytest.fixture
def api():
    app = FastAPI()
    app.include_router(enrichment.router)
    enrichment.registry.clear()
    enrichment.set_interpreter(lambda req: Interpretation(needs=list(req.needs), expanded_queries=[],
                                                          clarification=None, partner_type=None))
    enrichment.set_candidate_provider(lambda req: [C1, C2])
    yield TestClient(app)
    for setter in (enrichment.set_interpreter, enrichment.set_candidate_provider, enrichment.set_assessor):
        setter(None)
    enrichment.registry.clear()


def events(resp):
    return [SseEvent(**json.loads(next(l[6:] for l in b.splitlines() if l.startswith("data: "))))
            for b in resp.text.strip().split("\n\n")]


def run(api, rid="req_a"):
    api.post(f"/api/v1/search/{rid}/enrichment", json=BODY)
    return events(api.get(f"/api/v1/search/{rid}/events?revision=1"))


def test_stream_emits_validated_assessments_then_complete(api):
    client = fake([verdict(1, "direct_match", [("need_u1", "supported", [1])]),
                   verdict(2, "insufficient_evidence", [])])
    enrichment.set_assessor(lambda q, n, c, cb: assess(q, n, c, client=client, on_result=cb))
    ev = run(api)
    assert [e.event_type for e in ev] == ["progress", "interpretation", "progress", "assessment", "assessment",
                                         "complete"]
    assert ev[2].payload == {"stage": "assessment", "state": "started", "candidates": 2}
    AssessmentPayload(**ev[3].payload)
    done = ev[-1].payload
    assert done["assessed"] == 2 and done["batches"] == 1 and "assessment_ms" in done and "interpretation_ms" in done


def test_new_revision_during_assessment_discards_late_results(api):
    def assessor(q, n, c, cb):
        enrichment.registry.register("req_a", enrichment.SearchRequest(**(BODY | {"revision": 2})))
        return assess(q, n, c, client=fake([verdict(1, "direct_match", [("need_u1", "supported", [1])])]),
                      on_result=cb)

    enrichment.set_assessor(assessor)
    ev = run(api)
    assert "assessment" not in [e.event_type for e in ev] and ev[-1].payload["code"] == "STALE_REVISION"


def test_assessment_failure_or_timeout_keeps_interpretation_and_completes(api, monkeypatch):
    def down(q, n, c, cb):
        raise InferenceError("UNAVAILABLE", "x", True)

    enrichment.set_assessor(down)
    ev = run(api, "req_d")
    types = [e.event_type for e in ev]
    assert "interpretation" in types and types[-1] == "complete"
    assert next(e for e in ev if e.event_type == "error").payload == {
        "code": "ASSESSMENT_UNAVAILABLE", "message": "Assessment is unavailable; initial results are unaffected.",
        "retryable": True, "stage": "assessment"}

    monkeypatch.setattr(enrichment, "ASSESS_TIMEOUT_S", 0.1)
    enrichment.set_assessor(lambda q, n, c, cb: (time.sleep(1), ([], BatchStats()))[1])
    ev = run(api, "req_t")
    assert next(e for e in ev if e.event_type == "error").payload["code"] == "ASSESSMENT_TIMEOUT"


def test_interpretation_failure_still_assesses_with_request_needs(api):
    def boom(req):
        raise InferenceError("UNAVAILABLE", "x", True)

    enrichment.set_interpreter(boom)
    client = fake([verdict(1, "related_capability", [("need_u1", "partial", [1])])])
    enrichment.set_assessor(lambda q, n, c, cb: assess(q, n, c, client=client, on_result=cb))
    ev = run(api, "req_i")
    assert [e.event_type for e in ev].count("assessment") == 1


def test_coverage_lines_parse_leniently_and_garbage_is_counted():
    c = fake([{"candidate": 1, "category": "direct_match", "explanation": "Fits.", "unresolved_questions": [],
               "coverage": ["need_u1 | Supported | E1, E2", "need_u2: partial", "nonsense line"]}])
    out, stats = assess("glucose sensor", NEEDS, [C1], client=c)
    cov = {n.need_id: (n.support, len(n.evidence)) for n in out[0].need_coverage}
    assert cov == {"need_u1": ("supported", 2), "need_u2": ("none", 0)}
    assert stats.corrections == {"unparseable_coverage": 1, "support_without_evidence": 1}


def test_zero_indexed_candidates_are_shifted_once():
    c = fake([verdict(0, "direct_match", [("need_u1", "supported", [1])]),
              verdict(1, "insufficient_evidence", [])])
    out, stats = assess("glucose sensor", NEEDS, [C1, C2], client=c)
    assert [a.entity_id for a in out] == ["ent_c1", "ent_c2"] and stats.corrections == {"zero_indexed_candidates": 1}
