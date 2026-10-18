"""EXTRA C3: documented former / emeritus persons from page text."""
from app.contracts import Entity, Sentence
from app.search.build import former_cue_sentence


def person(name, etype='person', status='unknown'):
    return Entity(schema_version='1', entity_id='ent_x', entity_type=etype, name=name, canonical_profiles=['https://x.invalid/p'],
                  status=status, resolution_state='uncertain')


def sents(*texts):
    return [Sentence(schema_version='1', sentence_id=f'ver_x:s{i}', version_id='ver_x', passage_id='ver_x:p1', text=t)
            for i, t in enumerate(texts, 1)]


def test_split_emeritus_header_marks_the_person_former():
    assert former_cue_sentence(person('Christian Joppke'), sents('Prof. em.', 'Dr.', 'Christian Joppke', 'Emeritus')) == 'ver_x:s1'


def test_former_members_list_marks_only_named_people():
    s = sents('Former members: Dr Pascal Corso - Dr Barna Becsek')
    assert former_cue_sentence(person('Dr Barna Becsek'), s) == 'ver_x:s1'
    assert former_cue_sentence(person('Dr Anna Novak'), s) is None


def test_unrelated_former_wording_units_and_known_status_are_untouched():
    assert former_cue_sentence(person('Severin Fankhauser'), sents('Severin Fankhauser', 'Wir helfen ehemaligen Patientinnen.')) is None
    assert former_cue_sentence(person('Emeritus Lab', etype='unit'), sents('Emeritus Lab')) is None
    assert former_cue_sentence(person('Prof. em. Dr. X Y', status='current'), sents('Prof. em.')) is None
