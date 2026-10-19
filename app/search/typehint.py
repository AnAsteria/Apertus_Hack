"""EXTRA A3: soft entity-type preference from cue words when the user asked for 'Anything'.

Deterministic, EN/DE/FR/IT/RU. Never filters and never overrides an explicit entity type:
matching entities get their fused score multiplied by BOOST before diversification.
"""
import os
from .analysis import words

BOOST = float(os.environ.get('BERNMATCH_TYPE_HINT_BOOST', '1.5'))
CUES = {
    'person': set('''researcher researchers professor professors prof scientist scientists expert experts person people
who whom investigator pi forscher forscherin forschende wissenschaftler wissenschaftlerin professorin experte expertin
person personen chercheur chercheuse chercheurs scientifique expert experte professeur professeure ricercatore
ricercatrice ricercatori scienziato scienziata esperto esperta professore professoressa исследователь исследователи
учёный учёные ученый ученые профессор эксперт эксперты'''.split()),
    'infrastructure': set('''platform platforms facility facilities equipment instrument instruments infrastructure core
plattform plattformen infrastruktur gerät geräte einrichtung plateforme plateformes équipement infrastructure
piattaforma piattaforme strumentazione infrastruttura платформа платформы оборудование инфраструктура'''.split()),
    'project': set('''project projects study studies trial trials pilot projekt projekte studie studien projet projets
étude études progetto progetti studio studi проект проекты исследование'''.split()),
}


def preferred_type(query):
    """Return the single cued entity type, or None when there is no cue or cues conflict."""
    found = {t for t, cues in CUES.items() if set(words(query)) & cues}
    return found.pop() if len(found) == 1 else None
