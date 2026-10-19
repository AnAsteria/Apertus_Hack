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


# Cards must lead to someone to contact: a person, group, lab, unit, platform, service or
# project. News posts, fact sheets, navigation pages ("About us", "Research - Faculty of ...")
# and headline-like page titles are not actors; they are dropped from the cards (still indexed).
NEWS_URL_WORDS = {'news','aktuell','aktuelles','factsheets','stories','story','blog','press','presse',
                  'medien','media','mediarelations','events','veranstaltungen','newsletter','magazin',
                  'studium','studies','lehre','teaching','weiterbildung'}
GENERIC_TITLES = {'discover','about us','über uns','ueber uns','team','unser team','our team','research',
                  'forschung','recherche','research groups','forschungsgruppen','projects','projekte',
                  'home','startseite','overview','übersicht','services','dienstleistungen','contact','kontakt',
                  'research activities','forschungsaktivitäten','all','alle','people','personen'}
GENERIC_PREFIX = re.compile(r'^(research|forschung|recherche|projects?|projekte|studium|university)\b', re.I)
ACTOR_WORDS = re.compile(r'\b(group|groupe|lab|labs|laboratory|laboratoire|center|centre|institute|clinic|platform|'
                         r'facility|facilities|core|department|departement|division|abteilung|unit|programme|program|'
                         r'network|netzwerk|service|project|projekt|study|studie|trial)\b'
                         r'|(klinik|zentrum|institut|labor|gruppe|plattform|studie|projekt)', re.I)
HEADLINE_WORDS = re.compile(r'\b(published|publiziert|winners?|gewinner|meet|joins|announces?|new hope|'
                            r'bestätigt|confirmed|top \d+|stehen fest|award(ed)?)\b', re.I)
FUNCTION_WORDS = {'of','for','the','to','and','in','on','with','auf','für','der','die','das','und','von','des',
                  'mit','auch','de','la','le','et','pour','du','les'}


def not_an_actor(name, entity_type, urls):
    """True for news/navigation/article pages that do not lead to a contact. People are never
    dropped; a title naming a group, lab, institute, clinic, platform, service or project is kept.
    Judged from the title and URL path only (no model)."""
    if entity_type == 'person':
        return False
    title = re.sub(r'\s+', ' ', name).strip()
    low = title.casefold()
    if low in GENERIC_TITLES or ' | ' in title or 'alphabetisch' in low or HEADLINE_WORDS.search(title):
        return True
    if ACTOR_WORDS.search(title):
        return False
    if GENERIC_PREFIX.match(title):
        return True  # "Research - Faculty of Medicine", "Projects: Cancer Research"
    paths = [u.split('//', 1)[-1].split('?')[0].casefold() for u in urls]
    path_words = set(re.split(r'[^0-9a-zà-ÿ]+', ' '.join(p.split('/', 1)[-1] for p in paths)))
    if path_words & NEWS_URL_WORDS:
        return True
    words = title.split()
    if entity_type != 'project' and ':' in title and len(words) >= 6:
        return True  # "Start-up-Förderung in Diabetestechnologie: Die DCB Open Innovation Challenge ..."
    # A sentence-like title ("Targeting the niche of drug-tolerant tumor-repopulating cells ...").
    return entity_type != 'project' and len(words) >= 5 and sum(w.casefold() in FUNCTION_WORDS for w in words) >= 2


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
