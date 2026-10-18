"""T30: fusion over query variants and the enriched pass."""
from app.contracts import Result, SearchRequest, SearchResponse
from app.search.expansion import expanded_search, rrf_fuse


def card(eid):
    return Result(entity_id=eid, entity_type='unit', rank=1, display_name=eid, reason='r',
                  evidence=[{'version_id': 'v', 'sentence_id': 'v:s1', 'text': 't', 'url': 'https://x.invalid/' + eid}],
                  freshness='unknown', retrieval={'query_variant': 'original'})


class Backend:
    def __init__(self, table):
        self.table, self.seen = table, []

    def search(self, req):
        self.seen.append(req)
        if req.query == 'boom':
            raise RuntimeError('x')
        return SearchResponse(schema_version='1', request_id='r', revision=req.revision, results=[card(e) for e in self.table.get(req.query, [])],
                              limitations=[], enrichment_state='not_requested')


REQ = SearchRequest(schema_version='1', query='Therapieresistenz Krebs', revision=3, entity_type='unit')


def test_expansion_brings_in_cross_lingual_hit_and_records_variants():
    backend = Backend({'Therapieresistenz Krebs': ['news', 'clinic'], 'cancer therapy resistance': ['ctr', 'news']})
    fused, used = expanded_search(backend, REQ, ['cancer therapy resistance'])
    ids = [r.entity_id for r in fused]
    assert ids[0] == 'news' and 'ctr' in ids and used == ['cancer therapy resistance']
    ctr = fused[ids.index('ctr')]
    assert ctr.retrieval['query_variant'] == 'expansion' and ctr.retrieval['query_variants'] == ['expansion: cancer therapy resistance']
    assert fused[0].retrieval['query_variants'] == ['original', 'expansion: cancer therapy resistance']


def test_constraints_are_kept_duplicates_dropped_variants_bounded_and_failures_ignored(monkeypatch):
    backend = Backend({'Therapieresistenz Krebs': ['a']})
    fused, used = expanded_search(backend, REQ, ['therapieresistenz krebs', 'boom', 'x1', 'x2', 'x3', 'x4'])
    assert 'therapieresistenz krebs' not in used and len(used) == 4
    assert all(r.entity_type == 'unit' and r.revision == 3 for r in backend.seen)
    assert [r.entity_id for r in fused] == ['a']


def test_rrf_fuse_without_labels_matches_the_ablation_rule():
    fused = rrf_fuse([[card('a'), card('b')], [card('b'), card('c')]])
    assert [r.entity_id for r in fused] == ['b', 'a', 'c'] and [r.rank for r in fused] == [1, 2, 3]
    assert 'query_variants' not in fused[0].retrieval
