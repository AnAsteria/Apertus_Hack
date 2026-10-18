"""Deterministic answer policy (T31): confident, low confidence, too broad or no evidence.

Pure functions over retrieval signals; no LLM, no network. Thresholds are configuration,
chosen on development queries and ad hoc probes only (see app/search/README.md).
"""
import os
import re
from collections import Counter

from .analysis import STOP, words

# Words that carry no topic: quantifiers, request verbs and generic role nouns.
GENERIC = set('''all every any some show list give find search look need want who which where
whole entire everything everyone overview research researchers researcher scientists scientist
experts expert people persons person groups group units unit labs lab institutes institute
projects project partners partner university universities bern berne unibe topic topics field
fields area areas
alle jede jeder jedes zeige zeig liste finde suche gib brauche wer welche welcher wo gesamte
ganze forschung forscher forscherin forschende wissenschaftler wissenschaftlerin experten expertin
leute personen gruppen gruppe institut institute projekte projekt partner universität
tous toutes tout montre trouve cherche chercheurs chercheur scientifiques experts personnes groupes
tutti tutte mostra trova cerca ricercatori ricercatore scienziati esperti persone gruppi
'''.split())
TYPE_LABELS = {'person': 'People', 'unit': 'Groups and institutes', 'project': 'Projects',
               'infrastructure': 'Platforms and infrastructure', 'service': 'Services'}
COVERAGE = ('The indexed corpus covers public pages of the University of Bern (including ARTORG) and '
            'the Diabetes Center Berne, with a focus on diabetes, oncology, neurology and medtech.')


def thresholds():
    return {'confident_dense': float(os.environ.get('BERNMATCH_CONFIDENT_DENSE', '.885')),
            'broad_max_terms': int(os.environ.get('BERNMATCH_BROAD_MAX_TERMS', '1')),
            'broad_max_gap': float(os.environ.get('BERNMATCH_BROAD_MAX_GAP', '1.0')),
            'broad_min_hosts': int(os.environ.get('BERNMATCH_BROAD_MIN_HOSTS', '4'))}


def topic_terms(query):
    """Content words that name a topic (Cyrillic words count: Russian queries have no stop list)."""
    return [w for w in words(query) if len(w) > 2 and w not in STOP and w not in GENERIC]


def _host(url):
    host = url.split('//', 1)[-1].split('/', 1)[0].casefold()
    return host[4:] if host.startswith('www.') else host


def classify(query, results, *, dense_ok, best_dense, abstain_dense, limits=None):
    """Return (outcome, suggestions, limitation or None). `results` are Result models."""
    limits = limits or thresholds()
    if not results:
        return 'no_evidence', [{'kind': 'coverage', 'label': COVERAGE, 'value': None},
                               {'kind': 'rephrase', 'label': 'Describe the need with a specific method, disease, technology or product.', 'value': None}], None
    hosts = Counter(_host(e.url) for r in results for e in r.evidence[:1])
    types = Counter(r.entity_type for r in results)
    dense = [r.retrieval.get('dense') for r in results if r.retrieval.get('dense') is not None]
    gap = (max(dense) - min(dense)) if len(dense) >= 5 else None
    terms = topic_terms(query)
    if (len(terms) <= limits['broad_max_terms'] and len(hosts) >= limits['broad_min_hosts']
            and (gap is None or gap <= limits['broad_max_gap'])):
        suggestions = [{'kind': 'institution', 'label': 'Only ' + host, 'value': host} for host, _ in hosts.most_common(3)]
        suggestions += [{'kind': 'entity_type', 'label': TYPE_LABELS[t], 'value': t} for t, _ in types.most_common(2)]
        suggestions.append({'kind': 'rephrase', 'label': 'Add the problem, method or application you care about.', 'value': None})
        return 'too_broad', suggestions, ('The request is very broad; these are examples, not a ranked answer. '
                                          'Narrow it to get matches.')
    if not dense_ok:
        return 'low_confidence', [{'kind': 'rephrase', 'label': 'Try again later for multilingual matching, or use the words of the source pages.', 'value': None}], \
            'Only keyword matching was available, so relevance is less certain.'
    if best_dense < limits['confident_dense']:
        return 'low_confidence', [{'kind': 'rephrase', 'label': 'Add a specific method, disease, technology or product.', 'value': None},
                                  {'kind': 'rephrase', 'label': 'Try the request in English or German, the main languages of the sources.', 'value': None},
                                  {'kind': 'coverage', 'label': COVERAGE, 'value': None}], \
            'These are possible matches with low confidence: no stored passage is a close match.'
    return 'confident', [], None
