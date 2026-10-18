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
        if len(word) < 3 or word in STOP or word in out:
            continue
        if any(stemmer(lang).stemWord(word) in stored for lang in LANGUAGES):
            out.append(word)
    return out


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
