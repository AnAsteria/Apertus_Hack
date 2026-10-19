"""EXTRA A6: same-name person entities merge through aliases; uncertain cases stay apart."""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location('mpd', Path(__file__).parents[2] / 'tools' / 'merge_person_duplicates.py')
mpd = importlib.util.module_from_spec(spec); spec.loader.exec_module(mpd)


def ent(eid, name, kind='person', status='unknown', profiles=(), claims=(), aliases=()):
    return {'entity_id': eid, 'entity_type': kind, 'name': name, 'status': status, 'canonical_profiles': list(profiles),
            'claim_ids': list(claims), 'contact_claim_ids': [], 'affiliation_entity_ids': [], 'alias_entity_ids': list(aliases)}


def test_titles_and_word_order_do_not_split_a_person():
    assert mpd.name_key('Prof. Dr. Ben Jann') == mpd.name_key('Jann, Ben')
    assert mpd.name_key('Prof. Dr. Smith') is None  # one name word is not enough to merge on


def test_profile_page_entity_becomes_canonical_and_collects_claims():
    es = [ent('a', 'Ben Jann', claims=['c1']), ent('b', 'Prof. Dr. Ben Jann', profiles=['https://x/jann'], claims=['c2']),
          ent('c', 'Daniel Ahmed (PI)', kind='unit'), ent('d', 'Daniel Ahmed', claims=['c3'])]
    merges = mpd.merge(es)
    b = es[1]
    assert b['alias_entity_ids'] == ['a'] and set(b['claim_ids']) == {'c1', 'c2'}
    assert es[3]['alias_entity_ids'] == ['c']  # the "(PI)" unit page folds into the person
    assert len(merges) == 2


def test_conflicting_status_retired_or_already_aliased_stay_apart():
    es = [ent('a', 'Anna Muster', status='current'), ent('b', 'Anna Muster', status='former'),
          ent('c', 'Eva Beispiel', status='retired'), ent('d', 'Eva Beispiel'),
          ent('e', 'Max Probe'), ent('f', 'Max Probe'), ent('g', 'Other', aliases=['f'])]
    assert mpd.merge(es) == []
