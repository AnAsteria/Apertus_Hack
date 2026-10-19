"""Max per entity BEFORE rank fusion: duplicate passages cannot add votes."""
import re
import numpy as np

# Listing/news/report pages that the cheap T06 classifier can label as units.
# They are kept searchable but ranked below real entity pages (never removed).
NON_ENTITY_WORDS = {'news','aktuell','archiv','archive','event','events','veranstaltungen','publications',
                    'publikationen','seminar','seminars','symposium','symposien','jobs','stellen','vorlage',
                    'template','lernzielkatalog','erfolgsmeldungen','medienmitteilungen','jb','newsletter',
                    # jury, 19 Oct: legal/career/empty-title pages seen in live top 10s (runs/jury/search/)
                    'legal','notice','impressum','disclaimer','datenschutz','privacy','career','careers','karriere',
                    'untitled'}
NON_ENTITY_PREFIXES = ('jahresbericht','medienmitteilung','unibernjahresbericht','annualreport')
DEMOTION = .5
TITLES = {'prof','dr','md','phd','med','pd','dipl','ing','msc','bsc','mba','mag'}


def duplicate_key(name, entity_type):
    """Same words in any order, titles ignored: "Glisic Marija, Prof., MD, PhD" == "Marija Glisic".
    Type only separates people from the rest: "ARTORG 3D-Printing Core Facility" came back as
    infrastructure AND as unit (its category page), the same thing twice for the reader."""
    words = re.findall(r'[^\W_]+', name.casefold())  # digits count: "Top 3" is not "Top 20"
    return (entity_type == 'person', ' '.join(sorted(w for w in words if w not in TITLES)))


def non_entity_page(name, urls):
    """True for listing/news/report-like pages, judged from title and URL words only."""
    if any(u.split('?')[0].casefold().endswith('.pdf') for u in urls):
        return True
    words = set(re.split(r'[^0-9a-zà-ÿ]+', ' '.join([name]+[u.split('//',1)[-1] for u in urls]).casefold()))
    return (bool(words & NON_ENTITY_WORDS) or {'summer','school'} <= words
            or any(w.startswith(NON_ENTITY_PREFIXES) for w in words))


def entity_max(scores, entries, allowed):
    best = {}
    for index,score in scores:
        for eid in entries[index]['entity_ids']:
            if eid not in allowed:
                continue
            old = best.get(eid)
            if old is None or score > old[0] or (score == old[0] and index < old[1]):
                best[eid] = (float(score),int(index))
    return best


def reciprocal_rank_fusion(channels, constant=60, depth=100, weights=None):
    """Weighted RRF: each channel adds weight/(constant+rank). Equal weights = plain RRF."""
    scores = {}
    weights = weights or [1.]*len(channels)
    for channel,weight in zip(channels,weights):
        ranked = sorted(channel,key=lambda eid:(-channel[eid][0],eid))[:depth]
        for rank,eid in enumerate(ranked,1):
            scores[eid] = scores.get(eid,0.) + weight/(constant+rank)
    return scores


def diversify(scores, representatives, limit=10, relevance_weight=.85):
    """MMR over relevance-normalized scores. No institutional quotas."""
    if not scores:
        return []
    scale = max(scores.values())
    # No cut-off on the fused score: under RRF an entity ranked first by both
    # channels scores 2/61, while every single-channel candidate scores at most
    # 1/61, so a "half the best" cut-off left one card. Candidates are already
    # bounded by each channel's depth and the dense similarity threshold.
    remaining = set(scores)
    selected = []
    while remaining and len(selected) < limit:
        def criterion(eid):
            redundancy = max((float(np.dot(representatives[eid],representatives[other])) for other in selected),default=0.)
            return relevance_weight*scores[eid]/scale-(1-relevance_weight)*max(0.,redundancy)
        winner = min(remaining,key=lambda eid:(-criterion(eid),-scores[eid],eid))
        selected.append(winner); remaining.remove(winner)
    return selected
