"""EXTRA A3: cue words for a soft type preference (off by default)."""
from app.search.typehint import preferred_type


def test_cues_in_several_languages():
    assert preferred_type('professor for medical image analysis') == 'person'
    assert preferred_type('Forscherin für Strömungsmechanik') == 'person'
    assert preferred_type('Which platform offers sequencing?') == 'infrastructure'
    assert preferred_type('Pilotstudie zur Glukosemessung') is None  # 'pilotstudie' is one compound word
    assert preferred_type('insulin dosing') is None


def test_conflicting_cues_give_no_hint():
    assert preferred_type('researcher on a sequencing platform') is None
