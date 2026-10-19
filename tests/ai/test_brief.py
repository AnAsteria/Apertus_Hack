"""T23/T24/T28: brief, email draft and translation are validated before display (fake model)."""
from app.ai.brief import make_brief, make_email, translate, _Brief, _Email, _Translations
from app.ai.client import JsonResult, Usage
from app.contracts import Result


def card(eid, name, texts):
    return Result(entity_id=eid, entity_type='unit', rank=1, display_name=name, reason='r',
                  fields={'expertise': [{'claim_id': 'c1', 'value': 'insulin dosing'}]},
                  evidence=[{'version_id': 'v' + eid, 'sentence_id': f'v{eid}:s{i}', 'text': t, 'url': 'https://x.invalid/' + eid}
                            for i, t in enumerate(texts, 1)], freshness='unknown', retrieval={})


class Fake:
    def __init__(self, value):
        self.value, self.messages = value, None

    def complete_json(self, messages, schema, **kw):
        self.messages = messages
        return JsonResult(schema.model_validate(self.value), 'backend_constrained', 'apertus-test', Usage(10, 5), 0.1, 1)


CARDS = [card('a', 'Diabetes Tech Lab', ['The lab develops insulin dosing algorithms.', 'It runs 3 clinical pilots.']),
         card('b', 'Imaging Group', ['The group builds MRI methods.'])]


def test_brief_maps_evidence_numbers_to_stored_quotes_and_withholds_invented_details():
    fake = Fake({'summary': 'Two groups may fit.', 'entries': [
        {'candidate': 1, 'why': 'It develops insulin dosing algorithms in 3 pilots.', 'evidence': [1, 2, 3], 'open_questions': ['Is the team available?']},
        {'candidate': 2, 'why': 'They raised 5 million CHF; contact prof@x.ch', 'evidence': [3], 'open_questions': []},
        {'candidate': 7, 'why': 'Ghost candidate', 'evidence': [], 'open_questions': []}]})
    b = make_brief('insulin dosing partner', CARDS, 'de', analyst_note='call next week', client=fake)
    assert 'German' in fake.messages[0]['content']
    a, g = b['entries']
    assert a['why_ai'].startswith('It develops') and [e['text'] for e in a['evidence']] == [CARDS[0].evidence[0].text, CARDS[0].evidence[1].text]
    assert g['why_ai'].startswith("Apertus' wording was withheld")          # invented number and e-mail
    assert g['evidence'][0]['text'] == 'The group builds MRI methods.'      # E3 is its own sentence
    assert len(b['entries']) == 2 and b['analyst_note'] == 'call next week' and b['language'] == 'de'


def test_skipped_candidates_still_appear_without_ai_text():
    b = make_brief('q', CARDS, client=Fake({'summary': 'ok', 'entries': [{'candidate': 2, 'why': 'MRI methods.', 'evidence': [3], 'open_questions': []}]}))
    assert [e['name'] for e in b['entries']] == ['Imaging Group', 'Diabetes Tech Lab']
    assert b['entries'][1]['why_ai'] is None


def test_email_draft_has_no_recipient_and_rejects_invented_contacts():
    brief = make_brief('q', CARDS, client=Fake({'summary': 'Two groups.', 'entries': []}))
    ok = make_email(brief, 'fr', client=Fake({'subject': 'Collaboration', 'body': 'Dear [Name], we would like to talk.'}))
    assert ok['to'] is None and ok['body'].startswith('Dear [Name]') and 'Not sent' in ok['label']
    bad = make_email(brief, client=Fake({'subject': 'x', 'body': 'Call me at +41 31 555 12 12 or mail a@b.ch'}))
    assert bad['body'].startswith('Draft withheld')


def test_translation_keeps_numbers_or_is_withheld():
    fake = Fake({'texts': ['Il gruppo gestisce 3 progetti pilota.', 'Il laboratorio sviluppa algoritmi.']})
    out = translate(['The group runs 3 pilot projects.', 'The lab builds 2 algorithms.'], 'it', client=fake)
    assert out == ['Il gruppo gestisce 3 progetti pilota.', None]   # second lost the number "2"
