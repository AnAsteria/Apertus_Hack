"""T37 deterministic grounding checks on synthetic data (no model, no network)."""
from evaluation.grounding import check_cards, check_index

STORED = {'v1:s1': {'sentence_id': 'v1:s1', 'version_id': 'v1', 'text': 'The lab builds sensors.', 'url': 'https://x.invalid/a'}}


def resolve(sids):
    try:
        return [STORED[s] for s in dict.fromkeys(sids)]
    except KeyError:
        raise KeyError('evidence_unavailable')


def ent(status='current', fields=None, sids=('v1:s1',)):
    return {'entity': {'status': status}, 'fields': fields or {}, 'claim_sentence_ids': list(sids)}


def test_clean_index_has_no_problems():
    out = check_index({'e1': ent(fields={'expertise': [{'claim_id': 'c', 'value': 'sensors'}]})}, resolve)
    assert out['problems'] == [] and out['counts']['field_values'] == 1


def test_index_problems_are_reported():
    out = check_index({
        'nofx': ent(fields={'expertise': [{'claim_id': 'c', 'value': 'x'}]}, sids=()),
        'former': ent(status='former', fields={'official_contact': [{'claim_id': 'c', 'value': 'mail'}]}),
        'gone': ent(sids=('v9:s9',)),
    }, resolve)
    assert {p['problem'] for p in out['problems']} == {'fields_without_claim_evidence', 'former_entity_shows_contact',
                                                        'claim_sentence_unresolvable:KeyError'}


def card(**ev):
    base = {'sentence_id': 'v1:s1', 'version_id': 'v1', 'text': 'The lab builds sensors.', 'url': 'https://x.invalid/a'}
    return {'entity_id': 'e1', 'evidence': [base | ev], 'fields': {}, 'retrieval': {}}


def test_served_quotes_must_be_byte_identical_and_version_bound():
    rows = [{'query_id': 'q', 'results': [card(), card(text='The lab builds sensors!'), card(version_id='v2'),
                                          card(sentence_id='v1:s7'), card(url='https://other.invalid/')]}]
    out = check_cards(rows, resolve)
    assert [p['problem'] for p in out['problems']] == ['quote_not_identical', 'cross_version_reference',
                                                       'quote_unresolvable', 'url_mismatch']
    assert out['counts'] == {'cards': 5, 'quotes': 5}
