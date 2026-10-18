"""Language-specific lexical analysis; character terms help German compounds.

Terms are data, never interpolated SQL/FTS syntax. No translation or language API.
"""
import re
import unicodedata
import threading
import snowballstemmer
from langdetect import DetectorFactory, detect_langs
from langdetect.lang_detect_exception import LangDetectException

DetectorFactory.seed = 0
LANGUAGES = {'en': 'english', 'de': 'german', 'fr': 'french', 'it': 'italian', 'ru': 'russian'}
_local = threading.local()

def stemmer(lang):
    if not hasattr(_local,'stemmers'):
        _local.stemmers = {code:snowballstemmer.stemmer(name) for code,name in LANGUAGES.items()}
    return _local.stemmers[lang]
STOP = set('the and for with from that this what which find research partners a an of to in on or is are der die das ein eine und für mit von zu im des dem den nach le la les de des du et pour un une il lo gli del della con per di e'.split())


def words(text):
    return re.findall(r'[^\W\d_]+', unicodedata.normalize('NFKC', text).casefold(), re.UNICODE)


def analyze(text, language):
    lang = language if language in LANGUAGES else 'en'
    result = []
    for word in words(text):
        if word in STOP or len(word) < 2:
            continue
        result.append(stemmer(lang).stemWord(word))
        # Prefix keeps grams distinct from natural stems; 4-char overlaps match
        # components of long German nouns without pretending to translate them.
        if lang == 'de' and len(word) >= 7:
            result.extend('zzgram' + word[i:i+4] for i in range(len(word)-3))
    return tuple(result)


def language_of(text):
    if re.search('[\u0400-\u04ff]', text):
        return 'ru'
    try:
        guesses = detect_langs(text)
        if guesses and guesses[0].lang in LANGUAGES and guesses[0].prob >= .8:
            return guesses[0].lang
    except LangDetectException:
        pass
    return None


def query_terms(text):
    # Detection is uncertain for short queries. Try all corpus analyzers rather
    # than discard an available keyword match. This does not translate words.
    terms = set(t for lang in ('en','de','fr','it','ru') for t in analyze(text, lang))
    # A short query component (Krebs) must also match grams of an indexed
    # longer compound (Krebserkrankungen), without bloating every short word
    # in the stored index with additional grams.
    for word in words(text):
        if 4 <= len(word) < 7 and word not in STOP:
            terms.update('zzgram'+word[i:i+4] for i in range(len(word)-3))
    return sorted(terms)[:512]


def match_expression(terms):
    return ' OR '.join('"' + term.replace('"','""') + '"' for term in terms)
