"""Deterministic "why this result" data (T36): channels, ranks, matched words, language path.

Built only from retrieval signals and stored text, never from a model. No probabilities.
"""
from .analysis import LANGUAGES, STOP, analyze, stemmer, words


def channel_ranks(channel):
    """Entity -> 1-based rank inside one retrieval channel (score desc, entity id asc)."""
    return {eid: i for i, eid in enumerate(sorted(channel, key=lambda e: (-channel[e][0], e)), 1)}


def matched_words(query, texts, language):
    """Query words whose stem occurs in the evidence texts (any analyzer), surface form kept."""
    stored = set()
    for text in texts:
        stored.update(analyze(text, language if language in LANGUAGES else 'en'))
    out = []
    for word in words(query):
        if len(word) < 3 or word in STOP or word in FUNCTION_WORDS or word in out:
            continue
        if any(stemmer(lang).stemWord(word) in stored for lang in LANGUAGES):
            out.append(word)
    return out


# Function words that the short STOP list misses; they must not appear as "matched" evidence.
FUNCTION_WORDS = set("""bei zur zum vom beim am im ins ans aufs über unter auf aus nach ohne gegen durch bis seit
wie als oder auch nicht sich sie er es wir ihr man sind ist war hat haben werden wird kann
was why how who what when where which with without into onto about over under between than
not but also can are was were has have had will would should could all show find
pour par sur dans avec sans aux est sont qui que quoi une des les
per con senza sono che chi una gli dei delle alla nel""".split())

LANGUAGE_NAMES = {'en': 'English', 'de': 'German', 'fr': 'French', 'it': 'Italian', 'ru': 'Russian'}


def reason(*, keyword_rank, dense_rank, matched, query_language, evidence_language, demoted, former):
    parts = []
    if keyword_rank and matched:
        parts.append('keyword match on ' + ', '.join('"%s"' % w for w in matched[:5]) + ' (keyword rank %d)' % keyword_rank)
    elif keyword_rank:
        parts.append('keyword match (keyword rank %d)' % keyword_rank)
    if dense_rank:
        parts.append('multilingual meaning similarity (similarity rank %d)' % dense_rank)
    text = 'Found by ' + ' and '.join(parts) + ' in stored source text.' if parts else 'Matched stored source text.'
    if query_language and evidence_language and query_language != evidence_language:
        text += ' %s request, %s evidence.' % (LANGUAGE_NAMES.get(query_language, query_language),
                                                LANGUAGE_NAMES.get(evidence_language, evidence_language))
    if demoted:
        text += ' Ranked lower because the page looks like a listing, news or report page.'
    if former:
        text = 'Documented as former. ' + text
    return text


import re as _re

_EMAIL = _re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+')
_PHONE = _re.compile(r'\+?\d[\d \-/().]{7,}\d')


def contact_bearing(text: str) -> bool:
    """EXTRA F5: a sentence that carries an e-mail address or a phone number."""
    return bool(_EMAIL.search(text) or _PHONE.search(text) and _re.search(r'(tel|phone|fax|telefon|\+41)', text, _re.I))
