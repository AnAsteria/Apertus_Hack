"""T36: deterministic 'why this result' data."""
from app.search.explain import channel_ranks, matched_words, reason


def test_channel_ranks_order_by_score_then_id():
    assert channel_ranks({'b': (2., 0), 'a': (2., 1), 'c': (5., 2)}) == {'c': 1, 'a': 2, 'b': 3}


def test_matched_words_use_stems_across_languages_and_skip_stopwords():
    text = 'The group develops insulin dosing algorithms for diabetes therapy.'
    assert matched_words('insulin therapies for the diabetic', [text], 'en') == ['insulin', 'therapies', 'diabetic']
    assert matched_words('Insulintherapie', ['Die Gruppe forscht zur Insulintherapie.'], 'de') == ['insulintherapie']
    assert matched_words('quantum', [text], 'en') == []


def test_reason_names_channels_language_path_and_demotion():
    text = reason(keyword_rank=3, dense_rank=1, matched=['insulin'], query_language='de',
                  evidence_language='en', demoted=True, former=False)
    assert '"insulin"' in text and 'keyword rank 3' in text and 'similarity rank 1' in text
    assert 'German request, English evidence' in text and 'listing' in text
    only_dense = reason(keyword_rank=None, dense_rank=2, matched=[], query_language='ru',
                        evidence_language='en', demoted=False, former=True)
    assert only_dense.startswith('Documented as former.') and 'keyword' not in only_dense


def test_function_words_are_never_reported_as_matched_evidence():
    text = 'Forschung bei Krebs zur Therapieresistenz, show all results.'
    assert matched_words('Forschungspartner für Therapieresistenz bei Krebs', [text], 'de') == ['therapieresistenz', 'krebs']
    assert matched_words('show me all monkeys', [text], 'en') == []
