"""T20 ablation runner with FAKE backends, interpreter and assessor. Synthetic data only."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.ai.assess import BatchStats
from app.ai.client import Usage
from app.ai.interpret import Interpretation
from app.contracts import AssessmentPayload, Need, Result, SearchResponse
from evaluation.ablation import _InterpretationCache, assessment_quality, rrf_fuse, run_config
from evaluation.report import compute

GOLD = {"gold_version": "t", "queries": [
    {"query_id": "Q1-en", "intent_group_id": "Q1", "split": "development", "text": "glucose sensors",
     "language": "en", "requested_type": None, "category": "lay",
     "expected": [{"name": "Sensor Lab", "type": "unit", "urls": ["https://example.org/sensor"]}], "provenance": []},
    {"query_id": "Q2-en", "intent_group_id": "Q2", "split": "development", "text": "quantum satellites",
     "language": "en", "requested_type": None, "category": "absent", "expected": [], "provenance": []}]}


def card(eid, url):
    return Result(entity_id=eid, entity_type="unit", rank=1, display_name=eid, fields={}, reason="",
                  freshness="unknown", retrieval={},
                  evidence=[{"version_id": "ver_" + "a" * 32, "sentence_id": "ver_" + "a" * 32 + ":s1",
                             "text": "x", "url": url}])


class Backend:
    """Finds the sensor lab only via the expansion term 'CGM'."""
    def __init__(self):
        self.queries = []

    def search(self, req):
        self.queries.append(req.query)
        hits = {"glucose sensors": [card("ent_other", "https://example.org/other")],
                "CGM": [card("ent_sensor", "https://example.org/sensor")]}.get(req.query, [])
        return SearchResponse(schema_version="1", request_id="req_x", revision=1, results=hits, limitations=[],
                              enrichment_state="not_requested")


def interp(text):
    return Interpretation(needs=[Need(schema_version="1", need_id="need_u", text=text, origin="user",
                                      kind="competency")],
                          expanded_queries=[{"language": "en", "text": "CGM", "source": text}]
                          if text == "glucose sensors" else [],
                          clarification=None, partner_type=None, usage=Usage(100, 20))


def assessor(q, needs, results):
    payloads = [AssessmentPayload(entity_id=r.entity_id,
                                  category="direct_match" if r.entity_id == "ent_sensor" else "insufficient_evidence",
                                  need_coverage=[], explanation="x", evidence=[], unresolved_questions=[])
                for r in results]
    return payloads, BatchStats(candidates=len(results), usage=Usage(300, 80))


def test_rrf_fuse_keeps_first_card_and_renumbers():
    a, b = card("ent_a", "u"), card("ent_b", "u")
    fused = rrf_fuse([[a, b], [b]])
    assert [r.entity_id for r in fused] == ["ent_b", "ent_a"] and [r.rank for r in fused] == [1, 2]


def test_expansion_changes_recall_and_assessment_is_scored_separately(tmp_path):
    backends = {"hybrid": Backend()}
    gold = dict(GOLD)
    from evaluation import gold as goldmod
    base = run_config("hybrid", gold, "development", backends)
    assert compute(base, gold)["recall_at_k"]["mean"] == 0.0
    cache = _InterpretationCache(str(tmp_path / "interp.json"))
    exp = run_config("hybrid_expansion", gold, "development", backends, interpret_fn=interp, cache=cache,
                     interpret_model="m")
    assert compute(exp, gold)["recall_at_k"]["mean"] == 1.0
    assert exp["rows"][0]["expansions"] == ["CGM"] and exp["rows"][0]["tokens"] == 120
    full = run_config("hybrid_expansion_assessment", gold, "development", backends, interpret_fn=None,
                      assess_fn=assessor, cache=cache, interpret_model="m")  # interpretation served from cache
    assert full["rows"][0]["tokens"] == 380
    q = assessment_quality(full, gold)
    assert q["expected_marked_direct_or_related"] == {"rate": 1.0, "n": 1}
    assert q["non_expected_marked_direct"]["rate"] == 0.0
    assert compute(full, gold)["correct_abstention"]["rate"] == 1.0


def test_failures_are_recorded_without_text():
    class Broken:
        def search(self, req):
            raise RuntimeError("secret query text")
    run = run_config("hybrid", GOLD, "development", {"hybrid": Broken()})
    assert {r["status"] for r in run["rows"]} == {500} and run["rows"][0]["error"] == "RuntimeError"
    assert "secret" not in str(run)


def test_expansion_that_breaks_abstention_is_visible_in_metrics():
    def greedy(text):  # expands even the absent query into a matching term
        return Interpretation(needs=[], expanded_queries=[{"language": "en", "text": "CGM", "source": text}],
                              clarification=None, partner_type=None, usage=Usage(1, 1))
    run = run_config("hybrid_expansion", GOLD, "development", {"hybrid": Backend()}, interpret_fn=greedy,
                     cache=None, interpret_model="m")
    assert compute(run, GOLD)["correct_abstention"]["rate"] == 0.0
