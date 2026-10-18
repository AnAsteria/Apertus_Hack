"""T31 answer policy: deterministic outcome classes and narrowing suggestions."""
from app.contracts import Result, SearchResponse
from app.search.outcome import classify, topic_terms

LIMITS = {'confident_dense': .88, 'broad_max_terms': 1, 'broad_max_gap': .02, 'broad_min_hosts': 4}


def card(i, host, dense, etype='unit'):
    return Result(entity_id=f'ent_{i}', entity_type=etype, rank=i, display_name=f'Entity {i}', reason='r',
                  evidence=[{'version_id': 'v', 'sentence_id': f'v:s{i}', 'text': 't', 'url': f'https://{host}/p{i}'}],
                  freshness='unknown', retrieval={'dense': dense})


def run(query, results, best, dense_ok=True):
    return classify(query, results, dense_ok=dense_ok, best_dense=best, abstain_dense=.865, limits=LIMITS)


def test_no_results_is_no_evidence_with_coverage_hint():
    outcome, suggestions, note = run('show me all monkeys', [], 0.)
    assert outcome == 'no_evidence' and note is None
    assert suggestions[0]['kind'] == 'coverage'


def test_generic_request_spread_across_institutions_is_too_broad():
    hosts = ['a.unibe.ch', 'b.unibe.ch', 'c.unibe.ch', 'd.unibe.ch', 'e.unibe.ch']
    results = [card(i, hosts[i % 5], .885 - i * .001) for i in range(1, 11)]
    outcome, suggestions, note = run('find all biologists', results, .885)
    assert outcome == 'too_broad' and 'examples' in note
    assert {s['kind'] for s in suggestions} == {'institution', 'entity_type', 'rephrase'}
    assert all(s['value'].endswith('unibe.ch') for s in suggestions if s['kind'] == 'institution')


def test_specific_request_is_not_broad_even_when_spread():
    hosts = ['a.unibe.ch', 'b.unibe.ch', 'c.unibe.ch', 'd.unibe.ch', 'e.unibe.ch']
    results = [card(i, hosts[i % 5], .9 - i * .001) for i in range(1, 11)]
    assert run('insulin dosing decision support', results, .9)[0] == 'confident'


def test_broad_word_with_clear_winner_is_not_broad():
    # A large score gap means one page clearly answers even a one-word request.
    hosts = ['a.unibe.ch', 'b.unibe.ch', 'c.unibe.ch', 'd.unibe.ch', 'e.unibe.ch']
    results = [card(1, hosts[0], .93)] + [card(i, hosts[i % 5], .86) for i in range(2, 11)]
    assert run('pharmacology', results, .93)[0] == 'confident'


def test_uncertain_band_is_low_confidence():
    results = [card(i, 'artorg.unibe.ch', .87) for i in range(1, 4)]
    outcome, suggestions, note = run('ultrasound microrobots', results, .87)
    assert outcome == 'low_confidence' and 'low confidence' in note
    assert all(s['kind'] == 'rephrase' for s in suggestions)


def test_keyword_only_mode_never_claims_confidence():
    results = [card(1, 'artorg.unibe.ch', None)]
    assert run('ultrasound microrobots', results, 0., dense_ok=False)[0] == 'low_confidence'


def test_topic_terms_ignore_generic_words_in_all_languages():
    assert topic_terms('Find all researchers') == []
    assert topic_terms('Zeige alle Forscher für Diabetes') == ['diabetes']
    assert topic_terms('Trova tutti i ricercatori') == []
    assert topic_terms('биологи') == ['биологи']


def test_response_fields_are_optional_for_existing_producers():
    r = SearchResponse(schema_version='1', request_id='r', revision=1, results=[], limitations=[], enrichment_state='not_requested')
    assert r.outcome is None and r.suggestions == []
