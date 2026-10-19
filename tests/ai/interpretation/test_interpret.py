"""T18 interpretation and SSE enrichment with a FAKE endpoint/interpreter. Fictional company text only."""
import json
import logging
import os
import sys
import time

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from app.ai.client import ApertusClient, InferenceError
from app.ai.config import InferenceConfig
from app.ai.interpret import Interpretation, interpret
from app.api import enrichment
from app.contracts import Need, SseEvent

COMPANY = "Fictional startup Zebra Sports builds a wearable glucose sensor for endurance athletes."
USER_NEED = Need(schema_version="1", need_id="need_u1", text="clinical validation partner", origin="user",
                 kind="competency")
MODEL_OUT = {
    "needs": [{"text": "clinical validation partner", "kind": "competency"},       # duplicate of user need
              {"text": "wearable glucose sensor", "kind": "product"},
              {"text": "sweat-based glucose sensing", "kind": "competency"}],
    "partner_type": "unit",
    "expansions": [{"source": "glucose sensor", "text": "continuous glucose monitoring", "language": "en"},
                   {"source": "glucose sensor", "text": "Glukosesensor", "language": "de"},
                   {"source": "glucose sensor", "text": "CGM", "language": "en"},
                   {"source": "glucose sensor", "text": "cgm", "language": "en"},             # duplicate
                   {"source": "insulin pump", "text": "Insulinpumpe", "language": "de"}],     # source not in request
    "is_broad": False,
    "clarification": "Which sport?",
    "scope": "in_scope",
    "scope_reason": "research",
}


def fake_client(out=MODEL_OUT, status=200, reject_schema=False):
    calls = []

    def handler(req):
        body = json.loads(req.content)
        calls.append(body)
        if status != 200:
            return httpx.Response(status, json={})
        if reject_schema and "response_format" in body:
            return httpx.Response(400, json={})
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(out)}}],
                                         "usage": {"prompt_tokens": 300, "completion_tokens": 120}})

    c = ApertusClient(InferenceConfig(base_url="https://fake.test/v1", api_key="k", max_retries=0),
                      transport=httpx.MockTransport(handler), sleep=lambda s: None)
    c.calls = calls
    return c


# --- interpretation ------------------------------------------------------------------
def test_user_needs_kept_first_and_suggestions_deduplicated():
    r = interpret("glucose sensor partners", COMPANY, [USER_NEED], client=fake_client())
    assert r.needs[0] == USER_NEED
    assert [(n.text, n.origin) for n in r.needs[1:]] == [("wearable glucose sensor", "suggested"),
                                                         ("sweat-based glucose sensing", "suggested")]
    assert all(n.need_id.startswith("need_s") for n in r.needs[1:])
    assert r.dropped["duplicate_need"] == 1
    again = interpret("glucose sensor partners", COMPANY, [USER_NEED], client=fake_client())
    assert [n.need_id for n in again.needs] == [n.need_id for n in r.needs]


def test_expansions_are_separate_and_tied_to_request_terms():
    r = interpret("glucose sensor partners", COMPANY, client=fake_client())
    assert [(e["text"], e["language"]) for e in r.expanded_queries] == [
        ("continuous glucose monitoring", "en"), ("Glukosesensor", "de"), ("CGM", "en")]
    assert r.dropped["expansion_source_not_in_request"] == 1 and r.dropped["duplicate_expansion"] == 1
    assert all(n.text not in {e["text"] for e in r.expanded_queries} for n in r.needs)


def test_clarification_only_for_broad_requests_without_context():
    assert interpret("glucose sensor", COMPANY, client=fake_client()).clarification is None
    broad = MODEL_OUT | {"is_broad": True}
    assert interpret("medtech partners", None, client=fake_client(broad)).clarification == "Which sport?"
    assert interpret("medtech partners", COMPANY, client=fake_client(broad)).clarification is None


def test_only_user_needs_from_the_request_are_trusted():
    smuggled = Need(schema_version="1", need_id="need_x", text="must be in Zurich", origin="suggested",
                    kind="constraint")
    r = interpret("glucose sensor", COMPANY, [USER_NEED, smuggled], client=fake_client())
    assert smuggled not in r.needs and r.needs[0] == USER_NEED


def test_suggestion_limit_and_payload_shape():
    many = MODEL_OUT | {"needs": [{"text": f"need number {i}", "kind": "competency"} for i in range(8)]}
    r = interpret("glucose sensor", COMPANY, client=fake_client(many))
    assert sum(n.origin == "suggested" for n in r.needs) == 6 and r.dropped["need_limit"] == 2
    p = r.payload()
    assert set(p) == {"needs", "expanded_queries", "clarification", "scope", "scope_reason"}
    [Need(**n) for n in p["needs"]]


def test_fallback_mode_is_labelled_and_company_text_not_logged(caplog):
    caplog.set_level(logging.DEBUG)
    r = interpret("glucose sensor", COMPANY, client=fake_client(reject_schema=True))
    assert r.decoding_mode == "validated_retry_fallback"
    assert "Zebra" not in caplog.text and "endurance" not in caplog.text


def test_endpoint_failure_raises_inference_error():
    with pytest.raises(InferenceError):
        interpret("glucose sensor", COMPANY, client=fake_client(status=503))


# --- SSE enrichment -------------------------------------------------------------------
BODY = {"schema_version": "1", "query": "glucose sensor partners", "revision": 1, "entity_type": None,
        "company_context": COMPANY, "needs": [USER_NEED.model_dump()], "enrichment_requested": True}


@pytest.fixture
def api():
    app = FastAPI()
    app.include_router(enrichment.router)
    enrichment.registry.clear()
    enrichment.set_candidate_provider(lambda req: [])  # no candidates: assessment is skipped
    yield TestClient(app)
    enrichment.set_interpreter(None)
    enrichment.set_candidate_provider(None)
    enrichment.registry.clear()


def events(resp):
    out = []
    for block in resp.text.strip().split("\n\n"):
        data = next(l[6:] for l in block.splitlines() if l.startswith("data: "))
        out.append(SseEvent(**json.loads(data)))
    return out


def ok_interpreter(req):
    return interpret(req.query, req.company_context, req.needs, client=fake_client())


def test_stream_progress_interpretation_complete(api):
    enrichment.set_interpreter(ok_interpreter)
    r = api.post("/api/v1/search/req_abc/enrichment", json=BODY)
    assert r.status_code == 202 and r.json()["events_url"] == "/api/v1/search/req_abc/events?revision=1"
    s = api.get(r.json()["events_url"])
    assert s.headers["content-type"].startswith("text/event-stream")
    ev = events(s)
    assert [e.event_type for e in ev] == ["progress", "interpretation", "progress", "complete"]
    assert ev[2].payload == {"stage": "assessment", "state": "skipped", "reason": "no_candidates"}
    assert [e.event_sequence for e in ev] == [0, 1, 2, 3] and all(e.revision == 1 for e in ev)
    needs = [Need(**n) for n in ev[1].payload["needs"]]
    assert needs[0].origin == "user" and ev[1].payload["decoding_mode"] == "backend_constrained"


def test_newer_revision_makes_running_stream_stale(api):
    def slow_then_superseded(req):
        enrichment.registry.register("req_abc", enrichment.SearchRequest(**(BODY | {"revision": 2})))
        return ok_interpreter(req)

    enrichment.set_interpreter(slow_then_superseded)
    api.post("/api/v1/search/req_abc/enrichment", json=BODY)
    ev = events(api.get("/api/v1/search/req_abc/events?revision=1"))
    assert ev[-1].event_type == "error" and ev[-1].payload["code"] == "STALE_REVISION"


def test_older_revision_cannot_replace_newer(api):
    api.post("/api/v1/search/req_abc/enrichment", json=BODY | {"revision": 3})
    assert api.post("/api/v1/search/req_abc/enrichment", json=BODY).status_code == 409
    assert api.get("/api/v1/search/req_abc/events?revision=1").status_code == 409


def test_timeout_and_unavailable_are_error_events(api, monkeypatch):
    monkeypatch.setattr(enrichment, "INTERPRET_TIMEOUT_S", 0.05)
    enrichment.set_interpreter(lambda req: time.sleep(0.5))
    api.post("/api/v1/search/req_t/enrichment", json=BODY)
    ev = events(api.get("/api/v1/search/req_t/events?revision=1"))
    err = next(e for e in ev if e.event_type == "error")
    assert err.payload["code"] == "ENRICHMENT_TIMEOUT" and err.payload["retryable"] is True
    assert err.payload["stage"] == "interpretation" and ev[-1].event_type == "complete"

    def down(req):
        raise InferenceError("UNAVAILABLE", "x", True)

    enrichment.set_interpreter(down)
    api.post("/api/v1/search/req_u/enrichment", json=BODY)
    ev = events(api.get("/api/v1/search/req_u/events?revision=1"))
    assert next(e for e in ev if e.event_type == "error").payload["code"] == "ENRICHMENT_UNAVAILABLE"


def test_unexpected_failure_does_not_leak_details(api):
    def boom(req):
        raise RuntimeError(f"secret detail {req.company_context}")

    enrichment.set_interpreter(boom)
    api.post("/api/v1/search/req_b/enrichment", json=BODY)
    s = api.get("/api/v1/search/req_b/events?revision=1")
    assert "Zebra" not in s.text
    assert next(e for e in events(s) if e.event_type == "error").payload["code"] == "ENRICHMENT_FAILED"


def test_request_validation(api):
    assert api.get("/api/v1/search/req_none/events?revision=1").status_code == 404
    assert api.post("/api/v1/search/not-a-request/enrichment", json=BODY).status_code == 400
    assert api.post("/api/v1/search/req_big/enrichment", json=BODY | {"query": "x" * 2001}).status_code == 413


def test_packed_expansions_are_split_and_cut_fragment_dropped():
    packed = MODEL_OUT | {"expansions": [
        {"source": "glucose sensor", "text": "continuous glucose monitoring, glucose biosensor; CGM", "language": "en"},
        {"source": "glucose sensor", "text": "Glukosesensor, kontinuierliche Glukosemessung, tragbarer Glukosemoni",
         "language": "de"}]}
    packed["expansions"][1]["text"] = packed["expansions"][1]["text"].ljust(78, "x")
    r = interpret("glucose sensor partners", COMPANY, client=fake_client(packed))
    assert [e["text"] for e in r.expanded_queries] == ["continuous glucose monitoring", "glucose biosensor", "CGM",
                                                     "Glukosesensor", "kontinuierliche Glukosemessung"]


def test_unstated_constraints_are_dropped_but_stated_ones_kept():
    out = MODEL_OUT | {"needs": [{"text": "located in Bern", "kind": "constraint"},
                                 {"text": "endurance athletes as users", "kind": "constraint"}]}
    r = interpret("glucose sensor partners", COMPANY, client=fake_client(out))
    assert [n.text for n in r.needs] == ["endurance athletes as users"] and r.dropped["constraint_not_stated"] == 1


def test_default_interpreter_caches_per_normalised_request(monkeypatch):
    calls = []

    def fake_interpret(query, ctx, needs):
        calls.append(query)
        return Interpretation(needs=[], expanded_queries=[], clarification=None, partner_type=None)

    monkeypatch.setattr(enrichment, "interpret", fake_interpret)
    enrichment._interp_cache.clear()
    req = enrichment.SearchRequest(**BODY)
    enrichment._default_interpreter(req)
    enrichment._default_interpreter(enrichment.SearchRequest(**(BODY | {"query": "  Glucose SENSOR partners ", "revision": 2})))
    assert len(calls) == 1
    enrichment._default_interpreter(enrichment.SearchRequest(**(BODY | {"query": "something else"})))
    assert len(calls) == 2


# --- B2 (#127): timeout fallback to the fast model -------------------------------------
def _quick(req):
    return interpret(req.query, req.company_context, req.needs, client=fake_client())


def test_slow_primary_falls_back_to_fast_model(api, monkeypatch):
    monkeypatch.setattr(enrichment, "INTERPRET_DEADLINE_S", 0.05)
    enrichment.set_interpreter(lambda req: (time.sleep(0.5), _quick(req))[1], fallback=_quick)
    api.post("/api/v1/search/req_f/enrichment", json=BODY)
    ev = events(api.get("/api/v1/search/req_f/events?revision=1"))
    types = [e.event_type for e in ev]
    assert {"stage": "interpretation", "state": "fallback", "reason": "ENRICHMENT_TIMEOUT"} in [e.payload for e in ev]
    interp = next(e for e in ev if e.event_type == "interpretation")
    assert interp.payload["model"] == "fallback" and "error" not in types and types[-1] == "complete"


def test_failing_primary_falls_back_and_failing_fallback_reports_error(api):
    def down(req):
        raise InferenceError("UNAVAILABLE", "x", True)

    enrichment.set_interpreter(down, fallback=_quick)
    api.post("/api/v1/search/req_g/enrichment", json=BODY)
    ev = events(api.get("/api/v1/search/req_g/events?revision=1"))
    assert next(e for e in ev if e.event_type == "interpretation").payload["model"] == "fallback"

    enrichment.set_interpreter(down, fallback=down)
    api.post("/api/v1/search/req_h/enrichment", json=BODY)
    ev = events(api.get("/api/v1/search/req_h/events?revision=1"))
    assert next(e for e in ev if e.event_type == "error").payload["code"] == "ENRICHMENT_UNAVAILABLE"
    assert ev[-1].event_type == "complete"


def test_primary_in_time_reports_primary_model(api):
    enrichment.set_interpreter(_quick, fallback=_quick)
    api.post("/api/v1/search/req_p/enrichment", json=BODY)
    ev = events(api.get("/api/v1/search/req_p/events?revision=1"))
    assert next(e for e in ev if e.event_type == "interpretation").payload["model"] == "primary"


# --- T39 (#100): scope check -> honest refusal ----------------------------------------
def _scoped(scope):
    def f(req):
        r = _quick(req)
        r.scope, r.scope_reason = scope, ("research" if scope == "in_scope" else "consumer_request")
        return r
    return f


@pytest.mark.parametrize("first,scope,model_ok,expect", [
    ("low_confidence", "out_of_scope", True, "out_of_scope"),
    ("no_evidence", "out_of_scope", True, "out_of_scope"),
    ("confident", "out_of_scope", True, None),      # confident is never downgraded
    ("low_confidence", "unclear", True, None),      # unclear never refuses
    ("low_confidence", "in_scope", True, None),
])
def test_scope_outcome_update(api, monkeypatch, first, scope, model_ok, expect):
    monkeypatch.setattr(enrichment, "SCOPE_REFUSAL", True)
    enrichment.set_interpreter(_scoped(scope), fallback=_quick)
    enrichment.set_outcome_provider(lambda req: first)
    try:
        api.post("/api/v1/search/req_s/enrichment", json=BODY)
        ev = events(api.get("/api/v1/search/req_s/events?revision=1"))
    finally:
        enrichment.set_outcome_provider(None)
    interp = next(e for e in ev if e.event_type == "interpretation").payload
    assert interp["scope"] == scope and interp["outcome_update"] == expect
    skipped = {"stage": "assessment", "state": "skipped", "reason": "out_of_scope"} in [e.payload for e in ev]
    assert skipped == (expect == "out_of_scope") and ev[-1].event_type == "complete"


def test_fallback_model_never_refuses(api, monkeypatch):
    monkeypatch.setattr(enrichment, "SCOPE_REFUSAL", True)
    monkeypatch.setattr(enrichment, "INTERPRET_DEADLINE_S", 0.05)
    enrichment.set_interpreter(lambda req: (time.sleep(0.5), _quick(req))[1], fallback=_scoped("out_of_scope"))
    enrichment.set_outcome_provider(lambda req: "no_evidence")
    try:
        api.post("/api/v1/search/req_t/enrichment", json=BODY)
        ev = events(api.get("/api/v1/search/req_t/events?revision=1"))
    finally:
        enrichment.set_outcome_provider(None)
    interp = next(e for e in ev if e.event_type == "interpretation").payload
    assert interp["model"] == "fallback" and interp["outcome_update"] is None


def test_scope_refusal_is_off_by_default(api):
    assert enrichment.SCOPE_REFUSAL is False
    enrichment.set_interpreter(_scoped("out_of_scope"), fallback=_quick)
    enrichment.set_outcome_provider(lambda req: "no_evidence")
    try:
        api.post("/api/v1/search/req_d/enrichment", json=BODY)
        ev = events(api.get("/api/v1/search/req_d/events?revision=1"))
    finally:
        enrichment.set_outcome_provider(None)
    interp = next(e for e in ev if e.event_type == "interpretation").payload
    assert interp["scope"] == "out_of_scope" and interp["outcome_update"] is None
