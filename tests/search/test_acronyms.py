"""EXTRA A4: acronym mining (off by default in serving)."""
from app.search.acronyms import mine


def test_mines_initial_matching_pairs_seen_twice():
    texts = ['We study continuous glucose monitoring (CGM) in type 1 diabetes.',
             'Data from continuous glucose monitoring (CGM) devices.',
             'The Diabetes Center Berne (DCB) funds projects.',          # seen once: not kept
             'A new method (XYZ) for things.']                           # initials do not match: not kept
    assert mine(texts) == {'CGM': 'continuous glucose monitoring'}
