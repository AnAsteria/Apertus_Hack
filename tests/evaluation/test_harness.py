"""Harness tests. Expected numbers are worked out by hand in comments, not by the code under test.
Cards and URLs are SYNTHETIC (example.org); these tests check scoring only, never retrieval quality."""
import copy
import json
import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app import main
from app.api import search as search_api
from evaluation import gold as G
from evaluation import metrics as M
from evaluation import report, runner


def card(rank, url, etype="unit", fields=None):
    return {"rank": rank, "entity_type": etype, "display_name": f"E{rank}", "reason": "r",
            "evidence": [{"url": url, "text": "t"}], "fields": fields or {}}


def test_url_normalisation_ignores_scheme_www_fragment_trailing_slash():
    assert M.norm_url("https://www.Example.org/a/b/#x") == M.norm_url("http://example.org/a/b")
    assert M.norm_url("https://example.org/a") != M.norm_url("https://example.org/a2")


def test_recall_at_10_counts_only_top_ten():
    # expected A, B, C. A is rank 2, C is rank 11 (outside top 10), B never appears -> 1 of 3.
    results = [card(i, f"https://example.org/x{i}") for i in range(1, 13)]
    results[1] = card(2, "https://example.org/A")
    results[10] = card(11, "https://example.org/C")
    exp = [{"urls": [f"https://example.org/{n}"], "type": "unit"} for n in "ABC"]
    assert M.recall_at_k(results, exp, 10) == pytest.approx(1 / 3)
    assert M.recall_at_k(results, exp, 12) == pytest.approx(2 / 3)
    assert M.recall_at_k(results, [], 10) is None


def test_recall_requires_matching_type_unless_accepted():
    r = [card(1, "https://example.org/p", etype="person")]
    unit = {"urls": ["https://example.org/p"], "type": "unit"}
    assert M.recall_at_k(r, [unit]) == 0.0  # a person card never counts as the unit
    assert M.recall_at_k(r, [{**unit, "accept_types": ["person"]}]) == 1.0


def test_language_variant_urls_count_as_one_entity():
    r = [card(1, "https://example.org/de/projekt")]
    e = {"urls": ["https://example.org/en/project", "https://example.org/de/projekt"], "type": "unit"}
    assert M.recall_at_k(r, [e]) == 1.0


def test_names_separate_two_entities_that_share_a_page():
    page = "https://example.org/programmes"
    ctr = {"urls": [page], "type": "unit", "names": ["Cancer Therapy Resistance", "CTR"]}
    rns = {"urls": [page], "type": "unit", "names": ["Regenerative Neuroscience", "RNS"]}
    cards = [{**card(1, page), "display_name": "Regenerative Neuroscience - RNS"}]
    assert M.recall_at_k(cards, [rns]) == 1.0
    assert M.recall_at_k(cards, [ctr]) == 0.0  # same page, wrong programme
    assert M.avoided(cards, [ctr]) is True and M.avoided(cards, [rns]) is False


def test_percentiles_use_nearest_rank_and_median_averages_middle_pair():
    v = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    assert M.percentile(v, 95) == 100  # ceil(0.95*10)=10th value
    assert M.percentile(v, 50) == 50   # ceil(5)=5th value
    assert M.median(v) == 55           # (50+60)/2
    assert M.percentile(list(range(1, 21)), 95) == 19  # ceil(19)=19th value
    assert M.percentile([], 95) is None


def test_link_coverage_exposure_and_support_rate():
    cards = [card(1, "https://a.example/x"), card(2, "https://a.example/y"), card(3, "https://b.example/z")]
    cards.append({"rank": 4, "entity_type": "unit", "display_name": "E4", "reason": "r", "evidence": [], "fields": {}})
    assert M.link_coverage(cards) == 0.75  # 3 of 4 carry a URL
    ex = M.institutional_exposure(cards[:3])
    assert ex["shares"] == {"a.example": pytest.approx(2 / 3), "b.example": pytest.approx(1 / 3)}
    assert ex["max_share"] == pytest.approx(2 / 3)
    assert M.support_rate(["supported", "supported", "partly", "unsupported"]) == {
        "n": 4, "supported": 0.5, "partly": 0.25, "unsupported": 0.25}
    assert M.support_rate([])["n"] == 0


def test_field_completeness_is_share_of_cards_with_a_value():
    cs = [card(1, "https://e.org/1", fields={"expertise": [{"claim_id": "c", "value": "v"}]}),
          card(2, "https://e.org/2")]
    out = M.field_completeness(cs, ("expertise", "contact"))
    assert out == {"expertise": 0.5, "contact": 0.0}


def q(qid, group, split="development", cat="professional", expected=None, **kw):
    base = {"query_id": qid, "intent_group_id": group, "split": split, "text": "imaging partners",
            "language": "en", "requested_type": "unit", "category": cat,
            "expected": expected if expected is not None else [{"name": "x", "type": "unit", "urls": ["https://example.org/research/imaging"]}],
            "provenance": [{"url": "https://example.org/research/imaging", "note": "synthetic"}]}
    base.update(kw)
    return base


def test_validate_catches_leakage_missing_provenance_and_bad_absent():
    g = {"queries": [q("a", "g1", split="development"), q("b", "g1", split="evaluation")]}
    assert any("split across partitions" in p for p in G.validate(g))
    g = {"queries": [q("a", "g1", provenance=[])]}
    assert any("missing provenance" in p for p in G.validate(g))
    g = {"queries": [q("a", "g1", cat="absent")]}  # absent but lists expected
    assert any("absent query must not list" in p for p in G.validate(g))
    g = {"queries": [q("a", "g1", expected=[])]}
    assert any("needs at least one expected" in p for p in G.validate(g))
    assert G.validate({"queries": [q("a", "g1")]}) == []
    assert any("30-50" in p for p in G.validate({"queries": [q("a", "g1")]}, final=True))


def test_freeze_detects_any_change_to_queries(tmp_path):
    p = tmp_path / "gold.json"
    g = {"gold_version": "t", "queries": [q("a", "g1", split="evaluation")]}
    p.write_text(json.dumps(g))
    G.freeze(str(p))
    assert G.check_frozen(str(p))
    g2 = copy.deepcopy(g)
    g2["queries"][0]["text"] = "changed after freezing"
    p.write_text(json.dumps(g2))
    assert not G.check_frozen(str(p))


@pytest.fixture
def fixture_client(monkeypatch, tmp_path):
    monkeypatch.setenv("BERNMATCH_FIXTURE_MODE", "1")
    monkeypatch.setenv("BERNMATCH_DATA_DIR", str(tmp_path))
    search_api.set_backend(None)
    return TestClient(main.app)


def write_gold(tmp_path, queries):
    p = tmp_path / "gold.json"
    p.write_text(json.dumps({"gold_version": "test", "queries": queries}))
    return str(p)


def test_run_and_report_against_fixture_endpoint(fixture_client, tmp_path):
    queries = [
        q("hit", "g1"),  # the synthetic imaging group is rank 1 of unit cards -> recall 1.0
        q("miss", "g2", expected=[{"name": "n", "type": "unit", "urls": ["https://example.org/not-there"]}]),
        q("none", "g3", cat="absent", expected=[], requested_type="service"),  # fixture returns [] for service
        q("bad_abstain", "g4", cat="absent", expected=[]),  # fixture returns cards for unit -> not abstained
    ]
    path = write_gold(tmp_path, queries)
    run = runner.run_gold(path, split="development", client=fixture_client, config_name="fixture")
    rep = report.compute(run, G.load(path))
    assert rep["n_queries"] == 4 and rep["n_failed"] == 0
    assert rep["recall_at_k"]["n"] == 2 and rep["recall_at_k"]["mean"] == 0.5  # (1.0 + 0.0) / 2
    assert rep["correct_abstention"] == {"rate": 0.5, "n": 2}  # one correct, one not
    assert rep["latency_ms"]["n"] == 4 and rep["latency_ms"]["median"] is not None
    assert rep["tokens_per_query"] is None and rep["indexing_time_s"] is None


def test_evaluation_split_refuses_unfrozen_gold(fixture_client, tmp_path):
    path = write_gold(tmp_path, [q("e1", "g1", split="evaluation")])
    with pytest.raises(PermissionError):
        runner.run_gold(path, split="evaluation", client=fixture_client)
    G.freeze(path)
    assert runner.run_gold(path, split="evaluation", client=fixture_client)["rows"]


def test_report_rejects_run_from_a_different_gold(fixture_client, tmp_path):
    path = write_gold(tmp_path, [q("a", "g1")])
    run = runner.run_gold(path, split="development", client=fixture_client)
    other = {"queries": [q("a", "g1", text="other text")]}
    with pytest.raises(ValueError):
        report.compute(run, other)


def test_failed_queries_are_counted_and_not_silently_dropped(tmp_path):
    class Down:
        def post(self, *a, **k):
            import httpx
            raise httpx.ConnectError("down")
    path = write_gold(tmp_path, [q("a", "g1")])
    run = runner.run_gold(path, split="development", client=Down())
    assert run["rows"][0]["error"] == "ConnectError" and run["rows"][0]["results"] == []
    rep = report.compute(run, G.load(path))
    assert rep["n_failed"] == 1 and rep["recall_at_k"]["mean"] == 0.0


def test_sample_sheet_roundtrip(fixture_client, tmp_path):
    path = write_gold(tmp_path, [q("a", "g1")])
    run = runner.run_gold(path, split="development", client=fixture_client)
    sheet = tmp_path / "s.csv"
    n = report.write_sample_sheet(run, str(sheet), n=2)
    assert n == 2
    lines = sheet.read_text(encoding="utf-8").splitlines()
    rows = [l.split(",") for l in lines[1:]]
    filled = "\n".join([lines[0]] + [l.rstrip(",") + ",supported," if l.endswith(",,") else l for l in lines[1:]])
    sheet.write_text(filled, encoding="utf-8")
    assert report.support_from_sheet(str(sheet))["n"] == 2


def test_fields_match_the_card_field_names_emitted_by_t08():
    from app.grounding.fields import FIELD_FOR, INVERSE_FIELD
    from evaluation.report import FIELDS
    assert set(FIELDS) == set(FIELD_FOR.values()) - {"related"} | set(INVERSE_FIELD.values())
